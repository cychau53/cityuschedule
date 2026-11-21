from cityuschedule.ge_courses import get_ge_course_info, search_ge_courses


ADDED_COURSE_CODES = [
    "GE1356",
    "GE1357",
    "GE1358",
    "GE1359",
    "GE2129",
    "GE2134",
    "GE2135",
    "GE2136",
    "GE2137",
    "GE2138",
    "GE2248",
    "GE2256",
    "GE2258",
    "GE2260",
    "GE2262",
    "GE2263",
    "GE2266",
    "GE2267",
    "GE2334",
    "GE2335",
    "GE2338",
    "GE2339",
    "GE3108",
    "GE3109",
    "GE3204",
    "GE3207",
    "GE3208",
    "GE3209",
    "GE4103",
]


def test_added_ge_courses_are_available_by_code() -> None:
    for course_code in ADDED_COURSE_CODES:
        course = get_ge_course_info(course_code)
        assert course is not None
        assert course["course_code"] == course_code


def test_added_ge_courses_are_searchable_by_title_and_code() -> None:
    assert search_ge_courses("GE1357")
    assert search_ge_courses("Introduction to Chemistry")
    assert search_ge_courses("Democracy at the Movies")
