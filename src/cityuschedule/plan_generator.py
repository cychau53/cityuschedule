"""Generate ranked, clash-free course plans that follow CityU registration rules.

This is the only plan search in the package. Menu option 8 and the
``--courses`` / ``--add-ge`` command use it: course sections come from the
GE course details (menu option 6) and are fitted around the saved AIMS
timetable (menu option 3), so the user never writes a JSON file. It reuses the
project's existing building blocks instead of repeating them:

==============================  =============================================
Job                             Existing code reused
==============================  =============================================
Read the course catalogue       ``course_catalog.load_course_catalog``
Read GE section data            ``course_catalog.load_ge_section_catalog``
Course credits                  ``course_catalog.load_credit_catalogs``,
                                ``planner.calculate_course_credits``
Catalogue rows -> sections      ``course_planner.catalogue_to_planned_sections``
Hand-made bundles               ``course_planner.build_course_bundle``
Lecture + tutorial bundles      ``aims_table_parser.ParsedAimsTable
                                .registration_bundles``
Time parsing and clash check    ``schedule_conflicts.time_to_minutes``,
                                ``slots_overlap``
Walking time between buildings  ``travel_time.load_travel_times``,
                                ``walking_minutes``
GE areas and terms              ``ge_courses.load_ge_courses``
Calendar export                 ``planner.planned_sections_to_sessions``,
                                ``calendar_export.export_ics``
==============================  =============================================

What this module adds is the search itself and the CityU course
registration rules (Academic Regulations and Records Office,
https://www.cityu.edu.hk/arro/creg/creg_main.htm):

* Study load: full-time 12-18 credit units, part-time at most 11, Summer
  Term at most 7. The maximum is a hard limit unless an overload is allowed;
  plans under the minimum are flagged as needing approval. LC2018, LC2031
  and PED courses do not count towards the study load.
* Pre-registered courses (from AIMS) stay fixed, or with
  ``allow_section_changes`` they may move to other sections. A change is
  one drop + add request, and fewer changes rank higher.
* Section status from the Master Class Schedule: full sections are only
  used through the waitlist (3rd time-ticket, not guaranteed); sections
  that are not web-enabled or are restricted need the AIMS e-form in the
  last time-ticket. Plans that need fewer of these rank higher.
* Courses not offered in the chosen term are left out. Prerequisites and
  precursors are surfaced for the student to verify; the planner does not
  track completed courses.
* Each plan lists its add/drop steps with CRNs and notes the GE quota
  control in the 2nd time-ticket.

The generator only plans. It never logs in to AIMS, registers, holds seats
or watches seat numbers, which CityU does not allow programs to do.
"""

from __future__ import annotations

import bisect
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import cached_property
from itertools import pairwise
from pathlib import Path

from .aims_fit import DAY_NAMES
from .aims_table_parser import AimsSession, ParsedAimsTable
from .calendar_export import export_ics
from .course_catalog import DEFAULT_CREDIT_CATALOGS, CatalogCourse, catalogue_dir
from .course_planner import (
    PlannedSection,
    build_course_bundle,
    catalogue_to_planned_sections,
)
from .planner import calculate_course_credits, planned_sections_to_sessions
from .schedule_conflicts import TimeSlot, slots_overlap, time_to_minutes
from .timetable import WEEKDAYS, format_timetable
from .travel_time import load_travel_times, walking_minutes

_DAY_LETTERS = {name: letter for letter, name in DAY_NAMES.items()}


def to_day(value: str) -> str:
    """``Mon``/``monday``/``M`` -> ``Mon`` (``R`` is Thursday, as in AIMS)."""
    text = str(value or "").strip()
    day = DAY_NAMES.get(text.upper()) if len(text) == 1 else text[:3].capitalize()
    if day not in WEEKDAYS:
        raise ValueError(f"Unknown day: {value!r}")
    return day


def to_days(values: Iterable[str] | None) -> frozenset[str]:
    return frozenset(
        to_day(part)
        for value in values or ()
        for part in str(value).replace(",", " ").split()
    )


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ---------------------------------------------------------------------------
# CityU course registration rules
# ---------------------------------------------------------------------------

# Study load per semester/term: (minimum, maximum) credit units.
# https://www.cityu.edu.hk/arro/creg/creg_sdfu.htm
STUDY_LOADS: dict[str, tuple[int, int]] = {
    "full-time": (12, 18),
    "part-time": (0, 11),
    "summer": (0, 7),
}

# Non-credit-bearing courses that do not count towards the study load.
# https://www.cityu.edu.hk/arro/creg/creg_main.htm
NON_CREDIT_COURSES = frozenset({"LC2018", "LC2031"})
NON_CREDIT_PREFIXES = ("PED",)

# Warn when a section has this many seats or fewer left.
FEW_SEATS_LEFT = 3

_COURSE_CODE_RE = re.compile(r"\b[A-Z]{2,4}\s?\d{4}[A-Z]?\b")


def counts_toward_study_load(course_code: str) -> bool:
    code = course_code.upper()
    return code not in NON_CREDIT_COURSES and not code.startswith(NON_CREDIT_PREFIXES)


def resolve_study_load(name: str | None) -> tuple[int, int] | None:
    """``full-time``/``part-time``/``summer`` -> ``(min, max)``; ``None`` = no rule."""
    key = str(name or "").strip().casefold().replace("_", "-").replace(" ", "-")
    if key in {"", "none", "off"}:
        return None
    key = {"fulltime": "full-time", "parttime": "part-time"}.get(key, key)
    if key not in STUDY_LOADS:
        raise ValueError(f"Unknown study load {name!r}; use full-time, part-time or summer")
    return STUDY_LOADS[key]


def term_key(text: str) -> tuple[str, str] | None:
    """Read a term in any of the formats used by CityU and this project.

    ``2627A``, ``Semester A 2026/27``, ``2026-27 Sem A`` -> ``("26", "A")``;
    ``2026-27 Summer`` or ``2627S`` -> ``("26", "S")``.
    """
    upper = str(text or "").upper()
    compact = re.fullmatch(r"\s*(\d\d)(\d\d)\s*([ABS])\s*", upper)
    if compact:
        return compact.group(1), compact.group(3)
    year = re.search(r"20(\d\d)\s*[-/]\s*\d\d", upper)
    if not year:
        return None
    if "SUMMER" in upper:
        return year.group(1), "S"
    part = re.search(r"\bSEM(?:ESTER)?\.?\s*([AB])\b", upper)
    return (year.group(1), part.group(1)) if part else None


def _term_keys(value) -> tuple[tuple[str, str], ...]:
    items = value if isinstance(value, (list, tuple)) else str(value or "").split(",")
    return tuple(dict.fromkeys(k for k in (term_key(str(i)) for i in items) if k))


def _course_codes(value) -> tuple[str, ...]:
    """Course codes from a list or free text such as ``"CS1102 or CS1302"``."""
    items = [value] if isinstance(value, str) else [str(item) for item in value or ()]
    codes = [
        code.replace(" ", "")
        for item in items
        for code in _COURSE_CODE_RE.findall(item.upper())
    ]
    return tuple(dict.fromkeys(codes))


@dataclass(frozen=True)
class CourseRequirements:
    """Catalogue rules for one course (any one listed code is enough)."""

    prerequisites: tuple[str, ...] = ()
    precursors: tuple[str, ...] = ()
    exclusive: tuple[str, ...] = ()
    terms: tuple[tuple[str, str], ...] = ()


def course_requirements_from_records(
    records: Iterable[Mapping],
) -> dict[str, CourseRequirements]:
    result: dict[str, CourseRequirements] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        code = str(record.get("course_code", record.get("code", ""))).strip().upper()
        if not code:
            continue
        need = CourseRequirements(
            prerequisites=_course_codes(record.get("prerequisites")),
            precursors=_course_codes(record.get("precursors")),
            exclusive=_course_codes(record.get("exclusive_courses")),
            terms=_term_keys(record.get("offering_terms", record.get("terms"))),
        )
        old = result.get(code)
        if old and not need.terms:
            need = replace(need, terms=old.terms)
        if need != CourseRequirements():
            result[code] = need
    return result


def load_course_requirements(
    extra_paths: Iterable[str | Path] = (),
) -> dict[str, CourseRequirements]:
    """Requirements and offering terms from ``data/catalogue/*_course_requirements.json``,
    GE terms from ``data/ge_courses.json``, then any extra catalogue files."""
    from .ge_courses import load_ge_courses

    records: list = []
    for path in (*(catalogue_dir() / name for name in DEFAULT_CREDIT_CATALOGS), *extra_paths):
        if not Path(path).is_file():
            continue
        with open(path, encoding="utf-8-sig") as file:
            data = json.load(file)
        if isinstance(data, Mapping):
            data = data.get("courses", [])
        records.extend(data if isinstance(data, list) else [])
    try:
        ge_records = [r for r in load_ge_courses() if r.get("terms")]
    except (OSError, ValueError):
        ge_records = []
    requirements = course_requirements_from_records(records)
    for code, need in course_requirements_from_records(ge_records).items():
        requirements[code] = replace(requirements.get(code, CourseRequirements()), terms=need.terms)
    return requirements


def load_ge_areas() -> dict[str, str]:
    """GE course code -> ``Area 1``/``Area 2``/``Area 3``/``University Req.``."""
    from .ge_courses import load_ge_courses

    try:
        return {str(r["course_code"]).upper(): str(r.get("area") or "") for r in load_ge_courses()}
    except (OSError, ValueError):
        return {}


@dataclass(frozen=True)
class SectionStatus:
    """Registration status of one section from Master Class Schedule fields."""

    full: bool = False
    seats: int | None = None
    waitlist: str = ""  # "Y", "N" or "" when unknown
    web_enabled: bool = True
    restrictions: str = ""


def section_status(section: PlannedSection) -> SectionStatus:
    availability = str(section.availability or "").strip().upper()
    seats = int(availability) if availability.isdigit() else None
    waitlist = str(section.waitlist or "").strip().upper()
    waitlist = {"YES": "Y", "NO": "N", "TRUE": "Y", "FALSE": "N"}.get(waitlist, waitlist)
    restrictions = str(section.restrictions or "").strip() or "; ".join(
        note for note in section.notes
        if re.search(r"\b(only for|not for|restrict)", str(note), re.IGNORECASE)
    )
    return SectionStatus(
        full=availability in {"FULL", "CLOSED"} or seats == 0,
        seats=seats,
        waitlist=waitlist,
        web_enabled=str(section.web or "").strip().upper() not in {"N", "NO", "FALSE"},
        restrictions=restrictions,
    )


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Meeting:
    """One weekly class meeting. ``slot`` is the shared ``TimeSlot`` type."""

    course_code: str
    section: str
    slot: TimeSlot
    location: str = ""
    building: str = ""
    fixed: bool = False

    @property
    def day(self) -> str:
        return self.slot.day

    @cached_property
    def start(self) -> int:
        return time_to_minutes(self.slot.start)

    @cached_property
    def end(self) -> int:
        return time_to_minutes(self.slot.end)

    @property
    def label(self) -> str:
        return self.slot.label


def _meeting(course_code, section, day, start, end, location="", building="", fixed=False):
    day = to_day(day)
    if time_to_minutes(end) <= time_to_minutes(start):
        raise ValueError(f"{course_code} {section} on {day} ends before it starts ({start}-{end})")
    return Meeting(
        course_code=course_code.upper(),
        section=section,
        slot=TimeSlot(day=day, start=start, end=end, label=f"{course_code.upper()} {section}"),
        location=location,
        building=(building or location.split(" ", 1)[0]).upper(),
        fixed=fixed,
    )


@dataclass(frozen=True)
class CourseOption:
    """One complete registration bundle of a course, e.g. ``C01`` + ``T03``."""

    course_code: str
    title: str
    credits: int
    section_codes: tuple[str, ...]
    sections: tuple[PlannedSection, ...]
    meetings: tuple[Meeting, ...]
    # "web" (Web Add/Drop), "waitlist" (full, has a waitlist),
    # "e-form" (not web-enabled) or "closed" (full, no waitlist).
    route: str = "web"
    restricted: bool = False
    notes: tuple[str, ...] = ()
    preregistered: bool = False
    # Pre-registered sections this bundle replaces (empty = keeps them).
    replaces_sections: tuple[str, ...] = ()

    @property
    def days(self) -> frozenset[str]:
        return frozenset(m.day for m in self.meetings)

    @property
    def label(self) -> str:
        return f"{self.course_code} " + "+".join(self.section_codes)

    @property
    def registration_risk(self) -> int:
        """1 if the bundle needs a waitlist, e-form, restriction check or swap."""
        return int(self.route != "web" or self.restricted or bool(self.replaces_sections))

    @property
    def crn_text(self) -> str:
        crns = {s.section.upper(): s.crn for s in self.sections if s.crn}
        return ", ".join(
            f"{code} CRN {crns[code]}" if code in crns else code for code in self.section_codes
        )


@dataclass(frozen=True)
class PlanOptions:
    """Settings for :func:`generate_course_plans`.

    ``required_sections`` maps a course to sections it must use, e.g.
    ``{"CS2311": ("C01",)}``. ``bundle_definitions`` lists complete bundles
    by hand, e.g. ``{"GE1102": [["C01", "T01"]]}``.
    """

    required_courses: tuple[str, ...] = ()
    required_sections: Mapping[str, Sequence[str]] = field(default_factory=dict)
    exclude_courses: tuple[str, ...] = ()
    min_courses: int = 1
    max_courses: int | None = None
    ge_courses: int | None = None  # exact number of new GE courses
    min_credits: int | None = None
    max_credits: int | None = None
    preferred_days: tuple[str, ...] = ()
    avoid_days: tuple[str, ...] = ()
    earliest_start: str | None = None
    latest_end: str | None = None
    min_gap: int = 0
    lunch_minutes: int = 0
    lunch_window: tuple[str, str] = ("11:30", "14:30")
    max_daily_hours: float | None = None
    check_travel: bool = True
    max_results: int = 5
    search_limit: int = 200_000
    bundle_definitions: Mapping[str, Sequence[Sequence[str]]] = field(default_factory=dict)
    # CityU registration rules
    study_load: str | None = None
    allow_overload: bool = False
    allow_section_changes: bool = False
    seat_policy: str = "waitlist"  # "open", "waitlist" or "any"
    web_only: bool = False
    term: str | None = None  # e.g. "2627A" or "Semester A 2026/27"


@dataclass(frozen=True)
class PlanScore:
    new_courses: int
    total_credits: int
    registration_risk: int
    section_changes: int
    non_preferred_meetings: int
    days_on_campus: int
    idle_minutes: int
    early_or_late: int
    latest_finish: int


@dataclass(frozen=True)
class CoursePlan:
    chosen: tuple[CourseOption, ...]
    fixed_sessions: tuple[Mapping[str, str], ...]
    fixed_meetings: tuple[Meeting, ...]
    fixed_courses: tuple[str, ...]
    skipped_courses: tuple[str, ...]
    score: PlanScore
    study_load: tuple[int, int] | None = None
    ge_quota_courses: tuple[str, ...] = ()
    unknown_credit_courses: tuple[str, ...] = ()

    @property
    def total_credits(self) -> int:
        return self.score.total_credits

    @property
    def new_credits(self) -> int:
        """Credits of the courses this plan adds (fixed classes excluded)."""
        return sum(option.credits for option in self.chosen if not option.preregistered)

    @property
    def course_codes(self) -> tuple[str, ...]:
        return tuple(option.course_code for option in self.chosen)

    @property
    def sections(self) -> tuple[PlannedSection, ...]:
        return tuple(s for option in self.chosen for s in option.sections)

    @property
    def meetings(self) -> tuple[Meeting, ...]:
        new = (m for option in self.chosen for m in option.meetings)
        return tuple(sorted(
            (*self.fixed_meetings, *new),
            key=lambda m: (WEEKDAYS.index(m.day), m.start, m.label),
        ))

    @property
    def study_load_status(self) -> str:
        if not self.study_load:
            return ""
        low, high = self.study_load
        if self.total_credits < low:
            return f"below the {low}-credit minimum study load"
        if self.total_credits > high:
            return f"over the {high}-credit maximum study load"
        return ""

    def explain(self) -> str:
        s = self.score
        parts = [
            f"{s.new_courses} course(s) added",
            *([f"{s.total_credits} credits"] if s.total_credits else []),
            *(
                ["credits unknown for " + ", ".join(self.unknown_credit_courses)]
                if self.unknown_credit_courses else []
            ),
            f"{s.days_on_campus} day(s) on campus",
            f"{s.idle_minutes} min waiting between classes",
        ]
        if s.non_preferred_meetings:
            parts.append(f"{s.non_preferred_meetings} class(es) on non-preferred days")
        if s.early_or_late:
            parts.append(f"{s.early_or_late} class(es) before 09:00 or after 19:00")
        if s.section_changes:
            parts.append(f"{s.section_changes} pre-registered course(s) change section")
        if s.registration_risk - s.section_changes > 0:
            parts.append(
                f"{s.registration_risk - s.section_changes} course(s) need a waitlist, "
                "e-form or restriction check"
            )
        if self.study_load_status:
            parts.append(self.study_load_status)
        if self.skipped_courses:
            parts.append("leaves out " + ", ".join(self.skipped_courses))
        return "; ".join(parts)

    def registration_steps(self) -> list[str]:
        """Add/drop checklist for this plan, following CityU's process."""
        steps: list[str] = []
        if self.study_load:
            low, high = self.study_load
            line = f"Study load: {self.total_credits} credits (allowed {f'{low}-{high}' if low else f'up to {high}'})"
            if self.study_load_status:
                kind = "reduced load" if self.total_credits < low else "overload"
                line += (
                    f"; a {kind} needs approval from your home academic unit "
                    "(AIMS e-form: Study Load Adjustment)"
                )
            steps.append(line)
        kept = [*self.fixed_courses] + [
            option.label for option in self.chosen
            if option.preregistered and not option.replaces_sections
        ]
        if kept:
            steps.append("Keep pre-registered: " + ", ".join(kept))

        actions = []
        for option in self.chosen:
            if option.replaces_sections:
                actions.append(
                    f"Web Add/Drop, in ONE request: drop {option.course_code} "
                    f"{'+'.join(option.replaces_sections)} and add {option.crn_text} "
                    "(check seats first; a dropped seat may be taken by others)"
                )
        for option in self.chosen:
            if option.route == "web" and not option.preregistered:
                together = ", all sections together" if len(option.section_codes) > 1 else ""
                actions.append(f"Web Add/Drop: add {option.course_code} ({option.crn_text}){together}")
        for option in self.chosen:
            if option.route == "waitlist" and not option.preregistered:
                actions.append(
                    "Waitlist from 8:45 am on the first day of the 3rd time-ticket: "
                    f"{option.course_code} ({option.crn_text}); a seat is not guaranteed"
                )
        for option in self.chosen:
            if option.route in {"e-form", "closed"} and not option.preregistered:
                reason = "not web-enabled" if option.route == "e-form" else "full with no waitlist"
                actions.append(
                    "AIMS e-form (Add/Drop of Non-Web-enabled Course) in the last "
                    f"time-ticket: {option.course_code} ({option.crn_text}); {reason}, "
                    "needs approval from the course-offering unit"
                )
        steps.extend(f"{number}. {action}" for number, action in enumerate(actions, start=1))
        steps.extend(
            f"Note: {option.course_code}: {note}" for option in self.chosen for note in option.notes
        )
        if len(self.ge_quota_courses) > 1:
            steps.append(
                "Note: GE quota control: the 2nd time-ticket allows only a limited "
                "number of GE Area 1-3 courses (see the ARRO time-ticket page for "
                "your cohort); add the rest of " + ", ".join(self.ge_quota_courses)
                + " in the 3rd time-ticket if seats remain"
            )
        return steps

    def to_sessions(self) -> list[dict[str, str]]:
        """Kept AIMS classes plus the new sections, as session dictionaries."""
        fixed = [
            dict(s) for s in self.fixed_sessions
            if s.get("day") and s.get("start_time") and s.get("end_time")
        ]
        return fixed + planned_sections_to_sessions(
            tuple(s for s in self.sections if s.day and s.start and s.end)
        )

    def to_dict(self) -> dict:
        """Plain data for saving the plan (menu option 10 shows saved plans)."""
        return {
            "total_credits": self.total_credits,
            "summary": self.explain(),
            "courses": [option.label for option in self.chosen],
            "sections": [
                {
                    "course_code": s.course_code,
                    "section": s.section,
                    "crn": s.crn,
                    "day": s.day,
                    "start": s.start,
                    "end": s.end,
                    "location": s.location,
                }
                for s in self.sections
            ],
            "registration_steps": self.registration_steps(),
        }


_REJECTION_TEXT = {
    "clash": "classes clash",
    "avoid_day": "uses an avoided day",
    "time_window": "outside the allowed start/end time",
    "min_gap": "gap between classes too short",
    "travel": "not enough time to walk between buildings",
    "lunch": "no lunch break",
    "daily_hours": "too many hours in one day",
    "max_credits": "over the credit limit",
    "max_courses": "over the course limit",
    "ge_courses": "wrong number of GE courses",
    "min_credits": "not enough credits",
    "min_courses": "too few courses",
    "required_section": "does not include a required section",
    "full_section": "section is full (no seats or no waitlist)",
    "not_web": "not web-enabled or has registration restrictions",
    "exclusive": "exclusive with another course in the plan",
}


@dataclass
class PlanReport:
    """The best plans plus the reasons other combinations were rejected."""

    plans: list[CoursePlan]
    explored: int = 0
    truncated: bool = False
    rejections: Counter = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)
    # course code -> section bundles that fit the fixed timetable on their own
    fitting: dict[str, tuple[CourseOption, ...]] = field(default_factory=dict)

    def fit_summary(self) -> list[str]:
        """One line per course: how many timeslots fit your timetable."""
        lines = []
        for code, fits in sorted(self.fitting.items()):
            if not fits:
                lines.append(f"{code} has no timeslot that fits your timetable")
                continue
            slots = "; ".join(
                "+".join(o.section_codes) + " " + ", ".join(
                    f"{m.day} {_clock(m.start)}-{_clock(m.end)}" for m in o.meetings
                )
                for o in fits
            )
            count = "one timeslot" if len(fits) == 1 else f"{len(fits)} timeslots"
            verb = "fits" if len(fits) == 1 else "fit"
            lines.append(f"{code} has {count} that {verb} your timetable: {slots}")
        return lines

    def __iter__(self):
        return iter(self.plans)

    def __len__(self) -> int:
        return len(self.plans)

    def explain_no_plans(self) -> str:
        if self.plans:
            return ""
        lines = ["No plan satisfies all settings."]
        for key, count in self.rejections.most_common():
            if key != "bound":
                lines.append(f"  {count:>6} option(s) rejected: {_REJECTION_TEXT.get(key, key)}")
        if self.truncated:
            lines.append("  Search stopped early; narrow the course list.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Building bundles
# ---------------------------------------------------------------------------


def build_course_options(
    course: CatalogCourse,
    bundle_definitions: Sequence[Sequence[str]] | None = None,
) -> list[CourseOption]:
    """Every complete registration bundle of ``course``.

    Bundles come from ``ParsedAimsTable.registration_bundles`` (one section
    of each activity type from the same section family, the same rule as
    menu option 4), or from ``bundle_definitions`` checked with
    ``build_course_bundle``.
    """
    code = course.code.upper()
    planned = catalogue_to_planned_sections([course])
    if bundle_definitions:
        bundles = [
            tuple(dict.fromkeys(s.section.upper() for s in build_course_bundle(course, list(d))))
            for d in bundle_definitions
        ]
    else:
        table = ParsedAimsTable(
            course_code=code,
            sessions=tuple(
                AimsSession(
                    course_code=code,
                    crn=s.crn,
                    section=s.section.upper(),
                    credit=course.credits or 0,
                    day=_DAY_LETTERS[to_day(s.day)] if s.day else None,
                    start_time=s.start or None,
                    end_time=s.end or None,
                )
                for s in planned
            ),
        )
        try:
            bundles = table.registration_bundles()
        except ValueError as error:
            raise ValueError(
                f"{code}: {error}; list its complete bundles in a bundle file"
            ) from None

    credits = int(course.credits or 0) if counts_toward_study_load(code) else 0
    options = []
    for codes in dict.fromkeys(bundles):
        sections = tuple(s for s in planned if s.section.upper() in codes)
        meetings = tuple(
            _meeting(code, s.section, s.day, s.start, s.end, s.location)
            for s in sections if s.day and s.start and s.end
        )
        route, restricted, notes = _bundle_registration(codes, sections)
        options.append(CourseOption(
            course_code=code,
            title=course.title,
            credits=credits,
            section_codes=codes,
            sections=sections,
            meetings=meetings,
            route=route,
            restricted=restricted,
            notes=notes,
        ))
    return options


def _bundle_registration(
    codes: Sequence[str],
    sections: Sequence[PlannedSection],
) -> tuple[str, bool, tuple[str, ...]]:
    """How a bundle is registered, from Master Class Schedule fields."""
    route, restricted, notes = "web", False, []
    for code in codes:
        status = section_status(next(s for s in sections if s.section.upper() == code))
        if not status.web_enabled:
            route = "e-form"
        if status.restrictions:
            restricted = True
            notes.append(
                f"{code} has registration restrictions ({status.restrictions}); if you "
                "are not eligible, apply with the AIMS e-form in the last time-ticket"
            )
        if status.full:
            if status.waitlist != "N":
                route = "waitlist" if route == "web" else route
                if not status.waitlist:
                    notes.append(f"{code} is full; check Waitlist Avail in the Master Class Schedule")
            elif route != "e-form":
                route = "closed"
        elif status.seats is not None and status.seats <= FEW_SEATS_LEFT:
            notes.append(f"{code} has only {status.seats} seat(s) left; have a backup plan")
    return route, restricted, tuple(dict.fromkeys(notes))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class _Rules:
    """Checks one bundle against the classes already placed."""

    def __init__(self, options: PlanOptions, travel: Mapping[str, Mapping[str, int]]):
        self.avoid = to_days(options.avoid_days)
        self.prefer = to_days(options.preferred_days)
        self.earliest = time_to_minutes(options.earliest_start) if options.earliest_start else None
        self.latest = time_to_minutes(options.latest_end) if options.latest_end else None
        self.min_gap = max(0, options.min_gap)
        self.lunch = max(0, options.lunch_minutes)
        self.lunch_start, self.lunch_end = map(time_to_minutes, options.lunch_window)
        self.max_daily = int(options.max_daily_hours * 60) if options.max_daily_hours else None
        self.travel = travel
        self.unknown_buildings: set[str] = set()

    def walk(self, first: Meeting, second: Meeting) -> int | None:
        if not self.travel:
            return 0
        minutes = walking_minutes(first.building, second.building, self.travel)
        if minutes is None:
            self.unknown_buildings.update(
                b for b in (first.building, second.building) if b and b not in self.travel
            )
        return minutes

    def add(self, state: dict[str, tuple[Meeting, ...]], option: CourseOption):
        """Return ``(new_state, None)`` or ``(None, reason)``."""
        if option.days & self.avoid:
            return None, "avoid_day"
        new_state = dict(state)
        for meeting in option.meetings:
            if (self.earliest is not None and meeting.start < self.earliest) or (
                self.latest is not None and meeting.end > self.latest
            ):
                return None, "time_window"
            day = new_state.get(meeting.day, ())
            if any(slots_overlap(m.slot, meeting.slot) for m in day):
                return None, "clash"
            day = tuple(sorted((*day, meeting), key=lambda m: (m.start, m.end)))
            here = day.index(meeting)
            neighbours = []
            if here > 0:
                neighbours.append((day[here - 1], meeting))
            if here + 1 < len(day):
                neighbours.append((meeting, day[here + 1]))
            for first, second in neighbours:
                gap = second.start - first.end
                if gap < self.min_gap and not (first.fixed or second.fixed):
                    return None, "min_gap"
                walk = self.walk(first, second)
                if walk is not None and walk > gap:
                    return None, "travel"
            new_state[meeting.day] = day
        for name in option.days:
            day = new_state[name]
            if self.max_daily is not None and sum(m.end - m.start for m in day) > self.max_daily:
                return None, "daily_hours"
            added_classes = tuple(meeting for meeting in day if not meeting.fixed)
            if self.lunch and not self._has_lunch(added_classes):
                return None, "lunch"
        return new_state, None

    def _has_lunch(self, day: tuple[Meeting, ...]) -> bool:
        cursor = self.lunch_start
        for meeting in day:
            if meeting.end <= cursor:
                continue
            if meeting.start >= self.lunch_end:
                break
            if meeting.start - cursor >= self.lunch:
                return True
            cursor = max(cursor, meeting.end)
        return self.lunch_end - cursor >= self.lunch


def _rank_key(plan: CoursePlan) -> tuple:
    """Lower is better. The first five parts never improve as classes are
    added, which lets the search skip branches (see ``lower_bound``)."""
    s = plan.score
    return (
        -s.new_courses,
        -s.total_credits,
        s.registration_risk,
        s.non_preferred_meetings,
        s.days_on_campus,
        s.idle_minutes,
        s.early_or_late,
        s.latest_finish,
        tuple(option.label for option in plan.chosen),
    )


def generate_course_plans(
    courses: Sequence[CatalogCourse],
    options: PlanOptions | None = None,
    *,
    fixed_sessions: Iterable[Mapping[str, str]] = (),
    credit_courses: Sequence[CatalogCourse] = (),
    travel_times: Mapping[str, Mapping[str, int]] | None = None,
    requirements: Mapping[str, CourseRequirements] | None = None,
    ge_areas: Mapping[str, str] | None = None,
) -> PlanReport:
    """Search for the best clash-free plans.

    ``courses`` are the candidate courses (from ``load_course_catalog``);
    any course not in ``required_courses`` is optional. ``fixed_sessions``
    are classes already in the timetable, e.g. the pre-registered courses
    from ``load_aims_html``. ``credit_courses`` (``load_credit_catalogs()``)
    supplies missing credits. ``travel_times`` defaults to
    ``data/travel_time.json``. ``requirements`` (``load_course_requirements()``)
    and ``ge_areas`` (``load_ge_areas()``) switch on the catalogue checks
    and the GE quota note.
    """
    options = options or PlanOptions()
    requirements = {k.upper(): v for k, v in (requirements or {}).items()}
    ge_areas = {k.upper(): v for k, v in (ge_areas or {}).items()}
    if options.max_results < 1:
        raise ValueError("max_results must be at least 1")
    if options.seat_policy not in {"open", "waitlist", "any"}:
        raise ValueError("seat_policy must be 'open', 'waitlist' or 'any'")
    study_load = resolve_study_load(options.study_load)
    report = PlanReport(plans=[])
    warn = report.warnings.append

    max_credits = options.max_credits
    if study_load and not options.allow_overload:
        if max_credits is not None and max_credits > study_load[1]:
            warn(
                f"Maximum credits lowered from {max_credits} to {study_load[1]}, the CityU "
                "study-load limit; an overload needs approval from your home academic unit"
            )
        if max_credits is None or max_credits > study_load[1]:
            max_credits = study_load[1]
    min_credits = options.min_credits
    if min_credits is not None and max_credits is not None and min_credits > max_credits:
        raise ValueError("min_credits cannot be greater than max_credits")

    if travel_times is None and options.check_travel:
        try:
            travel_times = load_travel_times()
        except OSError:
            travel_times = {}
    rules = _Rules(options, travel_times if options.check_travel else {})

    term = None
    if options.term:
        term = term_key(options.term)
        if term is None:
            raise ValueError(f"Unknown term {options.term!r}; use e.g. 2627A or 'Semester A 2026/27'")

    excluded = {c.upper() for c in options.exclude_courses}
    required_sections = {
        code.upper(): {s.upper() for s in sections}
        for code, sections in options.required_sections.items()
    }
    required = {c.upper() for c in options.required_courses} | set(required_sections)
    bundle_definitions = {k.upper(): v for k, v in options.bundle_definitions.items()}
    catalogue_codes = {c.code.upper() for c in courses}
    known_credits = [c for c in (*courses, *credit_courses) if c.credits is not None]

    def credits_of(code: str) -> int | None:
        total, unknown = calculate_course_credits({code}, known_credits)
        return None if unknown else total

    # Pre-registered (fixed) timetable -------------------------------------
    fixed_sessions = tuple(fixed_sessions)
    preregistered: dict[str, set[str]] = {}
    for session in fixed_sessions:
        code = str(session.get("course_code", "")).upper()
        if code:
            preregistered.setdefault(code, set()).add(str(session.get("section", "")).upper())
    movable: set[str] = set()
    if options.allow_section_changes:
        movable = {c for c in preregistered if c in catalogue_codes and c not in excluded}
        stuck = sorted(set(preregistered) - movable)
        if stuck:
            warn("Pre-registered but not in your course list, so they stay as they are: " + ", ".join(stuck))
        required |= movable
    kept_sessions = tuple(
        s for s in fixed_sessions if str(s.get("course_code", "")).upper() not in movable
    )
    fixed, unscheduled = [], []
    for s in kept_sessions:
        code, section = str(s.get("course_code", "")).upper(), str(s.get("section", ""))
        if s.get("day") and s.get("start_time") and s.get("end_time"):
            fixed.append(_meeting(
                code, section, s["day"], s["start_time"], s["end_time"],
                " ".join(p for p in (s.get("building", ""), s.get("room", "")) if p),
                s.get("building", ""), fixed=True,
            ))
        else:
            unscheduled.append(f"{code} {section}".strip())
    if unscheduled:
        warn("No fixed time (not checked for clashes): " + ", ".join(sorted(set(unscheduled))))
    state: dict[str, tuple[Meeting, ...]] = {}
    for meeting in sorted(fixed, key=lambda m: (m.start, m.end)):
        state[meeting.day] = (*state.get(meeting.day, ()), meeting)
    fixed_codes = set(preregistered) - movable
    fixed_credits, unknown_fixed = calculate_course_credits(
        {c for c in fixed_codes if counts_toward_study_load(c)}, known_credits
    )
    uses_credits = study_load is not None or min_credits is not None or max_credits is not None
    if unknown_fixed and uses_credits:
        warn("Credits unknown for pre-registered courses (counted as 0): " + ", ".join(unknown_fixed))

    # Candidate courses ----------------------------------------------------
    taken = fixed_codes
    catalogue: dict[str, CatalogCourse] = {}
    unknown_credits, unchecked = [], []
    for course in courses:
        code = course.code.upper()
        if code in excluded or code in catalogue:
            continue
        if code in fixed_codes:
            warn(f"{code} is already in your timetable; skipped (allow section changes to move it)")
            continue
        need = requirements.get(code, CourseRequirements())
        problem = ""
        if term and need.terms and term not in need.terms:
            problem = "not offered in the chosen term"
        elif set(need.exclusive) & taken:
            problem = "exclusive with " + ", ".join(sorted(set(need.exclusive) & taken))
        if problem:
            if code not in required:
                warn(f"{code} skipped: {problem}")
                continue
            warn(f"{code}: {problem}; kept because it is required")
        if need.prerequisites or need.precursors:
            unchecked.append(code)
        if course.credits is None:
            credits = credits_of(code)
            if credits is None:
                unknown_credits.append(code)
            course = replace(course, credits=credits)
        catalogue[code] = course
    if unknown_credits and uses_credits:
        warn("Credits unknown (counted as 0): " + ", ".join(sorted(unknown_credits)))
    if unchecked:
        warn(
            "Check prerequisites/precursors in DegreeWorks or the course catalogue: "
            + ", ".join(sorted(unchecked))
        )
    missing = sorted(required - set(catalogue))
    if missing:
        raise ValueError("Required course(s) not available in the catalogue: " + ", ".join(missing))

    exclusive_pairs: dict[str, set[str]] = {}
    for code, need in requirements.items():
        for other in need.exclusive:
            exclusive_pairs.setdefault(code, set()).add(other)
            exclusive_pairs.setdefault(other, set()).add(code)

    options_by_course: dict[str, list[CourseOption]] = {}
    for code, course in catalogue.items():
        course_options = build_course_options(course, bundle_definitions.get(code))
        wanted = required_sections.get(code)
        if wanted:
            unknown = wanted - {s.section.upper() for s in course.sections}
            if unknown:
                raise ValueError(f"Unknown required section(s) for {code}: {', '.join(sorted(unknown))}")
            kept = [o for o in course_options if wanted <= set(o.section_codes)]
            report.rejections["required_section"] += len(course_options) - len(kept)
            course_options = kept
        need = requirements.get(code, CourseRequirements())
        allowed = []
        for option in course_options:
            if code in movable:
                keeps = set(option.section_codes) == preregistered[code]
                if not keeps and option.route != "web":
                    report.rejections["full_section"] += 1  # never swap a seat for a full section
                    continue
                option = replace(
                    option, preregistered=True,
                    replaces_sections=() if keeps else tuple(sorted(preregistered[code])),
                )
            elif options.web_only and (option.route == "e-form" or option.restricted):
                report.rejections["not_web"] += 1
                continue
            elif (option.route == "closed" and options.seat_policy != "any") or (
                option.route == "waitlist" and options.seat_policy == "open"
            ):
                report.rejections["full_section"] += 1
                continue
            allowed.append(option)
            if len(option.meetings) < len(option.sections):
                warn(f"{option.label} has a section with no fixed time; it is not checked for clashes")
        if not allowed and code in required:
            warn(f"{code} has no complete section bundle that can be registered")
        options_by_course[code] = allowed
    report.warnings[:] = list(dict.fromkeys(report.warnings))
    for code, course_options in options_by_course.items():
        if code not in movable:
            report.fitting[code] = tuple(o for o in course_options if rules.add(state, o)[1] is None)

    # Branch-and-bound search ---------------------------------------------
    order = sorted(options_by_course, key=lambda c: (c not in required, len(options_by_course[c]), c))
    is_ge = {c: c.startswith("GE") for c in order}
    remaining_credits = [0] * (len(order) + 1)
    remaining_courses = [0] * (len(order) + 1)
    remaining_ge = [0] * (len(order) + 1)
    for index in range(len(order) - 1, -1, -1):
        code = order[index]
        remaining_credits[index] = remaining_credits[index + 1] + max(
            (o.credits for o in options_by_course[code]), default=0
        )
        remaining_ge[index] = remaining_ge[index + 1] + int(is_ge[code] and bool(options_by_course[code]))
        remaining_courses[index] = remaining_courses[index + 1] + int(bool(options_by_course[code]))
    credit_cap = max_credits if max_credits is not None else 10**9
    early, late = time_to_minutes("09:00"), time_to_minutes("19:00")
    plans: list[CoursePlan] = []
    top_keys: list[tuple] = []  # rank keys of the best plans so far
    keep = max(options.max_results * 4, 50)

    def record(chosen: list[CourseOption], current: dict, credits: int) -> None:
        total = fixed_credits + credits
        if min_credits is not None and total < min_credits:
            report.rejections["min_credits"] += 1
            return
        if len(chosen) < options.min_courses:
            report.rejections["min_courses"] += 1
            return
        new_meetings = [m for o in chosen for m in o.meetings]
        score = PlanScore(
            new_courses=len(chosen),
            total_credits=total,
            registration_risk=sum(o.registration_risk for o in chosen),
            section_changes=sum(1 for o in chosen if o.replaces_sections),
            non_preferred_meetings=sum(1 for m in new_meetings if m.day not in rules.prefer) if rules.prefer else 0,
            days_on_campus=sum(1 for day in current.values() if day),
            idle_minutes=sum(
                max(0, b.start - a.end) for day in current.values() for a, b in pairwise(day)
            ),
            early_or_late=sum(1 for m in new_meetings if m.start < early or m.end > late),
            latest_finish=max((day[-1].end for day in current.values() if day), default=0),
        )
        chosen_codes = {o.course_code for o in chosen}
        plan = CoursePlan(
            chosen=tuple(chosen),
            fixed_sessions=kept_sessions,
            fixed_meetings=tuple(fixed),
            fixed_courses=tuple(sorted(fixed_codes)),
            skipped_courses=tuple(c for c in order if c not in chosen_codes),
            score=score,
            study_load=study_load,
            ge_quota_courses=tuple(
                o.course_code for o in chosen if ge_areas.get(o.course_code, "").startswith("Area")
            ),
            unknown_credit_courses=tuple(
                o.course_code for o in chosen if o.course_code in unknown_credits
            ),
        )
        plans.append(plan)
        key = _rank_key(plan)
        if len(top_keys) < options.max_results or key < top_keys[-1]:
            bisect.insort(top_keys, key)
            del top_keys[options.max_results:]
        if len(plans) > keep * 2:
            plans.sort(key=_rank_key)
            del plans[keep:]

    def search(index, chosen, current, credits, ge_count, non_preferred, risk) -> None:
        if report.explored >= options.search_limit:
            report.truncated = True
            return
        report.explored += 1
        if options.ge_courses is not None and ge_count + remaining_ge[index] < options.ge_courses:
            report.rejections["ge_courses"] += 1
            return
        if index == len(order):
            record(chosen, current, credits)
            return
        if min_credits is not None and fixed_credits + credits + remaining_credits[index] < min_credits:
            report.rejections["min_credits"] += 1
            return
        best_credits = min(credit_cap, fixed_credits + credits + remaining_credits[index])
        days = sum(1 for day in current.values() if day)
        most_courses = len(chosen) + remaining_courses[index]
        if options.max_courses is not None:
            most_courses = min(most_courses, options.max_courses)
        if options.ge_courses is not None:
            most_courses = min(
                most_courses,
                len(chosen) - ge_count + options.ge_courses
                + sum(1 for c in order[index:] if not is_ge[c] and options_by_course[c]),
            )
        bound = (-most_courses, -best_credits, risk, non_preferred, days)
        if len(top_keys) >= options.max_results and bound > top_keys[-1][:5]:
            report.rejections["bound"] += 1
            return

        code = order[index]
        at_limit = options.max_courses is not None and len(chosen) >= options.max_courses
        ge_full = is_ge[code] and options.ge_courses is not None and ge_count >= options.ge_courses
        exclusive = bool(exclusive_pairs.get(code, set()) & {o.course_code for o in chosen})
        if at_limit or ge_full or exclusive:
            reason = "exclusive" if exclusive else "ge_courses" if ge_full else "max_courses"
            report.rejections[reason] += 1
            if code in required:
                return
        else:
            for option in options_by_course[code]:
                if max_credits is not None and fixed_credits + credits + option.credits > max_credits:
                    report.rejections["max_credits"] += 1
                    continue
                new_state, reason = rules.add(current, option)
                if reason:
                    report.rejections[reason] += 1
                    continue
                extra = sum(1 for m in option.meetings if m.day not in rules.prefer) if rules.prefer else 0
                search(
                    index + 1, [*chosen, option], new_state, credits + option.credits,
                    ge_count + int(is_ge[code]), non_preferred + extra, risk + option.registration_risk,
                )
        if code not in required:
            search(index + 1, chosen, current, credits, ge_count, non_preferred, risk)

    search(0, [], state, 0, 0, 0, 0)
    plans.sort(key=_rank_key)
    report.plans = plans[: options.max_results]
    if rules.unknown_buildings:
        warn(
            "Walking time unknown for building(s) " + ", ".join(sorted(rules.unknown_buildings))
            + "; those transfers were not checked"
        )
    return report


# ---------------------------------------------------------------------------
# Display and export
# ---------------------------------------------------------------------------

PLANNING_ONLY_NOTICE = (
    "These plans are for planning only. Register yourself in AIMS during your "
    "time-ticket; seats change in real time, so keep a backup plan."
)


def format_plan(plan: CoursePlan, number: int | None = None, steps: bool = True) -> str:
    lines = [f"{'Plan' if number is None else f'Plan {number}'}: {plan.explain()}"]
    tags = {"waitlist": "waitlist", "e-form": "e-form", "closed": "full, no waitlist"}
    for option in plan.chosen:
        labels = []
        if option.replaces_sections:
            labels.append("change from " + "+".join(option.replaces_sections))
        elif option.preregistered:
            labels.append("pre-registered")
        if option.route in tags:
            labels.append(tags[option.route])
        if option.restricted:
            labels.append("restricted")
        credits = "?" if option.course_code in plan.unknown_credit_courses else option.credits
        lines.append(
            f"  {option.label}  ({credits} cr)  {option.title}".rstrip()
            + (f"  [{', '.join(labels)}]" if labels else "")
        )
    if plan.fixed_courses:
        lines.append("  Kept from your AIMS timetable: " + ", ".join(plan.fixed_courses))
    lines.extend(
        f"  {line}" for line in format_timetable(plan.to_sessions()).splitlines() if line
    )
    if steps and plan.registration_steps():
        lines.append("  Registration steps:")
        lines.extend(f"    {step}" for step in plan.registration_steps())
    return "\n".join(lines)


def export_plan(
    plan: CoursePlan,
    output: str | Path,
    semester_start: str,
    semester_end: str,
    exclusions_path: str | None = None,
) -> str:
    """Write the plan, including kept AIMS classes, to an .ics calendar."""
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    return export_ics(
        plan.to_sessions(), str(output), semester_start, semester_end,
        exclusions_path=exclusions_path,
    )
