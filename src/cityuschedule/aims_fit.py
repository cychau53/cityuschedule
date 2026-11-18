from __future__ import annotations

from itertools import combinations

from .aims_table_parser import AimsSession, ParsedAimsTable
from .travel_time import time as check_travel_time


DAY_NAMES = {
    "M": "Mon",
    "T": "Tue",
    "W": "Wed",
    "R": "Thu",
    "F": "Fri",
    "S": "Sat",
    "U": "Sun",
}


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _session_days(sessions: list[AimsSession]) -> set[str]:
    return {
        DAY_NAMES[session.day]
        for session in sessions
        if session.day is not None
    }


def bundle_preferred_day_count(
    table: ParsedAimsTable,
    bundle: tuple[str, ...],
    preferred_days: list[str] | None = None,
) -> int:
    sessions_by_section = {
        session.section: session
        for session in table.scheduled_sessions
    }
    preferred_days_set = {
        day.capitalize() for day in (preferred_days or [])
    }
    return len(
        _session_days(
            [sessions_by_section[section] for section in bundle]
        )
        & preferred_days_set
    )


def sessions_overlap(first: AimsSession, second: AimsSession) -> bool:
    """Check weekly time overlap; ignore unscheduled sessions."""
    if not first.is_scheduled or not second.is_scheduled:
        return False

    if first.day != second.day:
        return False

    assert first.start_time is not None
    assert first.end_time is not None
    assert second.start_time is not None
    assert second.end_time is not None

    return (
        _minutes(first.start_time) < _minutes(second.end_time)
        and _minutes(second.start_time) < _minutes(first.end_time)
    )


def fitting_registration_bundles(
    table: ParsedAimsTable,
    base_sessions: tuple[AimsSession, ...],
    preferred_days: list[str] | None = None,
    avoid_days: list[str] | None = None,
) -> list[tuple[str, ...]]:
    """Keep complete bundles that fit the base timetable and allow transfers."""
    sessions_by_section = {
        session.section: session
        for session in table.scheduled_sessions
    }

    preferred_days_set = {
        day.capitalize() for day in (preferred_days or [])
    }
    avoided_days = {
        day.capitalize() for day in (avoid_days or [])
    }
    fitting: list[tuple[tuple[str, ...], int]] = []

    for bundle in table.registration_bundles():
        selected = [
            sessions_by_section[section]
            for section in bundle
        ]
        bundle_days = _session_days(selected)

        if bundle_days & avoided_days:
            continue

        internal_conflict = any(
            sessions_overlap(first, second)
            for first, second in combinations(selected, 2)
        )
        if internal_conflict:
            continue

        base_conflict = any(
            sessions_overlap(candidate, existing)
            for candidate in selected
            for existing in base_sessions
        )
        if base_conflict:
            continue

        try:
            check_travel_time(
                [
                    _to_travel_session(session)
                    for session in (*base_sessions, *selected)
                ]
            )
        except ValueError:
            continue

        fitting.append(
            (bundle, len(bundle_days & preferred_days_set))
        )

    fitting.sort(key=lambda item: -item[1])
    return [bundle for bundle, _ in fitting]


def convert_aims_sessions(
    rows: list[dict[str, str]],
) -> tuple[AimsSession, ...]:
    """Convert existing AIMS reader output for weekly fit checking."""
    day_codes = {
        "Mon": "M",
        "Tue": "T",
        "Wed": "W",
        "Thu": "R",
        "Fri": "F",
        "Sat": "S",
        "Sun": "U",
    }

    converted: list[AimsSession] = []

    for row in rows:
        day = row.get("day", "").strip()
        start = row.get("start_time", "").strip()
        end = row.get("end_time", "").strip()

        # Unscheduled entries do not block timetable slots.
        if not day or not start or not end:
            continue

        if day not in day_codes:
            raise ValueError(f"Unrecognized AIMS timetable day: {day!r}")

        converted.append(
            AimsSession(
                course_code=row["course_code"],
                crn=row.get("crn", ""),
                section=row["section"],
                # Credits are not needed for time-conflict checking.
                credit=0,
                day=day_codes[day],
                start_time=start,
                end_time=end,
                building=row.get("building", "").strip(),
            )
        )

    return tuple(converted)


def _session_label(session: AimsSession) -> str:
    return (
        f"{session.course_code}-{session.section} "
        f"{session.day} {session.start_time}-{session.end_time}"
    )


def _to_travel_session(session: AimsSession) -> dict[str, str]:
    assert session.day is not None
    assert session.start_time is not None
    assert session.end_time is not None

    return {
        "course_code": session.course_code,
        "section": session.section,
        "day": DAY_NAMES[session.day],
        "start_time": session.start_time,
        "end_time": session.end_time,
        "building": session.building,
    }


def registration_bundle_conflicts(
    table: ParsedAimsTable,
    bundle: tuple[str, ...],
    base_sessions: tuple[AimsSession, ...],
    avoid_days: list[str] | None = None,
) -> list[str]:
    """Explain timetable, day-preference, and travel rejection reasons."""
    by_section = {
        session.section: session
        for session in table.scheduled_sessions
    }
    selected = [by_section[section] for section in bundle]
    reasons: list[str] = []
    bundle_days = _session_days(selected)
    avoided_days = bundle_days & {
        day.capitalize() for day in (avoid_days or [])
    }

    if avoided_days:
        reasons.append(
            "Uses avoided day(s): " + ", ".join(sorted(avoided_days))
        )

    for first, second in combinations(selected, 2):
        if sessions_overlap(first, second):
            reasons.append(
                f"Internal overlap: {_session_label(first)} "
                f"overlaps {_session_label(second)}"
            )

    for candidate in selected:
        for existing in base_sessions:
            if sessions_overlap(candidate, existing):
                reasons.append(
                    f"Base timetable overlap: {_session_label(candidate)} "
                    f"overlaps {_session_label(existing)}"
                )

    if not any("overlap" in reason.lower() for reason in reasons):
        try:
            check_travel_time(
                [
                    _to_travel_session(session)
                    for session in (*base_sessions, *selected)
                ]
            )
        except ValueError as error:
            reasons.append(str(error))

    return reasons