import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "ge_courses.json"


def load_ge_courses() -> list[dict]:
    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_ge_course_info(course_code: str) -> dict | None:
    course_code = course_code.strip().upper()

    for course in load_ge_courses():
        if course["course_code"].upper() == course_code:
            return course

    return None

def search_ge_courses(keyword: str) -> list[dict]:
    keyword = keyword.strip().lower()

    if not keyword:
        return []

    results = []

    for course in load_ge_courses():
        searchable_text = " ".join(
            [
                course.get("course_code", ""),
                course.get("course_title", ""),
                course.get("area", ""),
                course.get("area_name", ""),
                course.get("offering_unit", ""),
            ]
        ).lower()

        if keyword in searchable_text:
            results.append(course)

    return results

def filter_ge_courses_by_exam(
    courses: list[dict],
    *,
    with_exam: bool = False,
) -> list[dict]:
    """
    Filter an existing course list by its explicit exam status.

    Args:
        courses: Course dictionaries to filter.
        with_exam: False for courses without exams;
                   True for courses with exams.

    Returns:
        Matching course dictionaries, preserving their order and fields.

    Courses with missing or non-boolean 'with_exam' values are excluded.
    The input list and its dictionaries are not modified.
    """
    if not isinstance(with_exam, bool):
        raise TypeError("with_exam must be True or False.")

    return [
        course
        for course in courses
        if course.get("with_exam") is with_exam
    ]

def get_ge_courses_without_exam() -> list[dict]:
    """Load GE courses and return only those explicitly without exams."""
    return filter_ge_courses_by_exam(
        load_ge_courses(),
        with_exam=False,
    )

def _normalize_ge_area(area: str | int) -> str:
    """
    Convert an area value to 'Area 1', 'Area 2', or 'Area 3'.

    Accepted examples:
        1, "1", "Area 1", "area 1", " AREA 1 "
    """
    if isinstance(area, bool) or not isinstance(area, (str, int)):
        raise TypeError("area must be a string or integer.")

    value = str(area).strip().casefold()

    if value.startswith("area"):
        value = value[4:].strip()

    if value not in {"1", "2", "3"}:
        raise ValueError(
            "area must be 1, 2, 3, 'Area 1', 'Area 2', or 'Area 3'."
        )

    return f"Area {value}"

def filter_ge_courses_by_area(
    courses: list[dict],
    area: str | int,
) -> list[dict]:
    """
    Return courses belonging to the requested GE area.

    Courses with missing or invalid area values are excluded.
    The input list and its dictionaries are not modified.
    """
    target_area = _normalize_ge_area(area)
    results = []

    for course in courses:
        try:
            course_area = _normalize_ge_area(course.get("area"))
        except (TypeError, ValueError):
            continue

        if course_area == target_area:
            results.append(course)

    return results


def get_ge_courses_by_area(area: str | int) -> list[dict]:
    """Load GE courses and return those in the requested area."""
    return filter_ge_courses_by_area(load_ge_courses(), area)
