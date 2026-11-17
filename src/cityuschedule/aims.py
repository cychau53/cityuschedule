import re
from pathlib import Path

from bs4 import BeautifulSoup


DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TIME_RANGE = re.compile(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})")
UNSCHEDULED_SECTION = re.compile(
    r"([A-Z]{2,4}\d{4})\s+([A-Z]{1,3}\d{1,3})"
)


def load_aims_html(html_path: str) -> list[dict[str, str]]:
    path = Path(html_path)
    if not path.is_file():
        raise FileNotFoundError(f"AIMS HTML file not found: {path}")

    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    table = soup.select_one("table.ctt-matrix")

    if table is None:
        raise ValueError(
            "No AIMS weekly timetable found. "
            "Save the original weekly timetable page as HTML."
        )

    headers = [
        cell.get_text(" ", strip=True)
        for cell in table.select("th.ctt-matrix-th-day")
    ]
    expected = [
        "Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday",
    ]
    if headers != expected:
        raise ValueError("Unrecognized AIMS timetable day columns.")

    rows = [
        row
        for row in table.find_all("tr")
        if row.find("td", class_="ctt-matrix-td-time") is not None
    ]

    times = []
    for row in rows:
        label = row.find("td", class_="ctt-matrix-td-time")
        match = TIME_RANGE.fullmatch(label.get_text(strip=True))
        if match is None:
            raise ValueError("Unrecognized timetable time row.")
        times.append(match.groups())

    # Each entry is the first row no longer occupied by a merged cell.
    occupied_until = [0] * 7
    sessions = []

    for row_index, row in enumerate(rows):
        cells = row.find_all("td", recursive=False)
        day_index = 0

        for cell in cells:
            classes = cell.get("class", [])
            if "ctt-matrix-td-time" in classes:
                continue

            while (
                day_index < 7
                and occupied_until[day_index] > row_index
            ):
                day_index += 1

            if day_index >= 7:
                raise ValueError("Unexpected extra timetable column.")

            span = int(cell.get("rowspan", 1))
            if (
                span < 1
                or row_index + span > len(rows)
                or int(cell.get("colspan", 1)) != 1
            ):
                raise ValueError("Unsupported timetable cell span.")

            occupied_until[day_index] = row_index + span

            if "ctt-matrix-cell-class" in classes:
                lines = [
                    line.strip()
                    for line in cell.get_text("\n", strip=True).splitlines()
                    if line.strip()
                ]
                if len(lines) < 3 or not lines[0].isdigit():
                    raise ValueError(
                        f"Unrecognized class cell: {lines!r}"
                    )

                course_code, separator, section = lines[1].rpartition("-")
                if not separator or not course_code or not section:
                    raise ValueError(
                        f"Unrecognized course/section: {lines[1]}"
                    )

                location = " ".join(lines[2:])
                building, _, room = location.partition(" ")

                sessions.append({
                    "course_code": course_code,
                    "course_title": "",
                    "crn": lines[0],
                    "section": section,
                    # Preserve AIMS's section label rather than guess
                    # whether it means lecture, tutorial, or seminar.
                    "type": section,
                    "day": DAYS[day_index],
                    "start_time": times[row_index][0],
                    "end_time": times[row_index + span - 1][1],
                    "building": building,
                    "room": room,
                })

            elif cell.get_text(strip=True):
                raise ValueError("Unexpected text in a timetable cell.")

            day_index += 1

        while day_index < 7 and occupied_until[day_index] > row_index:
            day_index += 1

        if day_index != 7:
            raise ValueError("Incomplete timetable row.")

    unscheduled_label = soup.find(
        string=re.compile(
            r"Sections with no scheduled date and time",
            re.IGNORECASE,
        )
    )

    if unscheduled_label is not None:
        label_cell = unscheduled_label.find_parent("td")

        if label_cell is not None:
            value_cell = label_cell.find_next("td")

            if value_cell is not None:
                for course_code, section in UNSCHEDULED_SECTION.findall(
                    value_cell.get_text(" ", strip=True)
                ):
                    sessions.append({
                        "course_code": course_code,
                        "course_title": "",
                        "crn": "",
                        "section": section,
                        "type": section,
                        "day": "",
                        "start_time": "",
                        "end_time": "",
                        "building": "",
                        "room": "",
                    })

    if not sessions:
        raise ValueError("No scheduled classes found in the AIMS HTML.")

    return sessions