"""Import course-section offerings from saved AIMS HTML pages."""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


DAY_MAP = {
    "M": "Mon",
    "T": "Tue",
    "W": "Wed",
    "R": "Thu",
    "F": "Fri",
    "S": "Sat",
    "U": "Sun",
}

def parse_aims_section_rows(html_path: str | Path) -> list[dict]:
    html_path = Path(html_path)
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")

    section_table = None
    headers = []

    for table in soup.find_all("table"):
        table_headers = [
            cell.get_text(" ", strip=True)
            for cell in table.find_all("th")
        ]

        if {"CRN", "Section", "Credit", "Day", "Time"}.issubset(
            table_headers
        ):
            section_table = table
            headers = table_headers
            break

    if section_table is None:
        raise ValueError(
            f"Could not find an AIMS course-section table in {html_path}"
        )

    sections = []
    current_section = None

    for row in section_table.find_all("tr"):
        cells = row.find_all("td", recursive=False)

        if not cells:
            continue

        values = [
            cell.get_text(" ", strip=True)
            for cell in cells
        ]

        if len(values) == len(headers) and values[0].isdigit():
            current_section = dict(zip(headers, values))
            current_section["notes"] = []
            sections.append(current_section)
        elif current_section is not None:
            note = " ".join(value for value in values if value)

            if note:
                current_section["notes"].append(note)

    if not sections:
        raise ValueError(
            f"No course-section rows were found in {html_path}"
        )

    return sections

def normalize_aims_sections(rows: list[dict]) -> list[dict]:
    sections = []

    for row in rows:
        day_code = row["Day"].strip().upper()
        time_text = row["Time"].strip()

        # Retain untimed administrative rows separately later.
        if not day_code and not time_text:
            continue

        if day_code not in DAY_MAP:
            raise ValueError(
                f"Unsupported day {day_code!r} "
                f"for section {row['Section']}"
            )

        time_match = re.fullmatch(
            r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})",
            time_text,
        )

        if time_match is None:
            raise ValueError(
                f"Unsupported time {time_text!r} "
                f"for section {row['Section']}"
            )

        start, end = (
            value.zfill(5)
            for value in time_match.groups()
        )

        if start >= end:
            raise ValueError(
                f"Invalid time range for section {row['Section']}"
            )

        sections.append(
            {
                "section": row["Section"],
                "day": DAY_MAP[day_code],
                "start": start,
                "end": end,
                "location": " ".join(
                    value.strip()
                    for value in (row["Bldg"], row["Room"])
                    if value.strip()
                ),
                "section_credits": int(row["Credit"]),
                "date_range": row["Date"],
                "crn": row["CRN"],
                "availability": row["Avail"].lstrip(":").strip(),
                "web": row["WEB"],
                "notes": list(row["notes"]),
                "raw": dict(row),
            }
        )

    return sections

def build_aims_course_record(
    html_path: str | Path,
    course_code: str,
    course_title: str,
) -> dict:
    rows = parse_aims_section_rows(html_path)
    sections = normalize_aims_sections(rows)

    if not sections:
        raise ValueError("No timed sections were found")

    positive_credits = {
        section["section_credits"]
        for section in sections
        if section["section_credits"] > 0
    }

    if len(positive_credits) != 1:
        raise ValueError(
            "Could not determine a single course-credit value. "
            f"Found: {sorted(positive_credits)}"
        )

    credits = positive_credits.pop()

    return {
        "code": course_code.strip().upper(),
        "title": course_title.strip(),
        "credits": credits,
        "source_file": Path(html_path).name,
        "sections": sections,
        "untimed_rows": [
            row
            for row in rows
            if not row["Day"].strip() and not row["Time"].strip()
        ],
        "registration_rules_verified": False,
    }