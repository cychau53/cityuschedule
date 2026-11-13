import json
from datetime import date, datetime, timedelta
from pathlib import Path
from datetime import timezone
from icalendar import Calendar, Event
from zoneinfo import ZoneInfo
DEFAULT_TIMEZONE = "Asia/Hong_Kong"


WEEKDAY_NUMBERS = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}

def is_excluded(
    day: date,
    holidays: set[date],
    breaks: list[tuple[date, date]],
) -> bool:
    if day in holidays:
        return True

    return any(start <= day <= end for start, end in breaks)

def load_exclusions(path: str) -> tuple[set[date], list[tuple[date, date]]]:
    with open(path, encoding="utf-8") as file:
        data = json.load(file)

    holidays = {
        date.fromisoformat(value)
        for value in data.get("holidays", [])
    }

    breaks = [
        (
            date.fromisoformat(item["start"]),
            date.fromisoformat(item["end"]),
        )
        for item in data.get("breaks", [])
    ]

    return holidays, breaks

def export_ics(
    sessions: list[dict[str, str]],
    output_path: str,
    semester_start: str,
    semester_end: str,
    timezone_name: str = "Asia/Hong_Kong",
    exclusions_path: str | None = None,
) -> str:
    start_date = date.fromisoformat(semester_start)
    end_date = date.fromisoformat(semester_end)
    tz = ZoneInfo(timezone_name)

    if exclusions_path:
        holidays, breaks = load_exclusions(exclusions_path)
    else:
        holidays, breaks = set(), []

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
            datetime.combine(first_class_date, start_time, tzinfo=tz),
        )
        event.add(
            "dtend",
            datetime.combine(first_class_date, end_time, tzinfo=tz),
        )
        event.add(
            "rrule",
            {
                "freq": "weekly",
                "until": datetime.combine(
                    end_date,
                    end_time,
                    tzinfo=tz,
                ).astimezone(timezone.utc),
            },
        )

        calendar.add_component(event)

    output = Path(output_path)
    output.write_bytes(calendar.to_ical())

    return str(output)