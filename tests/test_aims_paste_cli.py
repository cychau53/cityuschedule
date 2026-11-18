from io import StringIO
import sys

from cityuschedule import cli
from cityuschedule.course_catalog import CatalogCourse


def test_colored_output_uses_terminal_colors(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)

    cli._print_green("Combined total if added: 20")
    cli._print_red("Rejected bundles:")

    assert output.getvalue().splitlines() == [
        "\033[32mCombined total if added: 20\033[0m",
        "\033[31mRejected bundles:\033[0m",
    ]


def test_argument_errors_are_red_in_terminal(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    error_output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stderr", error_output)
    parser = cli._CityUScheduleArgumentParser(prog="cityuschedule")

    try:
        parser.error("AIMS HTML file not found")
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("Expected parser.error to exit")

    assert (
        "\033[31mcityuschedule: error: AIMS HTML file not found\033[0m"
        in error_output.getvalue()
    )


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
    assert "Suggested bundles:" in output
    assert "1. C01 + T01" in output


def test_paste_cli_reprompts_after_empty_enter(monkeypatch, capsys):
    prepare_cli(monkeypatch, [])
    inputs = iter(
        ["", *PASTED_TABLE.splitlines(), "END", "", ""]
    )
    monkeypatch.setattr("builtins.input", lambda: next(inputs))

    cli.main()

    output = capsys.readouterr().out
    assert output.count("Paste ONE course's complete AIMS offering table.") == 2
    assert "No table was entered. Please paste the AIMS table and try again." in output
    assert "Candidate complete bundles: 1" in output


def test_paste_cli_reprompts_for_missing_course_code(monkeypatch, capsys):
    prepare_cli(monkeypatch, [])
    table_without_heading = "\n".join(PASTED_TABLE.splitlines()[1:])
    inputs = iter(
        [
            *table_without_heading.splitlines(),
            "END",
            "",
            "TEST1001",
            "",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda: next(inputs))

    cli.main()

    output = capsys.readouterr().out
    assert output.count("If the copied table did not include the course heading") == 2
    assert "A course code is required for this table." in output
    assert "Course: TEST1001" in output


def test_paste_cli_reprompts_after_wrong_table(monkeypatch, capsys):
    prepare_cli(monkeypatch, [], pasted_table="")
    wrong_table = (
        "Pre-requisites/precursors\n"
        "Nil\n"
        "Exclusive Course"
    )
    inputs = iter(
        [
            *wrong_table.splitlines(),
            "END",
            *PASTED_TABLE.splitlines(),
            "END",
            "",
            "",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda: next(inputs))

    cli.main()

    output = capsys.readouterr().out
    assert output.count("Paste ONE course's complete AIMS offering table.") == 2
    assert (
        "That doesn't look like a complete AIMS course offering table."
        in output
    )
    assert "Course: TEST1001" in output


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