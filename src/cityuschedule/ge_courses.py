import json
from importlib.resources import files
from pathlib import Path

PACKAGE_DATA_DIRECTORY = Path(__file__).resolve().parent / "data"
SOURCE_DATA_DIRECTORY = Path(__file__).resolve().parents[2] / "data"
DATA_DIRECTORY = (
    PACKAGE_DATA_DIRECTORY
    if (PACKAGE_DATA_DIRECTORY / "ge_courses.json").is_file()
    else SOURCE_DATA_DIRECTORY
)
DATA_PATH = DATA_DIRECTORY / "ge_courses.json"
SECTION_DATA_PATH = DATA_DIRECTORY / "ge_course_information.json"



def _read_json_records(
    path: Path,
    *,
    allow_missing_or_blank: bool = False,
) -> list[dict]:
    """Read a JSON list of dictionaries."""
    try:
        content = path.read_text(encoding="utf-8-sig").strip()
    except FileNotFoundError:
        if allow_missing_or_blank:
            return []
        raise

    if not content:
        if allow_missing_or_blank:
            return []

        raise ValueError(f"{path} is empty.")

    try:
        records = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path}: {exc}"
        ) from exc

    if not isinstance(records, list):
        raise ValueError(
            f"{path} must contain a list of dictionaries."
        )

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(
                f"Record {index} in {path} must be a dictionary."
            )

    return records


def _record_course_code(
    record: dict,
    *,
    path: Path,
    index: int,
) -> str:
    """Get a normalized course code from a record."""
    course_code = record.get("course_code")

    if not isinstance(course_code, str) or not course_code.strip():
        raise ValueError(
            f"Record {index} in {path} has no valid course_code."
        )

    return course_code.strip().upper()


def load_ge_courses() -> list[dict]:
    """
    Combine basic GE information with section meeting records.

    Returns one flat dictionary per section meeting.
    Courses without section records are retained with empty section fields.
    """
    courses = _read_json_records(DATA_PATH)

    sections = _read_json_records(
        SECTION_DATA_PATH,
        allow_missing_or_blank=True,
    )

    section_fields = (
        "crn",
        "section",
        "term",
        "capacity",
        "day",
        "time",
        "type",
        "building",
        "room",
        "instructor",
    )

    sections_by_course: dict[str, list[dict]] = {}

    for index, section in enumerate(sections):
        course_code = _record_course_code(
            section,
            path=SECTION_DATA_PATH,
            index=index,
        )

        sections_by_course.setdefault(course_code, []).append(section)

    combined_records = []

    for index, course in enumerate(courses):
        course_code = _record_course_code(
            course,
            path=DATA_PATH,
            index=index,
        )

        # Remove a previously attached nested field, if present.
        basic_info = {
            key: value
            for key, value in course.items()
            if key != "sections"
        }
        basic_info["course_code"] = course_code

        matching_sections = sections_by_course.get(course_code, [])

        if not matching_sections:
            combined_records.append(
                {
                    **basic_info,
                    **{
                        field: None
                        for field in section_fields
                    },
                }
            )
            continue

        for section in matching_sections:
            combined_records.append(
                {
                    **basic_info,
                    **{
                        field: section.get(field)
                        for field in section_fields
                    },
                }
            )

    return combined_records


def get_ge_course_info(course_code: str) -> dict | None:
    course_code = course_code.strip().upper()

    for course in load_ge_courses():
        if course["course_code"].upper() == course_code:
            return course

    return None

def search_ge_courses(keyword: str) -> list[dict]:
    clauses = [
        " ".join(clause.casefold().split())
        for clause in keyword.split("+")
    ]

    if not clauses or any(not clause for clause in clauses):
        return []

    results = []

    for course in load_ge_courses():
        if all(
            _ge_course_matches_clause(course, clause)
            for clause in clauses
        ):
            results.append(course)

    return results


def _ge_course_matches_clause(
    course: dict,
    clause: str,
) -> bool:
    if clause == "without exam":
        return course.get("with_exam") is False
    if clause == "with exam":
        return course.get("with_exam") is True
    if clause == "cross":
        return course.get("cross_institutional") is True
    if clause == "not cross":
        return course.get("cross_institutional") is False
    if clause in {"area 1", "area 2", "area 3"}:
        try:
            return _normalize_ge_area(course.get("area")) == clause.title()
        except (TypeError, ValueError):
            return False
    if clause.startswith("level "):
        return course in filter_ge_courses_by_level(
            [course],
            clause.removeprefix("level ").strip(),
        )

    searchable_text = " ".join(
        str(course.get(field) or "")
        for field in (
            "course_code",
            "course_title",
            "area",
            "area_name",
            "offering_unit",
            "level",
        )
    ).casefold()
    return clause in searchable_text


def filter_ge_courses_by_cross_institutional(
    courses: list[dict],
    *,
    cross_institutional: bool,
) -> list[dict]:
    """Filter courses by their explicit cross-institutional status."""
    if not isinstance(cross_institutional, bool):
        raise TypeError("cross_institutional must be True or False.")

    return [
        course
        for course in courses
        if course.get("cross_institutional") is cross_institutional
    ]


_GE_LEVEL_ORDER = ("A1", "A2", "B1", "B2", "B3", "B4")


def filter_ge_courses_by_level(
    courses: list[dict],
    level_query: str,
) -> list[dict]:
    """Filter courses by a level, level family, or inclusive level range."""
    normalized_query = " ".join(level_query.casefold().split()).upper()
    if normalized_query in {"A", "B"}:
        requested_levels = {
            level for level in _GE_LEVEL_ORDER if level.startswith(normalized_query)
        }
    elif " TO " in normalized_query:
        start, end = normalized_query.split(" TO ", maxsplit=1)
        try:
            start_index = _GE_LEVEL_ORDER.index(start)
            end_index = _GE_LEVEL_ORDER.index(end)
        except ValueError:
            return []
        if start_index > end_index:
            return []
        requested_levels = set(_GE_LEVEL_ORDER[start_index : end_index + 1])
    elif normalized_query in _GE_LEVEL_ORDER:
        requested_levels = {normalized_query}
    else:
        return []

    return [
        course
        for course in courses
        if requested_levels.intersection(
            level.strip().upper()
            for level in str(course.get("level") or "").split(",")
        )
    ]


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
