import pytest

from cityuschedule.ge_courses import filter_ge_courses_by_exam


@pytest.fixture
def courses():
    return [
        {"course_code": "NO_EXAM", "with_exam": False},
        {"course_code": "HAS_EXAM", "with_exam": True},
        {"course_code": "MISSING"},
        {"course_code": "NULL", "with_exam": None},
        {"course_code": "STRING", "with_exam": "false"},
        {"course_code": "ZERO", "with_exam": 0},
    ]


def test_returns_only_explicit_no_exam_courses(courses):
    result = filter_ge_courses_by_exam(courses)

    assert [course["course_code"] for course in result] == ["NO_EXAM"]


def test_returns_only_explicit_exam_courses(courses):
    result = filter_ge_courses_by_exam(courses, with_exam=True)

    assert [course["course_code"] for course in result] == ["HAS_EXAM"]


def test_empty_list():
    assert filter_ge_courses_by_exam([]) == []


def test_does_not_change_input(courses):
    original = [course.copy() for course in courses]

    filter_ge_courses_by_exam(courses)

    assert courses == original


@pytest.mark.parametrize("invalid_value", [None, "false", 0, 1])
def test_rejects_non_boolean_filter(courses, invalid_value):
    with pytest.raises(TypeError):
        filter_ge_courses_by_exam(
            courses,
            with_exam=invalid_value,
        )
