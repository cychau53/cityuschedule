from __future__ import annotations

import csv
import json
from pathlib import Path

CSV_PATH = Path("data/catalogue/other_courses.csv")
JSON_PATH = Path("data/catalogue/other_course_requirements.json")


def main() -> None:
    courses = []

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            credits = row.get("credits", "").strip()

            courses.append(
                {
                    "course_code": row.get("course_code", "").strip(),
                    "title": row.get("title", "").strip(),
                    "credits": float(credits) if credits else None,
                    "prerequisites": row.get("prerequisites", "").strip(),
                    "precursors": row.get("precursors", "").strip(),
                    "equivalents": row.get("equivalents", "").strip(),
                    "exclusions": row.get("exclusions", "").strip(),
                    "offering_terms": row.get("offering_terms", "").strip(),
                    "course_aims": row.get("course_aims", "").strip(),
                }
            )

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    with JSON_PATH.open("w", encoding="utf-8") as file:
        json.dump(courses, file, ensure_ascii=False, indent=2)

    print(f"Converted {len(courses)} courses to {JSON_PATH}")


if __name__ == "__main__":
    main()