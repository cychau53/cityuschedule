from __future__ import annotations

from dataclasses import dataclass, field

from .aims_table_parser import AIMSSession, AIMSTable


def convert_ge_records_to_aims_table(
    course_code: str,
    records: list[dict],
) -> AIMSTable:
    """Convert GE importer records into an AIMS-compatible table."""
    sessions = []

    for record in records:
        start_time, end_time = _split_time(record["time"])

        sessions.append(
            AIMSSession(
                crn=record["crn"],
                section=record["section"],
                day=record["day"],
                start_time=start_time,
                end_time=end_time,
                type=record["type"],
                building=record["building"],
                room=record["room"],
                instructor=record["instructor"],
            )
        )

    return AIMSTable(
        course_code=course_code.upper(),
        course_credit=0,
        sessions=sessions,
    )


def _split_time(time_text: str) -> tuple[str, str]:
    parts = time_text.split("-")

    if len(parts) != 2:
        raise ValueError(
            f"Unrecognized GE meeting time: {time_text!r}."
        )

    return parts[0].strip(), parts[1].strip()
