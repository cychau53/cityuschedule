from __future__ import annotations

import argparse
import json
import re
import tempfile
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

COLUMNS = (
    "crn",
    "section",
    "term",
    "type",
    "capacity",
    "day",
    "time",
    "building",
    "room",
    "instructor",
)


def normalize_course_code(course_code: str) -> str:
    """Validate and normalize a GE course code."""
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
    """
    Extract section meeting rows using exactly ten lowercase keys.

    course_code is accepted for compatibility with existing callers.
    It is deliberately not included in the output.
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []
    found_table = False

    for table in soup.select("table.ax-mobile-table"):
        header_row = table.select_one("thead tr")

        if header_row is None:
            continue

        headers = [
            " ".join(cell.get_text(" ", strip=True).split()).casefold()
            for cell in header_row.find_all(
                ["th", "td"],
                recursive=False,
            )
        ]

        if not all(column in headers for column in COLUMNS):
            continue

        found_table = True
        indexes = {
            column: headers.index(column)
            for column in COLUMNS
        }

        for row in table.select("tbody > tr"):
            cells = row.find_all("td", recursive=False)

            if not cells:
                continue

            if len(cells) <= max(indexes.values()):
                if len(cells) == 1 and cells[0].has_attr("colspan"):
                    continue

                raise ValueError(
                    "A Course Section row has an unexpected "
                    f"number of columns: {len(cells)}."
                )

            values = {
                column: " ".join(
                    cells[indexes[column]]
                    .get_text(" ", strip=True)
                    .split()
                )
                for column in COLUMNS
            }

            if not values["crn"]:
                continue

            if not values["crn"].isdigit():
                raise ValueError(
                    f"Unrecognized CRN: {values['crn']!r}."
                )

            capacity = values["capacity"]

            instructor_cell = cells[indexes["instructor"]]
            instructors = [
                " ".join(item.get_text(" ", strip=True).split())
                for item in instructor_cell.find_all("li")
                if item.get_text(" ", strip=True)
            ]

            records.append(
                {
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
            )

    if not found_table:
        raise ValueError(
            "No recognizable Course Section table found. "
            "The page may have no published section table, "
            "require JavaScript, or use a different structure."
        )

    # Preserve different meeting days/times for the same CRN.
    unique_records = {}

    for record in records:
        key = json.dumps(
            record,
            sort_keys=True,
            ensure_ascii=False,
        )
        unique_records[key] = record

    return list(unique_records.values())


def parse_ge_course_information(
    html_path: str | Path,
) -> list[dict]:
    """Read section information from a saved HTML file."""
    return parse_ge_course_information_html(
        Path(html_path).read_bytes()
    )


def fetch_ge_course_information(
    course_code: str,
    *,
    timeout: float = 30,
) -> list[dict]:
    """Download one course page and return its section records."""
    course_code = normalize_course_code(course_code)

    if timeout <= 0:
        raise ValueError("timeout must be greater than zero.")

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
            f"{course_code}: could not download the page: {exc}"
        ) from exc

    try:
        records = parse_ge_course_information_html(
            html,
            course_code=course_code,
        )
    except ValueError as exc:
        raise ValueError(f"{course_code}: {exc}") from exc

    if not records:
        raise ValueError(
            f"{course_code}: no section rows were extracted. "
            "Output file left unchanged."
        )

    return records


def _write_records(
    records: list[dict],
    output_path: str | Path,
) -> None:
    """Write through a unique temporary file before replacing the output."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(
                records,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        temporary_path.replace(output_path)

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def update_ge_course_information_from_web(
    course_codes: list[str],
    output_path: str | Path = DATA_PATH,
    *,
    timeout: float = 30,
) -> list[dict]:
    """
    Fetch requested courses and replace the output with their records.

    No output is written unless every requested course succeeds.
    """
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero.")

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
    """
    Import a directory of saved course pages.

    No output is written if an eligible file fails or no rows are found.
    """
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

    records = []

    for html_file in html_files:
        try:
            file_records = parse_ge_course_information(html_file)
        except ValueError as exc:
            raise ValueError(f"{html_file}: {exc}") from exc

        if not file_records:
            raise ValueError(
                f"{html_file}: no section rows extracted. "
                "Output file left unchanged."
            )

        records.extend(file_records)

    _write_records(records, output_path)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch CityU GE section information or import saved HTML. "
            "Successful imports replace the output JSON file."
        )
    )

    parser.add_argument(
        "course_codes",
        nargs="*",
        help="Course codes such as GE1101 GE1102",
    )

    parser.add_argument(
        "--html-directory",
        type=Path,
        help="Import saved HTML files instead of downloading pages",
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

    if args.html_directory is not None and args.course_codes:
        parser.error(
            "Use course codes or --html-directory, not both."
        )

    try:
        if args.html_directory is not None:
            count = update_ge_course_information(
                args.html_directory,
                output_path=args.output,
            )
        else:
            course_codes = args.course_codes

            if not course_codes:
                try:
                    entered = input(
                        "Enter GE course codes separated by spaces "
                        "or commas: "
                    )
                except EOFError:
                    parser.error(
                        "No interactive input available. "
                        "Pass course codes as command-line arguments."
                    )

                course_codes = entered.replace(",", " ").split()

            records = update_ge_course_information_from_web(
                course_codes,
                output_path=args.output,
                timeout=args.timeout,
            )

            count = len(records)

    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    print(
        f"Saved {count} section record(s) "
        f"to {args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
