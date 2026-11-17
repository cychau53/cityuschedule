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