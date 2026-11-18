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
    credit_catalog: list[str] | None = None,
) -> list[dict]:
    if not credit_catalog:
        return []

    credits = []

    for path in credit_catalog:
        path = Path(path)

        if not path.exists():
            continue

        with path.open(
            "r",
            encoding="utf-8-sig",
        ) as file:
            records = json.load(file)

        if isinstance(records, dict):
            records = [records]

        credits.extend(records)

    return credits
