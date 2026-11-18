import argparse
import csv
import json
import os
from pathlib import Path
import sys
from typing import TextIO

from .calendar_export import export_ics
from .conflicts import find_conflicts
from .timetable import format_timetable
from .aims import load_aims_html

from .course_catalog import load_course_catalog, load_credit_catalogs
from .planner import (
    calculate_course_credits,
    generate_plans,
    generate_aims_ge_plans,
    export_plan_ics,
)

from .ge_courses import get_ge_course_info, search_ge_courses
from .ge_importer import update_ge_courses_from_html

from .aims_table_parser import parse_aims_table
from .aims_fit import (
    bundle_preferred_day_count,
    convert_aims_sessions,
    fitting_registration_bundles,
    registration_bundle_conflicts,
)

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


def _aims_path_config_file() -> Path:
    config_root = Path(
        os.environ.get("APPDATA")
        or str(Path.home() / ".config")
    )
    return config_root / "cityuschedule" / "aims_html_path.txt"


def _load_saved_aims_path() -> str | None:
    config_file = _aims_path_config_file()
    try:
        saved_path = config_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as error:
        _print_red(f"Could not read saved AIMS path: {error}")
        return None
    return saved_path or None


def _save_aims_path(path: str) -> None:
    config_file = _aims_path_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(path, encoding="utf-8")


def _prompt_path(label: str, default: str | None = None) -> str | None:
    default_text = f" [{default}]" if default else ""
    value = input(f"{label}{default_text}: ").strip()
    if not value:
        return default
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def _colorize(
    text: str,
    color: str,
    file: TextIO | None = None,
) -> str:
    output = sys.stdout if file is None else file
    if output.isatty() and "NO_COLOR" not in os.environ:
        return f"\033[{color}m{text}\033[0m"
    return text


def _print_color(
    text: str,
    color: str,
    file: TextIO | None = None,
) -> None:
    output = sys.stdout if file is None else file
    print(_colorize(text, color, output), file=output)


def _print_green(text: str) -> None:
    _print_color(text, "32")


def _print_yellow(text: str) -> None:
    _print_color(text, "33")


def _print_blue(text: str) -> None:
    _print_color(text, "34")


def _print_red(text: str, file: TextIO | None = None) -> None:
    _print_color(text, "31", file)


class _CityUScheduleArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        _print_red(
            f"{self.prog}: error: {message}",
            file=sys.stderr,
        )
        self.exit(2)


def _menu_command(
    choice: str,
    saved_aims_path: str | None = None,
) -> tuple[list[str] | None, str | None]:
    if choice == "1":
        path = _prompt_path("CSV timetable path")
        return ([path], None) if path else (None, None)

    if choice == "2":
        path = _prompt_path(
            "AIMS timetable HTML path (enter a new path to change it)",
            saved_aims_path,
        )
        return (
            (["--aims-html", path], path)
            if path
            else (None, None)
        )

    if choice == "3":
        path = saved_aims_path or _prompt_path(
            "Saved AIMS timetable HTML path"
        )
        return (
            (["--aims-html", path, "--paste-aims"], path)
            if path
            else (None, None)
        )

    if choice == "4":
        keyword = input("GE search keyword: ").strip()
        return (
            (["--ge-search", keyword], None)
            if keyword
            else (None, None)
        )

    if choice == "5":
        course_code = input("GE course code: ").strip()
        return (
            (["--ge-info", course_code], None)
            if course_code
            else (None, None)
        )

    if choice == "6":
        source_type = input("Export source (CSV or AIMS): ").strip().upper()
        if source_type not in {"CSV", "AIMS"}:
            _print_red("Choose CSV or AIMS.")
            return None, None

        if source_type == "AIMS":
            path = saved_aims_path or _prompt_path("AIMS timetable HTML path")
        else:
            path = _prompt_path("CSV file path")
        if not path:
            return None, None

        command = [path] if source_type == "CSV" else [
            "--aims-html",
            path,
        ]
        command.append("--export")

        output = _prompt_path("Output .ics path", "cityu_timetable.ics")
        if output:
            command.extend(["--output", output])

        start = input(
            "Semester start [2026-08-31]: "
        ).strip()
        if start:
            command.extend(["--semester-start", start])

        end = input(
            "Semester end [2026-11-28]: "
        ).strip()
        if end:
            command.extend(["--semester-end", end])

        return command, path if source_type == "AIMS" else None

    if choice == "7":
        aims_path = saved_aims_path or _prompt_path(
            "Saved AIMS timetable HTML path"
        )
        catalogue_path = _prompt_path(
            "Course timetable catalogue JSON path"
        )
        if not aims_path or not catalogue_path:
            return None, None
        return (
            [
                "--aims-html",
                aims_path,
                "--timetable-catalog",
                catalogue_path,
            ],
            aims_path,
        )

    if choice == "8":
        html_path = _prompt_path("Saved GE course HTML path")
        if not html_path:
            return None, None
        output_path = _prompt_path(
            "Output JSON path",
            "data/ge_courses.json",
        )
        command = ["--ge-html", html_path]
        if output_path:
            command.extend(["--ge-output", output_path])
        return command, None

    return None, None


def interactive_menu() -> None:
    saved_aims_path = _load_saved_aims_path()
    while True:
        if saved_aims_path:
            _print_yellow(f"\nRemembered AIMS HTML: {saved_aims_path}")
        _print_yellow(
            "\nCityU Schedule\n"
            "1. Check a CSV timetable\n"
            "2. Check or change saved AIMS timetable\n"
            "3. Paste and check an AIMS course offering\n"
            "4. Search GE courses\n"
            "5. Show GE course details\n"
            "6. Export a timetable calendar\n"
            "7. Generate course plans\n"
            "8. Import GE courses from HTML\n"
            "0. Exit"
        )
        try:
            choice = input(
                _colorize("Choose an option: ", "33")
            ).strip()
            if choice in {"0", "q", "Q"}:
                return

            command, aims_path_to_save = _menu_command(
                choice,
                saved_aims_path,
            )
        except EOFError:
            return

        if command is None:
            if choice not in {"1", "2", "3", "4", "5", "6", "7", "8"}:
                _print_red("Choose an option from 0 to 8.")
            else:
                _print_red("Required input was not provided.")
            continue

        try:
            main(command)
        except SystemExit as error:
            if error.code:
                print(
                    "\nTask failed. Returning to the menu; "
                    "choose another option or 0 to exit."
                )
            continue

        if aims_path_to_save:
            saved_aims_path = aims_path_to_save
            try:
                _save_aims_path(aims_path_to_save)
            except OSError as error:
                _print_red(f"Could not save AIMS path: {error}")


def main(argv: list[str] | None = None) -> None:
    command_line = sys.argv[1:] if argv is None else argv
    if not command_line:
        interactive_menu()
        return

    parser = _CityUScheduleArgumentParser(
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
        "--export",
        action="store_true",
        help="Export the timetable as an .ics calendar file",
    )

    parser.add_argument(
        "--exclusions",
        help="JSON file containing holidays and teaching breaks to exclude",
    )
    parser.add_argument(
        "--timetable-catalog",
        nargs="+",
        help="JSON timetable catalogue(s) containing course sections for planning",
    )

    parser.add_argument(
        "--credit-catalog",
        nargs="+",
        help="JSON credit catalogue(s) containing course credits",
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
        "--add-ge",
        type=int,
        default=0,
        help="Number of GE courses to add to the fixed AIMS timetable",
    )

    parser.add_argument(
        "--ge-bundles",
        help="JSON file containing complete GE section combinations",
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
        help=(
            "Days to prefer when ranking plans or AIMS paste bundles, "
            "such as Mon Tue Wed"
        ),
    )
    parser.add_argument(
        "--require-section",
        nargs="+",
        help="Exact course sections that must appear, such as TEST101 C01",
    )
    parser.add_argument(
        "--avoid-days",
        nargs="+",
        help=(
            "Days that plans or AIMS paste bundles must not use, "
            "such as Fri Sat"
        ),
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

    parser.add_argument(
        "--paste-aims",
        action="store_true",
        help="Paste one AIMS course table and check weekly timetable fit",
    )

    args = parser.parse_args(command_line)

    if args.paste_aims:
        if not args.aims_html:
            parser.error("--paste-aims requires --aims-html.")

        if args.csv_file:
            parser.error(
                "--paste-aims uses --aims-html, not a CSV timetable."
            )

        if (
            args.timetable_catalog
            or args.add_ge
            or args.ge_bundles
            or args.export
            or args.export_plan is not None
            or args.ge_html
            or args.ge_info
            or args.ge_search
        ):
            parser.error(
                "Run --paste-aims separately from timetable catalogue planning, "
                "GE lookup/import, and export."
            )

        try:
            base_rows = load_aims_html(args.aims_html)
            base_sessions = convert_aims_sessions(base_rows)
            credit_courses = load_credit_catalogs(args.credit_catalog)

            while True:
                _print_yellow("Paste ONE course's complete AIMS offering table.")
                _print_yellow(
                    "Finish by typing END on a new line and pressing Enter."
                )
                print()

                lines = []
                empty_paste = False
                while True:
                    try:
                        line = input()
                    except EOFError:
                        raise ValueError(
                            "Input ended before END. Paste again and finish "
                            "with END on its own line."
                        ) from None

                    if line.strip() == "END":
                        break
                    if not line.strip() and not lines:
                        empty_paste = True
                        break

                    if line.strip():
                        lines.append(line)

                if empty_paste or not any(line.strip() for line in lines):
                    _print_red(
                        "No table was entered. Please paste the AIMS table "
                        "and try again."
                    )
                    continue

                pasted_table = "\n".join(lines)
                try:
                    parse_aims_table(pasted_table)
                except ValueError as error:
                    if not str(error).startswith("Course code is required."):
                        _print_red(
                            "That doesn't look like a complete AIMS course "
                            "offering table. Paste the full table, including "
                            "its CRN, Section, and Credit rows, and try again."
                        )
                        continue

                while True:
                    _print_yellow(
                        "If the copied table did not include the course "
                        "heading, enter its course code (for example GE2130); "
                        "otherwise press Enter:"
                    )
                    try:
                        course_code = input().strip() or None
                    except EOFError:
                        raise ValueError(
                            "Input ended before the course code was confirmed."
                        ) from None

                    try:
                        table = parse_aims_table(
                            pasted_table,
                            course_code=course_code,
                        )
                    except ValueError as error:
                        if (
                            course_code is None
                            and str(error).startswith("Course code is required.")
                        ):
                            _print_red(
                                "A course code is required for this table. "
                                "Enter it now; do not press Enter."
                            )
                            continue
                        raise
                    break

                break
            _print_yellow(
                "Enter unavailable section codes separated by spaces or "
                "commas, or press Enter for none:"
            )
            try:
                unavailable_sections = list({
                    section.upper()
                    for section in input().replace(",", " ").split()
                })
            except EOFError:
                raise ValueError(
                    "Input ended before unavailable sections were "
                    "confirmed. Press Enter to continue without exclusions."
                ) from None

            known_sections = {
                session.section.upper()
                for session in table.sessions
            }
            unknown_sections = (
                set(unavailable_sections) - known_sections
            )
            if unknown_sections:
                raise ValueError(
                    "Unknown section code(s): "
                    + ", ".join(sorted(unknown_sections))
                )

            pasted_course_credits = table.course_credit
            aims_credits, unknown_aims_courses = calculate_course_credits(
                {
                    row["course_code"]
                    for row in base_rows
                },
                credit_courses,
            )
            candidates = table.registration_bundles()
            fitting = fitting_registration_bundles(
                table,
                base_sessions,
                preferred_days=args.prefer_days,
                avoid_days=args.avoid_days,
                unavailable_sections=unavailable_sections,
            )

        except (OSError, ValueError) as error:
            parser.error(str(error))

        print()
        print(f"Course: {table.course_code}")
        print(f"Parsed sections: {len(table.sessions)}")
        print(f"Scheduled sections: {len(table.scheduled_sessions)}")
        print(
            "Ignored unscheduled sections: "
            f"{len(table.sessions) - len(table.scheduled_sessions)}"
        )
        print(f"Candidate complete bundles: {len(candidates)}")
        print(f"Bundles fitting weekly timetable: {len(fitting)}")
        if unavailable_sections:
            print(
                "Unavailable sections excluded: "
                + ", ".join(sorted(unavailable_sections))
            )
        print()
        _print_blue(f"Pasted course credits: {pasted_course_credits}")
        if unknown_aims_courses:
            missing_codes = ", ".join(unknown_aims_courses)
            print(
                "AIMS timetable credits: incomplete "
                f"(known subtotal {aims_credits}; missing: "
                f"{missing_codes})"
            )
            print(
                "Combined total if added: incomplete "
                f"(known subtotal "
                f"{aims_credits + pasted_course_credits}; "
                f"missing: {missing_codes})"
            )
        else:
            combined_credits = aims_credits + pasted_course_credits
            _print_blue(f"AIMS timetable credits: {aims_credits}")
            _print_blue(
                f"Combined total if added: {combined_credits}"
            )

        if not candidates:
            _print_red(
                "No complete scheduled bundle was generated. "
                "Check the pasted table and section-family rules."
            )
        elif not fitting:
            _print_red(
                "No complete bundle fits: each has an internal overlap, "
                "overlaps the base timetable, lacks sufficient travel time, "
                "or uses an avoided day."
            )
        else:
            _print_green("Suggested bundles:")
            by_section = {
                session.section: session
                for session in table.scheduled_sessions
            }

            for number, bundle in enumerate(fitting, start=1):
                preferred_count = bundle_preferred_day_count(
                    table,
                    bundle,
                    args.prefer_days,
                )
                preferred_label = (
                    f" ({preferred_count} preferred day(s))"
                    if preferred_count
                    else ""
                )
                print()
                _print_green(
                    f"{number}. {' + '.join(bundle)}{preferred_label}"
                )

                for section in bundle:
                    session = by_section[section]
                    _print_green(
                        f"   CRN {session.crn}: {session.section} "
                        f"{session.day} {session.start_time}-{session.end_time}"
                    )

        fitting_set = set(fitting)
        rejected = [
            bundle
            for bundle in candidates
            if bundle not in fitting_set
        ]

        if rejected:
            _print_red("\nRejected bundles:")

            for number, bundle in enumerate(rejected, start=1):
                _print_red(f"\n{number}. {' + '.join(bundle)}")

                reasons = registration_bundle_conflicts(
                    table,
                    bundle,
                    base_sessions,
                    avoid_days=args.avoid_days,
                    unavailable_sections=unavailable_sections,
                )

                for reason in reasons:
                    _print_red(f"   - {reason}")

        print()
        print(
            "Weekly time-fit and travel between known buildings only. "
            "Eligibility, seat availability, date ranges, and multiple "
            "meeting rows are not validated."
        )
        return

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
    if args.aims_html and (args.timetable_catalog or args.credit_catalog):
        try:
            timetable_courses = []
            credit_courses = []

            for catalog_path in args.timetable_catalog or []:
                timetable_courses.extend(load_course_catalog(catalog_path))

            for catalog_path in args.credit_catalog or []:
                credit_courses.extend(load_course_catalog(catalog_path))

            if args.add_ge > 0:
                if not args.ge_bundles:
                    raise ValueError(
                        "--ge-bundles is required when using --add-ge"
                    )

                with open(
                    args.ge_bundles,
                    "r",
                    encoding="utf-8-sig",
                ) as file:
                    course_bundles = json.load(file)

                ge_courses = [
                    course
                    for course in timetable_courses
                    if course.code.upper().startswith("GE")
                ]

                plans = generate_aims_ge_plans(
                    args.aims_html,
                    ge_courses,
                    credit_courses,
                    args.add_ge,
                    max_results=args.max_results,
                    min_credits=args.min_credits,
                    max_credits=args.max_credits,
                    preferred_days=args.prefer_days,
                    avoid_days=args.avoid_days,
                    course_bundles=course_bundles,
                )
            else:

                plans = generate_plans(
                    args.aims_html,
                    timetable_courses,
                    credit_courses=credit_courses,
                    max_results=args.max_results,
                    min_credits=args.min_credits,
                    max_credits=args.max_credits,
                    required_courses=args.required,
                    preferred_days=args.prefer_days,
                    required_sections=args.require_section,
                    avoid_days=args.avoid_days,
                    min_gap=args.min_gap,                
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

    print(format_timetable(sessions))
    print(f"\nLoaded {len(sessions)} class sessions.")
    print(f"Found {len(conflicts)} clash(es).")

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