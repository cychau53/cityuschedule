"""Generate ranked, clash-free course plans.

This module builds complete registration bundles for each course (for
example one lecture ``C01`` plus one tutorial ``T03``), searches every
combination that fits around an optional fixed timetable, and returns the
best plans first.

Typical use::

    from cityuschedule.course_catalog import load_course_catalog
    from cityuschedule.plan_generator import PlanOptions, generate_course_plans

    courses = load_course_catalog("course_catalog.json")
    report = generate_course_plans(
        courses,
        PlanOptions(
            required_courses=("CS2311",),
            max_credits=18,
            avoid_days=("Fri",),
            lunch_minutes=45,
        ),
    )
    for number, plan in enumerate(report.plans, start=1):
        print(format_plan(plan, number))

Rules applied while searching:

* Every chosen course uses one complete bundle: one section of each
  activity type (lecture, tutorial, lab, ...) from the same section family.
  All weekly meetings of a section are kept together.
* Optional courses may be left out; required courses never are.
* Plans never clash with each other or with the fixed timetable.
* Day filters (``avoid_days``), time windows, minimum gaps, a lunch break,
  a daily-hours limit and walking time between buildings are only checked
  for the new classes, so a fixed timetable that already breaks a rule does
  not reject every plan.
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise, product
from pathlib import Path

from .course_catalog import CatalogCourse, load_course_catalog
from .course_planner import PlannedSection, catalogue_to_planned_sections

# ---------------------------------------------------------------------------
# Days, times and buildings
# ---------------------------------------------------------------------------

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_DAY_ALIASES = {
    "M": "Mon", "MO": "Mon", "MON": "Mon", "MONDAY": "Mon",
    "T": "Tue", "TU": "Tue", "TUE": "Tue", "TUES": "Tue", "TUESDAY": "Tue",
    "W": "Wed", "WE": "Wed", "WED": "Wed", "WEDNESDAY": "Wed",
    "R": "Thu", "TH": "Thu", "THU": "Thu", "THUR": "Thu", "THURS": "Thu",
    "THURSDAY": "Thu",
    "F": "Fri", "FR": "Fri", "FRI": "Fri", "FRIDAY": "Fri",
    "S": "Sat", "SA": "Sat", "SAT": "Sat", "SATURDAY": "Sat",
    "U": "Sun", "SU": "Sun", "SUN": "Sun", "SUNDAY": "Sun",
}

# Old academic-building codes that still appear in course data.
BUILDING_ALIASES = {
    "AC1": "YEUNG",
    "AC2": "LI",
    "AC3": "LAU",
}


def normalize_day(value: str) -> str:
    """Return ``Mon`` .. ``Sun`` for any common spelling (``R`` = Thursday)."""
    key = (value or "").strip().upper().rstrip(".")
    try:
        return _DAY_ALIASES[key]
    except KeyError:
        raise ValueError(f"Unknown day: {value!r}") from None


def normalize_days(values: Iterable[str] | None) -> frozenset[str]:
    """Normalize a list of days; comma-separated items are also accepted."""
    days = set()
    for value in values or ():
        for part in str(value).replace(",", " ").split():
            days.add(normalize_day(part))
    return frozenset(days)


def parse_time(value: str) -> int:
    """Convert ``9:00``, ``09:00`` or ``09:00:00`` to minutes after midnight."""
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*", value or "")
    if not match:
        raise ValueError(f"Invalid time: {value!r}")
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 23 or minutes > 59:
        raise ValueError(f"Invalid time: {value!r}")
    return hours * 60 + minutes


def format_minutes(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def building_code(location: str, known_buildings: Iterable[str] = ()) -> str:
    """Guess the building code from a location such as ``LI 3508``."""
    first = (location or "").strip().split(" ", 1)[0].upper()
    if not first:
        return ""
    first = BUILDING_ALIASES.get(first, first)
    known = {code.upper() for code in known_buildings}
    if known and first not in known:
        return ""
    return first


def load_travel_times(path: str | Path | None = None) -> dict[str, dict[str, int]]:
    """Load the walking-time matrix shipped with the package."""
    if path is None:
        here = Path(__file__).resolve()
        candidates = (
            here.parents[2] / "data" / "travel_time.json",
            here.parent / "data" / "travel_time.json",
        )
        path = next((p for p in candidates if p.is_file()), candidates[0])
    with open(path, encoding="utf-8-sig") as file:
        data = json.load(file)
    return {
        start.upper(): {end.upper(): int(m) for end, m in row.items()}
        for start, row in data.items()
    }


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Meeting:
    """One weekly class meeting, either fixed or from a candidate bundle."""

    course_code: str
    section: str
    day: str
    start: int
    end: int
    location: str = ""
    building: str = ""
    fixed: bool = False

    @property
    def label(self) -> str:
        return f"{self.course_code} {self.section}"


@dataclass(frozen=True)
class CourseOption:
    """A complete registration bundle for one course."""

    course_code: str
    title: str
    credits: int
    section_codes: tuple[str, ...]
    sections: tuple[PlannedSection, ...]
    meetings: tuple[Meeting, ...]
    unscheduled_sections: tuple[str, ...] = ()

    @property
    def days(self) -> frozenset[str]:
        return frozenset(meeting.day for meeting in self.meetings)

    @property
    def label(self) -> str:
        return f"{self.course_code} " + "+".join(self.section_codes)


@dataclass(frozen=True)
class PlanOptions:
    """Settings for :func:`generate_course_plans`.

    ``required_sections`` maps a course code to section codes that must be in
    its bundle, e.g. ``{"CS2311": ("C01",)}``. ``bundle_definitions`` lets you
    list complete bundles yourself, e.g. ``{"GE1102": [["C01", "T01"]]}``.
    """

    required_courses: tuple[str, ...] = ()
    required_sections: Mapping[str, Sequence[str]] = field(default_factory=dict)
    exclude_courses: tuple[str, ...] = ()
    min_courses: int = 1
    max_courses: int | None = None
    min_credits: int | None = None
    max_credits: int | None = None
    target_credits: int | None = None
    preferred_days: tuple[str, ...] = ()
    avoid_days: tuple[str, ...] = ()
    earliest_start: str | None = None
    latest_end: str | None = None
    min_gap: int = 0
    lunch_minutes: int = 0
    lunch_window: tuple[str, str] = ("11:30", "14:30")
    max_daily_hours: float | None = None
    check_travel: bool = True
    early_class_before: str = "09:00"
    late_class_after: str = "19:00"
    max_results: int = 10
    search_limit: int = 200_000
    bundle_definitions: Mapping[str, Sequence[Sequence[str]]] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class PlanScore:
    """Numbers used to rank plans. Lower ``rank_key`` is better."""

    total_credits: int
    days_on_campus: int
    non_preferred_meetings: int
    idle_minutes: int
    early_classes: int
    late_classes: int
    latest_finish: int


@dataclass(frozen=True)
class CoursePlan:
    chosen: tuple[CourseOption, ...]
    fixed_meetings: tuple[Meeting, ...]
    fixed_credits: int
    skipped_courses: tuple[str, ...]
    score: PlanScore

    @property
    def total_credits(self) -> int:
        return self.score.total_credits

    @property
    def new_credits(self) -> int:
        return sum(option.credits for option in self.chosen)

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

    def explain(self) -> str:
        s = self.score
        parts = [
            f"{s.total_credits} credits",
            f"{s.days_on_campus} day(s) on campus",
            f"{s.idle_minutes} min waiting between classes",
        ]
        if s.non_preferred_meetings:
            parts.append(f"{s.non_preferred_meetings} class(es) on non-preferred days")
        if s.early_classes:
            parts.append(f"{s.early_classes} early class(es)")
        if s.late_classes:
            parts.append(f"{s.late_classes} late class(es)")
        if self.skipped_courses:
            parts.append("leaves out " + ", ".join(self.skipped_courses))
        return "; ".join(parts)

    def to_sessions(self, include_fixed: bool = True) -> list[dict[str, str]]:
        """Convert to the session dictionaries used by ``timetable`` and
        ``calendar_export``."""
        titles = {o.course_code: o.title for o in self.chosen}
        sessions = []
        for meeting in self.meetings:
            if meeting.fixed and not include_fixed:
                continue
            building, _, room = meeting.location.partition(" ")
            title = titles.get(meeting.course_code, "")
            sessions.append({
                "course_code": meeting.course_code,
                "course_title": title,
                "crn": "",
                "section": meeting.section,
                "type": meeting.section,
                "day": meeting.day,
                "start_time": format_minutes(meeting.start),
                "end_time": format_minutes(meeting.end),
                "building": building,
                "room": room,
                "summary": (
                    f"{meeting.course_code} {meeting.section}"
                    + (f" - {title}" if title else "")
                ),
            })
        return sessions


@dataclass
class PlanReport:
    """Result of a search: the best plans plus diagnostics."""

    plans: list[CoursePlan]
    explored: int = 0
    truncated: bool = False
    rejections: Counter = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)

    def __iter__(self):
        return iter(self.plans)

    def __len__(self) -> int:
        return len(self.plans)

    def explain_no_plans(self) -> str:
        if self.plans:
            return ""
        lines = ["No plan satisfies all settings."]
        reasons = {
            "clash": "classes clash",
            "avoid_day": "uses an avoided day",
            "time_window": "outside the allowed start/end time",
            "min_gap": "gap between classes too short",
            "travel": "not enough time to walk between buildings",
            "lunch": "no lunch break",
            "daily_hours": "too many hours in one day",
            "max_credits": "over the credit limit",
            "max_courses": "over the course limit",
            "min_credits": "not enough credits",
            "min_courses": "too few courses",
            "required_section": "does not include a required section",
        }
        for key, count in self.rejections.most_common():
            lines.append(f"  {count:>6} option(s) rejected: {reasons.get(key, key)}")
        if self.truncated:
            lines.append("  Search stopped early; raise search_limit or narrow the course list.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Building bundles
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"([A-Z])([A-Z]*)(\d+)")


def _activity_and_family(section_code: str) -> tuple[str, str]:
    """``C01`` -> (``C``, ``""``); ``LA1`` -> (``L``, ``A``)."""
    match = _SECTION_RE.fullmatch(section_code.upper())
    if not match:
        return section_code.upper(), ""
    return match.group(1), match.group(2)


def build_course_options(
    course: CatalogCourse,
    bundle_definitions: Sequence[Sequence[str]] | None = None,
    known_buildings: Iterable[str] = (),
) -> list[CourseOption]:
    """Return every complete registration bundle for ``course``.

    Without ``bundle_definitions`` a bundle contains one section of each
    activity type found in the course (for example C, T and L), all taken
    from the same section family. This matches the rule in
    ``ParsedAimsTable.registration_bundles``.
    """
    known_buildings = tuple(known_buildings)
    planned = catalogue_to_planned_sections([course])
    by_section: dict[str, list[PlannedSection]] = {}
    for section in planned:
        by_section.setdefault(section.section.upper(), []).append(section)

    if bundle_definitions:
        combos = []
        for definition in bundle_definitions:
            codes = tuple(dict.fromkeys(c.strip().upper() for c in definition if c.strip()))
            missing = [c for c in codes if c not in by_section]
            if missing:
                raise ValueError(
                    f"Unknown sections for {course.code}: {', '.join(missing)}"
                )
            if codes:
                combos.append(codes)
    else:
        activities = sorted({_activity_and_family(code)[0] for code in by_section})
        families: dict[str, dict[str, list[str]]] = {}
        for code in sorted(by_section):
            activity, family = _activity_and_family(code)
            families.setdefault(family, {}).setdefault(activity, []).append(code)
        combos = []
        for family_sections in families.values():
            choices = [family_sections.get(activity, []) for activity in activities]
            if all(choices):
                combos.extend(product(*choices))

    options = []
    for codes in dict.fromkeys(tuple(c) for c in combos):
        sections = tuple(s for code in codes for s in by_section[code])
        meetings = []
        unscheduled = []
        for section in sections:
            if not (section.day and section.start and section.end):
                unscheduled.append(section.section)
                continue
            if parse_time(section.end) <= parse_time(section.start):
                raise ValueError(
                    f"{course.code} {section.section} on {section.day} "
                    f"ends before it starts ({section.start}-{section.end})"
                )
            meetings.append(Meeting(
                course_code=course.code.upper(),
                section=section.section,
                day=normalize_day(section.day),
                start=parse_time(section.start),
                end=parse_time(section.end),
                location=section.location,
                building=building_code(section.location, known_buildings),
            ))
        options.append(CourseOption(
            course_code=course.code.upper(),
            title=course.title,
            credits=int(course.credits),
            section_codes=codes,
            sections=sections,
            meetings=tuple(meetings),
            unscheduled_sections=tuple(unscheduled),
        ))
    return options


def fixed_meetings_from_sessions(
    sessions: Iterable[Mapping[str, str]],
    known_buildings: Iterable[str] = (),
) -> tuple[list[Meeting], list[str]]:
    """Convert AIMS/CSV session dictionaries to fixed meetings.

    Returns the meetings plus labels of sessions without a fixed time.
    """
    known_buildings = tuple(known_buildings)
    meetings, unscheduled = [], []
    for session in sessions:
        code = str(session.get("course_code", "")).upper()
        section = str(session.get("section", ""))
        if not (session.get("day") and session.get("start_time") and session.get("end_time")):
            unscheduled.append(f"{code} {section}".strip())
            continue
        location = " ".join(
            part for part in (session.get("building", ""), session.get("room", "")) if part
        )
        meetings.append(Meeting(
            course_code=code,
            section=section,
            day=normalize_day(session["day"]),
            start=parse_time(session["start_time"]),
            end=parse_time(session["end_time"]),
            location=location,
            building=building_code(location, known_buildings),
            fixed=True,
        ))
    return meetings, unscheduled


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class _Rules:
    def __init__(self, options: PlanOptions, travel: Mapping[str, Mapping[str, int]]):
        self.avoid = normalize_days(options.avoid_days)
        self.prefer = normalize_days(options.preferred_days)
        self.earliest = parse_time(options.earliest_start) if options.earliest_start else None
        self.latest = parse_time(options.latest_end) if options.latest_end else None
        self.min_gap = max(0, options.min_gap)
        self.lunch = max(0, options.lunch_minutes)
        self.lunch_start = parse_time(options.lunch_window[0])
        self.lunch_end = parse_time(options.lunch_window[1])
        self.max_daily = (
            int(options.max_daily_hours * 60) if options.max_daily_hours else None
        )
        self.travel = travel if options.check_travel else {}
        self.unknown_travel: set[str] = set()

    def walk_minutes(self, first: Meeting, second: Meeting) -> int | None:
        if not self.travel:
            return 0
        a, b = first.building, second.building
        if not a or not b:
            missing = first if not a else second
            if missing.location:
                self.unknown_travel.add(missing.location.split(" ", 1)[0])
            return None
        if a == b:
            return 0
        return self.travel.get(a, {}).get(b)

    def add(
        self,
        state: dict[str, tuple[Meeting, ...]],
        option: CourseOption,
    ) -> tuple[dict[str, tuple[Meeting, ...]] | None, str | None]:
        if option.days & self.avoid:
            return None, "avoid_day"
        new_state = dict(state)
        for meeting in option.meetings:
            if self.earliest is not None and meeting.start < self.earliest:
                return None, "time_window"
            if self.latest is not None and meeting.end > self.latest:
                return None, "time_window"
            day = new_state.get(meeting.day, ())
            if any(m.start < meeting.end and meeting.start < m.end for m in day):
                return None, "clash"
            day = tuple(sorted((*day, meeting), key=lambda m: (m.start, m.end)))
            position = day.index(meeting)
            neighbours = []
            if position > 0:
                neighbours.append((day[position - 1], meeting))
            if position + 1 < len(day):
                neighbours.append((meeting, day[position + 1]))
            for first, second in neighbours:
                gap = second.start - first.end
                if gap < self.min_gap:
                    return None, "min_gap"
                walk = self.walk_minutes(first, second)
                if walk is not None and walk > gap:
                    return None, "travel"
            new_state[meeting.day] = day

        for day_name in option.days:
            day = new_state[day_name]
            if (
                self.max_daily is not None
                and sum(m.end - m.start for m in day) > self.max_daily
            ):
                return None, "daily_hours"
            if self.lunch and not self._has_lunch(day):
                return None, "lunch"
        return new_state, None

    def _has_lunch(self, day: tuple[Meeting, ...]) -> bool:
        cursor = self.lunch_start
        for meeting in day:
            if meeting.end <= cursor:
                continue
            if meeting.start >= self.lunch_end:
                break
            if min(meeting.start, self.lunch_end) - cursor >= self.lunch:
                return True
            cursor = max(cursor, meeting.end)
        return self.lunch_end - cursor >= self.lunch


def _score(
    chosen: Sequence[CourseOption],
    state: Mapping[str, tuple[Meeting, ...]],
    total_credits: int,
    rules: _Rules,
    early_before: int,
    late_after: int,
) -> PlanScore:
    idle = 0
    latest = 0
    for day in state.values():
        for first, second in pairwise(day):
            idle += max(0, second.start - first.end)
        if day:
            latest = max(latest, day[-1].end)
    new_meetings = [m for option in chosen for m in option.meetings]
    non_preferred = (
        sum(1 for m in new_meetings if m.day not in rules.prefer)
        if rules.prefer else 0
    )
    return PlanScore(
        total_credits=total_credits,
        days_on_campus=sum(1 for day in state.values() if day),
        non_preferred_meetings=non_preferred,
        idle_minutes=idle,
        early_classes=sum(1 for m in new_meetings if m.start < early_before),
        late_classes=sum(1 for m in new_meetings if m.end > late_after),
        latest_finish=latest,
    )


def _rank_key(plan: CoursePlan, target: int | None) -> tuple:
    s = plan.score
    credit_key = abs(s.total_credits - target) if target is not None else -s.total_credits
    return (
        credit_key,
        s.non_preferred_meetings,
        s.days_on_campus,
        s.idle_minutes,
        s.early_classes + s.late_classes,
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
) -> PlanReport:
    """Search for the best clash-free plans.

    Parameters
    ----------
    courses:
        Candidate courses with their sections (from ``load_course_catalog``).
        Every course not listed in ``required_courses`` is optional.
    options:
        Search and ranking settings, see :class:`PlanOptions`.
    fixed_sessions:
        Sessions already in the student's timetable, e.g. from
        ``load_aims_html``. New classes must fit around them.
    credit_courses:
        Credit catalogue used to count the fixed timetable's credits,
        e.g. ``load_credit_catalogs()``.
    travel_times:
        Walking-time matrix. Loaded from ``data/travel_time.json`` when
        omitted and ``options.check_travel`` is true.
    """
    options = options or PlanOptions()
    if options.max_results < 1:
        raise ValueError("max_results must be at least 1")
    if (
        options.min_credits is not None
        and options.max_credits is not None
        and options.min_credits > options.max_credits
    ):
        raise ValueError("min_credits cannot be greater than max_credits")

    if travel_times is None and options.check_travel:
        try:
            travel_times = load_travel_times()
        except OSError:
            travel_times = {}
    travel_times = travel_times or {}
    known_buildings = set(travel_times)
    for row in travel_times.values():
        known_buildings.update(row)

    report = PlanReport(plans=[])
    rules = _Rules(options, travel_times)

    # Fixed timetable ----------------------------------------------------
    fixed, unscheduled = fixed_meetings_from_sessions(fixed_sessions, known_buildings)
    if unscheduled:
        report.warnings.append(
            "No fixed time (not checked for clashes): " + ", ".join(sorted(set(unscheduled)))
        )
    state: dict[str, tuple[Meeting, ...]] = {}
    for meeting in fixed:
        state[meeting.day] = tuple(sorted(
            (*state.get(meeting.day, ()), meeting), key=lambda m: (m.start, m.end)
        ))
    fixed_codes = {m.course_code for m in fixed} | {
        u.split(" ", 1)[0] for u in unscheduled if u
    }
    credit_lookup = {c.code.upper(): int(c.credits) for c in (*credit_courses, *courses)}
    fixed_credits = 0
    unknown_fixed = []
    for code in sorted(fixed_codes):
        if code in credit_lookup:
            fixed_credits += credit_lookup[code]
        else:
            unknown_fixed.append(code)
    if unknown_fixed:
        report.warnings.append(
            "Credits unknown for fixed courses (counted as 0): " + ", ".join(unknown_fixed)
        )

    # Candidate courses -------------------------------------------------
    excluded = {c.upper() for c in options.exclude_courses}
    required = {c.upper() for c in options.required_courses}
    required_sections = {
        code.upper(): {s.upper() for s in sections}
        for code, sections in options.required_sections.items()
    }
    required |= set(required_sections)
    bundle_definitions = {k.upper(): v for k, v in options.bundle_definitions.items()}

    catalogue = {}
    for course in courses:
        code = course.code.upper()
        if code in excluded:
            continue
        if code in fixed_codes:
            report.warnings.append(f"{code} is already in your timetable; skipped")
            continue
        catalogue.setdefault(code, course)

    missing_required = sorted(required - set(catalogue))
    if missing_required:
        raise ValueError(
            "Required course(s) not available in the catalogue: "
            + ", ".join(missing_required)
        )

    options_by_course: dict[str, list[CourseOption]] = {}
    for code, course in catalogue.items():
        course_options = build_course_options(
            course, bundle_definitions.get(code), known_buildings
        )
        wanted = required_sections.get(code)
        if wanted:
            unknown = wanted - {s.section.upper() for s in course.sections}
            if unknown:
                raise ValueError(
                    f"Unknown required section(s) for {code}: {', '.join(sorted(unknown))}"
                )
            kept = [o for o in course_options if wanted <= set(o.section_codes)]
            report.rejections["required_section"] += len(course_options) - len(kept)
            course_options = kept
        for option in course_options:
            if option.unscheduled_sections:
                report.warnings.append(
                    f"{option.course_code} {', '.join(option.unscheduled_sections)} "
                    "has no fixed time and is not checked for clashes"
                )
        if not course_options and code in required:
            report.warnings.append(f"{code} has no complete section bundle")
        options_by_course[code] = course_options
    report.warnings = list(dict.fromkeys(report.warnings))

    # Required courses first, then the most constrained courses first.
    order = sorted(
        options_by_course,
        key=lambda c: (c not in required, len(options_by_course[c]), c),
    )
    max_credit_by_course = {
        c: max((o.credits for o in options_by_course[c]), default=0) for c in order
    }
    remaining_credits = [0] * (len(order) + 1)
    for index in range(len(order) - 1, -1, -1):
        remaining_credits[index] = (
            remaining_credits[index + 1] + max_credit_by_course[order[index]]
        )

    early_before = parse_time(options.early_class_before)
    late_after = parse_time(options.late_class_after)
    keep = max(options.max_results * 4, 50)
    plans: list[CoursePlan] = []
    # Sorted rank keys of the best ``max_results`` plans so far. The first
    # three parts of a key (credits, non-preferred classes, days on campus)
    # can only get worse as classes are added, so a branch whose best
    # possible start is already worse than the last kept plan is skipped.
    top_keys: list[tuple] = []
    credit_cap = options.max_credits if options.max_credits is not None else 10**9
    target = options.target_credits

    def record(chosen: list[CourseOption], current: dict, credits: int) -> None:
        total = fixed_credits + credits
        if options.min_credits is not None and total < options.min_credits:
            report.rejections["min_credits"] += 1
            return
        if len(chosen) < options.min_courses:
            report.rejections["min_courses"] += 1
            return
        chosen_codes = {o.course_code for o in chosen}
        plan = CoursePlan(
            chosen=tuple(chosen),
            fixed_meetings=tuple(fixed),
            fixed_credits=fixed_credits,
            skipped_courses=tuple(c for c in order if c not in chosen_codes),
            score=_score(chosen, current, total, rules, early_before, late_after),
        )
        plans.append(plan)
        key = _rank_key(plan, target)
        if len(top_keys) < options.max_results or key < top_keys[-1]:
            bisect.insort(top_keys, key)
            del top_keys[options.max_results:]
        if len(plans) > keep * 2:
            plans.sort(key=lambda p: _rank_key(p, target))
            del plans[keep:]

    def lower_bound(index: int, credits: int, non_preferred: int, current: dict) -> tuple:
        low = fixed_credits + credits
        high = min(credit_cap, low + remaining_credits[index])
        if target is None:
            credit_key = -high
        elif low <= target <= high:
            credit_key = 0
        else:
            credit_key = min(abs(low - target), abs(high - target))
        days = sum(1 for day in current.values() if day)
        return (credit_key, non_preferred, days)

    def search(
        index: int,
        chosen: list[CourseOption],
        current: dict,
        credits: int,
        non_preferred: int,
    ) -> None:
        if report.explored >= options.search_limit:
            report.truncated = True
            return
        report.explored += 1

        if index == len(order):
            record(chosen, current, credits)
            return

        if (
            options.min_credits is not None
            and fixed_credits + credits + remaining_credits[index] < options.min_credits
        ):
            report.rejections["min_credits"] += 1
            return

        if (
            len(top_keys) >= options.max_results
            and lower_bound(index, credits, non_preferred, current) > top_keys[-1][:3]
        ):
            report.rejections["bound"] += 1
            return

        code = order[index]
        is_required = code in required
        at_course_limit = (
            options.max_courses is not None and len(chosen) >= options.max_courses
        )

        if at_course_limit:
            if is_required:
                report.rejections["max_courses"] += 1
                return
        else:
            for option in options_by_course[code]:
                if (
                    options.max_credits is not None
                    and fixed_credits + credits + option.credits > options.max_credits
                ):
                    report.rejections["max_credits"] += 1
                    continue
                new_state, reason = rules.add(current, option)
                if reason:
                    report.rejections[reason] += 1
                    continue
                extra = (
                    sum(1 for m in option.meetings if m.day not in rules.prefer)
                    if rules.prefer else 0
                )
                search(
                    index + 1,
                    [*chosen, option],
                    new_state,
                    credits + option.credits,
                    non_preferred + extra,
                )

        if not is_required:
            search(index + 1, chosen, current, credits, non_preferred)

    search(0, [], state, 0, 0)

    plans.sort(key=lambda p: _rank_key(p, target))
    report.plans = plans[: options.max_results]
    if rules.unknown_travel:
        report.warnings.append(
            "Walking time unknown for building(s) "
            + ", ".join(sorted(rules.unknown_travel))
            + "; those transfers were not checked"
        )
    return report


# ---------------------------------------------------------------------------
# Display and command line
# ---------------------------------------------------------------------------


def format_plan(plan: CoursePlan, number: int | None = None) -> str:
    title = f"Plan {number}" if number is not None else "Plan"
    lines = [f"{title}: {plan.explain()}"]
    for option in plan.chosen:
        lines.append(
            f"  {option.course_code} {'+'.join(option.section_codes)}"
            f"  ({option.credits} cr)  {option.title}"
        )
    current_day = None
    for meeting in plan.meetings:
        if meeting.day != current_day:
            current_day = meeting.day
            lines.append(f"  {meeting.day}")
        marker = "  (fixed)" if meeting.fixed else ""
        lines.append(
            f"    {format_minutes(meeting.start)}-{format_minutes(meeting.end)}  "
            f"{meeting.label:<14} {meeting.location}{marker}"
        )
    return "\n".join(lines)


def _parse_required_sections(values: Sequence[str] | None) -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for value in values or ():
        code, _, sections = value.partition(":")
        if not code or not sections:
            raise argparse.ArgumentTypeError(
                f"Use COURSE:SECTION[,SECTION], e.g. CS2311:C01 (got {value!r})"
            )
        result.setdefault(code.upper(), []).extend(
            s.strip().upper() for s in sections.split(",") if s.strip()
        )
    return {code: tuple(sections) for code, sections in result.items()}


DEFAULT_SEMESTER_START = "2026-08-31"
DEFAULT_SEMESTER_END = "2026-11-28"


def export_plan(
    plan: CoursePlan,
    output: str | Path,
    semester_start: str,
    semester_end: str,
    exclusions_path: str | None = None,
) -> Path:
    """Write ``plan`` (including any fixed AIMS classes) to an .ics file."""
    from .calendar_export import export_ics

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    export_ics(
        plan.to_sessions(),
        str(output),
        semester_start,
        semester_end,
        exclusions_path=exclusions_path,
    )
    return output


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _ask_to_export(plans: Sequence[CoursePlan], args: argparse.Namespace) -> None:
    choice = _ask(
        f"Export a plan to .ics? Enter 1-{len(plans)}, or press Enter to skip: "
    )
    if not choice:
        return
    if not choice.isdigit() or not 1 <= int(choice) <= len(plans):
        print(f"Skipped export: {choice!r} is not a plan number.")
        return
    output = _ask(f"Output .ics path [{args.output}]: ") or args.output
    start = _ask(f"Semester start [{args.semester_start}]: ") or args.semester_start
    end = _ask(f"Semester end [{args.semester_end}]: ") or args.semester_end
    path = export_plan(plans[int(choice) - 1], output, start, end, args.exclusions)
    print(f"Exported plan {choice} to {path}")


def main(
    argv: Sequence[str] | None = None,
    prog: str = "python -m cityuschedule.plan_generator",
    parser_class: type[argparse.ArgumentParser] = argparse.ArgumentParser,
) -> int:
    parser = parser_class(
        prog=prog,
        description=(
            "Generate ranked, clash-free course plans from a timetable "
            "catalogue, optionally around a saved AIMS timetable."
        ),
    )
    parser.add_argument("catalog", nargs="+", help="Timetable catalogue JSON file(s)")
    parser.add_argument("--aims-html", help="Saved AIMS weekly timetable to plan around")
    parser.add_argument("--required", nargs="+", default=[], metavar="CODE")
    parser.add_argument("--require-section", nargs="+", default=[], metavar="CODE:SEC")
    parser.add_argument("--exclude", nargs="+", default=[], metavar="CODE")
    parser.add_argument("--min-courses", type=int, default=1)
    parser.add_argument("--max-courses", type=int)
    parser.add_argument("--min-credits", type=int)
    parser.add_argument("--max-credits", type=int)
    parser.add_argument("--target-credits", type=int)
    parser.add_argument("--prefer-days", nargs="+", default=[])
    parser.add_argument("--avoid-days", nargs="+", default=[])
    parser.add_argument("--earliest", help="Earliest class start, e.g. 09:00")
    parser.add_argument("--latest", help="Latest class end, e.g. 18:00")
    parser.add_argument("--min-gap", type=int, default=0, help="Minutes between classes")
    parser.add_argument("--lunch", type=int, default=0, help="Lunch break minutes (11:30-14:30)")
    parser.add_argument("--max-daily-hours", type=float)
    parser.add_argument("--no-travel-check", action="store_true")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--export", type=int, metavar="N", help="Export plan N as .ics")
    parser.add_argument(
        "--ask-export", action="store_true",
        help="After listing plans, ask which one to export",
    )
    parser.add_argument("--output", default="cityu_plan.ics")
    parser.add_argument(
        "--semester-start", default=DEFAULT_SEMESTER_START,
        help="First teaching day, YYYY-MM-DD",
    )
    parser.add_argument(
        "--semester-end", default=DEFAULT_SEMESTER_END,
        help="Last teaching day, YYYY-MM-DD",
    )
    parser.add_argument("--exclusions", help="Holidays and breaks JSON file")
    args = parser.parse_args(argv)

    try:
        courses = [c for path in args.catalog for c in load_course_catalog(path)]
        fixed_sessions = []
        credit_courses = []
        if args.aims_html:
            from .aims import load_aims_html
            from .course_catalog import load_credit_catalogs

            fixed_sessions = load_aims_html(args.aims_html)
            credit_courses = load_credit_catalogs()
        options = PlanOptions(
            required_courses=tuple(args.required),
            required_sections=_parse_required_sections(args.require_section),
            exclude_courses=tuple(args.exclude),
            min_courses=args.min_courses,
            max_courses=args.max_courses,
            min_credits=args.min_credits,
            max_credits=args.max_credits,
            target_credits=args.target_credits,
            preferred_days=tuple(args.prefer_days),
            avoid_days=tuple(args.avoid_days),
            earliest_start=args.earliest,
            latest_end=args.latest,
            min_gap=args.min_gap,
            lunch_minutes=args.lunch,
            max_daily_hours=args.max_daily_hours,
            check_travel=not args.no_travel_check,
            max_results=args.max_results,
        )
        report = generate_course_plans(
            courses,
            options,
            fixed_sessions=fixed_sessions,
            credit_courses=credit_courses,
        )
    except (OSError, ValueError, argparse.ArgumentTypeError) as error:
        parser.error(str(error))

    for warning in report.warnings:
        print(f"Note: {warning}")
    if not report.plans:
        print(report.explain_no_plans())
        return 1

    print(f"Found {len(report.plans)} plan(s) (checked {report.explored} combinations):\n")
    for number, plan in enumerate(report.plans, start=1):
        print(format_plan(plan, number))
        print()

    try:
        if args.export:
            if not 1 <= args.export <= len(report.plans):
                parser.error(f"--export must be between 1 and {len(report.plans)}")
            path = export_plan(
                report.plans[args.export - 1],
                args.output,
                args.semester_start,
                args.semester_end,
                args.exclusions,
            )
            print(f"Exported plan {args.export} to {path}")
        elif args.ask_export:
            _ask_to_export(report.plans, args)
    except (OSError, ValueError) as error:
        parser.error(f"Could not export plan: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
