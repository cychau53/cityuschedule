import sys
from io import StringIO

import pytest

from cityuschedule import cli
from cityuschedule.course_catalog import CatalogCourse


class TerminalOutput(StringIO):
    def isatty(self):
        return True


def test_colored_output_uses_terminal_colors(monkeypatch):
    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)

    cli._print_green("Combined total if added: 20")
    cli._print_yellow("Paste ONE course's complete AIMS offering table.")
    cli._print_blue("Pasted course credits: 3")
    cli._print_red("Rejected bundles:")

    assert output.getvalue().splitlines() == [
        "\033[32mCombined total if added: 20\033[0m",
        "\033[33mPaste ONE course's complete AIMS offering table.\033[0m",
        "\033[34mPasted course credits: 3\033[0m",
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
    assert (
        "\nBundles fitting weekly timetable: 1\n\n"
        "Pasted course credits: 3\n"
    ) in output
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


def test_paste_cli_exits_from_retry_prompt(monkeypatch):
    prepare_cli(monkeypatch, [], pasted_table="")
    inputs = iter(["q"])
    monkeypatch.setattr("builtins.input", lambda: next(inputs))

    cli.main()


def test_paste_cli_exits_package_when_user_enters_zero(monkeypatch):
    prepare_cli(monkeypatch, [], pasted_table="")
    inputs = iter(["0"])
    monkeypatch.setattr("builtins.input", lambda: next(inputs))

    try:
        cli.main()
    except SystemExit as error:
        assert error.code == 0
    else:
        raise AssertionError("Expected 0 to exit the package")


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


def test_paste_cli_rejects_bundle_without_enough_travel_time(monkeypatch):
    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
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

    text = output.getvalue()

    assert "Bundles fitting weekly timetable: 0" in text
    travel_reason = next(
        line for line in text.splitlines() if "Requires 16 minutes" in line
    )
    assert travel_reason.startswith("\033[31m   - ")
    assert travel_reason.endswith("\033[0m")


def test_paste_cli_ranks_preferred_days(monkeypatch, capsys):
    prepare_cli(monkeypatch, [], ["--prefer-days", "Wed"])

    cli.main()

    output = capsys.readouterr().out
    assert "1. C01 + T01 (match with prefer days)" in output


def test_paste_cli_reminds_user_of_day_settings(monkeypatch, capsys):
    prepare_cli(
        monkeypatch,
        [],
        ["--prefer-days", "Wed", "--avoid-days", "Thu"],
    )

    cli.main()

    output = capsys.readouterr().out
    assert (
        "Bundles fitting weekly timetable: 1\n\n"
        "Current prefer days: Wed\n"
        "Current avoid days: Thu"
    ) in output


def test_paste_cli_rejects_avoided_days(monkeypatch, capsys):
    prepare_cli(monkeypatch, [], ["--avoid-days", "Wed"])

    cli.main()

    output = capsys.readouterr().out
    assert "Bundles fitting weekly timetable: 0" in output
    assert "Uses avoided day(s): Wed" in output


@pytest.mark.parametrize(
    ("args", "expected_reason"),
    [
        (
            ["--min-gap", "15"],
            "Minimum gap of 15 minutes not met",
        ),
        (
            ["--lunch", "30", "--lunch-window", "1200", "1400"],
            "No 30-minute lunch break between 12:00 and 14:00 on Wed",
        ),
        (
            ["--earliest", "1300"],
            "starts before 13:00",
        ),
        (
            ["--latest", "1400"],
            "ends after 14:00",
        ),
    ],
)
def test_paste_cli_applies_time_constraints(
    monkeypatch,
    args,
    expected_reason,
):
    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    prepare_cli(monkeypatch, [], args)

    cli.main()

    text = output.getvalue()
    assert "Bundles fitting weekly timetable: 0" in text
    assert expected_reason in text
    reason_line = next(
        line for line in text.splitlines() if expected_reason in line
    )
    assert reason_line.startswith("\033[95m")
    assert "\033[95mNo complete bundle fits:" in text


def test_paste_cli_applies_settings_to_offering_not_saved_classes(
    monkeypatch,
    capsys,
):
    base_rows = [
        {
            "course_code": "BASE1001",
            "crn": "20001",
            "section": "C01",
            "day": "Wed",
            "start_time": "11:50",
            "end_time": "12:40",
            "building": "BOC",
        },
        {
            "course_code": "BASE1002",
            "crn": "20002",
            "section": "C01",
            "day": "Fri",
            "start_time": "08:00",
            "end_time": "08:50",
            "building": "BOC",
        },
    ]
    offering = PASTED_TABLE.replace(
        "12:00 - 13:50",
        "12:45 - 13:35",
    ).replace(
        "14:00 - 14:50",
        "13:45 - 14:35",
    )
    prepare_cli(
        monkeypatch,
        base_rows,
        [
            "--avoid-days", "Fri",
            "--min-gap", "10",
            "--lunch", "30",
            "--lunch-window", "1200", "1400",
            "--earliest", "0900",
            "--latest", "1800",
        ],
        pasted_table=offering,
    )

    cli.main()

    output = capsys.readouterr().out
    assert "Bundles fitting weekly timetable: 1" in output
    assert "Suggested bundles:" in output


def test_paste_cli_lists_avoid_only_rejections_first(monkeypatch, capsys):
    base_bundle = PASTED_TABLE.replace(
        "\nW\n12:00 - 13:50",
        "\nT\n12:00 - 13:50",
    ).replace(
        "\nW\n14:00 - 14:50",
        "\nT\n14:00 - 14:50",
    )
    avoid_bundle = (
        PASTED_TABLE.replace("13401", "13403")
        .replace("C01", "CA1")
        .replace("13402", "13404")
        .replace("T01", "TA1")
    )
    pasted_table = (
        base_bundle
        + "\n"
        + "\n".join(avoid_bundle.splitlines()[1:])
    )
    base_rows = [
        {
            "course_code": "BASE1001",
            "crn": "20001",
            "section": "C01",
            "day": "Tue",
            "start_time": "12:30",
            "end_time": "13:20",
            "building": "BOC",
        },
    ]
    prepare_cli(
        monkeypatch,
        base_rows,
        ["--avoid-days", "Wed"],
        pasted_table=pasted_table,
    )

    cli.main()

    output = capsys.readouterr().out
    avoid_only_index = output.index("1. CA1 + TA1 (crash with avoid days)")
    other_rejection_index = output.index("2. C01 + T01")
    assert avoid_only_index < other_rejection_index


def test_paste_cli_colors_preferred_bundle_and_days(monkeypatch):
    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    pasted_table = PASTED_TABLE.replace(
        "\nW\n14:00 - 14:50",
        "\nR\n14:00 - 14:50",
    )
    prepare_cli(monkeypatch, [], ["--prefer-days", "Thu"], pasted_table=pasted_table)

    cli.main()

    text = output.getvalue()
    assert (
        "\033[32m1. C01 + T01\033[0m "
        "\033[95m(match with prefer days)\033[0m"
    ) in text
    assert "\033[32m   CRN 13401: C01 W 12:00-13:50\033[0m" in text
    assert "\033[95m   CRN 13402: T01 R 14:00-14:50\033[0m" in text


def test_paste_cli_colors_avoided_bundle_and_days(monkeypatch):
    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    pasted_table = PASTED_TABLE.replace(
        "\nW\n14:00 - 14:50",
        "\nR\n14:00 - 14:50",
    )
    prepare_cli(monkeypatch, [], ["--avoid-days", "Thu"], pasted_table=pasted_table)

    cli.main()

    text = output.getvalue()
    assert (
        "\033[31m1. C01 + T01\033[0m "
        "\033[95m(crash with avoid days)\033[0m"
    ) in text
    assert "\033[31m   CRN 13401: C01 W 12:00-13:50\033[0m" in text
    assert "\033[95m   CRN 13402: T01 R 14:00-14:50\033[0m" in text


@pytest.mark.parametrize(
    ("limit_args", "warning"),
    [
        (
            ["--min-credits", "7"],
            "Warning: combined credits (6) are below the minimum (7).",
        ),
        (
            ["--max-credits", "5"],
            "Warning: combined credits (6) exceed the maximum (5).",
        ),
    ],
)
def test_paste_cli_warns_about_credit_limits_without_hiding_bundles(
    monkeypatch,
    limit_args,
    warning,
):
    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    base_rows = [
        {
            "course_code": "GE1401",
            "crn": "20001",
            "section": "C01",
            "day": "Mon",
            "start_time": "09:00",
            "end_time": "10:00",
            "building": "BOC",
        },
    ]
    prepare_cli(monkeypatch, base_rows, limit_args)

    cli.main()

    text = output.getvalue()
    assert (
        "\033[34mPasted course credits: 3\033[0m\n"
        "\033[34mAIMS timetable credits: 3\033[0m\n"
        "\033[34mCombined total if added: 6\033[0m\n"
        f"\033[31m{warning}\033[0m"
    ) in text
    assert "Suggested bundles:" in text


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
    assert (
        "Pasted course credits: 3\n"
        "AIMS timetable credits: 12\n"
        "Combined total if added: 15"
    ) in output
    assert (
        "Combined total if added: 15\n\n"
        "Suggested bundles:"
    ) in output


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
    assert (
        "AIMS timetable credits: incomplete "
        "(known subtotal 0; missing: BASE1001)\n"
        "Combined total if added: incomplete"
    ) in output