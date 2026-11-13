from cityuschedule.timetable import format_timetable


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


def test_formats_sessions_by_day():
    sessions = [
        make_session("Tue", "11:00", "12:50", "MA1200"),
        make_session("Mon", "09:00", "10:50", "CS1103"),
    ]

    output = format_timetable(sessions)

    assert "Weekly timetable" in output
    assert "Mon" in output
    assert "Tue" in output
    assert "CS1103" in output
    assert "MA1200" in output


def test_sorts_sessions_by_start_time():
    sessions = [
        make_session("Mon", "11:00", "12:50", "MA1200"),
        make_session("Mon", "09:00", "10:50", "CS1103"),
    ]

    output = format_timetable(sessions)
    lines = output.splitlines()

    cs_index = next(
        index for index, line in enumerate(lines) if "CS1103" in line
    )
    ma_index = next(
        index for index, line in enumerate(lines) if "MA1200" in line
    )

    assert cs_index < ma_index