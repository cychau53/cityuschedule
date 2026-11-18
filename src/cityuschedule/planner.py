from dataclasses import dataclass

from cityuschedule.aims import load_aims_html
from .course_catalog import CatalogCourse
from .course_planner import (
    PlannedSection,
    build_course_bundle,
    catalogue_to_planned_sections,
)
from .schedule_conflicts import TimeSlot, find_conflicts
from datetime import datetime

from itertools import combinations, product


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
        if session["day"] and session["start_time"] and session["end_time"]
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

    all_sessions = [
        session
        for session in aims_sessions + planned_sessions
        if session["day"] and session["start_time"] and session["end_time"]
    ]

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


def generate_plans(
    aims_html: str,
    timetable_courses: list[CatalogCourse],
    credit_courses: list[CatalogCourse] | None = None,
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
    planned_sections = catalogue_to_planned_sections(timetable_courses)

    course_credits = {
        course.code.upper(): course.credits
        for course in credit_courses
    }

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
            unique_course_codes = {
                section.course_code.upper()
                for section in chosen
            }

            catalogue_credits = sum(
                course_credits[course_code]
                for course_code in unique_course_codes
                if course_code in course_credits
            )

            aims_credits, unknown_aims_courses = calculate_aims_credits(
                aims_html,
                credit_courses,
            )

            total_credits = catalogue_credits + aims_credits
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

def sections_to_time_slots(
    sections: list[PlannedSection],
) -> list[TimeSlot]:
    return [
        slot
        for section in sections
        for slot in planned_to_time_slots(section)
    ]


def has_conflict(
    existing_slots: list[TimeSlot],
    new_sections: list[PlannedSection],
) -> bool:
    used_slots = list(existing_slots)

    for section in new_sections:
        candidate_slots = planned_to_time_slots(section)

        if find_conflicts(used_slots, candidate_slots):
            return True

        used_slots.extend(candidate_slots)

    return False

def generate_aims_ge_plans(
    aims_html: str,
    ge_courses: list[CatalogCourse],
    credit_courses: list[CatalogCourse],
    ge_count: int,
    max_results: int = 20,
    min_credits: int | None = None,
    max_credits: int | None = None,
    preferred_days: list[str] | None = None,
    avoid_days: list[str] | None = None,
    course_bundles: dict[str, list[list[str]]] | None = None,
) -> list[PlanResult]:
    if ge_count < 0:
        raise ValueError("--add-ge cannot be negative")

    existing_slots = aims_to_time_slots(aims_html)
    ge_sections = catalogue_to_planned_sections(ge_courses)

    sections_by_course: dict[str, list[PlannedSection]] = {}

    for section in ge_sections:
        sections_by_course.setdefault(section.course_code.upper(), []).append(section)

    ge_course_codes = sorted(sections_by_course)

    if ge_count > len(ge_course_codes):
        raise ValueError(
            f"Only {len(ge_course_codes)} GE courses are available, "
            f"but {ge_count} were requested"
        )

    credit_lookup_courses = {
        course.code.upper(): course
        for course in credit_courses
    }

    for course in ge_courses:
        code = course.code.upper()
        existing = credit_lookup_courses.get(code)

        if existing is not None and existing.credits != course.credits:
            raise ValueError(
                f"Conflicting credits for {code}: "
                f"credit catalogue says {existing.credits}, "
                f"imported timetable says {course.credits}"
            )

        credit_lookup_courses.setdefault(code, course)

    course_credits = {
        code: course.credits
        for code, course in credit_lookup_courses.items()
    }

    aims_credits, unknown_aims_courses = calculate_aims_credits(
        aims_html,
        list(credit_lookup_courses.values()),
    )

    if unknown_aims_courses:
        raise ValueError(
            "Cannot calculate an accurate total. "
            "Missing AIMS course credits: "
            + ", ".join(unknown_aims_courses)
        )

    preferred_days_set = {
        day.capitalize()
        for day in (preferred_days or [])
    }
    avoided_days = {
        day.capitalize()
        for day in (avoid_days or [])
    }

    results: list[PlanResult] = []

    courses_by_code = {
        course.code.upper(): course
        for course in ge_courses
    }

    bundle_definitions = {
        code.upper(): bundles
        for code, bundles in (course_bundles or {}).items()
    }

    options_by_course = {}

    for course_code in ge_course_codes:
        definitions = bundle_definitions.get(course_code)

        if not definitions:
            raise ValueError(
                f"No section bundles configured for {course_code}. "
                "Provide complete section combinations before planning."
            )

        options_by_course[course_code] = [
            build_course_bundle(
                courses_by_code[course_code],
                section_codes,
            )
            for section_codes in definitions
        ]

    for selected_courses in combinations(ge_course_codes, ge_count):
        course_options = [
            options_by_course[course_code]
            for course_code in selected_courses
        ]

        for bundle_choice in product(*course_options):
            chosen = [
                section
                for bundle in bundle_choice
                for section in bundle
            ]

            if has_conflict(existing_slots, chosen):
                continue

            plan_days = (
                {slot.day for slot in existing_slots}
                | {section.day for section in chosen}
            )
            if plan_days & avoided_days:
                continue

            ge_course_codes_selected = {
                section.course_code.upper()
                for section in chosen
            }

            ge_credits = sum(
                course_credits[course_code]
                for course_code in ge_course_codes_selected
                if course_code in course_credits
            )

            total_credits = aims_credits + ge_credits

            if min_credits is not None and total_credits < min_credits:
                continue

            if max_credits is not None and total_credits > max_credits:
                continue

            preferred_count = len(plan_days & preferred_days_set)

            results.append(
                PlanResult(
                    sections=tuple(chosen),
                    total_credits=total_credits,
                    conflicts=(),
                    preferred_day_count=preferred_count,
                )
            )

    results.sort(
        key=lambda result: (
            -result.preferred_day_count,
            result.total_credits,
        )
    )

    return results[:max_results]