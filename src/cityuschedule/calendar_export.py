from datetime import date, datetime, timedelta
from pathlib import Path

from icalendar import Calendar, Event


WEEKDAY_NUMBERS = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}


def export_ics(
    sessions: list[dict[str, str]],
    output_path: str,
    semester_start: str,
    semester_end: str,
) -> str:
    start_date = date.fromisoformat(semester_start)
    end_date = date.fromisoformat(semester_end)

    calendar = Calendar()
    calendar.add("prodid", "-//cityuschedule//EN")
    calendar.add("version", "2.0")

    for index, session in enumerate(sessions, start=1):
        weekday = WEEKDAY_NUMBERS[session["day"]]
        first_class_date = start_date + timedelta(
            days=(weekday - start_date.weekday()) % 7
        )

        start_time = datetime.strptime(session["start_time"], "%H:%M").time()
        end_time = datetime.strptime(session["end_time"], "%H:%M").time()

        event = Event()
        event.add(
            "uid",
            f"cityuschedule-{index}-{session['course_code']}-{session['section']}"
            "@cityuschedule",
        )
        event.add("summary", f"{session['course_code']} {session['type']}")
        event.add(
            "location",
            f"{session['building']} {session['room']}",
        )
        event.add(
            "dtstart",
            datetime.combine(first_class_date, start_time),
        )
        event.add(
            "dtend",
            datetime.combine(first_class_date, end_time),
        )
        event.add(
            "rrule",
            {
                "freq": "weekly",
                "until": datetime.combine(end_date, end_time),
            },
        )

        calendar.add_component(event)

    output = Path(output_path)
    output.write_bytes(calendar.to_ical())

    return str(output)