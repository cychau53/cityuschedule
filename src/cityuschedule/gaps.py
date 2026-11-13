from datetime import datetime


def find_gaps(
    sessions: list[dict[str, str]],
    minimum_minutes: int = 45,
) -> list[dict[str, str]]:
    gaps = []
    sessions_by_day = {}

    for session in sessions:
        sessions_by_day.setdefault(session["day"], []).append(session)

    for day, day_sessions in sessions_by_day.items():
        day_sessions.sort(key=lambda session: session["start_time"])

        for first, second in zip(day_sessions, day_sessions[1:]):
            first_end = datetime.strptime(first["end_time"], "%H:%M")
            second_start = datetime.strptime(second["start_time"], "%H:%M")
            gap_minutes = int((second_start - first_end).total_seconds() / 60)

            if gap_minutes >= minimum_minutes:
                gaps.append(
                    {
                        "day": day,
                        "start_time": first["end_time"],
                        "end_time": second["start_time"],
                        "minutes": str(gap_minutes),
                    }
                )

    return gaps


def format_gaps(gaps: list[dict[str, str]]) -> str:
    if not gaps:
        return "No free gaps of at least 45 minutes found."

    lines = ["Free gaps"]

    for gap in gaps:
        lines.append(
            f"  {gap['day']} {gap['start_time']}-{gap['end_time']} "
            f"({gap['minutes']} minutes)"
        )

    return "\n".join(lines)