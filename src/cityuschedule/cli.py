import argparse
import csv
from pathlib import Path

from .conflicts import find_conflicts
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

    args = parser.parse_args()

    if args.csv_file is None:
        print("cityuschedule is installed successfully.")
        print("Usage: cityuschedule check <csv_file>")
        return

    sessions = load_sessions(args.csv_file)
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


if __name__ == "__main__":
    main()