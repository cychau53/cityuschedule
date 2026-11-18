from __future__ import annotations

import json
from pathlib import Path

from .ge_course_information_importer import (
    fetch_ge_course_information,
    normalize_course_code,
)
from .ge_courses import (
    DATA_PATH,
    SECTION_DATA_PATH,
    _read_json_records,
)


COMBINED_DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "combined_ge_course_information.json"
)

SECTION_FIELDS = (
    "crn",
    "section",
    "term",
    "capacity",
    "day",
    "time",
    "type",
    "building",
    "room",
    "instructor",
)


def combine_ge_course_information(
    course_code: str,
    *,
    basic_path: str | Path = DATA_PATH,
    section_path: str | Path = SECTION_DATA_PATH,
    output_path: str | Path = COMBINED_DATA_PATH,
    timeout: float = 30,
) -> list[dict]:
    """
    Fetch one GE course, combine its basic and section information,
    and save the result as one JSON file.
    """
    course_code = normalize_course_code(course_code)

    # Run the section-information importer for the entered course.
    section_records = fetch_ge_course_information(
        course_code,
        timeout=timeout,
    )

    basic_records = _read_json_records(Path(basic_path))
    section_records = _read_json_records(Path(section_path))

    basic_record = _find_course_record(
        basic_records,
        course_code,
        source_path=basic_path,
    )

    matching_sections = [
        record
        for record in section_records
        if _record_course_code(
            record,
            source_path=section_path,
        )
        == course_code
    ]

    if not matching_sections:
        raise ValueError(
            f"No section information was found for {course_code} "
            f"in {section_path}."
        )

    combined_records = []

    for section in matching_sections:
        combined_records.append(
            {
                **basic_record,
                **{
                    field: section.get(field)
                    for field in SECTION_FIELDS
                },
            }
        )

    _write_json_records(
        combined_records,
        output_path,
    )

    return combined_records


def _find_course_record(
    records: list[dict],
    course_code: str,
    *,
    source_path: Path,
) -> dict:
    for index, record in enumerate(records):
        if (
            _record_course_code(
                record,
                source_path=source_path,
            )
            == course_code
        ):
            return record

    raise ValueError(
        f"GE course {course_code} was not found in {source_path}."
    )


def _record_course_code(
    record: dict,
    *,
    source_path: Path,
) -> str:
    course_code = record.get("course_code")

    if not isinstance(course_code, str) or not course_code.strip():
        raise ValueError(
            f"A record in {source_path} has no valid course_code."
        )

    return course_code.strip().upper()


def _write_json_records(
    records: list[dict],
    output_path: str | Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            records,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")


def main() -> None:
    course_code = input(
        "Enter a GE course code, for example GE1102: "
    ).strip()

    try:
        records = combine_ge_course_information(course_code)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}")
        return

    output_path = COMBINED_DATA_PATH

    print(
        f"Saved {len(records)} combined record(s) for "
        f"{records[0]['course_code']} to {output_path.resolve()}"
    )


if __name__ == "__main__":
    main()
