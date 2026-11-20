import pytest

from cityuschedule import ge_courses


@pytest.fixture
def catalogue(monkeypatch):
    courses = [
        {
            "course_code": "GE1001",
            "course_title": "Course Without Exam",
            "area": "Area 1",
            "level": "A1, B2",
            "terms": ["2026-27 Sem A"],
            "with_exam": False,
            "cross_institutional": False,
        },
        {
            "course_code": "GE2001",
            "course_title": "Introduction to a Course With Exam",
            "area": "Area 2",
            "level": "B1",
            "terms": ["2026-27 Sem B"],
            "with_exam": True,
            "cross_institutional": True,
        },
        {
            "course_code": "GE3001",
            "course_title": "Course with unknown exam status",
            "area": "Area 3",
            "level": "A2, B1",
            "terms": ["2026-27 Summer"],
        },
        {
            "course_code": "GE4001",
            "course_title": "Another course",
            "area": "University Req.",
            "level": "B2",
            "cross_institutional": False,
        },
    ]
    monkeypatch.setattr(ge_courses, "load_ge_courses", lambda: courses)
    return courses


@pytest.mark.parametrize(
    ("query", "expected_code"),
    [
        ("without exam", "GE1001"),
        ("WITHOUT EXAM", "GE1001"),
        ("With Exam", "GE2001"),
        ("wItH eXaM", "GE2001"),
    ],
)
def test_search_filters_by_exam_case_insensitively(
    catalogue,
    query,
    expected_code,
):
    results = ge_courses.search_ge_courses(query)

    assert [course["course_code"] for course in results] == [expected_code]


@pytest.mark.parametrize(
    ("query", "expected_code"),
    [
        ("Area 1", "GE1001"),
        ("Area1", "GE1001"),
        ("AREA 2", "GE2001"),
        ("area2", "GE2001"),
        ("area 3", "GE3001"),
        ("AREA3", "GE3001"),
    ],
)
def test_search_filters_by_area_case_insensitively(
    catalogue,
    query,
    expected_code,
):
    results = ge_courses.search_ge_courses(query)

    assert [course["course_code"] for course in results] == [expected_code]


def test_normal_keyword_search_remains_case_insensitive(catalogue):
    results = ge_courses.search_ge_courses("uNkNoWn ExAm")

    assert [course["course_code"] for course in results] == ["GE3001"]


@pytest.mark.parametrize(
    ("query", "expected_codes"),
    [
        ("level B", ["GE1001", "GE2001", "GE3001", "GE4001"]),
        ("levelB", ["GE1001", "GE2001", "GE3001", "GE4001"]),
        ("LEVEL b1", ["GE2001", "GE3001"]),
        ("levelB1", ["GE2001", "GE3001"]),
        ("Level A1 to B1", ["GE1001", "GE2001", "GE3001"]),
        ("levelA1toB1", ["GE1001", "GE2001", "GE3001"]),
        ("level a2", ["GE3001"]),
        ("level B1 to A1", []),
    ],
)
def test_search_filters_by_level(
    catalogue,
    query,
    expected_codes,
):
    results = ge_courses.search_ge_courses(query)

    assert [course["course_code"] for course in results] == expected_codes


def test_exam_filter_excludes_courses_without_explicit_exam_status(catalogue):
    results = ge_courses.search_ge_courses("without exam")

    assert all(course.get("with_exam") is False for course in results)


@pytest.mark.parametrize(
    ("query", "expected_codes"),
    [
        ("cross", ["GE2001"]),
        ("CROSS", ["GE2001"]),
        ("not cross", ["GE1001", "GE4001"]),
        ("NoT CrOsS", ["GE1001", "GE4001"]),
    ],
)
def test_search_filters_by_cross_institutional_status(
    catalogue,
    query,
    expected_codes,
):
    results = ge_courses.search_ge_courses(query)

    assert [course["course_code"] for course in results] == expected_codes


@pytest.mark.parametrize(
    ("query", "expected_codes"),
    [
        ("2627A", ["GE1001"]),
        ("2627 a", ["GE1001"]),
        ("2 6 2 7 a", ["GE1001"]),
        ("2627b", ["GE2001"]),
        ("2627 S", ["GE3001"]),
    ],
)
def test_search_filters_by_available_semester(
    catalogue,
    query,
    expected_codes,
):
    results = ge_courses.search_ge_courses(query)

    assert [course["course_code"] for course in results] == expected_codes


@pytest.mark.parametrize(
    ("query", "expected_codes"),
    [
        ("introduction + level B + with exam", ["GE2001"]),
        ("WITH EXAM + INTRODUCTION + LEVEL b", ["GE2001"]),
        ("2627B + introduction + LEVELB + with exam", ["GE2001"]),
        (
            "not cross + level A1 to B1 + Area 1 + without exam",
            ["GE1001"],
        ),
        ("GE2001 + introduction + cross", ["GE2001"]),
    ],
)
def test_search_combines_filters_and_keywords(
    catalogue,
    query,
    expected_codes,
):
    results = ge_courses.search_ge_courses(query)

    assert [course["course_code"] for course in results] == expected_codes


@pytest.mark.parametrize("query", ["+", "level B +", "+ cross"])
def test_search_ignores_no_empty_clauses(catalogue, query):
    assert ge_courses.search_ge_courses(query) == []
