from cityuschedule.gaps import find_gaps, format_gaps


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


def test_finds_gap_of_70_minutes():
    sessions = [
        make_session("Mon", "09:00", "10:50", "CS1103"),
        make_session("Mon", "12:00", "13:50", "MA1200"),
    ]

    gaps = find_gaps(sessions)

    assert len(gaps) == 1
    assert gaps[0]["minutes"] == "70"
    assert gaps[0]["start_time"] == "10:50"
    assert gaps[0]["end_time"] == "12:00"


def test_ignores_short_gap():
    sessions = [
        make_session("Mon", "09:00", "10:50", "CS1103"),
        make_session("Mon", "11:00", "12:50", "MA1200"),
    ]

    gaps = find_gaps(sessions, minimum_minutes=45)

    assert gaps == []


def test_formats_no_gaps():
    output = format_gaps([])

    assert output == "No free gaps of at least 45 minutes found."