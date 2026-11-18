import sys

from cityuschedule import cli
from cityuschedule.course_catalog import CatalogCourse


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


def prepare_cli(
    monkeypatch,
    base_rows,
    extra_args=None,
    unavailable_sections="",
    course_code="",
    pasted_table=PASTED_TABLE,
):
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

    lines = iter(
        pasted_table.splitlines()
        + ["END", course_code, unavailable_sections]
    )
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


def test_paste_cli_excludes_user_unavailable_sections(monkeypatch, capsys):
    prepare_cli(monkeypatch, [], unavailable_sections="T01")

    cli.main()

    output = capsys.readouterr().out
    assert "Unavailable sections excluded: T01" in output
    assert "Bundles fitting weekly timetable: 0" in output
    assert "Unavailable section(s): T01" in output


def test_paste_cli_accepts_copied_tabular_table(monkeypatch, capsys):
    copied_table = (
        "CRN\tSection\tCredit\tCampus\tWEB\tLevel\tAvail\tCap\tWaitlist\n"
        "Avail\tDate\tDay\tTime\tBldg\tRoom\tInstructor\tMedium of\n"
        "Instruction\n"
        "10681\tC01\t3\tMain Campus\tY\tB\t79\t80\tN\t"
        "11/01/2027 - 17/04/2027\tF\t12:00 - 14:50\tYEUNG\t"
        "G4702\tHE Yutian, CHAN Kim Lui Raise\tEnglish"
    )
    prepare_cli(
        monkeypatch,
        [],
        course_code="GE2130",
        pasted_table=copied_table,
    )

    cli.main()

    output = capsys.readouterr().out
    assert "Course: GE2130" in output
    assert "Parsed sections: 1" in output
    assert "Bundles fitting weekly timetable: 1" in output


def test_paste_cli_rejects_unknown_unavailable_sections(monkeypatch):
    prepare_cli(monkeypatch, [], unavailable_sections="T99")

    try:
        cli.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("Expected unknown section validation to fail")


def test_paste_cli_reports_combined_credits(monkeypatch, capsys):
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
    prepare_cli(
        monkeypatch,
        base_rows,
        ["--credit-catalog", "credits.json"],
    )
    monkeypatch.setattr(
        cli,
        "load_credit_catalogs",
        lambda paths: [
            CatalogCourse(
                code="BASE1001",
                title="Base course",
                credits=12,
                sections=(),
            )
        ],
    )

    cli.main()

    output = capsys.readouterr().out
    assert "Pasted course credits: 3" in output
    assert "AIMS timetable credits: 12" in output
    assert "Combined total if added: 15" in output


def test_paste_cli_uses_builtin_cs_ge_and_other_credit_catalogs(
    monkeypatch,
    capsys,
):
    base_rows = [
        {
            "course_code": course_code,
            "crn": str(index),
            "section": "C01",
            "day": day,
            "start_time": "09:00",
            "end_time": "10:00",
            "building": "BOC",
        }
        for index, (course_code, day) in enumerate(
            [
                ("CS1102", "Mon"),
                ("GE1401", "Tue"),
                ("MA1200", "Thu"),
            ],
            start=1,
        )
    ]
    prepare_cli(monkeypatch, base_rows)

    cli.main()

    output = capsys.readouterr().out
    assert "AIMS timetable credits: 9" in output
    assert "Combined total if added: 12" in output


def test_paste_cli_reports_missing_base_course_credits(
    monkeypatch,
    capsys,
):
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
    prepare_cli(
        monkeypatch,
        base_rows,
        ["--credit-catalog", "credits.json"],
    )
    monkeypatch.setattr(cli, "load_credit_catalogs", lambda paths: [])

    cli.main()

    output = capsys.readouterr().out
    assert "AIMS timetable credits: incomplete" in output
    assert "missing: BASE1001" in output
    assert "Combined total if added: incomplete" in output