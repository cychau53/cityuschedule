from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "ge_course_information.json"
)

COURSE_CODE_PATTERN = re.compile(r"GE\d{4}[A-Z]?")

FIELDS = {
    "crn": "CRN",
    "section": "Section",
    "term": "Term",
    "type": "Type",
    "capacity": "Capacity",
    "day": "Day",
    "time": "Time",
    "building": "Building",
    "room": "Room",
    "instructor": "Instructor",
}


def normalize_course_code(course_code: str) -> str:
    """Validate and normalize a user-supplied GE course code."""
    course_code = course_code.strip().upper()

    if not COURSE_CODE_PATTERN.fullmatch(course_code):
        raise ValueError(
            f"Invalid GE course code: {course_code!r}. "
            "Expected a value such as GE1102."
        )

    return course_code


def parse_ge_course_information_html(
    html: str | bytes,
    *,
    course_code: str | None = None,
) -> list[dict]:
    """Extract section records from an HTML document."""
    soup = BeautifulSoup(html, "html.parser")
    record = {
    "crn": values["crn"],
    "section": values["section"],
    "term": values["term"],
    "capacity": (
        int(capacity)
        if capacity.isdigit()
        else capacity
    ),
    "day": values["day"],
    "time": values["time"],
    "type": values["type"],
    "building": values["building"],
    "room": values["room"],
    "instructor": (
        ", ".join(instructors)
        if instructors
        else values["instructor"]
    ),
}

records.append(record)
    found_table = False

    for table in soup.find_all("table"):
        header_row = None
        indexes = {}

        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            labels = [
                " ".join(
                    cell.get_text(" ", strip=True).split()
                ).casefold()
                for cell in cells
            ]

            if all(field in labels for field in FIELDS):
                header_row = row
                indexes = {
                    field: labels.index(field)
                    for field in FIELDS
                }
                break

        if header_row is None:
            continue

        found_table = True
        passed_header = False

        for row in table.find_all("tr"):
            if row is header_row:
                passed_header = True
                continue

            if not passed_header:
                continue

            cells = row.find_all("td", recursive=False)

            if len(cells) <= max(indexes.values()):
                continue

            record = {
                output_name: " ".join(
                    cells[indexes[field]]
                    .get_text(" ", strip=True)
                    .split()
                )
                for field, output_name in FIELDS.items()
            }

            if not record["CRN"].isdigit():
                continue

            capacity = record["Capacity"]
            if capacity.isdigit():
                record["Capacity"] = int(capacity)

            instructor_cell = cells[indexes["instructor"]]
            instructors = [
                item.get_text(" ", strip=True)
                for item in instructor_cell.find_all("li")
                if item.get_text(" ", strip=True)
            ]

            if instructors:
                record["Instructor"] = ", ".join(instructors)

            records.append(record)

    if not found_table:
        raise ValueError(
            "No recognizable Course Section table found. "
            "The page may have no published sections, require "
            "JavaScript, or use a different HTML structure."
        )

    # Remove duplicate rows, including duplicated display tables.
    unique_records = {}
    for record in records:
        key = tuple(
            record.get(field)
            for field in (
                "course_code",
                "CRN",
                "Section",
                "Term",
                "Day",
                "Time",
                "Building",
                "Room",
                "Instructor",
            )
        )
        unique_records[key] = record

    return list(unique_records.values())


def parse_ge_course_information(
    html_path: str | Path,
) -> list[dict]:
    """Read section information from a saved HTML file."""
    html_path = Path(html_path)
    filename_code = html_path.stem.strip().upper()

    course_code = (
        filename_code
        if COURSE_CODE_PATTERN.fullmatch(filename_code)
        else None
    )

    return parse_ge_course_information_html(
        html_path.read_bytes(),
        course_code=course_code,
    )


def fetch_ge_course_information(
    course_code: str,
    *,
    timeout: float = 30,
) -> list[dict]:
    """Download and parse one course page."""
    course_code = normalize_course_code(course_code)
    url = f"https://www.cityu.edu.hk/ge_info/Course/{course_code}"

    request = Request(
        url,
        headers={
            "User-Agent": "cityuschedule GE course information importer",
            "Accept": "text/html",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            html = response.read()
    except HTTPError as exc:
        raise RuntimeError(
            f"{course_code}: server returned HTTP {exc.code}."
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"{course_code}: could not download the course page: {exc}"
        ) from exc

    records = parse_ge_course_information_html(
        html,
        course_code=course_code,
    )

    if not records:
        raise ValueError(
            f"{course_code}: no section rows were extracted. "
            "Existing stored records will not be removed."
        )

    return records


def _write_records(records: list[dict], output_path: str | Path) -> None:
    """Write JSON through a temporary file before replacing the target."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")

    try:
        temporary_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _load_existing_records(output_path: str | Path) -> list[dict]:
    """Read existing data without silently ignoring invalid JSON."""
    output_path = Path(output_path)

    if not output_path.exists():
        return []

    records = json.loads(output_path.read_text(encoding="utf-8"))

    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise ValueError(
            f"{output_path} must contain a list of dictionaries."
        )

    return records


def update_ge_course_information_from_web(
    course_codes: list[str],
    output_path: str | Path = DATA_PATH,
    *,
    timeout: float = 30,
) -> list[dict]:
    """
    Fetch the requested courses and save a list of section dictionaries.

    Replaces the output file only after every requested course
    has been fetched and parsed successfully.
    """
    codes = list(
        dict.fromkeys(
            normalize_course_code(code)
            for code in course_codes
        )
    )

    if not codes:
        raise ValueError("Enter at least one GE course code.")

    records = []

    for code in codes:
        records.extend(
            fetch_ge_course_information(
                code,
                timeout=timeout,
            )
        )

    _write_records(records, output_path)

    return records

def update_ge_course_information(
    html_directory: str | Path,
    output_path: str | Path = DATA_PATH,
) -> int:
    """Preserve local-directory import, replacing the output dataset."""
    html_directory = Path(html_directory)

    if not html_directory.is_dir():
        raise NotADirectoryError(
            f"HTML directory does not exist: {html_directory}"
        )

    html_files = [
        path
        for path in sorted(html_directory.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in {"", ".htm", ".html"}
    ]

    if not html_files:
        raise ValueError("No eligible HTML files found.")

    all_records = []

    for html_file in html_files:
        try:
            all_records.extend(
                parse_ge_course_information(html_file)
            )
        except (OSError, ValueError) as exc:
            print(f"Skipping {html_file.name}: {exc}")

    if not all_records:
        raise ValueError(
            "No section records extracted. Output file left unchanged."
        )

    _write_records(all_records, output_path)
    print(f"Exported {len(all_records)} records to {output_path}")

    return len(all_records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import CityU GE course-section information."
    )
    parser.add_argument(
        "course_codes",
        nargs="*",
        help="Course codes such as GE1101 GE1102",
    )
    parser.add_argument(
        "--html-directory",
        help="Import saved HTML files instead of downloading webpages",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_PATH,
        help="Output JSON file",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="Download timeout in seconds",
    )

    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero.")

    if args.html_directory and args.course_codes:
        parser.error(
            "Use course codes or --html-directory, not both."
        )

    try:
        if args.html_directory:
            update_ge_course_information(
                args.html_directory,
                args.output,
            )
            return

        course_codes = args.course_codes

        if not course_codes:
            entered = input(
                "Enter GE course codes, separated by spaces or commas: "
            )
            course_codes = entered.replace(",", " ").split()

        summary = update_ge_course_information_from_web(
            course_codes,
            output_path=args.output,
            timeout=args.timeout,
        )

        print(
            f"\nUpdated {len(summary['updated_courses'])} course(s); "
            f"failed {len(summary['failed_courses'])} course(s).\n"
            f"Imported {summary['imported_records']} section record(s).\n"
            f"Stored records: {summary['total_records']}."
        )

        if summary["updated_courses"]:
            print(f"Saved to: {summary['output_path']}")

        if summary["failed_courses"]:
            raise SystemExit(1)

    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
