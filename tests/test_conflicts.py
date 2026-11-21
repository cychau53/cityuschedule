from cityuschedule.conflicts import find_conflicts


def make_session(
    course_code: str,
    day: str,
    start_time: str,
    end_time: str,
    session_type: str = "LEC",
):
    return {
        "course_code": course_code,
        "course_title": "Test course",
        "crn": "12345",
        "section": "A",
        "type": session_type,
        "day": day,
        "start_time": start_time,
        "end_time": end_time,
        "building": "AC",
        "room": "LT-1",
    }


def test_detects_overlapping_sessions():
    first = make_session("CS1103", "Mon", "09:00", "10:50")
    second = make_session("MA1200", "Mon", "10:30", "11:20")

    conflicts = find_conflicts([first, second])

    assert len(conflicts) == 1
    assert conflicts[0] == (first, second)


def test_does_not_detect_non_overlapping_sessions():
    first = make_session("CS1103", "Mon", "09:00", "10:50")
    second = make_session("MA1200", "Mon", "11:00", "12:50")

    conflicts = find_conflicts([first, second])

    assert conflicts == []


def test_does_not_detect_conflicts_on_different_days():
    first = make_session("CS1103", "Mon", "09:00", "10:50")
    second = make_session("MA1200", "Tue", "09:00", "10:50")

    conflicts = find_conflicts([first, second])

    assert conflicts == []