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
    section_credits: int | None = None
    date_range: str = ""
    crn: str = ""
    availability: str = ""
    web: str = ""
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogCourse:
    code: str
    title: str
    credits: int
    sections: tuple[CatalogSection, ...]


DEFAULT_CREDIT_CATALOGS = (
    "cs_course_requirements.json",
    "ge_course_requirements.json",
    "other_course_requirements.json",
)


def load_course_catalog(path: str | Path) -> list[CatalogCourse]:
    with open(path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    if isinstance(data, dict):
        items = data.get("courses", [])
    else:
        items = data

    courses = []

    for item in items:
        course_code = item.get("course_code", item.get("code", ""))

        sections = tuple(
            CatalogSection(
                course_code=course_code,
                section=section["section"],
                day=section["day"],
                start=section["start"],
                end=section["end"],
                location=section.get("location", ""),
                section_credits=(
                    int(section["section_credits"])
                    if section.get("section_credits") is not None
                    else None
                ),
                date_range=section.get("date_range", ""),
                crn=section.get("crn", ""),
                availability=section.get("availability", ""),
                web=section.get("web", ""),
                notes=tuple(section.get("notes", [])),
            )
            for section in item.get("sections", [])
        )

        courses.append(
            CatalogCourse(
                code=course_code,
                title=item.get("title", ""),
                credits=int(item["credits"]),
                sections=sections,
            )
        )

    return courses


def load_credit_catalogs(
    extra_paths: list[str] | None = None,
) -> list[CatalogCourse]:
    source_catalogue_dir = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "catalogue"
    )
    if source_catalogue_dir.is_dir():
        catalogue_dir = source_catalogue_dir
    else:
        catalogue_dir = (
            Path(__file__).resolve().parent
            / "data"
            / "catalogue"
        )

    courses = []
    for filename in DEFAULT_CREDIT_CATALOGS:
        courses.extend(load_course_catalog(catalogue_dir / filename))

    for path in extra_paths or []:
        courses.extend(load_course_catalog(path))

    courses_by_code: dict[str, CatalogCourse] = {}
    for course in courses:
        code = course.code.upper()
        existing = courses_by_code.get(code)
        if existing is not None and existing.credits != course.credits:
            raise ValueError(
                f"Conflicting credits for {code}: "
                f"{existing.credits} and {course.credits}"
            )
        courses_by_code.setdefault(code, course)

    return list(courses_by_code.values())