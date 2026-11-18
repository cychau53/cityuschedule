from cityuschedule.aims_fit import (
    fitting_registration_bundles,
    sessions_overlap,
)
from cityuschedule.aims_table_parser import AimsSession, ParsedAimsTable


def make_session(section, day, start, end, course="TEST1001"):
    return AimsSession(
        course_code=course,
        crn="10001",
        section=section,
        credit=0,
        day=day,
        start_time=start,
        end_time=end,
    )


def test_overlapping_sessions():
    first = make_session("C01", "M", "09:00", "10:50")
    second = make_session("T01", "M", "10:00", "11:50")

    assert sessions_overlap(first, second)
    assert sessions_overlap(second, first)


def test_different_days_do_not_overlap():
    first = make_session("C01", "M", "09:00", "10:50")
    second = make_session("T01", "T", "09:00", "10:50")

    assert not sessions_overlap(first, second)


def test_back_to_back_sessions_do_not_overlap():
    first = make_session("C01", "M", "09:00", "10:00")
    second = make_session("T01", "M", "10:00", "11:00")

    assert not sessions_overlap(first, second)


def test_unscheduled_session_is_ignored():
    admin = make_session("A01", None, None, None)
    lecture = make_session("C01", "M", "09:00", "10:50")

    assert not sessions_overlap(admin, lecture)


def test_keep_only_bundle_that_fits_base():
    table = ParsedAimsTable(
        course_code="TEST1001",
        sessions=(
            make_session("C01", "M", "09:00", "10:50"),
            make_session("T01", "M", "11:00", "11:50"),
            make_session("T02", "T", "11:00", "11:50"),
        ),
    )
    base = (
        make_session(
            "S01", "M", "11:00", "12:00", course="OTHER1001"
        ),
    )

    assert fitting_registration_bundles(table, base) == [
        ("C01", "T02"),
    ]


def test_reject_internally_conflicting_bundle():
    table = ParsedAimsTable(
        course_code="TEST1001",
        sessions=(
            make_session("C01", "M", "09:00", "10:50"),
            make_session("T01", "M", "10:00", "11:00"),
        ),
    )

    assert fitting_registration_bundles(table, ()) == []


def test_lecture_conflict_rejects_every_bundle():
    table = ParsedAimsTable(
        course_code="TEST1001",
        sessions=(
            make_session("C01", "M", "09:00", "10:50"),
            make_session("T01", "M", "11:00", "11:50"),
            make_session("T02", "T", "11:00", "11:50"),
        ),
    )
    base = (
        make_session(
            "S01", "M", "09:30", "10:00", course="OTHER1001"
        ),
    )

    assert fitting_registration_bundles(table, base) == []

def test_convert_aims_sessions_maps_days_and_skips_unscheduled():
    from cityuschedule.aims_fit import convert_aims_sessions

    day_pairs = [
        ("Mon", "M"),
        ("Tue", "T"),
        ("Wed", "W"),
        ("Thu", "R"),
        ("Fri", "F"),
        ("Sat", "S"),
        ("Sun", "U"),
    ]

    rows = [
        {
            "course_code": "BASE1001",
            "crn": str(20000 + index),
            "section": "C01",
            "day": day,
            "start_time": "09:00",
            "end_time": "10:50",
        }
        for index, (day, _) in enumerate(day_pairs)
    ]

    rows.append({
        "course_code": "GE1401",
        "crn": "",
        "section": "A01",
        "day": "",
        "start_time": "",
        "end_time": "",
    })

    converted = convert_aims_sessions(rows)

    assert len(converted) == 7
    assert [session.day for session in converted] == [
        code for _, code in day_pairs
    ]
    assert converted[0].course_code == "BASE1001"
    assert converted[0].crn == "20000"
    assert converted[0].start_time == "09:00"
    assert converted[0].end_time == "10:50"


def test_converted_base_sessions_work_with_fit_checker():
    from cityuschedule.aims_fit import convert_aims_sessions

    base = convert_aims_sessions([
        {
            "course_code": "BASE1001",
            "crn": "20001",
            "section": "C01",
            "day": "Wed",
            "start_time": "12:00",
            "end_time": "13:50",
        },
    ])

    table = ParsedAimsTable(
        course_code="TEST1001",
        sessions=(
            make_session("C01", "W", "12:30", "14:00"),
            make_session("T01", "W", "15:00", "15:50"),
        ),
    )

    assert fitting_registration_bundles(table, base) == []