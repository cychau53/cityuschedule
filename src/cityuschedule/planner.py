from dataclasses import dataclass

from cityuschedule.aims import load_aims_html
from .course_catalog import CatalogCourse
from .course_planner import PlannedSection, catalogue_to_planned_sections
from .schedule_conflicts import TimeSlot, find_conflicts
from datetime import datetime


@dataclass(frozen=True)
class PlanResult:
    sections: tuple[PlannedSection, ...]
    total_credits: int
    conflicts: tuple[tuple[TimeSlot, TimeSlot], ...]
    preferred_day_count: int = 0


def aims_to_time_slots(aims_html: str) -> list[TimeSlot]:
    sessions = load_aims_html(aims_html)

    return [
        TimeSlot(
            day=session["day"],
            start=session["start_time"],
            end=session["end_time"],
            label=f"{session['course_code']} {session['section']}",
        )
        for session in sessions
    ]


def planned_to_time_slots(section: PlannedSection) -> list[TimeSlot]:
    return [
        TimeSlot(
            day=section.day,
            start=section.start,
            end=section.end,
            label=f"{section.course_code} {section.section}",
        )
    ]

def planned_sections_to_sessions(
    sections: tuple[PlannedSection, ...],
) -> list[dict[str, str]]:
    sessions = []

    for section in sections:
        sessions.append(
            {
                "course_code": section.course_code,
                "course_title": section.course_title,
                "crn": "",
                "section": section.section,
                "type": section.section,
                "day": section.day,
                "start_time": section.start,
                "end_time": section.end,
                "building": "",
                "room": section.location,
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

def export_plan_ics(
    aims_html: str,
    plan: PlanResult,
    output_path: str,
    semester_start: str,
    semester_end: str,
    exclusions_path: str | None = None,
) -> None:
    from cityuschedule.aims import load_aims_html
    from cityuschedule.calendar_export import export_ics

    aims_sessions = load_aims_html(aims_html)
    planned_sessions = planned_sections_to_sessions(plan.sections)

    all_sessions = aims_sessions + planned_sessions

    export_ics(
        all_sessions,
        output_path,
        semester_start,
        semester_end,
        "Asia/Hong_Kong",
        exclusions_path,
    )


def evaluate_course(
    existing_slots: list[TimeSlot],
    course: CatalogCourse,
    section: PlannedSection,
) -> PlanResult:
    candidate_slots = planned_to_time_slots(section)
    candidate_labels = {slot.label for slot in candidate_slots}
    existing_labels = {slot.label for slot in existing_slots}

    conflicts = tuple(
        (existing, candidate)
        for existing, candidate in find_conflicts(existing_slots, candidate_slots)
        if existing.label not in candidate_labels
        or candidate.label not in existing_labels
    )

    return PlanResult(
        sections=(section,),
        total_credits=course.credits,
        conflicts=conflicts,
    )


def generate_plans(
    aims_html: str,
    courses: list[CatalogCourse],
    max_results: int = 20,
    min_credits: int | None = None,
    max_credits: int | None = None,
    required_courses: list[str] | None = None,
    preferred_days: list[str] | None = None,
    required_sections: list[str] | None = None,
    avoid_days: list[str] | None = None,
    min_gap: int = 0,
) -> list[PlanResult]:
    existing_slots = aims_to_time_slots(aims_html)
    planned_sections = catalogue_to_planned_sections(courses)

    sections_by_course: dict[str, list[PlannedSection]] = {}

    for section in planned_sections:
        sections_by_course.setdefault(section.course_code, []).append(section)

    course_codes = list(sections_by_course)

    required_courses_set = set(required_courses or [])
    preferred_days_set = {
        day.capitalize() for day in (preferred_days or [])
    }
    avoided_days = {
        day.capitalize() for day in (avoid_days or [])
    }

    required_section_values = list(required_sections or [])

    if len(required_section_values) % 2 != 0:
        raise ValueError(
            "Invalid --require-section arguments. "
            "Provide course code and section pairs, such as: "
            "--require-section TEST101 C01"
        )

    required_section_pairs = {
        (required_section_values[index], required_section_values[index + 1])
        for index in range(0, len(required_section_values), 2)
    }
    required_course_codes_from_sections = {
        course_code for course_code, _ in required_section_pairs
    }

    all_required_courses = (
        required_courses_set | required_course_codes_from_sections
    )

    missing_required = all_required_courses - set(course_codes)

    if missing_required:
        return []

    results: list[PlanResult] = []

    def search(
        index: int,
        chosen: list[PlannedSection],
        used_slots: list[TimeSlot],
    ) -> None:
        if len(results) >= max_results:
            return

        if index == len(course_codes):
            total_credits = sum(
                section.credits
                for section in chosen
            )

            if min_credits is not None and total_credits < min_credits:
                return

            if max_credits is not None and total_credits > max_credits:
                return

            plan_days = {section.day for section in chosen}
            preferred_count = len(plan_days & preferred_days_set)

            if plan_days & avoided_days:
                return

            results.append(
                PlanResult(
                    sections=tuple(chosen),
                    total_credits=total_credits,
                    conflicts=(),
                    preferred_day_count=preferred_count,
                )
            )
            return

        course_code = course_codes[index]

        if (
            all_required_courses
            and course_code not in all_required_courses
        ):
            search(
                index + 1,
                chosen,
                used_slots,
            )
            return
            

        for section in sections_by_course[course_code]:
            section_pair = (section.course_code, section.section)

            if (
                required_section_pairs
                and section_pair not in required_section_pairs
            ):
                continue

            candidate_slots = planned_to_time_slots(section)
            conflicts = find_conflicts(used_slots, candidate_slots)


            if conflicts:
                continue


            if min_gap > 0:
                candidate_start = datetime.strptime(
                    section.start, "%H:%M"
                )
                candidate_end = datetime.strptime(
                    section.end, "%H:%M"
                )


                for used_slot in used_slots:
                    if used_slot.day != section.day:
                        continue


                    used_start = datetime.strptime(
                        used_slot.start, "%H:%M"
                    )
                    used_end = datetime.strptime(
                        used_slot.end, "%H:%M"
                    )


                    if candidate_end <= used_start:
                        gap_minutes = int(
                            (
                                used_start - candidate_end
                            ).total_seconds()
                            / 60
                        )
                    elif used_end <= candidate_start:
                        gap_minutes = int(
                            (
                                candidate_start - used_end
                            ).total_seconds()
                            / 60
                        )
                    else:
                        continue


                    if gap_minutes < min_gap:
                        break


                else:
                    search(
                        index + 1,
                        chosen + [section],
                        used_slots + candidate_slots,
                    )


                continue


            search(
                index + 1,
                chosen + [section],
                used_slots + candidate_slots,
            )

    search(0, [], existing_slots)

    results.sort(
        key=lambda plan: (
            -plan.preferred_day_count,
            plan.total_credits,
        )
    )

    return results