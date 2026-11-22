import re
from collections import Counter
from io import StringIO
from pathlib import Path

import pytest

from cityuschedule import cli
from cityuschedule.plan_generator import PlanReport

EXAMPLE = Path(__file__).resolve().parents[1] / "course_catalog.json"

AIMS_HTML = """
<html><body><table class="ctt-matrix">
<tr><th class="ctt-matrix-th-time">Time</th>
<th class="ctt-matrix-th-day">Monday</th><th class="ctt-matrix-th-day">Tuesday</th>
<th class="ctt-matrix-th-day">Wednesday</th><th class="ctt-matrix-th-day">Thursday</th>
<th class="ctt-matrix-th-day">Friday</th><th class="ctt-matrix-th-day">Saturday</th>
<th class="ctt-matrix-th-day">Sunday</th></tr>
<tr><td class="ctt-matrix-td-time">10:00-10:50</td>
<td class="ctt-matrix-cell-blank">&nbsp;</td><td class="ctt-matrix-cell-blank">&nbsp;</td>
<td class="ctt-matrix-cell-blank">&nbsp;</td>
<td class="ctt-matrix-cell-class">10001<br>CS2311-C01<br>LI 3508</td>
<td class="ctt-matrix-cell-blank">&nbsp;</td><td class="ctt-matrix-cell-blank">&nbsp;</td>
<td class="ctt-matrix-cell-blank">&nbsp;</td></tr>
</table></body></html>
"""

pytestmark = pytest.mark.skipif(
    not EXAMPLE.is_file(), reason="example catalogue missing"
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))


def feed(monkeypatch, *answers):
    lines = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *args: next(lines))


def plan(*args):
    cli.main(["--timetable-catalog", str(EXAMPLE), "--term", "2627A", *args])


def test_csv_timetable_is_still_available_to_course_planner(
    monkeypatch,
    tmp_path,
):
    csv_path = str(tmp_path / "courses.csv")
    planner_calls = []
    monkeypatch.setattr(
        cli,
        "_run_course_planner",
        lambda args, parser: planner_calls.append(args),
    )

    cli.main([csv_path, "--courses", "GE1102"])

    assert planner_calls[0].csv_file == csv_path


def test_plan_command_lists_ranked_plans(capsys):
    plan("--required", "TEST101", "--no-travel-check")
    output = capsys.readouterr().out
    assert "Plan 1: 2 course(s) added; 5 credits; 1 day(s) on campus" in output
    assert "TEST101 C02" in output
    assert "planning only" in output


def test_plan_command_plans_around_aims_timetable(tmp_path, capsys):
    aims = tmp_path / "aims.html"
    aims.write_text(AIMS_HTML, encoding="utf-8")
    plan("--aims-html", str(aims), "--required", "TEST101", "--no-travel-check")
    output = capsys.readouterr().out
    first_plan = output.split("Plan 1", 1)[1].split("\n\n", 1)[0]
    assert "CS2311 C01" in first_plan
    assert "Kept from your AIMS timetable: CS2311" in first_plan
    assert "TEST101 has one timeslot that fits your timetable: C02 Fri 09:00-11:50" in output
    # TEST101 C01 (Thu 10:00) clashes with the fixed CS2311 class.
    assert "TEST101 C01" not in output


def test_plan_command_reports_when_nothing_fits(capsys):
    plan("--required", "TEST101", "--avoid-days", "Thu", "Fri")
    assert "uses an avoided day" in capsys.readouterr().out


def test_plan_command_rejects_unknown_required_course(capsys):
    with pytest.raises(SystemExit) as error:
        plan("--required", "ZZZ9999")
    assert error.value.code == 2
    assert "ZZZ9999" in capsys.readouterr().err


def test_plan_command_no_longer_accepts_completed_courses(capsys):
    with pytest.raises(SystemExit) as error:
        plan("--completed", "CS1102")
    assert error.value.code == 2
    assert "--completed" in capsys.readouterr().err


def test_plan_command_rejects_odd_require_section(capsys):
    with pytest.raises(SystemExit):
        plan("--require-section", "TEST101")
    assert "course code and section pairs" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("flag", "value"),
    [("--export", None), ("--export-plan", "1")],
)
def test_calendar_export_flags_are_removed(flag, value, capsys):
    arguments = [flag]
    if value:
        arguments.append(value)
    with pytest.raises(SystemExit) as error:
        cli.main(arguments)
    assert error.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_require_section_pairs():
    assert cli._required_section_pairs(["test101", "c02", "TEST201", "C01"]) == {
        "TEST101": ["C02"], "TEST201": ["C01"],
    }


def test_ask_saves_plans(monkeypatch):
    saved = []
    monkeypatch.setattr(cli, "_load_saved_bundles", list)
    monkeypatch.setattr(cli, "_save_bundles_to_disk", saved.extend)
    feed(monkeypatch, "1")
    plan("--ask", "--no-travel-check")
    assert saved and saved[0]["plan"]["sections"]
    assert saved[0]["plan"]["registration_steps"]
    assert saved[0]["plan"]["sessions"]
    assert saved[0]["plan"]["days_on_campus"] == 1
    assert saved[0]["plan"]["web_add_drop"]
    assert "waiting between classes" not in saved[0]["plan"]["summary"]


def test_ask_warns_and_skips_duplicate_saved_plan(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    output = TerminalOutput()
    saved = []
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(cli, "_load_saved_bundles", lambda: saved)
    monkeypatch.setattr(
        cli,
        "_save_bundles_to_disk",
        lambda plans: saved.__setitem__(slice(None), plans),
    )
    monkeypatch.setattr(cli, "_prompt_plan_save_choices", lambda count: [0])
    args = [
        "--timetable-catalog", str(EXAMPLE), "--term", "2627A",
        "--ask", "--no-travel-check",
    ]

    cli.main(args)
    assert len(saved) == 1
    output.seek(0)
    output.truncate(0)

    cli.main(args)

    assert len(saved) == 1
    assert (
        "\033[31mPlan 1 has already been saved.\033[0m"
        in output.getvalue()
    )


def test_course_plan_uses_ge_section_data(capsys):
    cli.main([
        "--courses", "GE1102", "--term", "2627B",
        "--no-travel-check", "--study-load", "none",
    ])
    output = capsys.readouterr().out
    assert "GE1102 C01+T01  (3 cr)" in output
    assert "CRN 15453" in output


def test_added_plan_courses_are_green_in_terminal(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)

    cli.main([
        "--courses", "GE1102", "--term", "2627B",
        "--no-travel-check", "--study-load", "none",
    ])

    lines = output.getvalue().splitlines()
    ge_lines = [line for line in lines if "GE1102" in line]

    assert any(line.startswith("\033[32m  GE1102 has") for line in ge_lines)
    assert any(line.startswith("\033[32m  GE1102 C01+T01") for line in ge_lines)
    assert any(
        line.startswith("\033[32m") and "GE1102" in line and ":" in line
        for line in ge_lines
    )
    assert any(line.startswith("\033[33mPlan 1:") for line in lines)
    assert (
        "\033[34mPlease check seat availability in 3. Paste and check an "
        "AIMS course offering.\033[0m"
        in output.getvalue()
    )
    assert "waiting between classes" not in output.getvalue()


def test_menu_option_7_builds_plan_command(monkeypatch, tmp_path):
    aims_file = tmp_path / "saved.html"
    aims_file.write_text("<html></html>", encoding="utf-8")
    saved_path = str(aims_file)
    prompts = []
    answers = iter(["2627B", "ge1102, ge1105", "1"])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": prompts.append(prompt) or next(answers),
    )
    settings = cli.BasicSettings(prefer_days=("Mon",), avoid_days=("Fri",), max_credits=18)
    command, aims_path = cli._menu_command("7", saved_path, settings)
    assert prompts[0].startswith("Semester to check")
    assert prompts[1].startswith("Course codes")
    assert prompts[2].startswith("How many GE courses")
    assert command == [
        "--aims-html", saved_path,
        "--prefer-days", "Mon",
        "--avoid-days", "Fri",
        "--max-credits", "18",
        "--term", "2627B",
        "--courses", "GE1102", "GE1105",
        "--add-ge", "1",
        "--ask",
    ]
    assert aims_path == saved_path


def test_menu_option_7_without_aims_or_courses(monkeypatch, capsys):
    feed(monkeypatch, "2627A", "", "", "GE1105", "")
    command, path = cli._menu_command("7", None, cli.BasicSettings())
    assert command is not None
    assert "--courses" in command
    assert path is None
    assert "at least one course code" in capsys.readouterr().out

    feed(monkeypatch, "2627B", "", "GE1102", "two", "2", "1")
    command, _ = cli._menu_command("7", None, cli.BasicSettings())
    assert command is not None
    term_index = command.index("--term")
    assert command[term_index : term_index + 2] == ["--term", "2627B"]
    assert command[command.index("--add-ge") + 1] == "1"
    assert "whole number of GE courses from 1 to 1" in capsys.readouterr().out


def test_menu_option_7_ge_count_must_be_one_through_code_count(
    monkeypatch,
    capsys,
):
    prompts = []
    answers = iter(["2", "invalid", "1"])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": prompts.append(prompt) or next(answers),
    )

    assert cli._prompt_plan_ge_count(1) == "1"
    assert all("(enter a positive integer)" in prompt for prompt in prompts)
    assert "whole number of GE courses from 1 to 1" in capsys.readouterr().out


def test_menu_option_7_zero_exits_during_ge_count_prompt(monkeypatch):
    feed(monkeypatch, "0")

    with pytest.raises(SystemExit) as error:
        cli._prompt_plan_ge_count(1)

    assert error.value.code == 0


def test_menu_option_7_blank_ge_count_uses_course_count(monkeypatch):
    feed(monkeypatch, "")
    assert cli._prompt_plan_ge_count(3) == "3"


def test_menu_option_7_reprompts_invalid_course_code(monkeypatch, capsys):
    feed(monkeypatch, "2627B", "", "GE-1102", "GE1102", "1")

    command, _ = cli._menu_command("7", None, cli.BasicSettings())

    assert command is not None
    assert command[-7:] == [
        "--term",
        "2627B",
        "--courses",
        "GE1102",
        "--add-ge",
        "1",
        "--ask",
    ]
    assert "Invalid course code" in capsys.readouterr().out


def test_menu_option_7_reprompts_course_unavailable_in_term(
    monkeypatch,
    tmp_path,
):
    aims_file = tmp_path / "saved.html"
    aims_file.write_text("<html></html>", encoding="utf-8")
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    feed(monkeypatch, "2627A", "GE1102", "1", "GE1105")

    command, _ = cli._menu_command(
        "7",
        str(aims_file),
        cli.BasicSettings(),
    )

    assert command is not None
    assert command[-7:] == [
        "--term",
        "2627A",
        "--courses",
        "GE1105",
        "--add-ge",
        "1",
        "--ask",
    ]
    assert "\033[31mNo section details for GE1102 in 2627A." in output.getvalue()


def test_invalid_plan_course_reprompts_without_returning_to_menu(
    monkeypatch,
    capsys,
):
    feed(
        monkeypatch,
        "7",
        "2627A",
        "",
        "GE1102",
        "1",
        "",
        "GE1105",
        "q",
        "0",
    )
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    commands = []
    monkeypatch.setattr(
        cli,
        "main",
        lambda argv=None, **kwargs: commands.append(argv),
    )

    cli.interactive_menu()

    assert len(commands) == 1
    assert "--courses" in commands[0]
    assert commands[0][commands[0].index("--courses") + 1] == "GE1105"
    output = capsys.readouterr().out
    assert "No section details for GE1102 in 2627A" in output


def test_menu_option_7_reprompts_invalid_aims_path(monkeypatch, tmp_path, capsys):
    aims = tmp_path / "aims.html"
    aims.write_text(AIMS_HTML, encoding="utf-8")
    feed(
        monkeypatch,
        "2627A",
        str(tmp_path / "missing.html"),
        str(aims),
        "GE1105",
        "1",
    )

    command, path = cli._menu_command("7", None, cli.BasicSettings())

    assert command is not None
    assert path == str(aims)
    assert "Invalid AIMS timetable" in capsys.readouterr().out


def test_plan_ask_reprompts_invalid_save_choices(monkeypatch, capsys):
    feed(monkeypatch, "1,99", "1")
    saved = []
    monkeypatch.setattr(cli, "_load_saved_bundles", list)
    monkeypatch.setattr(cli, "_save_bundles_to_disk", saved.extend)

    plan("--ask", "--no-travel-check")

    output = capsys.readouterr().out
    assert saved
    assert "Enter plan numbers from 1 to" in output
    assert "Export a plan" not in output


def test_menu_runs_plan_generator(monkeypatch, capsys, tmp_path):
    """Option 7 asks for a semester along with AIMS timetable and courses."""
    html = tmp_path / "aims.html"
    html.write_text(AIMS_HTML, encoding="utf-8")
    feed(monkeypatch, "7", "2627B", "GE1102", "", "0")
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: str(html))
    cli.interactive_menu()
    output = capsys.readouterr().out
    assert "7. Generate timetable plans" in output
    assert "11." not in output
    assert "JSON" not in output
    assert "GE1102 has 2 timeslots that fit your timetable" in output
    assert "Kept from your AIMS timetable: CS2311" in output
    assert "GE1102 C01+T01  (3 cr)" in output


def test_menu_plan_generator_repeats_until_q(monkeypatch, capsys, tmp_path):
    aims = tmp_path / "aims.html"
    aims.write_text(AIMS_HTML, encoding="utf-8")
    commands = []
    feed(
        monkeypatch,
        "7",
        "2627B",
        "GE1102",
        "",
        "2627B",
        "GE1102",
        "",
        "q",
        "0",
    )
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: str(aims))
    monkeypatch.setattr(
        cli,
        "main",
        lambda argv=None, **kwargs: commands.append(argv),
    )

    cli.interactive_menu()

    output = capsys.readouterr().out
    assert len(commands) == 2
    assert output.count("Generate timetable plans") == 2
    assert output.count("CityU Schedule") == 2


def test_menu_plan_return_signal_returns_to_menu(monkeypatch, capsys, tmp_path):
    html = tmp_path / "aims.html"
    html.write_text(AIMS_HTML, encoding="utf-8")
    feed(monkeypatch, "7", "2627B", "GE1102", "", "0")
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: str(html))
    commands = []
    monkeypatch.setattr(
        cli,
        "main",
        lambda argv=None, **kwargs: commands.append(argv) or True,
    )

    cli.interactive_menu()

    output = capsys.readouterr().out
    assert len(commands) == 1
    assert output.count("CityU Schedule") == 2


def test_plan_save_prompt_return_signal_propagates(monkeypatch):
    def return_to_menu(_):
        raise cli._ReturnToMenu

    monkeypatch.setattr(cli, "_prompt_plan_save_choices", return_to_menu)

    arguments = [
        "--timetable-catalog",
        str(EXAMPLE),
        "--term",
        "2627A",
        "--required",
        "TEST101",
        "--ask",
    ]

    assert cli.main(arguments) is None
    assert cli.main(arguments, _from_menu=True) is True


def test_basic_setting_plan_rejections_are_purple(monkeypatch):
    output = []
    monkeypatch.setattr(cli, "_print_red", lambda text, file=None: output.append(("red", text)))
    monkeypatch.setattr(cli, "_print_purple", lambda text: output.append(("purple", text)))
    report = PlanReport(
        [],
        rejections=Counter({
            "avoid_day": 1,
            "time_window": 1,
            "min_gap": 1,
            "lunch": 1,
            "min_credits": 2,
            "max_credits": 1,
            "class_bundles": 1,
        }),
    )

    cli._print_plan_rejections(report, no_plans=True)

    purple_lines = {text for color, text in output if color == "purple"}
    assert purple_lines == {
        "  1. uses an avoided day",
        "  2. outside the allowed start/end time",
        "  3. gap between classes too short",
        "  4. no lunch break",
    }
    assert ("red", "  5. not enough credits") in output
    assert ("red", "  6. over the credit limit") in output
    assert ("red", "  7. no class bundles fit") in output
    assert all("rejected" not in line for _, line in output)


CLASH_HTML = AIMS_HTML.replace(
    "10:00-10:50</td>\n<td class=\"ctt-matrix-cell-blank\">&nbsp;</td>"
    "<td class=\"ctt-matrix-cell-blank\">&nbsp;</td>\n"
    "<td class=\"ctt-matrix-cell-blank\">&nbsp;</td>",
    "13:00-13:50</td>\n<td class=\"ctt-matrix-cell-blank\">&nbsp;</td>"
    "<td class=\"ctt-matrix-cell-blank\">&nbsp;</td>\n"
    "<td class=\"ctt-matrix-cell-class\">10003<br>MA1200-C01<br>YEUNG 5503</td>",
)


def test_ge1102_against_saved_timetable(tmp_path, capsys):
    """GE1102 (menu option 6 data) fits or clashes with the saved timetable."""
    html = tmp_path / "aims.html"
    html.write_text(AIMS_HTML, encoding="utf-8")
    cli.main(["--aims-html", str(html), "--courses", "GE1102", "--term", "2627B"])
    output = capsys.readouterr().out
    assert "GE1102 has 2 timeslots that fit your timetable" in output
    assert "Plan 2:" in output

    assert "MA1200-C01" in CLASH_HTML
    html.write_text(CLASH_HTML, encoding="utf-8")
    cli.main(["--aims-html", str(html), "--courses", "GE1102", "--term", "2627B"])
    output = capsys.readouterr().out
    assert "classes clash" in output
    assert "GE1102 has no timeslot that fits your timetable" in output


def test_menu_option_7_q_returns_to_menu(monkeypatch):
    feed(monkeypatch, "q")
    with pytest.raises(cli._ReturnToMenu):
        cli._menu_command("7", None, cli.BasicSettings())


# --- the examples from the group chat ---------------------------------------


def ge_sections():
    """GE1111 can be taken Tue 15:00-17:50 or Fri 09:00-11:50 (as in the
    group chat); GE2222 and GE3333 have one section each."""
    from cityuschedule.course_catalog import CatalogCourse, CatalogSection

    def ge(code, *slots):
        return CatalogCourse(code, f"{code} title", None, tuple(
            CatalogSection(code, section, day, start, end, "LI 3508")
            for section, day, start, end in slots
        ))

    return [
        ge("GE1111", ("C01", "Tue", "15:00", "17:50"), ("C02", "Fri", "09:00", "11:50")),
        ge("GE2222", ("C01", "Wed", "09:00", "11:50")),
        ge("GE3333", ("C01", "Thu", "10:00", "12:50")),
    ]


@pytest.fixture
def ge_data(monkeypatch):
    monkeypatch.setattr(cli, "load_ge_section_catalog", lambda term=None: ge_sections())


def test_one_plan_per_timeslot(ge_data, capsys):
    cli.main(["--courses", "GE1111", "--term", "2627A", "--no-travel-check"])
    output = capsys.readouterr().out
    assert "GE1111 has 2 timeslots that fit your timetable" in output
    plan1 = output.split("Plan 1:", 1)[1].split("Plan 2:", 1)[0]
    plan2 = output.split("Plan 2:", 1)[1]
    assert {("Tue" in plan1), ("Tue" in plan2)} == {True, False}
    assert {("Fri" in plan1), ("Fri" in plan2)} == {True, False}
    # No credit limit was set, so missing GE credit data is not a problem.
    assert "Credits unknown" not in output


def test_saved_timetable_leaves_one_slot(ge_data, tmp_path, capsys):
    aims = tmp_path / "aims.html"
    aims.write_text(AIMS_HTML, encoding="utf-8")  # CS2311 C01 on Thu 10:00-10:50
    cli.main([
        "--aims-html", str(aims), "--courses", "GE1111", "GE3333",
        "--term", "2627A", "--avoid-days", "Fri", "--no-travel-check",
    ])
    output = capsys.readouterr().out
    # Friday is avoided, so only the Tuesday class of GE1111 is left;
    # GE3333 (Thu 10:00) clashes with CS2311 in the saved AIMS timetable.
    assert "GE1111 has one timeslot that fits your timetable: C01 Tue 15:00-17:50" in output
    assert "GE3333 has no timeslot that fits your timetable" in output


def test_fit_summary_colors_multiple_ge_courses_distinctly(
    ge_data,
    monkeypatch,
):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        "cityuschedule.plan_generator.load_course_requirements",
        lambda paths=(): {},
    )

    cli.main([
        "--courses", "GE1111", "GE2222", "GE3333",
        "--add-ge", "2", "--term", "2627A", "--no-travel-check",
        "--max-results", "10",
    ])

    fit_colors = {}
    plan_course_colors = {}
    for line in output.getvalue().splitlines():
        match = re.match(
            r"\033\[(38;2;\d+;\d+;\d+)m\s+(GE\d{4}[A-Z]?)\b",
            line,
        )
        if not match:
            continue
        color, course_code = match.groups()
        if "timeslot" in line or "no class bundles fit" in line:
            fit_colors[course_code] = color
        elif re.search(rf"\b{course_code}\s+\S+", line):
            plan_course_colors[course_code] = color

    assert set(fit_colors) == {"GE1111", "GE2222", "GE3333"}
    assert len(set(fit_colors.values())) == 3
    assert len(plan_course_colors) >= 2
    assert all(
        plan_course_colors[code] == fit_colors[code]
        for code in plan_course_colors
    )


def test_choose_how_many_ge_courses(ge_data, capsys):
    cli.main(["--courses", "GE1111", "GE2222", "GE3333", "--add-ge", "2",
              "--term", "2627A", "--no-travel-check", "--max-results", "10"])
    output = capsys.readouterr().out
    plans = output.split("Plan ")[1:]
    assert plans
    for plan in plans:
        header = plan.split("\n", 1)[0]
        assert header.split(": ", 1)[1].startswith("2 course(s) added")


def test_unknown_course_code_is_reported(ge_data, capsys):
    cli.main(["--courses", "GE1111", "GE9999", "--term", "2627A", "--no-travel-check"])
    output = capsys.readouterr().out
    assert "no section details for GE9999" in output
    assert "Plan 1:" in output


def test_plan_command_prompts_for_valid_semester(monkeypatch, capsys):
    answers = iter(["invalid", "2627B"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    requested_terms = []
    monkeypatch.setattr(
        cli,
        "load_ge_section_catalog",
        lambda term=None: requested_terms.append(term) or ge_sections(),
    )

    cli.main(["--courses", "GE1111", "--no-travel-check"])

    output = capsys.readouterr().out
    assert "Enter a valid semester" in output
    assert requested_terms == ["2026-27 Sem B"]
    assert "Plan 1:" in output


def test_menu_reprompts_when_semester_has_no_ge_data(
    monkeypatch,
    capsys,
):
    feed(monkeypatch, "2526A", "2627A", "", "GE1111", "")
    requested_terms = []

    def section_catalog(term=None):
        requested_terms.append(term)
        return [] if term == "2025-26 Sem A" else ge_sections()

    monkeypatch.setattr(cli, "load_ge_section_catalog", section_catalog)

    command, _ = cli._menu_command("7", None, cli.BasicSettings())

    assert command is not None
    assert command[command.index("--term") + 1] == "2627A"
    assert requested_terms == ["2025-26 Sem A", "2026-27 Sem A"]
    assert "Currently, we don't have data for 2526A" in (
        capsys.readouterr().out
    )


def test_plan_command_reports_when_semester_has_no_ge_data(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(cli, "load_ge_section_catalog", lambda term=None: [])

    with pytest.raises(SystemExit) as error:
        cli.main(["--courses", "GE1111", "--term", "2526A"])

    assert error.value.code == 2
    assert "Currently, we don't have data for 2526A" in capsys.readouterr().err
