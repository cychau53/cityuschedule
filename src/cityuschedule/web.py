"""Small local web interface for CityUSchedule."""

import colorsys
import html
import re
import secrets
import tempfile
import threading
import webbrowser
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .aims import load_aims_html
from .conflicts import find_conflicts
from .course_catalog import (
    load_credit_catalogs,
    load_ge_section_catalog,
)
from .ge_courses import load_ge_courses, search_ge_courses
from .plan_generator import (
    PLANNING_ONLY_NOTICE,
    PlanOptions,
    format_plan,
    generate_course_plans,
)
from .timetable import format_timetable


COURSE_COLOR_CLASSES = [
    "course-color-1",
    "course-color-2",
    "course-color-3",
    "course-color-4",
    "course-color-5",
    "course-color-6",
    "course-color-7",
    "course-color-8",
]


def colorize_course_codes_in_html(text: str) -> str:
    import re

    def replace_course_code(match: re.Match[str]) -> str:
        course_code = match.group(0)
        course_class = course_color_class(course_code)
        escaped_code = html.escape(course_code)
        return (
            f'<span class="{course_class}">'
            f"{escaped_code}</span>"
        )

    return re.sub(
        r"\b[A-Z]{2,4}\d{4}[A-Z]?\b",
        replace_course_code,
        html.escape(text),
    )

def course_color_class(course_code: str) -> str:
    normalized = course_code.strip().upper()
    index = sum(ord(character) for character in normalized) % len(
        COURSE_COLOR_CLASSES
    )
    return COURSE_COLOR_CLASSES[index]


def _term_label(term: str) -> str | None:
    term = term.strip().upper()
    if len(term) != 5:
        return None
    year = term[:4]
    part = term[4:]
    if not year.isdigit() or part not in {"A", "B", "S"}:
        return None
    season = "Summer" if part == "S" else f"Sem {part}"
    return f"20{year[:2]}-{int(year[:2]) + 1:02d} {season}"


def _page(title: str, body: str) -> bytes:
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    .course-color-1 {{ color: #008000; }}
    .course-color-2 {{ color: #00008b; }}
    .course-color-3 {{ color: #a020f0; }}
    .course-color-4 {{ color: #b8860b; }}
    .course-color-5 {{ color: #cc0000; }}
    .course-color-6 {{ color: #00688b; }}
    .course-color-7 {{ color: #8b008b; }}
    .course-color-8 {{ color: #8b4513; }}
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, sans-serif; }}
    body {{ max-width: 980px; margin: 0 auto; padding: 24px; background: #f6f8fb; color: #172033; }}
    h1 {{ margin-top: 0; }}
    nav {{display: grid;grid-template-columns: repeat(2, minmax(0, 1fr));gap: 10px;margin-bottom: 18px;}}
    nav a {{display: block;padding: 12px;background: #e8eefb;border-radius: 7px;color: #172033;text-decoration: none;font-weight: 700;}}nav a:hover {{background: #d8e4ff;}}
    @media (max-width: 700px) {{nav {{grid-template-columns: 1fr;}}}}
    form {{ display: grid; gap: 12px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 12px #0001; }}
    label {{ font-weight: 650; }}
    input, select, textarea {{ width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #bbc3d1; border-radius: 7px; }}
    textarea {{ min-height: 280px; resize: vertical; font-family: monospace; }}
    button {{ border: 0; border-radius: 7px; padding: 11px 16px; background: #155eef; color: white; font-weight: 700; cursor: pointer; }}
    button.delete {{ background: #b42318; }}
    .error {{ color: #b42318; background: #fff1f0; border: 1px solid #ffccc7; padding: 12px; border-radius: 8px; font-weight: 650; }}
    .notice {{ background: #eef4ff; border: 1px solid #b2c9ff; padding: 12px; border-radius: 8px; }}
    pre {{ white-space: pre-wrap; background: #fff; border: 1px solid #dde2ea; padding: 16px; border-radius: 8px; }}
    pre.course-plan {{ margin: 12px 0; }}
    .added-course {{ color: #008000; }}
    .plan-heading {{ color: #856000; }}
  </style>
</head>
<body>
  <h1>CityUSchedule</h1>
  <nav>
    <a href="/settings">Basic settings</a>
    <a href="/aims">Check or change saved AIMS timetable</a>
    <a href="/aims-offering">Paste and check an AIMS course offering</a>
    <a href="/saved-course-bundles">Saved course bundles</a>
    <a href="/ge-search">Search GE courses</a>
    <a href="/ge-info">Show GE course details</a>
    <a href="/planner">Generate timetable plans</a>
    <a href="/saved-plans">Saved timetable plan</a>
  </nav>
  {body}
</body>
</html>"""
    return document.encode("utf-8")


def _form() -> str:
    return """<form method="post" enctype="multipart/form-data">
  <input type="hidden" name="action" value="plan">

  <label for="term">Semester</label>
  <input id="term" name="term" placeholder="2627B" required>

  <label for="courses">Course codes (comma or space separated)</label>
  <input id="courses" name="courses" placeholder="GE1102 GE1401">

  <label for="aims">Replacement AIMS timetable HTML (optional)</label>
  <input id="aims" name="aims" type="file" accept=".html,.htm,text/html" aria-describedby="aims-help">
  <p id="aims-help" class="notice">
    Leave this blank to reuse the timetable saved under
    <a href="/aims">Check or change saved AIMS timetable</a>.
    Upload a file here only to use a different timetable for this
    planning request.
  </p>

  <label for="add_ge">Number of GE courses to add</label>
  <input id="add_ge" name="add_ge" type="number" min="1" value="1" required>

  <label for="max_results">Maximum plans</label>
  <input id="max_results" name="max_results" type="number" min="1" value="5">

  <label for="seats">Seat policy</label>
  <select id="seats" name="seats">
    <option value="waitlist">Waitlist allowed</option>
    <option value="open">Open seats only</option>
    <option value="any">Any availability</option>
  </select>

  <label>
    <input name="no_travel" type="checkbox"
           value="1" style="width:auto">
    Skip walking-time checks
  </label>

  <button type="submit">Generate timetable plans</button>
</form>
<p class="notice">
  This is a planning aid. Verify availability and registration
  requirements in AIMS.
</p>"""


def _basic_settings_form() -> str:
    from .cli import _load_basic_settings

    settings = _load_basic_settings()
    return f"""<h2>Basic timetable settings</h2>
<form method="post" action="/settings">
  <input type="hidden" name="action" value="save-settings">
  <label for="prefer_days">Preferred days</label>
  <input id="prefer_days" name="prefer_days" value="{html.escape(', '.join(settings.prefer_days))}" placeholder="Mon, Tue">
  <label for="avoid_days">Days to avoid</label>
  <input id="avoid_days" name="avoid_days" value="{html.escape(', '.join(settings.avoid_days))}" placeholder="Fri">
  <label for="min_credits">Minimum credits (optional)</label>
  <input id="min_credits" name="min_credits" type="number" min="0" value="{'' if settings.min_credits is None else settings.min_credits}">
  <label for="max_credits">Maximum credits (optional)</label>
  <input id="max_credits" name="max_credits" type="number" min="0" value="{'' if settings.max_credits is None else settings.max_credits}">
  <label for="earliest_start">Earliest class start (optional)</label>
  <input id="earliest_start" name="earliest_start" value="{html.escape(settings.earliest_start or '')}" placeholder="09:00">
  <label for="latest_end">Latest class end (optional)</label>
  <input id="latest_end" name="latest_end" value="{html.escape(settings.latest_end or '')}" placeholder="18:00">
  <label for="min_gap">Minimum gap between classes (minutes)</label>
  <input id="min_gap" name="min_gap" type="number" min="0" value="{settings.min_gap}">
  <label for="lunch_minutes">Lunch break needed (minutes)</label>
  <input id="lunch_minutes" name="lunch_minutes" type="number" min="0" value="{settings.lunch_minutes}">
  <label for="lunch_start">Lunch window start</label>
  <input id="lunch_start" name="lunch_start" value="{html.escape(settings.lunch_window[0])}" placeholder="11:30">
  <label for="lunch_end">Lunch window end</label>
  <input id="lunch_end" name="lunch_end" value="{html.escape(settings.lunch_window[1])}" placeholder="14:30">
  <button type="submit">Save basic settings</button>
</form>
<p class="notice">Saved settings are used when generating plans and are shared with the command-line app.</p>"""


def _save_basic_settings(fields: dict[str, str]) -> str:
    from .cli import (
        BasicSettings,
        _parse_clock_time,
        _parse_day_list,
        _parse_lunch_window,
        _validate_lunch_duration,
    )
    from .cli import _save_basic_settings as save_settings

    prefer_days = _parse_day_list(fields.get("prefer_days", ""))
    avoid_days = _parse_day_list(fields.get("avoid_days", ""))
    if set(prefer_days) & set(avoid_days):
        raise ValueError("A day cannot be both preferred and avoided.")

    def optional_credits(field: str) -> int | None:
        value = fields.get(field, "").strip()
        if not value:
            return None
        try:
            credits = int(value)
        except ValueError:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be a non-negative integer.") from None
        if credits < 0:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be a non-negative integer.")
        return credits

    def nonnegative_minutes(field: str) -> int:
        value = fields.get(field, "").strip() or "0"
        try:
            minutes = int(value)
        except ValueError:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be a non-negative integer.") from None
        if minutes < 0:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be a non-negative integer.")
        return minutes

    min_credits = optional_credits("min_credits")
    max_credits = optional_credits("max_credits")
    if (
        min_credits is not None
        and max_credits is not None
        and min_credits > max_credits
    ):
        raise ValueError("Minimum credits cannot exceed maximum credits.")

    lunch_minutes = nonnegative_minutes("lunch_minutes")
    lunch_window = _parse_lunch_window(
        f"{fields.get('lunch_start', '11:30') or '11:30'}-"
        f"{fields.get('lunch_end', '14:30') or '14:30'}"
    )
    _validate_lunch_duration(lunch_minutes, lunch_window)

    earliest = fields.get("earliest_start", "").strip()
    latest = fields.get("latest_end", "").strip()
    earliest_start = (
        _parse_clock_time(earliest, "Earliest class start")
        if earliest else None
    )
    latest_end = (
        _parse_clock_time(latest, "Latest class end", allow_24=True)
        if latest else None
    )
    if (
        earliest_start is not None
        and latest_end is not None
        and earliest_start > latest_end
    ):
        raise ValueError("Earliest class start cannot be later than latest class end.")

    settings = BasicSettings(
        prefer_days=prefer_days,
        avoid_days=avoid_days,
        min_credits=min_credits,
        max_credits=max_credits,
        lunch_minutes=lunch_minutes,
        lunch_window=lunch_window,
        min_gap=nonnegative_minutes("min_gap"),
        earliest_start=earliest_start,
        latest_end=latest_end,
    )
    save_settings(settings)
    return "Basic settings saved."


def _saved_bundles_link() -> str:
    return (
        '<p><a href="/saved-plans">'
        "View saved timetable plans</a></p>"
    )


def _save_plan_form(
    token: str,
    plans: list[dict],
    *,
    retry: bool = False,
) -> str:
    choices = []
    for index, plan in enumerate(plans, start=1):
        courses = plan.get("courses", [])
        course_label = ", ".join(
            str(course) for course in courses
        ) if isinstance(courses, list) else ""
        label = f"Save Plan {index}"
        if course_label:
            label += f": {course_label}"
        choices.append(
            f'<label><input type="checkbox" name="plan_{index}" value="1" '
            f'style="width:auto"> {html.escape(label)}</label>'
        )
    choices_html = "\n".join(choices)
    heading = "Choose another plan to save" if retry else "Save plans"
    return f"""<form method="post" action="/save-plans">
  <input type="hidden" name="action" value="save-plans">
  <input type="hidden" name="plan_token" value="{html.escape(token)}">
  <h2>{heading}</h2>
  {choices_html}
  <button type="submit">Save selected plans</button>
</form>"""


def _delete_saved_timetable_plan(number_value: str) -> str:
    from .cli import _load_saved_bundles, _save_bundles_to_disk

    try:
        number = int(number_value)
    except ValueError:
        raise ValueError("Choose a valid saved plan number.") from None

    saved_plans = _load_saved_bundles()
    if not saved_plans:
        raise ValueError("No saved plans were found.")
    if not 1 <= number <= len(saved_plans):
        raise ValueError(f"Plan number must be from 1 to {len(saved_plans)}.")

    del saved_plans[number - 1]
    _save_bundles_to_disk(saved_plans)
    return f"Deleted Plan {number}."

def _format_saved_plan_html(plan: dict, number: int) -> str:
    from .cli import (
        _format_saved_plan,
        _saved_plan_added_sections,
    )

    added_sections = _saved_plan_added_sections(plan)
    added_course_codes = {
        code for code, _ in added_sections
    }

    rendered_lines = []
    in_web_add_drop = False
    web_course_code = None

    for line in _format_saved_plan(plan, number).splitlines():
        escaped_line = html.escape(line)
        colored_line = colorize_course_codes_in_html(escaped_line)

        if line == f"Plan {number}":
            rendered_lines.append(
                f'<span class="plan-heading">{colored_line}</span>'
            )
            continue

        if line == "Web Add/Drop:":
            in_web_add_drop = True
            web_course_code = None
            rendered_lines.append(colored_line)
            continue

        if line == "Other registration steps:":
            in_web_add_drop = False
            web_course_code = None

        if in_web_add_drop:
            web_course = re.match(
                r"^\s+\d+\.\s+([A-Z]{2,4}\s?\d{4}[A-Z]?)\s*$",
                line.upper(),
            )

            if web_course:
                web_course_code = web_course.group(1).replace(
                    " ", ""
                )

            is_registration_action = re.match(
                r"^\s+(?:add|drop)\s+",
                line,
                re.IGNORECASE,
            )

            if (
                web_course_code in added_course_codes
                and (web_course or is_registration_action)
            ):
                rendered_lines.append(
                    '<span class="added-course">'
                    f"{colored_line}</span>"
                )
                continue

        prefix = "Course(s) added: "

        if (
            line.startswith(prefix)
            and line[len(prefix):] != "None"
        ):
            rendered_lines.append(
                html.escape(prefix)
                + '<span class="added-course">'
                + html.escape(line[len(prefix):])
                + "</span>"
            )
            continue

        session = re.match(
            r"^\s+\d{2}:\d{2}-\d{2}:\d{2}\s+"
            r"([A-Z]{2,4}\s?\d{4}[A-Z]?)\s+(\S+)",
            line.upper(),
        )

        if session and (
            session.group(1).replace(" ", ""),
            session.group(2),
        ) in added_sections:
            rendered_lines.append(
                '<span class="added-course">'
                f"{colored_line}</span>"
            )
        else:
            rendered_lines.append(colored_line)

    return (
        '<pre class="course-plan">'
        + "\n".join(rendered_lines)
        + "</pre>"
    )

def _saved_timetable_plans_page(
    notice: str | None = None,
) -> str:
    from .cli import (
        _load_saved_bundles,
        _saved_plan_data,
    )

    saved_plans = _load_saved_bundles()
    sections = []

    if notice:
        sections.append(
            f'<p class="notice">{html.escape(notice)}</p>'
        )

    sections.append("<h2>Saved timetable plans</h2>")

    if not saved_plans:
        sections.append("<p>No saved timetable plans.</p>")
        return "\n".join(sections)

    sections.append(
        f"<p>Found {len(saved_plans)} saved plan(s).</p>"
    )

    for index, entry in enumerate(saved_plans, start=1):
        plan = _saved_plan_data(entry)

        sections.append(
            _format_saved_plan_html(plan, index)
        )

        sections.append(
            '<form method="post" action="/delete-plan" '
            f'onsubmit="return confirm(\'Delete Plan {index}?\');">'
            '<input type="hidden" name="action" value="delete-plan">'
            '<input type="hidden" name="plan_number" '
            f'value="{index}">'
            '<button class="delete" type="submit">'
            f"Delete Plan {index}</button>"
            "</form>"
        )

    return "\n".join(sections)


def _saved_course_bundles_page() -> str:
    from .cli import (
        _course_bundle_sort_key,
        _load_saved_course_bundles,
    )

    bundles = sorted(
        _load_saved_course_bundles(),
        key=_course_bundle_sort_key,
    )

    sections = ["<h2>Saved course bundles</h2>"]

    if not bundles:
        sections.append("<p>No saved course bundles.</p>")
        return "\n".join(sections)

    sections.append(
        f"<p>Found {len(bundles)} saved course bundle(s).</p>"
    )

    for number, bundle in enumerate(bundles, start=1):
        course_code = str(
            bundle.get("course_code") or "Unknown"
        )

        meetings = [
            section
            for section in bundle.get("sections", [])
            if isinstance(section, dict)
        ]

        section_names = [
            str(section.get("section") or "").strip()
            for section in meetings
            if str(section.get("section") or "").strip()
        ]

        heading = f"{number}. {course_code}"

        if section_names:
            heading += " " + "+".join(section_names)

        lines = [heading]

        for section in meetings:
            time_range = (
                f"{section.get('start_time') or ''}-"
                f"{section.get('end_time') or ''}"
            ).strip("-")

            details = [
                str(section.get("section") or ""),
                (
                    f"CRN {section['crn']}"
                    if section.get("crn")
                    else ""
                ),
                str(section.get("day") or ""),
                time_range,
            ]

            lines.append(
                "  " + " ".join(
                    detail for detail in details if detail
                )
            )

        text = "\n".join(lines)
        sections.append(
            f"<pre>{html.escape(text)}</pre>"
        )

    return "\n".join(sections)


def _saved_bundles_page(
    notice: str | None = None,
) -> str:
    """Keep the old URL available without combining both lists."""
    message = ""

    if notice:
        message = (
            f'<p class="notice">{html.escape(notice)}</p>'
        )

    return (
        message
        + "<h2>Saved data</h2>"
        + '<p><a href="/saved-course-bundles">'
        + "View saved course bundles</a></p>"
        + '<p><a href="/saved-plans">'
        + "View saved timetable plans</a></p>"
    )


def _ge_search_form(keyword: str = "") -> str:
    return f"""<h2>Search Gateway Education courses</h2>
<form method="post" enctype="application/x-www-form-urlencoded">
  <input type="hidden" name="action" value="ge-search">
  <label for="keyword">Course code, title, area, offering unit, or filter</label>
  <input id="keyword" name="keyword" value="{html.escape(keyword)}" placeholder="GE1102 or management">
  <button type="submit">Search</button>
</form>"""


def _ge_info_form(course_code: str = "") -> str:
    return f"""<h2>Gateway Education course information</h2>
<form method="post" enctype="application/x-www-form-urlencoded">
  <input type="hidden" name="action" value="ge-info">
  <label for="course_code">Course code</label>
  <input id="course_code" name="course_code" value="{html.escape(course_code)}" placeholder="GE1102">
  <button type="submit">Show course</button>
</form>"""


def _aims_offering_form(
    course_code: str = "",
    offering_text: str = "",
) -> str:
    return f"""<h2>Paste and check an AIMS course offering</h2>
<p>
  Copy one course's complete offering table from AIMS.
  Upload your existing weekly timetable to check which complete
  section bundles fit.
</p>
<form method="post" action="/aims-offering"
      enctype="multipart/form-data">
  <input type="hidden" name="action" value="aims-offering">

  <label for="offering_course_code">Course code</label>
  <input id="offering_course_code" name="course_code"
         value="{html.escape(course_code)}"
         placeholder="GE1352" required>

  <label for="offering_text">Complete AIMS course offering table</label>
  <textarea id="offering_text" name="offering_text"
            spellcheck="false"
            placeholder="Paste the copied AIMS offering table here."
            required>{html.escape(offering_text)}</textarea>

  <label for="aims">Existing AIMS weekly timetable HTML</label>
  <input id="aims" name="aims" type="file"
         accept=".html,.htm,text/html" required>

  <button type="submit">Check complete section bundles</button>
</form>
<p class="notice">
  Saved basic timetable settings are applied.
  Unscheduled sessions do not block weekly timeslots.
  Results are for planning; verify registration details in AIMS.
</p>"""


def _check_aims_offering(
    fields: dict[str, str],
    upload: bytes | None,
    *,
    bundles_out: list[dict] | None = None,
) -> str:
    from .aims_fit import (
        DAY_NAMES,
        convert_aims_sessions,
        fitting_registration_bundles,
    )
    from .aims_table_parser import parse_aims_table
    from .cli import _load_basic_settings

    course_code = re.sub(
        r"\s+",
        "",
        fields.get("course_code", ""),
    ).upper()
    offering_text = fields.get("offering_text", "")

    if not re.fullmatch(r"[A-Z]+\d{4}[A-Z]?", course_code):
        raise ValueError("Enter a valid course code, such as GE1352.")

    if not offering_text.strip():
        raise ValueError("Paste the complete AIMS course offering table.")

    if not upload:
        raise ValueError("Upload your existing AIMS weekly timetable HTML.")

    table = parse_aims_table(
        offering_text,
        course_code=course_code,
    )

    if table.course_code != course_code:
        raise ValueError(
            f"The pasted table is for {table.course_code}, "
            f"but you entered {course_code}."
        )

    with tempfile.NamedTemporaryFile(
        suffix=".html",
        delete=False,
    ) as temporary:
        temporary.write(upload)
        temporary_path = Path(temporary.name)

    try:
        timetable_rows = load_aims_html(str(temporary_path))
    finally:
        temporary_path.unlink(missing_ok=True)

    base_sessions = convert_aims_sessions(timetable_rows)
    settings = _load_basic_settings()

    fitting = fitting_registration_bundles(
        table,
        base_sessions,
        preferred_days=list(settings.prefer_days),
        avoid_days=list(settings.avoid_days),
        min_gap=settings.min_gap,
        earliest_start=settings.earliest_start,
        latest_end=settings.latest_end,
        lunch_minutes=settings.lunch_minutes,
        lunch_window=settings.lunch_window,
    )

    all_bundles = table.registration_bundles()
    lines = [
        f"Course: {table.course_code}",
        f"Loaded {len(base_sessions)} fixed timetable meeting(s).",
        f"Parsed {len(table.sessions)} offering record(s).",
        f"Found {len(all_bundles)} complete scheduled bundle(s).",
        f"Found {len(fitting)} fitting bundle(s).",
        "",
    ]

    if not all_bundles:
        lines.append(
            "No complete scheduled bundles could be constructed. "
            "Check that you pasted the entire offering table."
        )
    elif not fitting:
        lines.append(
            "No complete bundles fit the uploaded timetable "
            "and current settings."
        )
    else:
        sessions_by_section = {
            session.section: session
            for session in table.scheduled_sessions
        }

        for number, bundle in enumerate(fitting, start=1):
            if bundles_out is not None:
                bundles_out.append({
                    "course_code": table.course_code,
                    "sections": [
                        {
                            "section": sessions_by_section[name].section,
                            "crn": sessions_by_section[name].crn,
                            "day": sessions_by_section[name].day or "",
                            "start_time": (
                                sessions_by_section[name].start_time or ""
                            ),
                            "end_time": (
                                sessions_by_section[name].end_time or ""
                            ),
                        }
                        for name in bundle
                    ],
                })
            lines.append(
                f"{number}. {table.course_code} {'+'.join(bundle)}"
            )

            for section in bundle:
                session = sessions_by_section[section]
                day = DAY_NAMES.get(
                    session.day or "",
                    session.day or "",
                )
                lines.append(
                    f"   CRN {session.crn}: {session.section} "
                    f"{day} {session.start_time}-{session.end_time} "
                    f"{session.building}".rstrip()
                )

            lines.append("")

    return "\n".join(lines)

def _aims_form() -> str:
    return """<h2>Check an AIMS timetable</h2>
<form method="post" enctype="multipart/form-data">
  <input type="hidden" name="action" value="aims-check">
  <label for="aims">Saved AIMS timetable HTML</label>
  <input id="aims" name="aims" type="file" accept=".html,text/html" required>
  <button type="submit">Check timetable</button>
</form>"""


def _generate(
    fields: dict[str, str],
    upload: bytes | None,
    plan_cache: dict[str, list[dict]],
    plan_cache_lock: threading.Lock,
) -> tuple[str, str | None, str]:
    term = fields.get("term", "").strip().upper()
    if len(term) != 5:
        raise ValueError("Enter a valid semester, for example 2627B.")

    wanted = []
    for item in fields.get("courses", "").replace(",", " ").upper().split():
        if item and item not in wanted:
            wanted.append(item)
    add_ge = int(fields.get("add_ge", "1") or "1")
    max_results = int(fields.get("max_results", "5") or "5")
    if add_ge < 1:
        raise ValueError("The GE course count must be at least 1.")
    if max_results < 1:
        raise ValueError("Maximum plans must be at least 1.")

    ge_term = _term_label(term)
    courses = load_ge_section_catalog(term=ge_term)
    missing = []
    if wanted:
        keep = set(wanted)
        courses = [course for course in courses if course.code.upper() in keep]
        found = {course.code.upper() for course in courses}
        missing = sorted(keep - found)
        
    from .cli import _load_saved_aims_path

    fixed_sessions = []

    if upload:
        with tempfile.NamedTemporaryFile(
            suffix=".html",
            delete=False,
        ) as temporary:
            temporary.write(upload)
            temporary_path = temporary.name

        try:
            fixed_sessions = load_aims_html(temporary_path)
        finally:
            Path(temporary_path).unlink(missing_ok=True)
    else:
        saved_aims_path = _load_saved_aims_path()

        if saved_aims_path and Path(saved_aims_path).is_file():
            fixed_sessions = load_aims_html(saved_aims_path)

    from .cli import _load_basic_settings

    basic_settings = _load_basic_settings()
    options = PlanOptions(
        ge_courses=add_ge,
        max_results=max_results,
        check_travel=fields.get("no_travel") != "1",
        seat_policy=fields.get("seats", "waitlist"),
        term=term,
        min_credits=basic_settings.min_credits,
        max_credits=basic_settings.max_credits,
        preferred_days=basic_settings.prefer_days,
        avoid_days=basic_settings.avoid_days,
        earliest_start=basic_settings.earliest_start,
        latest_end=basic_settings.latest_end,
        min_gap=basic_settings.min_gap,
        lunch_minutes=basic_settings.lunch_minutes,
        lunch_window=basic_settings.lunch_window,
    )

    report = generate_course_plans(
        courses,
        options,
        fixed_sessions=fixed_sessions,
        credit_courses=load_credit_catalogs(),
    )

    pieces = []
    if missing:
        pieces.append(
            f"Note: no section details for {', '.join(missing)} in "
            f"{ge_term or term}; those courses were left out of planning."
        )
    fit_lines = report.fit_summary()
    if fit_lines:
        pieces.append(
            "Timeslots that fit your timetable:\n"
            + "\n".join(fit_lines)
        )

    rejection_summary = getattr(
        report,
        "rejection_summary",
        None,
    )

    if callable(rejection_summary):
        rejection_lines = rejection_summary()

        if rejection_lines:
            pieces.append(
                "Options rejected "
                "(these describe rejected alternatives, "
                "not necessarily every plan):\n"
                + "\n".join(
                    line for _, line in rejection_lines
                )
            )
        
    token = None
    plans_html = ""

    if not report.plans:
        explanation = getattr(
            report,
            "explain_no_plans",
            None,
        )

        no_plan_message = (
            explanation()
            if callable(explanation)
            else ""
        )

        pieces.append(
            "No course plans matched the selected options."
            + (f"\n{no_plan_message}" if no_plan_message else "")
        )
    else:
        pieces.append(
            f"Found {len(report.plans)} course plan(s) "
            f"(checked "
            f"{getattr(report, 'explored', len(report.plans))} "
            f"combinations):"
        )
        plans_html = _format_plans_html(report.plans)

        saved_plan_data = [
            plan.to_dict()
            for plan in report.plans
        ]

        token = secrets.token_urlsafe(24)

        with plan_cache_lock:
            plan_cache[token] = saved_plan_data

            while len(plan_cache) > 64:
                del plan_cache[next(iter(plan_cache))]

    pieces.append(PLANNING_ONLY_NOTICE)

    return "\n\n".join(pieces), token, plans_html

def _course_color_for_line(
    line: str,
    colors: dict[str, str],
) -> str | None:
    for code, course_color in colors.items():
        pattern = (
            rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])"
        )

        if re.search(pattern, line, re.IGNORECASE):
            return course_color

    return None

def _format_plans_html(plans) -> str:
    rendered = []

    for number, plan in enumerate(plans, start=1):
        added_codes = list(dict.fromkeys(
            option.course_code
            for option in plan.chosen
            if not option.preregistered
        ))

        colors = {}

        if len(added_codes) == 1:
            colors[added_codes[0].upper()] = "#008000"
        elif len(added_codes) > 1:
            for index, code in enumerate(added_codes):
                hue = 0.5 + 0.13 * index / (len(added_codes) - 1)
                rgb = colorsys.hsv_to_rgb(hue, 0.88, 0.95)
                colors[code.upper()] = "rgb(" + ", ".join(
                    str(round(channel * 255))
                    for channel in rgb
                ) + ")"

        lines = []

        for line in format_plan(
            plan,
            number,
            steps=True,
        ).splitlines():
            course_color = _course_color_for_line(
                line,
                colors,
            )
            escaped_line = html.escape(line)

            if course_color:
                escaped_line = (
                    '<span style="color: '
                    f"{course_color}"
                    f'">{escaped_line}</span>'
                )

            lines.append(escaped_line)

        lines_text = "\n".join(lines)
        rendered.append(
            f'<pre class="course-plan">{lines_text}</pre>'
        )

    return "\n".join(rendered)



def _result_html(
    result: str,
    added_codes=(),
) -> str:
    parts = []
    lines = []

    def append_text_block():
        if not lines:
            return

        text = "\n".join(lines)
        rendered = []

        for line in text.splitlines():
            if any(
                re.search(
                    rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])",
                    line,
                    re.IGNORECASE,
                )
                for code in added_codes
            ):
                rendered.append(
                    '<span class="added-course">'
                    + html.escape(line)
                    + "</span>"
                )
            else:
                rendered.append(html.escape(line))

        parts.append("<pre>" + "\n".join(rendered) + "</pre>")
        lines.clear()

    for line in result.splitlines():
        if line.startswith("No course plans matched"):
            append_text_block()
            parts.append(
                '<div class="error" role="alert">'
                + html.escape(line)
                + "</div>"
            )
        else:
            lines.append(line)

    append_text_block()

    return "\n".join(parts)


def _save_selected_plans(
    fields: dict[str, str],
    plan_cache: dict[str, list[dict]],
    plan_cache_lock: threading.Lock,
) -> tuple[str, int]:
    from .cli import (
        _load_saved_bundles,
        _save_bundles_to_disk,
        _saved_plan_data,
        _saved_plan_signature,
    )

    token = fields.get("plan_token", "")
    with plan_cache_lock:
        plans = plan_cache.get(token)
    if not plans:
        raise ValueError("These generated plans are no longer available. Generate them again.")

    selected = []
    for key, value in fields.items():
        if not key.startswith("plan_") or value != "1":
            continue
        try:
            index = int(key.removeprefix("plan_")) - 1
        except ValueError:
            continue
        if 0 <= index < len(plans):
            selected.append(index)
    if not selected:
        raise ValueError("Select at least one plan to save.")

    saved = _load_saved_bundles()
    signatures = {
        _saved_plan_signature(_saved_plan_data(entry))
        for entry in saved
    }
    new_entries = []
    already_saved = 0
    for index in dict.fromkeys(selected):
        plan = plans[index]
        signature = _saved_plan_signature(plan)
        if signature in signatures:
            already_saved += 1
            continue
        signatures.add(signature)
        new_entries.append({"plan": plan})
    if new_entries:
        _save_bundles_to_disk(saved + new_entries)
    message = f"Saved {len(new_entries)} plan(s)."
    if already_saved:
        message += f" {already_saved} selected plan(s) were already saved."
    return message, already_saved


def _search_ge(keyword: str) -> str:
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("Enter a keyword to search.")
    results = search_ge_courses(keyword)
    if not results:
        return f"No Gateway Education courses found for '{keyword}'."

    unique: dict[str, dict] = {}
    for course in results:
        unique.setdefault(str(course.get("course_code") or "").upper(), course)

    lines = [f"Found {len(unique)} Gateway Education course(s):"]
    for course in unique.values():
        area = str(course.get("area_name") or course.get("area") or "Not specified")
        lines.extend([
            "",
            f"{course.get('course_code')} - {course.get('course_title')}",
            f"Area: {area}",
            f"Offering unit: {course.get('offering_unit') or 'Not specified'}",
            f"Level: {course.get('level') or 'Not specified'}",
            f"Terms: {', '.join(course.get('terms') or []) or 'Not specified'}",
            f"Cross-institutional: {'Yes' if course.get('cross_institutional') else 'No'}",
            f"With exam: {'Yes' if course.get('with_exam') else 'No'}",
        ])
    return "\n".join(lines)


def _get_ge_info(course_code: str) -> str:
    course_code = course_code.strip().upper()
    if not course_code:
        raise ValueError("Enter a course code.")
    course_records = [
        course for course in load_ge_courses()
        if str(course.get("course_code") or "").strip().upper() == course_code
    ]
    if not course_records:
        return f"No information found for '{course_code}'."
    course = course_records[0]
    lines = [
        f"{course_code} - {course.get('course_title') or 'No title'}",
        f"Area: {course.get('area_name') or course.get('area') or 'Not specified'}",
        f"Offering unit: {course.get('offering_unit') or 'Not specified'}",
        f"Level: {course.get('level') or 'Not specified'}",
        f"Terms: {', '.join(course.get('terms') or []) or 'Not specified'}",
        f"Cross-institutional: {'Yes' if course.get('cross_institutional') else 'No'}",
        f"Partner institutions: {', '.join(course.get('partner_institutions') or []) or 'None'}",
        f"With exam: {'Yes' if course.get('with_exam') else 'No'}",
    ]
    section_fields = (
        ("crn", "CRN"),
        ("section", "Section"),
        ("term", "Term"),
        ("capacity", "Capacity"),
        ("day", "Day"),
        ("time", "Time"),
        ("type", "Type"),
        ("building", "Building"),
        ("room", "Room"),
        ("instructor", "Instructor"),
    )
    sections = [record for record in course_records if record.get("section")]
    meeting_type_order = {"lecture": 0, "tutorial": 1, "laboratory": 2}
    sections.sort(
        key=lambda record: meeting_type_order.get(
            str(record.get("type") or "").strip().casefold(),
            len(meeting_type_order),
        )
    )
    if sections:
        lines.extend([
            "",
            f"Found {len(sections)} section meeting record(s).",
            "",
            "Section information:",
        ])
        meeting_numbers: dict[str, int] = {}
        for record in sections:
            raw_type = record.get("type")
            meeting_type = (
                " ".join(raw_type.split())
                if isinstance(raw_type, str) and raw_type.strip()
                else "Meeting"
            )
            type_key = meeting_type.casefold()
            meeting_numbers[type_key] = meeting_numbers.get(type_key, 0) + 1
            lines.append(f"{meeting_type} {meeting_numbers[type_key]}")
            for field, label in section_fields:
                value = record.get(field)
                if value is None:
                    text = "Not specified"
                elif isinstance(value, list):
                    text = ", ".join(str(item) for item in value) or "Not specified"
                else:
                    text = str(value).strip() or "Not specified"
                lines.append(f"  {label}: {text}")
            lines.append("")
    else:
        lines.extend(["", "Section information: Not specified"])
    return "\n".join(lines)


def _check_aims(upload: bytes | None) -> str:
    if not upload:
        raise ValueError("Choose a saved AIMS HTML file.")
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as temporary:
        temporary.write(upload)
        temporary_path = temporary.name
    try:
        sessions = load_aims_html(temporary_path)
    finally:
        Path(temporary_path).unlink(missing_ok=True)
    conflicts = find_conflicts(sessions)
    lines = [
        format_timetable(sessions),
        "",
        f"Loaded {len(sessions)} class sessions.",
        f"Found {len(conflicts)} clash(es).",
    ]
    for first, second in conflicts:
        lines.append(
            f"CLASH: {first['course_code']} {first['type']} "
            f"({first['day']} {first['start_time']}-{first['end_time']}) overlaps "
            f"{second['course_code']} {second['type']} "
            f"({second['day']} {second['start_time']}-{second['end_time']})"
        )
    return "\n".join(lines)


def _parse_multipart(body: bytes, content_type: str) -> tuple[dict[str, str], bytes | None]:
    if content_type.lower().startswith("application/x-www-form-urlencoded"):
        values = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
        fields = {key: items[0] if items else "" for key, items in values.items()}
        return fields, None
    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii", "replace")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    fields: dict[str, str] = {}
    upload = None
    if not message.is_multipart():
        return fields, upload
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        if 'name="aims"' in disposition:
            payload = part.get_payload(decode=True)
            if payload:
                upload = payload
            continue
        name = part.get_param("name", header="content-disposition")
        if name:
            payload = part.get_payload(decode=True)
            if payload is not None:
                fields[str(name)] = payload.decode(part.get_content_charset() or "utf-8", "replace")
    return fields, upload


class CityUScheduleHTTPServer(ThreadingHTTPServer):
    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.plan_results: dict[str, list[dict]] = {}
        self.plan_results_lock = threading.Lock()


class CityUScheduleWebHandler(BaseHTTPRequestHandler):
    server_version = "CityUSchedule/0.3"
    server: CityUScheduleHTTPServer

    def _handle_request_error(
        self,
        error: Exception,
    ) -> None:
        if isinstance(error, ValueError):
            status = 400
            title = "Invalid request"
        else:
            status = 500
            title = "Server error"

        message = str(error) or title

        body = (
            f'<h2>{html.escape(title)}</h2>'
            f'<p class="error">{html.escape(message)}</p>'
            '<p><a href="/">Return to home</a></p>'
        )

        self._send(
            _page(title, body),
            status=status,
        )
    
    def do_GET(self):
        try:
            path = urlparse(self.path).path
    
            if path == "/saved-course-bundles":
                try:
                    body = _saved_course_bundles_page()
                    status = 200
                except (ValueError, OSError) as error:
                    body = (
                        "<h2>Saved course bundles</h2>"
                        '<div class="error">'
                        + html.escape(str(error))
                        + "</div>"
                    )
                    status = 400
    
                self._send(
                    _page("Saved course bundles", body),
                    status=status,
                )
                return
    
            if path == "/saved-plans":
                try:
                    body = _saved_timetable_plans_page()
                    status = 200
                except (ValueError, OSError) as error:
                    body = (
                        "<h2>Saved timetable plans</h2>"
                        '<div class="error">'
                        + html.escape(str(error))
                        + "</div>"
                    )
                    status = 400
    
                self._send(
                    _page("Saved timetable plans", body),
                    status=status,
                )
                return
    
            if path == "/aims-offering":
                self._send(
                    _page(
                        "Check AIMS course offering",
                        _aims_offering_form(),
                    )
                )
                return
    
            if path in {"", "/", "/planner"}:
                self._send(
                    _page("CityUSchedule", _form())
                )
                return
    
            if path == "/settings":
                self._send(
                    _page(
                        "Basic settings",
                        _basic_settings_form(),
                    )
                )
                return
    
            if path == "/ge-search":
                self._send(
                    _page(
                        "Search GE courses",
                        _ge_search_form(),
                    )
                )
                return
    
            if path == "/ge-info":
                self._send(
                    _page(
                        "GE course information",
                        _ge_info_form(),
                    )
                )
                return
    
            if path == "/aims":
                self._send(
                    _page(
                        "Check AIMS timetable",
                        _aims_form(),
                    )
                )
                return
    
            if path == "/saved-bundles":
                try:
                    body = _saved_bundles_page()
                except (OSError, ValueError) as error:
                    self._send(
                        _page(
                            "Saved data",
                            '<div class="error">'
                            + html.escape(str(error))
                            + "</div>",
                        ),
                        status=500,
                    )
                    return
    
                self._send(
                    _page("Saved data", body)
                )
                return
    
            self.send_error(404)
    
        except ValueError as error:
            self._send(
                _page(
                    "Invalid request",
                    "<h2>Invalid request</h2>"
                    '<div class="error">'
                    + html.escape(str(error))
                    + "</div>"
                    + '<p><a href="/">Return to home</a></p>',
                ),
                status=400,
            )
    
        except Exception as error:
            self._send(
                _page(
                    "Server error",
                    "<h2>Server error</h2>"
                    '<div class="error">'
                    + html.escape(str(error))
                    + "</div>"
                    + '<p><a href="/">Return to home</a></p>',
                ),
                status=500,
            )

    def do_POST(self):
        if urlparse(self.path).path not in {
            "", "/", "/planner", "/settings", "/ge-search", "/ge-info",
            "/aims", "/aims-offering", "/save-plans", "/delete-plan",
        }:
            self.send_error(404)
            return

        fields = {}
                
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")
            fields, upload = _parse_multipart(body, content_type)
            action = fields.get("action", "")
            if action == "save-settings":
                result = _save_basic_settings(fields)
                body = (
                    f'<p class="notice">{html.escape(result)}</p>'
                    f'{_basic_settings_form()}'
                )
                self._send(_page("Basic settings saved", body))
            elif action == "ge-search":
                keyword = fields.get("keyword", "")
                result = _search_ge(keyword)
                body = _ge_search_form(keyword) + f"\n<pre>{html.escape(result)}</pre>"
                self._send(_page("GE search results", body))
            elif action == "ge-info":
                course_code = fields.get("course_code", "")
                result = _get_ge_info(course_code)
                body = _ge_info_form(course_code) + f"\n<pre>{html.escape(result)}</pre>"
                self._send(_page("GE course information", body))
            elif action == "aims-check":
                from .cli import _aims_path_config_file

                if not upload:
                    raise ValueError(
                        "Upload an AIMS weekly timetable HTML file."
                    )
                
                result = _check_aims(upload)
                config_file = _aims_path_config_file()
                config_file.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                saved_html = (
                    config_file.parent / "saved_aims_timetable.html"
                )

                with self.server.plan_results_lock:
                    saved_html.write_bytes(upload)
                    config_file.write_text(
                        str(saved_html.resolve()) + "\n",
                        encoding="utf-8",
                    )

                body = (
                    _aims_form()
                    + '<p class="notice">'
                    "AIMS timetable checked and saved. "
                    "Generate timetable plans will reuse it "
                    "when no replacement file is uploaded."
                    "</p>"
                    + f"<pre>{html.escape(result)}</pre>"
                    + '<p><a href="/planner">'
                    "Generate timetable plans</a></p>"
                )

                self._send(
                    _page("AIMS timetable results", body)
                )
            elif action == "aims-offering":
                course_code = fields.get("course_code", "")
                offering_text = fields.get("offering_text", "")
                bundles = []

                result = _check_aims_offering(
                    fields,
                    upload,
                    bundles_out=bundles,
                )

                body = _aims_offering_form(
                    course_code,
                    offering_text,
                )
                body += (
                    "<h2>Course offering results</h2>"
                    f"<pre>{html.escape(result)}</pre>"
                )

                if bundles:
                    token = secrets.token_urlsafe(24)

                    with self.server.plan_results_lock:
                        cache = self.server.course_bundle_results
                        cache[token] = bundles

                        while len(cache) > 64:
                            del cache[next(iter(cache))]

                    choices = []

                    for number, bundle in enumerate(bundles, start=1):
                        sections = "+".join(
                            section["section"]
                            for section in bundle["sections"]
                        )
                        label = (
                            f'{bundle["course_code"]} {sections}'
                        )

                        choices.append(
                            '<label><input type="checkbox" '
                            f'name="bundle_{number}" value="1" '
                            'style="width:auto"> '
                            f"{html.escape(label)}</label>"
                        )

                    body += (
                        '<form method="post" action="/aims-offering">'
                        '<input type="hidden" name="action" '
                        'value="save-course-bundles">'
                        '<input type="hidden" name="bundle_token" '
                        f'value="{html.escape(token)}">'
                        "<h2>Save course bundles</h2>"
                        + "\n".join(choices)
                        + '<button type="submit">'
                        "Save selected bundles</button></form>"
                    )

                self._send(_page("AIMS offering results", body))
            elif action == "save-course-bundles":
                from .cli import (
                    _load_saved_course_bundles,
                    _save_saved_course_bundles,
                    _saved_course_bundle_signature,
                )

                token = fields.get("bundle_token", "")

                with self.server.plan_results_lock:
                    bundles = (
                        self.server.course_bundle_results.get(token)
                    )

                    if bundles is None:
                        raise ValueError(
                            "These bundle results have expired. "
                            "Check the offering again."
                        )

                    selected = [
                        bundle
                        for number, bundle in enumerate(
                            bundles,
                            start=1,
                        )
                        if fields.get(f"bundle_{number}") == "1"
                    ]

                    if not selected:
                        raise ValueError(
                            "Select at least one bundle to save."
                        )

                    saved = _load_saved_course_bundles()
                    signatures = {
                        _saved_course_bundle_signature(bundle)
                        for bundle in saved
                    }

                    added = 0
                    duplicates = 0

                    for bundle in selected:
                        signature = (
                            _saved_course_bundle_signature(bundle)
                        )

                        if signature in signatures:
                            duplicates += 1
                            continue

                        signatures.add(signature)
                        saved.append(bundle)
                        added += 1

                    if added:
                        _save_saved_course_bundles(saved)

                message = (
                    f"Saved {added} course bundle(s). "
                    f"Skipped {duplicates} duplicate(s)."
                )

                body = (
                    f'<p class="notice">{html.escape(message)}</p>'
                    '<p><a href="/saved-course-bundles">'
                    "View saved course bundles</a></p>"
                    '<p><a href="/aims-offering">'
                    "Check another offering</a></p>"
                )

                self._send(_page("Course bundles saved", body))
            elif action == "save-plans":
                result, already_saved = _save_selected_plans(
                    fields,
                    self.server.plan_results,
                    self.server.plan_results_lock,
                )
                body = f'<p class="notice">{html.escape(result)}</p>'
                if already_saved:
                    token = fields.get("plan_token", "")
                    with self.server.plan_results_lock:
                        plans = self.server.plan_results.get(token)
                    if plans:
                        body += _save_plan_form(
                            token,
                            plans,
                            retry=True,
                        )
                body += _saved_bundles_link()
                self._send(_page("Plans saved", body))
            elif action == "delete-plan":
                result = _delete_saved_timetable_plan(
                    fields.get("plan_number", "")
                )

                self._send(
                    _page(
                        "Saved timetable plans",
                        _saved_timetable_plans_page(result),
                    )
                )
            else:
                result, token, plans_html = _generate(
                    fields,
                    upload,
                    self.server.plan_results,
                    self.server.plan_results_lock,
                )
                body = _form() + _result_html(
                    result,
                    re.findall(
                        r"^\s*([A-Z]{2,4}\d{4}[A-Z]?)\s+has\s+",
                        result,
                        re.MULTILINE | re.IGNORECASE,
                    ),
                )
                body += plans_html
                if token:
                    body += _save_plan_form(
                        token,
                        self.server.plan_results[token],
                    )
                self._send(_page("CityUSchedule results", body))
        except (ValueError, OSError) as error:
            path = urlparse(self.path).path
            if path == "/delete-plan":
                body = (
                    '<div class="error">'
                    + html.escape(str(error))
                    + "</div>"
                    + _saved_timetable_plans_page()
                )

                self._send(
                    _page("Saved timetable plans", body),
                    status=400,
                )
                return
            form = (
                _ge_search_form()
                if path == "/ge-search"
                else _ge_info_form()
                if path == "/ge-info"
                else _basic_settings_form()
                if path == "/settings"
                else _aims_form()
                if path == "/aims"
                else _aims_offering_form(
                    fields.get("course_code", ""),
                    fields.get("offering_text", ""),
                )
                if path == "/aims-offering"
                else _form()
            )
            body = f'<div class="error">{html.escape(str(error))}</div>\n{form}'
            self._send(_page("CityUSchedule", body), status=400)
        except Exception as error:
            path = urlparse(self.path).path

            form = (
                _ge_search_form()
                if path == "/ge-search"
                else _ge_info_form()
                if path == "/ge-info"
                else _basic_settings_form()
                if path == "/settings"
                else _aims_form()
                if path == "/aims"
                else _aims_offering_form(
                    fields.get("course_code", ""),
                    fields.get("offering_text", ""),
                )
                if path == "/aims-offering"
                else _form()
            )

            body = (
                '<div class="error">'
                "An unexpected server error occurred: "
                + html.escape(str(error))
                + "</div>\n"
                + form
            )

            self._send(
                _page("Server error", body),
                status=500,
            )

    def _send(
        self,
        body: bytes,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args):
        return


def create_web_server(host: str = "127.0.0.1", port: int = 8000):
    server = CityUScheduleHTTPServer(
        (host, port),
        CityUScheduleWebHandler,
    )
    server.course_bundle_results = {}
    return server

def run_web_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
) -> None:
    server = create_web_server(host, port)
    url_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{url_host}:{server.server_port}"
    print(f"CityUSchedule web app is running at {url}", flush=True)
    print("Press Ctrl+C to stop it.", flush=True)
    if open_browser:
        webbrowser.open(url, new=2)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
