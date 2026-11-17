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
                )
            )

    return planned