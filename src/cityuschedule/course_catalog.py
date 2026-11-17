import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CatalogSection:
    course_code: str
    section: str
    day: str
    start: str
    end: str
    location: str


@dataclass(frozen=True)
class CatalogCourse:
    code: str
    title: str
    credits: int
    sections: tuple[CatalogSection, ...]


def load_course_catalog(path: str | Path) -> list[CatalogCourse]:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, dict):
        items = data.get("courses", [])
    else:
        items = data

    courses = []

    for item in items:
        sections = tuple(
            CatalogSection(
                course_code=item.get("course_code", item.get("code", "")),
                section=section["section"],
                day=section["day"],
                start=section["start"],
                end=section["end"],
                location=section.get("location", ""),
            )
            for section in item.get("sections", [])
        )

        courses.append(
            CatalogCourse(
                code=item.get("course_code", item.get("code", "")),
                title=item.get("title", ""),
                credits=int(item["credits"]),
                sections=sections,
            )
        )

    return courses