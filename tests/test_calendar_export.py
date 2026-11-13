from pathlib import Path

from cityuschedule.calendar_export import export_ics


def make_session(day: str, start_time: str, end_time: str, course_code: str):
    return {
        "course_code": course_code,
        "course_title": "Test course",
        "crn": "12345",
        "section": "A",
        "type": "LEC",
        "day": day,
        "start_time": start_time,
        "end_time": end_time,
        "building": "AC",
        "room": "LT-1",
    }


def test_exports_ics_file(tmp_path):
    sessions = [
        make_session("Mon", "09:00", "10:50", "CS1103"),
        make_session("Tue", "11:00", "12:50", "MA1200"),
    ]

    output_path = tmp_path / "timetable.ics"

    result = export_ics(
        sessions,
        str(output_path),
        "2026-08-31",
        "2026-11-28",
    )

    file = Path(result)

    assert file.exists()
    assert file.stat().st_size > 0

    content = file.read_text(encoding="utf-8")

    assert "BEGIN:VCALENDAR" in content
    assert "BEGIN:VEVENT" in content
    assert "CS1103" in content
    assert "MA1200" in content


def test_exported_events_use_hong_kong_timezone(tmp_path):
    sessions = [
        make_session("Mon", "09:00", "10:50", "CS1103"),
    ]

    output_path = tmp_path / "timezone.ics"

    export_ics(
        sessions,
        str(output_path),
        "2026-08-31",
        "2026-11-28",
    )

    content = output_path.read_text(encoding="utf-8")

    assert "DTSTART;TZID=Asia/Hong_Kong" in content
    assert "DTEND;TZID=Asia/Hong_Kong" in content
    assert "UNTIL=20261128T025000Z" in content