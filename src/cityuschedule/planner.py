"""Helpers shared by the course plan generator and the command line.

The plan search itself lives in :mod:`cityuschedule.plan_generator`.
"""

from cityuschedule.aims import load_aims_html

from .course_catalog import CatalogCourse
from .course_planner import PlannedSection


def planned_sections_to_sessions(
    sections: tuple[PlannedSection, ...],
) -> list[dict[str, str]]:
    sessions = []

    for section in sections:
        sessions.append(
            {
                "course_code": section.course_code,
                "course_title": section.course_title,
                "crn": section.crn,
                "section": section.section,
                "type": section.section,
                "day": section.day,
                "start_time": section.start,
                "end_time": section.end,
                "building": section.location.partition(" ")[0],
                "room": section.location.partition(" ")[2],
                "summary": (
                    f"{section.course_code} {section.section}"
                    f" — {section.course_title}"
                ),
                "description": (
                    f"Selected plan: {section.course_code} {section.section}\n"
                    f"Credits: {section.credits}"
                ),
            }
        )

    return sessions


def calculate_aims_credits(
    aims_html: str,
    courses: list[CatalogCourse],
) -> tuple[int, list[str]]:
    aims_sessions = load_aims_html(aims_html)
    aims_course_codes = {
        session["course_code"].upper()
        for session in aims_sessions
    }

    return calculate_course_credits(aims_course_codes, courses)


def calculate_course_credits(
    course_codes: set[str],
    courses: list[CatalogCourse],
) -> tuple[int, list[str]]:
    course_credits = {
        course.code.upper(): course.credits
        for course in courses
    }

    total_credits = 0
    unknown_courses = []

    for course_code in sorted({code.upper() for code in course_codes}):
        credits = course_credits.get(course_code)

        if credits is None:
            unknown_courses.append(course_code)
            continue

        total_credits += credits

    return total_credits, unknown_courses
