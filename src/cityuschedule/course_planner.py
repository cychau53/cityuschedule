from dataclasses import dataclass

from .course_catalog import CatalogCourse, CatalogSection


@dataclass(frozen=True)
class PlannedSection:
    course_code: str
    course_title: str
    section: str
    day: str
    start: str
    end: str
    location: str
    credits: int
    section_credits: int | None = None
    date_range: str = ""
    crn: str = ""
    availability: str = ""
    web: str = ""
    notes: tuple[str, ...] = ()
    waitlist: str = ""
    restrictions: str = ""


def catalogue_to_planned_sections(
    courses: list[CatalogCourse],
) -> list[PlannedSection]:
    planned = []

    for course in courses:
        for section in course.sections:
            planned.append(
                PlannedSection(
                    course_code=course.code,
                    course_title=course.title,
                    section=section.section,
                    day=section.day,
                    start=section.start,
                    end=section.end,
                    location=section.location,
                    credits=course.credits,
                    section_credits=section.section_credits,
                    date_range=section.date_range,
                    crn=section.crn,
                    availability=section.availability,
                    web=section.web,
                    notes=section.notes,
                    waitlist=section.waitlist,
                    restrictions=section.restrictions,
                )
            )

    return planned


def build_course_bundle(
    course: CatalogCourse,
    section_codes: list[str],
) -> tuple[PlannedSection, ...]:
    requested = {
        code.strip().upper()
        for code in section_codes
        if code.strip()
    }

    if not requested:
        raise ValueError(
            f"No sections were selected for {course.code}"
        )

    planned = catalogue_to_planned_sections([course])

    available = {
        section.section.upper()
        for section in planned
    }

    missing = requested - available

    if missing:
        raise ValueError(
            f"Unknown sections for {course.code}: "
            f"{', '.join(sorted(missing))}"
        )

    return tuple(
        section
        for section in planned
        if section.section.upper() in requested
    )