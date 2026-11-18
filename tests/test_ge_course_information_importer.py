import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cityuschedule.ge_course_information_importer import _write_records


@pytest.fixture
def records():
    return [
        {
            "crn": "10419",
            "section": "10419CB1",
            "term": "2026-27 Summer",
            "capacity": 65,
            "day": "Wed",
            "time": "12:00:00 - 14:50:00",
            "type": "Lecture",
            "building": "MMW",
            "room": "3420",
            "instructor": "Dr. NG Pak Sheung",
        }
    ]


def test_writes_records_to_json(tmp_path, records):
    output_path = tmp_path / "ge_course_information.json"

    result = _write_records(records, output_path)

    assert result is None
    assert output_path.is_file()

    saved_records = json.loads(
        output_path.read_text(encoding="utf-8")
    )

    assert saved_records == records

    # No temporary files should remain.
    assert set(tmp_path.iterdir()) == {output_path}


def test_creates_missing_parent_directories(tmp_path, records):
    output_path = (
        tmp_path
        / "nested"
        / "data"
        / "ge_course_information.json"
    )

    assert not output_path.parent.exists()

    _write_records(records, output_path)

    assert output_path.is_file()
    assert json.loads(
        output_path.read_text(encoding="utf-8")
    ) == records


def test_accepts_string_output_path(tmp_path, records):
    output_path = tmp_path / "ge_course_information.json"

    _write_records(records, str(output_path))

    assert json.loads(
        output_path.read_text(encoding="utf-8")
    ) == records


def test_replaces_existing_file(tmp_path, records):
    output_path = tmp_path / "ge_course_information.json"
    output_path.write_text(
        '[{"crn": "OLD"}]',
        encoding="utf-8",
    )

    _write_records(records, output_path)

    assert json.loads(
        output_path.read_text(encoding="utf-8")
    ) == records

    assert set(tmp_path.iterdir()) == {output_path}


def test_preserves_unicode(tmp_path, records):
    output_path = tmp_path / "ge_course_information.json"
    records[0]["instructor"] = "陳老師"

    _write_records(records, output_path)

    content = output_path.read_text(encoding="utf-8")

    assert "陳老師" in content
    assert json.loads(content) == records


def test_writes_empty_list(tmp_path):
    output_path = tmp_path / "ge_course_information.json"

    _write_records([], output_path)

    assert json.loads(
        output_path.read_text(encoding="utf-8")
    ) == []


def test_output_ends_with_newline(tmp_path, records):
    output_path = tmp_path / "ge_course_information.json"

    _write_records(records, output_path)

    assert output_path.read_bytes().endswith(b"\n")


def test_serialization_failure_preserves_existing_file(tmp_path):
    output_path = tmp_path / "ge_course_information.json"
    original_content = '[{"crn": "EXISTING"}]\n'
    output_path.write_text(original_content, encoding="utf-8")

    # A set cannot be serialized by the default JSON encoder.
    invalid_records = [{"invalid_value": {1, 2, 3}}]

    with pytest.raises(TypeError):
        _write_records(invalid_records, output_path)

    assert output_path.read_text(
        encoding="utf-8"
    ) == original_content

    # The partially written temporary file should be removed.
    assert set(tmp_path.iterdir()) == {output_path}


def test_serialization_failure_does_not_create_output(tmp_path):
    output_path = tmp_path / "ge_course_information.json"
    invalid_records = [{"invalid_value": object()}]

    with pytest.raises(TypeError):
        _write_records(invalid_records, output_path)

    assert not output_path.exists()
    assert list(tmp_path.iterdir()) == []


def test_replace_failure_cleans_up_temporary_file(tmp_path, records):
    output_path = tmp_path / "ge_course_information.json"
    original_content = '[{"crn": "EXISTING"}]\n'
    output_path.write_text(original_content, encoding="utf-8")

    with patch.object(
        Path,
        "replace",
        side_effect=PermissionError("Simulated replacement failure"),
    ):
        with pytest.raises(
            PermissionError,
            match="Simulated replacement failure",
        ):
            _write_records(records, output_path)

    assert output_path.read_text(
        encoding="utf-8"
    ) == original_content

    assert set(tmp_path.iterdir()) == {output_path}
