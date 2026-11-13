import argparse
import csv
from pathlib import Path


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
    print(f"Loaded {len(sessions)} class sessions from {args.csv_file}")


if __name__ == "__main__":
    main()
