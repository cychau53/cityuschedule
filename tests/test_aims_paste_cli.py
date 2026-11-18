import sys

from cityuschedule import cli


PASTED_TABLE = """TEST1001
13401
C01
3
Main Campus
Y
B
150
150
N
11/01/2027 - 17/04/2027
W
12:00 - 13:50
BOC
LT401
ZHONG Yiming
English
13402
T01
0
Main Campus
Y
B
150
150
N
11/01/2027 - 17/04/2027
W
14:00 - 14:50
BOC
LT401
WONG Sung Ching Sam
English
"""


def prepare_cli(monkeypatch, base_rows, extra_args=None):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cityuschedule",
            "--aims-html",
            "test_base.html",
            "--paste-aims",
        ] + (extra_args or []),
    )

    monkeypatch.setattr(
        cli,
        "load_aims_html",
        lambda path: base_rows,
    )

    lines = iter(PASTED_TABLE.splitlines() + ["END"])
    monkeypatch.setattr(
        "builtins.input",
        lambda: next(lines),
    )


def test_paste_cli_reports_fitting_bundle(monkeypatch, capsys):
    base_rows = [
        {
            "course_code": "BASE1001",
            "crn": "20001",
            "section": "C01",
            "day": "Mon",
            "start_time": "09:00",
            "end_time": "10:50",
            "building": "BOC",
        },
    ]
    prepare_cli(monkeypatch, base_rows)

    cli.main()

    output = capsys.readouterr().out

    assert "Course: TEST1001" in output
    assert "Candidate complete bundles: 1" in output
    assert "Bundles fitting weekly timetable: 1" in output
    assert "1. C01 + T01" in output


def test_paste_cli_reports_conflicting_bundle(monkeypatch, capsys):
    base_rows = [
        {
            "course_code": "BASE1001",
            "crn": "20001",
            "section": "C01",
            "day": "Wed",
            "start_time": "12:30",
            "end_time": "13:20",
            "building": "BOC",
        },
    ]
    prepare_cli(monkeypatch, base_rows)

    cli.main()

    output = capsys.readouterr().out

    assert "Candidate complete bundles: 1" in output
    assert "Bundles fitting weekly timetable: 0" in output
    assert "No complete bundle fits" in output
    assert "Rejected bundles:" in output
    assert (
        "Base timetable overlap: "
        "TEST1001-C01 W 12:00-13:50 overlaps "
        "BASE1001-C01 W 12:30-13:20"
    ) in output


def test_paste_cli_rejects_bundle_without_enough_travel_time(
    monkeypatch,
    capsys,
):
    base_rows = [
        {
            "course_code": "BASE1001",
            "crn": "20001",
            "section": "C01",
            "day": "Wed",
            "start_time": "10:50",
            "end_time": "11:50",
            "building": "CMC",
        },
    ]
    prepare_cli(monkeypatch, base_rows)

    cli.main()

    output = capsys.readouterr().out

    assert "Bundles fitting weekly timetable: 0" in output
    assert "Requires 16 minutes, but only 10 minutes are available." in output


def test_paste_cli_ranks_preferred_days(monkeypatch, capsys):
    prepare_cli(monkeypatch, [], ["--prefer-days", "Wed"])

    cli.main()

    output = capsys.readouterr().out
    assert "1. C01 + T01 (1 preferred day(s))" in output


def test_paste_cli_rejects_avoided_days(monkeypatch, capsys):
    prepare_cli(monkeypatch, [], ["--avoid-days", "Wed"])

    cli.main()

    output = capsys.readouterr().out
    assert "Bundles fitting weekly timetable: 0" in output
    assert "Uses avoided day(s): Wed" in output