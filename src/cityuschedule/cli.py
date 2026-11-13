import argparse
import csv
from pathlib import Path

from .calendar_export import export_ics
from .conflicts import find_conflicts
from .gaps import find_gaps, format_gaps
from .timetable import format_timetable


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

    args = parser.parse_args()

    if args.csv_file is None:
        print("cityuschedule is installed successfully.")
        print("Usage: cityuschedule check <csv_file>")
        return

    sessions = load_sessions(args.csv_file)
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
        )
        print(f"Calendar exported to {output}")


if __name__ == "__main__":
    main()