import json
from pathlib import Path

from bs4 import BeautifulSoup

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "ge_courses.json"


def parse_ge_html(html_path: str | Path) -> list[dict]:
    html_path = Path(html_path)

    with html_path.open("r", encoding="utf-8", errors="ignore") as file:
        soup = BeautifulSoup(file, "html.parser")

    courses = []

    table = soup.find("table", id="id0mobileTableRegion")
    if table is None:
        table = soup.select_one("table.ax-mobile-table")

    if table is None:
        raise ValueError(
            f"Could not find the GE course table in {html_path}."
        )

    tbody = table.find("tbody")
    if tbody is None:
        raise ValueError(
            f"Could not find the GE course table body in {html_path}."
        )

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")

        if len(cells) < 6:
            continue

        course_cell = next(
            (
                cell
                for cell in cells
                if cell.find("a")
                and " - " in cell.find("a").get_text(strip=True)
            ),
            None,
        )
        if course_cell is None:
            continue

        course_index = cells.index(course_cell)
        if course_index + 4 >= len(cells) - 1:
            continue

        course_link = course_cell.find("a")
        course_text = course_link.get_text(strip=True) if course_link else ""

        course_code, course_title = course_text.split(" - ", 1)

        area_text = cells[course_index + 1].get_text(strip=True)
        offering_unit = cells[course_index + 2].get_text(strip=True)
        level = cells[course_index + 3].get_text(strip=True)

        term_elements = cells[course_index + 4].find_all(
            "div",
            class_="label-icon",
        )

        terms = [
            term.get_text(strip=True)
            for term in term_elements
            if term.get_text(strip=True)
        ]

        final_cell = cells[-1]
        with_exam_text = final_cell.get_text(strip=True).lower()

        partner_institution_elements = final_cell.find_all("a")
        partner_institutions = [
            link.get_text(strip=True)
            for link in partner_institution_elements
            if link.get_text(strip=True)
        ]

        courses.append(
            {
                "course_code": course_code.strip(),
                "course_title": course_title.strip(),
                "area": area_text,
                "category": area_text,
                "offering_unit": offering_unit,
                "level": level,
                "terms": terms,
                "with_exam": with_exam_text == "yes",
                "cross_institutional": bool(partner_institutions),
                "partner_institutions": partner_institutions,
            }
        )

    return courses


def update_ge_courses_from_html(
    html_paths: list[str | Path],
    output_path: str | Path = DATA_PATH,
) -> int:
    all_courses = {}

    for html_path in html_paths:
        for course in parse_ge_html(html_path):
            course_code = course["course_code"].upper()
            all_courses[course_code] = course

    courses = sorted(
        all_courses.values(),
        key=lambda course: course["course_code"],
    )

    output_path = Path(output_path)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(courses, file, ensure_ascii=False, indent=2)

    return len(courses)

