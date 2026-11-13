from collections import defaultdict

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def format_timetable(sessions: list[dict[str, str]]) -> str:
    sessions_by_day = defaultdict(list)

    for session in sessions:
        sessions_by_day[session["day"]].append(session)

    lines = ["Weekly timetable", ""]

    for day in WEEKDAYS:
        day_sessions = sessions_by_day.get(day, [])

        if not day_sessions:
            continue

        lines.append(day)
        day_sessions.sort(key=lambda session: session["start_time"])

        for session in day_sessions:
            lines.append(
                f"  {session['start_time']}-{session['end_time']}  "
                f"{session['course_code']} {session['type']}  "
                f"{session['building']} {session['room']}"
            )

        lines.append("")

    return "\n".join(lines).rstrip()