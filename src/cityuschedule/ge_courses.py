import json
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "ge_courses.json"
SECTION_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "ge_course_information.json"

_GE_SESSION_SOURCES: ContextVar[
    tuple[Path, Path] | None
] = ContextVar(
    "ge_session_sources",
    default=None,
)


@contextmanager
def use_ge_session_sources(
    basic_path: str | Path,
    section_path: str | Path,
):
    """Use session JSON files for GE loading within this context."""
    token = _GE_SESSION_SOURCES.set(
        (Path(basic_path), Path(section_path))
    )

    try:
        yield
    finally:
        _GE_SESSION_SOURCES.reset(token)

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
    sources = _GE_SESSION_SOURCES.get()

    if sources is None:
        basic_path = DATA_PATH
        section_path = SECTION_DATA_PATH
    else:
        basic_path, section_path = sources

    courses = _read_json_records(basic_path)

    sections = _read_json_records(
        section_path,
        allow_missing_or_blank=sources is None,
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
            path=section_path,
            index=index,
        )

        sections_by_course.setdefault(course_code, []).append(section)

    combined_records = []

    for index, course in enumerate(courses):
        course_code = _record_course_code(
            course,
            path=basic_path,
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
