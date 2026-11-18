from __future__ import annotations

from itertools import combinations

from .aims_table_parser import AimsSession, ParsedAimsTable

def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


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
) -> list[tuple[str, ...]]:
    """Keep complete bundles with no internal or base-timetable overlap."""
    sessions_by_section = {
        session.section: session
        for session in table.scheduled_sessions
    }

    fitting: list[tuple[str, ...]] = []

    for bundle in table.registration_bundles():
        selected = [
            sessions_by_section[section]
            for section in bundle
        ]

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

        fitting.append(bundle)

    return fitting

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
            )
        )

    return tuple(converted)

def _session_label(session: AimsSession) -> str:
    return (
        f"{session.course_code}-{session.section} "
        f"{session.day} {session.start_time}-{session.end_time}"
    )


def registration_bundle_conflicts(
    table: ParsedAimsTable,
    bundle: tuple[str, ...],
    base_sessions: tuple[AimsSession, ...],
) -> list[str]:
    """Explain internal and base-timetable overlaps for one bundle."""
    by_section = {
        session.section: session
        for session in table.scheduled_sessions
    }
    selected = [by_section[section] for section in bundle]
    reasons: list[str] = []

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

    return reasons