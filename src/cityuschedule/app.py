from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from cityuschedule.aims import load_aims_html
from cityuschedule.cli import load_sessions
from cityuschedule.course_catalog import (
    load_course_catalog,
    load_credit_catalogs,
    load_ge_section_catalog,
)
from cityuschedule.plan_generator import (
    PlanOptions,
    generate_course_plans,
    load_ge_areas,
    load_course_requirements,
)


st.set_page_config(
    page_title="CityUSchedule",
    page_icon="calendar",
    layout="wide",
)

st.title("CityUSchedule")
st.caption("Plan clash-free CityU timetables and review registration actions.")


@st.cache_data
def available_terms() -> list[str]:
    path = Path(__file__).resolve().parents[2] / "data" / "ge_course_information.json"
    if not path.is_file():
        return []
    try:
        records = json.loads(path.read_text(encoding="utf-8-sig"))
        return list(dict.fromkeys(
            str(record["term"]) for record in records
            if isinstance(record, dict) and record.get("term")
        ))
    except (OSError, json.JSONDecodeError):
        return []


def save_upload(upload, suffix: str) -> str:
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as file:
        file.write(upload.getvalue())
        return file.name


def parse_course_codes(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        code.upper()
        for code in re.findall(r"[A-Z]{2,4}\s?\d{4}[A-Z]?", value.upper())
    ))


with st.sidebar:
    st.header("Planning settings")
    terms = available_terms()
    term = st.selectbox("Term", terms or ["2026-27 Sem A"])

    timetable_file = st.file_uploader(
        "AIMS timetable HTML or CSV",
        type=["html", "htm", "csv"],
        help="Use an exported AIMS weekly timetable HTML page, or a timetable CSV.",
    )
    custom_catalog = st.file_uploader(
        "Optional timetable catalogue JSON",
        type=["json"],
        help="Provide a course catalogue with section meeting details.",
    )

    study_load = st.selectbox(
        "Study load",
        ["full-time", "part-time", "summer", "none"],
        index=0,
    )
    allow_overload = st.checkbox("Allow overload", value=False)
    check_travel = st.checkbox("Check walking time", value=True)

    preferred = st.multiselect(
        "Preferred days",
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    )
    avoid = st.multiselect(
        "Avoid days",
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    )

    min_credits = st.number_input("Minimum credits", min_value=0, value=0, step=1)
    max_credits = st.number_input("Maximum credits", min_value=0, value=18, step=1)
    max_courses = st.number_input("Maximum courses", min_value=1, value=6, step=1)
    max_results = st.slider("Plans to show", min_value=1, max_value=20, value=5)


courses = []
if custom_catalog is not None:
    custom_path = save_upload(custom_catalog, ".json")
    try:
        courses = load_course_catalog(custom_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        st.sidebar.error(str(error))
else:
    try:
        courses = load_ge_section_catalog(term=term)
    except (OSError, ValueError) as error:
        st.error(str(error))

course_codes = [course.code for course in courses]
if not course_codes:
    st.warning("No section data is available for this selection.")

col1, col2 = st.columns([2, 1])
with col1:
    selected_codes = st.multiselect(
        "Courses to include",
        options=course_codes,
        help="Choose courses that may be added to the timetable.",
    )
with col2:
    required_text = st.text_input(
        "Required courses",
        help="Separate course codes with commas or spaces.",
    )
required_codes = parse_course_codes(required_text)

fixed_sessions = []
if timetable_file is not None:
    try:
        if timetable_file.name.lower().endswith(".csv"):
            fixed_sessions = load_sessions(save_upload(timetable_file, ".csv"))
        else:
            fixed_sessions = load_aims_html(save_upload(timetable_file, ".html"))
        st.success(
            f"Loaded {len(fixed_sessions)} timetable session(s) "
            "from {timetable_file.name}"
        )
    except (OSError, ValueError) as error:
        st.error(str(error))


def sessions_to_frame(sessions: list[dict]) -> pd.DataFrame:
    rows = []
    for session in sessions:
        if not session.get("day"):
            continue
        location = session.get("location") or " ".join(
            filter(None, (session.get("building", ""), session.get("room", "")))
        )
        rows.append({
            "Day": session.get("day", ""),
            "Start": session.get("start_time") or session.get("start", ""),
            "End": session.get("end_time") or session.get("end", ""),
            "Course": session.get("course_code", ""),
            "Section": session.get("section") or session.get("type", ""),
            "Location": location,
        })
    return pd.DataFrame(rows)


generate = st.button("Generate plans", type="primary", use_container_width=True)

if generate:
    wanted = set(selected_codes) | set(required_codes)
    candidate_courses = [course for course in courses if course.code in wanted]
    if not candidate_courses:
        st.error("Choose at least one course or enter a required course.")
    else:
        try:
            options = PlanOptions(
                required_courses=required_codes,
                min_credits=min_credits or None,
                max_credits=max_credits or None,
                max_courses=int(max_courses),
                preferred_days=tuple(preferred),
                avoid_days=tuple(avoid),
                check_travel=check_travel,
                max_results=max_results,
                study_load=None if study_load == "none" else study_load,
                allow_overload=allow_overload,
                term=term,
            )
            report = generate_course_plans(
                candidate_courses,
                options,
                fixed_sessions=fixed_sessions,
                credit_courses=load_credit_catalogs(),
                requirements=load_course_requirements(),
                ge_areas=load_ge_areas(),
            )
        except (OSError, ValueError) as error:
            st.error(str(error))
        else:
            for warning in report.warnings:
                st.warning(warning)

            if not report.plans:
                st.error("No clash-free plans matched your settings.")
                if report.fit_summary():
                    st.write("\n".join(report.fit_summary()))
                if report.explain_no_plans():
                    st.caption(report.explain_no_plans())
            else:
                st.subheader(f"{len(report.plans)} plan(s)")
                for number, plan in enumerate(report.plans, start=1):
                    with st.expander(
                        f"Plan {number}: {plan.explain(include_idle=False)}",
                        expanded=number == 1,
                    ):
                        for option in plan.chosen:
                            st.markdown(
                                f"**{option.label}** - "
                                f"{option.credits if option.credits is not None else '?'} cr"
                                f"{' - ' + option.title if option.title else ''}"
                            )

                        sessions = sessions_to_frame(plan.to_sessions())
                        if not sessions.empty:
                            sessions = sessions.sort_values(
                                ["Day", "Start"],
                                key=lambda column: column.map(
                                    {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3,
                                     "Fri": 4, "Sat": 5, "Sun": 6}
                                ) if column.name == "Day" else column
                            )
                            st.dataframe(
                                sessions,
                                use_container_width=True,
                                hide_index=True,
                            )

                        if plan.registration_steps():
                            st.markdown("**Registration steps**")
                            for step in plan.registration_steps():
                                st.write(step)
