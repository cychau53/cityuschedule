from __future__ import annotations

import json
from pathlib import Path
from bs4 import BeautifulSoup

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "ge_course_information.json"


def parse_ge_course_information(html_path: str | Path) -> list[dict]:
    html_path = Path(html_path)

    with html_path.open("r", encoding="utf-8", errors="ignore") as file:
        soup = BeautifulSoup(file, "html.parser")

    records = []
    section_table = soup.find("table", class_="ax-mobile-table")

    if section_table and section_table.find("tbody"):
        for row in section_table.find("tbody").find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 10:
                capacity_raw = cells[4].get_text(strip=True)

                instructors = [
                    li.get_text(strip=True)
                    for li in cells[9].find_all("li")
                    if li.get_text(strip=True)
                ]
                instructor_val = (
                    ", ".join(instructors)
                    if instructors
                    else cells[9].get_text(strip=True)
                )

                records.append(
                    {
                        "CRN": cells[0].get_text(strip=True),
                        "Section": cells[1].get_text(strip=True),
                        "Term": cells[2].get_text(strip=True),
                        "Type": cells[3].get_text(strip=True),
                        "Capacity": int(capacity_raw)
                        if capacity_raw.isdigit()
                        else capacity_raw,
                        "Day": cells[5].get_text(strip=True),
                        "Time": cells[6].get_text(strip=True),
                        "Building": cells[7].get_text(strip=True),
                        "Room": cells[8].get_text(strip=True),
                        "Instructor": instructor_val,
                    }
                )

    return records


def update_ge_course_information(
    html_directory: str | Path,
    output_path: str | Path = DATA_PATH,
) -> int:
    html_directory = Path(html_directory)
    all_records = []

    for html_file in sorted(html_directory.glob("**/*")):
        if html_file.is_file() and html_file.suffix in ("", ".htm", ".html"):
            try:
                all_records.extend(parse_ge_course_information(html_file))
            except Exception as e:
                print(f"Skipping {html_file.name}: {e}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(all_records, file, ensure_ascii=False, indent=2)

    print(f"Exported {len(all_records)} records to {output_path}")
    return len(all_records)


if __name__ == "__main__":
    update_ge_course_information(Path("www.cityu.edu.hk/ge_info/Course"))
