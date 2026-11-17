import argparse
import csv
from pathlib import Path

from .calendar_export import export_ics
from .conflicts import find_conflicts
from .gaps import find_gaps, format_gaps
from .timetable import format_timetable
from .aims import load_aims_html

from .course_catalog import load_course_catalog
from .planner import generate_plans, export_plan_ics

from cityuschedule.ge_courses import get_ge_course_info, search_ge_courses
from .ge_importer import update_ge_courses_from_html

def load_sessions(csv_path: str) -> list[dict[str, str]]:
    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        sessions = list(reader)

    if not sessions:
        raise ValueError("The CSV file contains no class sessions")

    return sessions


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cityuschedule",
        description="Check CityU course timetables for clashes and export them as calendar events.",
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        help="Path to a course timetable CSV file",
    )
    parser.add_argument(
        "--aims-html",
        help="Path to a saved AIMS weekly timetable HTML page",
    )
    parser.add_argument(
        "--min-gap",
        type=int,
        default=45,
        help="Minimum gap length in minutes to report",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export the timetable as an .ics calendar file",
    )

    parser.add_argument(
        "--exclusions",
        help="JSON file containing holidays and teaching breaks to exclude",
    )
    parser.add_argument(
        "--catalog",
        help="JSON course catalogue used to generate clash-free course plans",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum number of course plans to display",
    )
    parser.add_argument(
        "--min-credits",
        type=int,
        help="Minimum total credits for generated course plans",
    )
    parser.add_argument(
        "--max-credits",
        type=int,
        help="Maximum total credits for generated course plans",
    )
    parser.add_argument(
        "--required",
        nargs="+",
        help="Course codes that must appear in every generated plan",
    )
    parser.add_argument(
        "--prefer-days",
        nargs="+",
        help="Days to prefer when ranking generated plans, such as Mon Tue Wed",
    )
    parser.add_argument(
        "--require-section",
        nargs="+",
        help="Exact course sections that must appear, such as TEST101 C01",
    )
    parser.add_argument(
        "--avoid-days",
        nargs="+",
        help="Days that generated plans must not use, such as Fri Sat",
    )

    parser.add_argument(
        "--export-plan",
        type=int,
        help="Export the selected plan number as an ICS calendar, starting from 1",
    )
    parser.add_argument(
        "--output",
        default="cityu_timetable.ics",
        help="Output .ics file path",
    )

    parser.add_argument(
        "--semester-start",
        default="2026-08-31",
        help="First day of the semester in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--semester-end",
        default="2026-11-28",
        help="Last day of the semester in YYYY-MM-DD format",
    )

    parser.add_argument(
        "--ge-html",
        nargs="+",
        help="GE course HTML files to import.",
    )

    parser.add_argument(
        "--ge-output",
        default="data/ge_courses.json",
        help="Path for the imported GE course JSON file.",
    )

    parser.add_argument(
        "--ge-info",
        metavar="COURSE_CODE",
        help="Show basic information for a Gateway Education course, e.g. GE2230",
    )
    parser.add_argument(
        "--ge-search",
        metavar="KEYWORD",
        help="Search Gateway Education courses by course code, title, area, or offering unit",
    )

    args = parser.parse_args()

    if args.ge_html:
        count = update_ge_courses_from_html(
            args.ge_html,
            args.ge_output,
        )

        print(f"Imported {count} Gateway Education course(s).")
        return

    if args.ge_info:
        course = get_ge_course_info(args.ge_info)

        if course is None:
            parser.error(
                f"No Gateway Education course information found for {args.ge_info}."
            )

        area_name = course.get("area_name", "")
        area_text = course.get("area", "")

        if area_name:
            area_text = f"{area_text} — {area_name}"

        print(
            f"{course['course_code']} — {course['course_title']}\n"
            f"Area: {area_text}\n"
            f"Offering unit: {course.get('offering_unit', '')}\n"
            f"Level: {course.get('level', '')}\n"
            f"Available in: {', '.join(course.get('terms', [])) or 'Not specified'}\n"
            f"With exam: {'Yes' if course.get('with_exam') else 'No'}\n"
            f"Cross-institutional: {'Yes' if course.get('cross_institutional') else 'No'}\n"
            f"Partner institutions: {', '.join(course.get('partner_institutions', [])) or 'None'}\n"
        )
        return

    if args.ge_search:
        results = search_ge_courses(args.ge_search)

        if not results:
            print(f"No Gateway Education courses found for '{args.ge_search}'.")
            return

        print(
            f"Found {len(results)} Gateway Education course(s) "
            f"for '{args.ge_search}':\n"
        )

        for course in results:
            area_name = course.get("area_name", "")
            area_text = course.get("area", "")

            if area_name:
                area_text = f"{area_text} — {area_name}"

            print(
                f"{course['course_code']} — {course['course_title']}\n"
                f"Area: {area_text}\n"
                f"Offering unit: {course.get('offering_unit', '')}\n"
                f"Level: {course.get('level', '')}\n"
                f"Available in: {', '.join(course.get('terms', [])) or 'Not specified'}\n"
                f"Cross-institutional: {'Yes' if course.get('cross_institutional') else 'No'}\n"
                f"Partner institutions: {', '.join(course.get('partner_institutions', [])) or 'None'}\n"
                f"With exam: {'Yes' if course.get('with_exam') else 'No'}\n"
            )

        return

    if args.csv_file and args.aims_html:
        parser.error("Choose either a CSV file or --aims-html, not both.")

    if not args.csv_file and not args.aims_html:
        parser.print_help()
        return
    if args.aims_html and args.catalog:
        try:
            courses = load_course_catalog(args.catalog)
            plans = generate_plans(
                args.aims_html,
                courses,
                max_results=args.max_results,
                min_credits=args.min_credits,
                max_credits=args.max_credits,
                required_courses=args.required,
                preferred_days=args.prefer_days,
                required_sections=args.require_section,
                avoid_days=args.avoid_days,
            )
        except (OSError, ValueError) as error:
            parser.error(str(error))

        if not plans:
            print("No clash-free course plans were found.")
            return

        print(f"Found {len(plans)} valid course plan(s):\n")

        for number, plan in enumerate(plans, start=1):
            preferred_label = (
                f", {plan.preferred_day_count} preferred day(s)"
                if plan.preferred_day_count
                else ""
            )

            print(
                f"Plan {number} — {plan.total_credits} credits"
                f"{preferred_label}"
            )
            for section in plan.sections:
                print(
                    f"  {section.course_code} {section.section} "
                    f"{section.day} {section.start}-{section.end} "
                    f"{section.location}"
                )

            print()

        if args.export_plan is not None:
            if not (args.semester_start and args.semester_end):
                parser.error(
                    "--semester-start and --semester-end are required "
                    "when using --export-plan"
                )

            plan_index = args.export_plan - 1

            if plan_index < 0 or plan_index >= len(plans):
                parser.error(
                    f"Plan {args.export_plan} does not exist. "
                    f"Choose a plan from 1 to {len(plans)}."
                )

            export_plan_ics(
                args.aims_html,
                plans[plan_index],
                args.output,
                args.semester_start,
                args.semester_end,
                exclusions_path=args.exclusions,
            )

            print(f"Exported plan {args.export_plan} to {args.output}")

        return
    
    try:
        if args.aims_html:
            sessions = load_aims_html(args.aims_html)
            print(
                "AIMS import: only scheduled grid classes are included. "
                "Sections without dates/times are not exported."
            )
        else:
            sessions = load_sessions(args.csv_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    conflicts = find_conflicts(sessions)
    gaps = find_gaps(sessions, args.min_gap)

    print(format_timetable(sessions))
    print(f"\nLoaded {len(sessions)} class sessions.")
    print(f"Found {len(conflicts)} clash(es).")
    print(format_gaps(gaps))

    for first, second in conflicts:
        print(
            f"CLASH: {first['course_code']} {first['type']} "
            f"({first['day']} {first['start_time']}-{first['end_time']}) overlaps "
            f"{second['course_code']} {second['type']} "
            f"({second['day']} {second['start_time']}-{second['end_time']})"
        )

    if args.export:
        output = export_ics(
            sessions,
            args.output,
            args.semester_start,
            args.semester_end,
            exclusions_path=args.exclusions,
        )
        print(f"Calendar exported to {output}")


if __name__ == "__main__":
    main()