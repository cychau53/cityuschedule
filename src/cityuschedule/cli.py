import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TextIO

from .aims import load_aims_html
from .aims_fit import (
    DAY_NAMES,
    bundle_preferred_day_count,
    convert_aims_sessions,
    fitting_registration_bundles,
    registration_bundle_conflicts,
)
from .aims_table_parser import parse_aims_table
from .calendar_export import export_ics
from .conflicts import find_conflicts
from .course_catalog import load_course_catalog, load_credit_catalogs
from .ge_courses import get_ge_course_info, search_ge_courses
from .ge_importer import update_ge_courses_from_html
from .planner import (
    calculate_course_credits,
    export_plan_ics,
    generate_aims_ge_plans,
    generate_plans,
)
from .timetable import format_timetable



@dataclass(frozen=True)
class BasicSettings:
    prefer_days: tuple[str, ...] = ()
    avoid_days: tuple[str, ...] = ()
    min_credits: int | None = None
    max_credits: int | None = None


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


def _cityuschedule_config_dir() -> Path:
    config_root = Path(
        os.environ.get("APPDATA")
        or str(Path.home() / ".config")
    )
    return config_root / "cityuschedule"


def _aims_path_config_file() -> Path:
    return _cityuschedule_config_dir() / "aims_html_path.txt"


def _basic_settings_config_file() -> Path:
    return _cityuschedule_config_dir() / "basic_settings.json"
def _saved_bundles_file() -> Path:
    return _cityuschedule_config_dir() / "saved_bundles.json"


def _load_saved_bundles() -> list[dict]:
    path = _saved_bundles_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_bundles_to_disk(bundles: list[dict]) -> None:
    path = _saved_bundles_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


_DAY_ALIASES = {
    "m": "Mon",
    "mon": "Mon",
    "monday": "Mon",
    "t": "Tue",
    "tue": "Tue",
    "tuesday": "Tue",
    "w": "Wed",
    "wed": "Wed",
    "wednesday": "Wed",
    "r": "Thu",
    "thu": "Thu",
    "thursday": "Thu",
    "f": "Fri",
    "fri": "Fri",
    "friday": "Fri",
    "s": "Sat",
    "sat": "Sat",
    "saturday": "Sat",
    "u": "Sun",
    "sun": "Sun",
    "sunday": "Sun",
}


def _parse_day_list(value: str) -> tuple[str, ...]:
    days = []
    for token in value.replace(",", " ").split():
        day = _DAY_ALIASES.get(token.casefold())
        if day is None:
            raise ValueError(
                f"Unrecognized day {token!r}. Use Mon, Tue, Wed, Thu, "
                "Fri, Sat, or Sun."
            )
        if day not in days:
            days.append(day)
    return tuple(days)


def _load_basic_settings() -> BasicSettings:
    settings_file = _basic_settings_config_file()
    try:
        values = json.loads(settings_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return BasicSettings()
    except (OSError, json.JSONDecodeError) as error:
        _print_red(f"Could not read basic settings: {error}")
        return BasicSettings()

    try:
        if not isinstance(values, dict):
            raise TypeError("Basic settings must be a JSON object.")

        prefer_days = values.get("prefer_days", [])
        avoid_days = values.get("avoid_days", [])
        min_credits = values.get("min_credits")
        max_credits = values.get("max_credits")
        if not isinstance(prefer_days, list) or not all(
            isinstance(day, str) for day in prefer_days
        ):
            raise ValueError("Preferred days in saved settings must be a list.")
        if not isinstance(avoid_days, list) or not all(
            isinstance(day, str) for day in avoid_days
        ):
            raise ValueError("Avoided days in saved settings must be a list.")

        normalized_prefer = _parse_day_list(" ".join(prefer_days))
        normalized_avoid = _parse_day_list(" ".join(avoid_days))
        for label, credits in (
            ("minimum", min_credits),
            ("maximum", max_credits),
        ):
            if credits is not None and (
                type(credits) is not int or credits < 0
            ):
                raise ValueError(
                    f"Saved {label} credits must be a non-negative integer."
                )
        if (
            min_credits is not None
            and max_credits is not None
            and min_credits > max_credits
        ):
            raise ValueError(
                "Saved minimum credits exceed maximum credits."
            )
        if set(normalized_prefer) & set(normalized_avoid):
            raise ValueError(
                "A day cannot be both preferred and avoided."
            )
    except (TypeError, ValueError) as error:
        _print_red(f"Invalid basic settings: {error}")
        return BasicSettings()

    return BasicSettings(
        prefer_days=normalized_prefer,
        avoid_days=normalized_avoid,
        min_credits=min_credits,
        max_credits=max_credits,
    )


def _save_basic_settings(settings: BasicSettings) -> None:
    values = {
        "prefer_days": list(settings.prefer_days),
        "avoid_days": list(settings.avoid_days),
        "min_credits": settings.min_credits,
        "max_credits": settings.max_credits,
    }
    settings_file = _basic_settings_config_file()
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(
        json.dumps(values, indent=2) + "\n",
        encoding="utf-8",
    )


def _prompt_days(label: str, current: tuple[str, ...]) -> tuple[str, ...]:
    current_value = ", ".join(current) or "none"
    response = input(
        f"{label} [{current_value}] (blank keeps, none clears): "
    ).strip()
    if not response:
        return current
    if response.casefold() in {"none", "clear"}:
        return ()
    return _parse_day_list(response)


def _prompt_credit_limit(
    label: str,
    current: int | None,
) -> int | None:
    current_value = str(current) if current is not None else "none"
    response = input(
        f"{label} [{current_value}] (blank keeps, none clears): "
    ).strip()
    if not response:
        return current
    if response.casefold() in {"none", "clear"}:
        return None
    try:
        credits = int(response)
    except ValueError:
        raise ValueError(f"{label} must be a non-negative integer.") from None
    if credits < 0:
        raise ValueError(f"{label} must be a non-negative integer.")
    return credits


def _prompt_basic_settings(current: BasicSettings) -> BasicSettings:
    while True:
        _print_yellow(
            "Basic settings: days may be entered as Mon/Tue/Wed/Thu/Fri/Sat/Sun "
            "or M/T/W/R/F/S/U."
        )
        try:
            prefer_days = _prompt_days("Prefer days", current.prefer_days)
            avoid_days = _prompt_days("Avoid days", current.avoid_days)
            min_credits = _prompt_credit_limit(
                "Minimum credits",
                current.min_credits,
            )
            max_credits = _prompt_credit_limit(
                "Maximum credits",
                current.max_credits,
            )
            if set(prefer_days) & set(avoid_days):
                raise ValueError(
                    "A day cannot be both preferred and avoided."
                )
            if (
                min_credits is not None
                and max_credits is not None
                and min_credits > max_credits
            ):
                raise ValueError(
                    "Minimum credits cannot exceed maximum credits."
                )
        except ValueError as error:
            _print_red(str(error))
            continue

        return BasicSettings(
            prefer_days=prefer_days,
            avoid_days=avoid_days,
            min_credits=min_credits,
            max_credits=max_credits,
        )


def _basic_settings_arguments(settings: BasicSettings) -> list[str]:
    arguments = []
    if settings.prefer_days:
        arguments.extend(["--prefer-days", *settings.prefer_days])
    if settings.avoid_days:
        arguments.extend(["--avoid-days", *settings.avoid_days])
    if settings.min_credits is not None:
        arguments.extend(["--min-credits", str(settings.min_credits)])
    if settings.max_credits is not None:
        arguments.extend(["--max-credits", str(settings.max_credits)])
    return arguments


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


def _exit_if_requested(value: str) -> None:
    if value.strip().casefold() in {"0", "q"}:
        raise SystemExit(0)


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


def _print_purple(text: str) -> None:
    _print_color(text, "95")


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
    settings: BasicSettings | None = None,
) -> tuple[list[str] | None, str | None]:
    settings = settings or BasicSettings()

    if choice == "2":
        path = _prompt_path("CSV timetable path")
        return ([path], None) if path else (None, None)

    if choice == "3":
        path = _prompt_path(
            "AIMS timetable HTML path (enter a new path to change it)",
            saved_aims_path,
        )
        return (
            (["--aims-html", path], path)
            if path
            else (None, None)
        )

    if choice == "4":
        path = saved_aims_path or _prompt_path(
            "Saved AIMS timetable HTML path"
        )
        if not path:
            return None, None
        command = ["--aims-html", path, "--paste-aims"]
        command.extend(_basic_settings_arguments(settings))
        return command, path

    if choice == "5":
        keyword = input("GE search keyword: ").strip()
        return (
            (["--ge-search", keyword], None)
            if keyword
            else (None, None)
        )

    if choice == "6":
        course_code = input("GE course code: ").strip()
        return (
            (["--ge-info", course_code], None)
            if course_code
            else (None, None)
        )

    if choice == "7":
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

    if choice == "8":
        aims_path = saved_aims_path or _prompt_path(
            "Saved AIMS timetable HTML path"
        )
        catalogue_path = _prompt_path(
            "Course timetable catalogue JSON path"
        )
        if not aims_path or not catalogue_path:
            return None, None
        command = [
            "--aims-html",
            aims_path,
            "--timetable-catalog",
            catalogue_path,
        ]
        command.extend(_basic_settings_arguments(settings))
        return command, aims_path

    if choice == "9":
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
    basic_settings = _load_basic_settings()
    while True:
        if saved_aims_path:
            _print_yellow(f"\nRemembered AIMS HTML: {saved_aims_path}")
        _print_yellow(
            "\nCityU Schedule\n"
            "1. Basic settings\n"
            "2. Check a CSV timetable\n"
            "3. Check or change saved AIMS timetable\n"
            "4. Paste and check an AIMS course offering\n"
            "5. Search GE courses\n"
            "6. Show GE course details\n"
            "7. Export a timetable calendar\n"
            "8. Generate course plans\n"
            "9. Import GE courses from HTML\n"
            "10. Bundles saved\n"
            "0. Exit\n"
            "Type delete all or delete names joined by 'and' to clear data."
        )
        try:
            choice = input(
                _colorize("Choose an option: ", "33")
            ).strip()
            if choice.casefold() in {"0", "q"}:
                return

            delete_command = choice.casefold()
            if delete_command.startswith("delete"):
                try:
                    if delete_command == "delete all":
                        _basic_settings_config_file().unlink(
                            missing_ok=True
                        )
                        _aims_path_config_file().unlink(missing_ok=True)
                        basic_settings = BasicSettings()
                        saved_aims_path = None
                        message = (
                            "All saved settings and AIMS path deleted."
                        )
                    else:
                        setting_fields = {
                            "avoid": (
                                "avoid_days",
                                (),
                                "avoid days",
                            ),
                            "prefer": (
                                "prefer_days",
                                (),
                                "preferred days",
                            ),
                            "min": (
                                "min_credits",
                                None,
                                "minimum credits",
                            ),
                            "max": (
                                "max_credits",
                                None,
                                "maximum credits",
                            ),
                        }
                        targets = list(
                            dict.fromkeys(
                                target.strip()
                                for target in delete_command[
                                    len("delete"):
                                ].split("and")
                            )
                        )
                        if not targets or any(
                            target not in {*setting_fields, "aims"}
                            for target in targets
                        ):
                            raise ValueError(
                                "Use delete all, delete avoid, delete "
                                "prefer, delete min, delete max, or "
                                "delete AIMS. Join multiple names with "
                                "'and'."
                            )

                        if "aims" in targets:
                            _aims_path_config_file().unlink(
                                missing_ok=True
                            )
                            saved_aims_path = None

                        labels = []
                        for target in targets:
                            if target == "aims":
                                labels.append("AIMS path")
                                continue
                            field, empty_value, label = setting_fields[
                                target
                            ]
                            basic_settings = replace(
                                basic_settings,
                                **{field: empty_value},
                            )
                            labels.append(label)
                        if any(target != "aims" for target in targets):
                            _save_basic_settings(basic_settings)
                        message = (
                            "Saved " + " and ".join(labels) + " deleted."
                        )
                except OSError as error:
                    basic_settings = _load_basic_settings()
                    saved_aims_path = _load_saved_aims_path()
                    _print_red(
                        f"Could not delete saved information: {error}"
                    )
                except ValueError as error:
                    _print_red(str(error))
                else:
                    _print_green(message)
                continue

            if choice == "1":
                basic_settings = _prompt_basic_settings(basic_settings)
                try:
                    _save_basic_settings(basic_settings)
                except OSError as error:
                    _print_red(f"Could not save basic settings: {error}")
                else:
                    _print_green("Basic settings saved.")
                continue
            if choice == "10":
                _show_saved_bundles()
                continue

            command, aims_path_to_save = _menu_command(
                choice,
                saved_aims_path,
                basic_settings,
            )
        except EOFError:
            return

        if command is None:
            if choice not in {
                "2", "3", "4", "5", "6", "7", "8", "9", "10"
            }:
                _print_red("Choose an option from 0 to 10.")
            else:
                _print_red("Required input was not provided.")
            continue

        try:
            main(command)
        except SystemExit as error:
            if error.code == 0:
                return
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

    if (
        args.min_credits is not None
        and args.max_credits is not None
        and args.min_credits > args.max_credits
    ):
        parser.error("--min-credits cannot exceed --max-credits.")

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

                    if not lines:
                        _exit_if_requested(line)
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
                        course_code_input = input()
                    except EOFError:
                        raise ValueError(
                            "Input ended before the course code was confirmed."
                        ) from None
                    _exit_if_requested(course_code_input)
                    course_code = course_code_input.strip() or None

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
                unavailable_input = input()
            except EOFError:
                raise ValueError(
                    "Input ended before unavailable sections were "
                    "confirmed. Press Enter to continue without exclusions."
                ) from None
            _exit_if_requested(unavailable_input)
            unavailable_sections = list({
                section.upper()
                for section in unavailable_input.replace(",", " ").split()
            })

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
        preferred_days = {
            day.capitalize() for day in (args.prefer_days or [])
        }
        avoided_days = {
            day.capitalize() for day in (args.avoid_days or [])
        }
        if preferred_days or avoided_days:
            print()
            if preferred_days:
                _print_purple(
                    "Current prefer days: "
                    + ", ".join(sorted(preferred_days))
                )
            if avoided_days:
                _print_purple(
                    "Current avoid days: "
                    + ", ".join(sorted(avoided_days))
                )
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
            if (
                args.min_credits is not None
                or args.max_credits is not None
            ):
                _print_red(
                    "Warning: credit limits could not be checked because "
                    "some AIMS course credits are missing."
                )
        else:
            combined_credits = aims_credits + pasted_course_credits
            _print_blue(f"AIMS timetable credits: {aims_credits}")
            _print_blue(
                f"Combined total if added: {combined_credits}"
            )
            if (
                args.min_credits is not None
                and combined_credits < args.min_credits
            ):
                _print_red(
                    f"Warning: combined credits ({combined_credits}) are "
                    f"below the minimum ({args.min_credits})."
                )
            if (
                args.max_credits is not None
                and combined_credits > args.max_credits
            ):
                _print_red(
                    f"Warning: combined credits ({combined_credits}) exceed "
                    f"the maximum ({args.max_credits})."
                )

        print()
        by_section = {
            session.section: session
            for session in table.scheduled_sessions
        }
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
            for number, bundle in enumerate(fitting, start=1):
                preferred_count = bundle_preferred_day_count(
                    table,
                    bundle,
                    args.prefer_days,
                )
                print()
                bundle_label = f"{number}. {' + '.join(bundle)}"
                if preferred_count:
                    print(
                        _colorize(bundle_label, "32")
                        + " "
                        + _colorize("(match with prefer days)", "95")
                    )
                else:
                    _print_green(bundle_label)

                for section in bundle:
                    session = by_section[section]
                    session_label = (
                        f"   CRN {session.crn}: {session.section} "
                        f"{session.day} "
                        f"{session.start_time}-{session.end_time}"
                    )
                    day_name = DAY_NAMES.get(session.day or "")
                    if day_name in preferred_days:
                        _print_purple(session_label)
                    else:
                        _print_green(session_label)

        fitting_set = set(fitting)
        rejected_bundles = [
            bundle
            for bundle in candidates
            if bundle not in fitting_set
        ]
        rejected = [
            (
                bundle,
                registration_bundle_conflicts(
                    table,
                    bundle,
                    base_sessions,
                    avoid_days=args.avoid_days,
                    unavailable_sections=unavailable_sections,
                ),
            )
            for bundle in rejected_bundles
        ]
        rejected.sort(
            key=lambda item: not (
                len(item[1]) == 1
                and item[1][0].startswith("Uses avoided day(s):")
            )
        )

        if rejected:
            _print_red("\nRejected bundles:")

            for number, (bundle, reasons) in enumerate(rejected, start=1):
                has_avoided_day = any(
                    reason.startswith("Uses avoided day(s):")
                    for reason in reasons
                )
                if has_avoided_day:
                    bundle_label = _colorize(
                        f"{number}. {' + '.join(bundle)}",
                        "31",
                    )
                    print(
                        f"\n{bundle_label} "
                        f"{_colorize('(crash with avoid days)', '95')}"
                    )
                    for section in bundle:
                        session = by_section[section]
                        session_label = (
                            f"   CRN {session.crn}: {session.section} "
                            f"{session.day} "
                            f"{session.start_time}-{session.end_time}"
                        )
                        if DAY_NAMES.get(session.day or "") in avoided_days:
                            _print_purple(session_label)
                        else:
                            _print_red(session_label)
                else:
                    _print_red(f"\n{number}. {' + '.join(bundle)}")

                for reason in reasons:
                    if (
                        has_avoided_day
                        and reason.startswith("Uses avoided day(s):")
                    ):
                        _print_purple(f"   - {reason}")
                    else:
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
        save_choice = input(
        "Save plans (e.g. 1 or 1,2, or Enter to skip): "
    ).strip()
    if save_choice:
        selected_indexes: list[int] = []
        for raw_item in save_choice.split(","):
            item = raw_item.strip()
            if not item.isdigit():
                continue
            idx = int(item) - 1
            if 0 <= idx < len(plans) and idx not in selected_indexes:
                selected_indexes.append(idx)

        if selected_indexes:
            from dataclasses import asdict, is_dataclass

            saved_bundles = _load_saved_bundles()
            for idx in selected_indexes:
                chosen_plan = plans[idx]
                plan_data = (
                    asdict(chosen_plan)
                    if is_dataclass(chosen_plan)
                    else {
                        "total_credits": getattr(chosen_plan, "total_credits", None),
                        "preferred_day_count": getattr(
                            chosen_plan, "preferred_day_count", None
                        ),
                        "sections": [
                            {
                                "course_code": getattr(s, "course_code", None),
                                "section": getattr(s, "section", None),
                                "day": getattr(s, "day", None),
                                "start": getattr(s, "start", None),
                                "end": getattr(s, "end", None),
                                "location": getattr(s, "location", None),
                            }
                            for s in getattr(chosen_plan, "sections", [])
                        ],
                    }
                )
                saved_bundles.append({
                    "plan": plan_data,
                    # 預留位置：日後爬蟲資料可直接加落呢度，例如 "scraped_info": None
                })
            try:
                _save_bundles_to_disk(saved_bundles)
                _print_green(f"Saved {len(selected_indexes)} bundle(s).")
            except OSError as error:
                _print_red(f"Could not save bundles: {error}")
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
