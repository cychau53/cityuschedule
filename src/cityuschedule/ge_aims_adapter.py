from __future__ import annotations

from .aims_table_parser import AIMSSession, AIMSTable


def convert_ge_records_to_aims_table(
    course_code: str,
    records: list[dict],
) -> AIMSTable:
    """Convert GE importer records into an AIMS-compatible table."""
    sessions = []

    for record in records:
        start_time, end_time = _split_time(record.get("time", ""))

        sessions.append(
            AIMSSession(
                crn=record.get("crn", ""),
                section=record.get("section", ""),
                day=record.get("day", ""),
                start_time=start_time,
                end_time=end_time,
                type=record.get("type", ""),
                building=record.get("building", ""),
                room=record.get("room", ""),
                instructor=record.get("instructor", ""),
            )
        )

    return AIMSTable(
        course_code=course_code.upper(),
        course_credit=3,
        sessions=sessions,
    )


def _split_time(time_text: str) -> tuple[str, str]:
    time_text = (time_text or "").strip()

    if not time_text:
        return "", ""

    parts = time_text.split("-")

    if len(parts) != 2:
        raise ValueError(
            f"Unrecognized GE meeting time: {time_text!r}."
        )

    return parts[0].strip(), parts[1].strip()
