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
    waitlist: str = ""
    restrictions: str = ""


@dataclass(frozen=True)
class CatalogCourse:
    code: str
    title: str
    credits: int | None
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
                waitlist=str(section.get("waitlist", "")),
                restrictions=str(section.get("restrictions", "")),
            )
            for section in item.get("sections", [])
        )

        raw_credits = item.get("credits")

        if raw_credits is None:
            section_credits = {
                section.section_credits
                for section in sections
                if section.section_credits is not None
            }

            if len(section_credits) == 1:
                credits: int | None = section_credits.pop()
            elif section_credits:
                raise ValueError(
                    f"Course {course_code} has no course-level credits and "
                    f"conflicting section credits: {sorted(section_credits)}"
                )
            else:
                credits = None
        else:
            credits = int(raw_credits)

        courses.append(
            CatalogCourse(
                code=course_code,
                title=item.get("title", ""),
                credits=credits,
                sections=sections,
            )
        )
    return courses


def catalogue_dir() -> Path:
    """Folder holding the bundled ``*_course_requirements.json`` files."""
    source_catalogue_dir = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "catalogue"
    )
    if source_catalogue_dir.is_dir():
        return source_catalogue_dir
    return (
        Path(__file__).resolve().parent
        / "data"
        / "catalogue"
    )


def load_ge_section_catalog(
    path: str | Path | None = None,
    term: str | None = None,
) -> list[CatalogCourse]:
    """Turn GE section records (``data/ge_course_information.json``) into
    catalogue courses, optionally keeping one term such as ``2026-27 Sem B``.

    Section codes such as ``15453C01`` start with the CRN; it is removed so
    the section is ``C01``. Credits are left empty and come from the credit
    catalogue.
    """
    if path is None:
        from .ge_courses import SECTION_DATA_PATH

        path = SECTION_DATA_PATH

    with open(path, "r", encoding="utf-8-sig") as file:
        records = json.load(file)

    sections_by_course: dict[str, list[CatalogSection]] = {}

    for record in records:
        if term and str(record.get("term", "")).casefold() != term.casefold():
            continue

        course_code = str(record.get("course_code", "")).strip().upper()
        crn = str(record.get("crn", "")).strip()
        section = str(record.get("section", "")).strip().upper()
        if crn and section.startswith(crn):
            section = section[len(crn):]
        start, _, end = str(record.get("time") or "").partition("-")

        sections_by_course.setdefault(course_code, []).append(
            CatalogSection(
                course_code=course_code,
                section=section,
                day=str(record.get("day") or ""),
                start=start.strip()[:5],
                end=end.strip()[:5],
                location=" ".join(
                    str(record.get(key) or "").strip()
                    for key in ("building", "room")
                ).strip(),
                crn=crn,
            )
        )

    return [
        CatalogCourse(
            code=code,
            title="",
            credits=None,
            sections=tuple(sections),
        )
        for code, sections in sorted(sections_by_course.items())
    ]


def load_credit_catalogs(
    extra_paths: list[str] | None = None,
) -> list[CatalogCourse]:
    courses = []
    for filename in DEFAULT_CREDIT_CATALOGS:
        courses.extend(load_course_catalog(catalogue_dir() / filename))

    for path in extra_paths or []:
        courses.extend(load_course_catalog(path))

    courses_by_code: dict[str, CatalogCourse] = {}

    for course in courses:
        code = course.code.upper()
        existing = courses_by_code.get(code)

        if existing is not None:
            if (
                existing.credits is not None
                and course.credits is not None
                and existing.credits != course.credits
            ):
                raise ValueError(
                    f"Conflicting credits for {code}: "
                    f"{existing.credits} and {course.credits}"
                )

            if existing.credits is None:
                courses_by_code[code] = course

        courses_by_code.setdefault(code, course)

    return list(courses_by_code.values())
