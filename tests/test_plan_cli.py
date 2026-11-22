from collections import Counter
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


def test_plan_command_exports_selected_plan(tmp_path):
    output = tmp_path / "nested" / "plan.ics"
    plan("--export-plan", "1", "--output", str(output), "--no-travel-check")
    assert "BEGIN:VEVENT" in output.read_text(encoding="utf-8")


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


def test_require_section_pairs():
    assert cli._required_section_pairs(["test101", "c02", "TEST201", "C01"]) == {
        "TEST101": ["C02"], "TEST201": ["C01"],
    }


def test_ask_saves_and_exports(monkeypatch, tmp_path):
    output = tmp_path / "chosen.ics"
    saved = []
    monkeypatch.setattr(cli, "_load_saved_bundles", list)
    monkeypatch.setattr(cli, "_save_bundles_to_disk", saved.extend)
    feed(monkeypatch, "1", "2", str(output), "", "")
    plan("--ask", "--no-travel-check")
    assert output.is_file()
    assert saved and saved[0]["plan"]["sections"]
    assert saved[0]["plan"]["registration_steps"]


def test_course_plan_uses_ge_section_data(capsys):
    cli.main([
        "--courses", "GE1102", "--term", "2627B",
        "--no-travel-check", "--study-load", "none",
    ])
    output = capsys.readouterr().out
    assert "GE1102 C01+T01  (3 cr)" in output
    assert "CRN 15453" in output


def test_menu_option_8_builds_plan_command(monkeypatch):
    feed(monkeypatch, "ge1102, ge1105", "1", "2627B")
    settings = cli.BasicSettings(prefer_days=("Mon",), avoid_days=("Fri",), max_credits=18)
    command, aims_path = cli._menu_command("8", "saved.html", settings)
    assert command == [
        "--aims-html", "saved.html",
        "--prefer-days", "Mon",
        "--avoid-days", "Fri",
        "--max-credits", "18",
        "--term", "2627B",
        "--courses", "GE1102", "GE1105",
        "--add-ge", "1",
        "--ask",
    ]
    assert aims_path == "saved.html"


def test_menu_option_8_without_aims_or_courses(monkeypatch, capsys):
    feed(monkeypatch, "", "", "", "GE1105", "", "2627A")
    command, path = cli._menu_command("8", None, cli.BasicSettings())
    assert command is not None
    assert "--courses" in command
    assert path is None
    assert "at least one course code" in capsys.readouterr().out

    feed(monkeypatch, "", "GE1102", "two", "2", "1", "2627B")
    command, _ = cli._menu_command("8", None, cli.BasicSettings())
    assert command is not None
    term_index = command.index("--term")
    assert command[term_index : term_index + 2] == ["--term", "2627B"]
    assert command[command.index("--add-ge") + 1] == "1"
    assert "whole number of GE courses from 1 to 1" in capsys.readouterr().out


def test_menu_option_8_ge_count_must_be_one_through_code_count(
    monkeypatch,
    capsys,
):
    prompts = []
    answers = iter(["0", "2", "1"])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": prompts.append(prompt) or next(answers),
    )

    assert cli._prompt_plan_ge_count(1) == "1"
    assert all("(1-1; Enter for 1" in prompt for prompt in prompts)
    assert "whole number of GE courses from 1 to 1" in capsys.readouterr().out


def test_menu_option_8_blank_ge_count_uses_course_count(monkeypatch):
    feed(monkeypatch, "")
    assert cli._prompt_plan_ge_count(3) == "3"


def test_menu_option_8_reprompts_invalid_course_code(monkeypatch, capsys):
    feed(monkeypatch, "", "GE-1102", "GE1102", "1", "2627B")

    command, _ = cli._menu_command("8", None, cli.BasicSettings())

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


def test_menu_option_8_reprompts_course_unavailable_in_term(monkeypatch, capsys):
    feed(monkeypatch, "GE1102", "1", "2627A", "GE1105")

    command, _ = cli._menu_command("8", "saved.html", cli.BasicSettings())

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
    assert "No section details for GE1102 in 2627A" in capsys.readouterr().out


def test_invalid_plan_course_reprompts_without_returning_to_menu(
    monkeypatch,
    capsys,
):
    feed(
        monkeypatch,
        "8",
        "",
        "GE1102",
        "1",
        "2627A",
        "",
        "",
        "GE1105",
        "0",
    )
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    commands = []
    monkeypatch.setattr(cli, "main", lambda argv=None: commands.append(argv))

    cli.interactive_menu()

    assert len(commands) == 1
    assert "--courses" in commands[0]
    assert commands[0][commands[0].index("--courses") + 1] == "GE1105"
    output = capsys.readouterr().out
    assert "No section details for GE1102 in 2627A" in output


def test_menu_option_8_reprompts_invalid_aims_path(monkeypatch, tmp_path, capsys):
    aims = tmp_path / "aims.html"
    aims.write_text(AIMS_HTML, encoding="utf-8")
    feed(
        monkeypatch,
        str(tmp_path / "missing.html"),
        str(aims),
        "GE1105",
        "1",
        "2627A",
    )

    command, path = cli._menu_command("8", None, cli.BasicSettings())

    assert command is not None
    assert path == str(aims)
    assert "Invalid AIMS timetable" in capsys.readouterr().out


def test_plan_dates_reprompt_invalid_and_out_of_order(monkeypatch, capsys):
    feed(monkeypatch, "2026-02-30", "2026-08-31")
    start = cli._prompt_plan_date("Semester start", "2026-08-31")

    feed(monkeypatch, "2026-08-01", "2026-11-28")
    end = cli._prompt_plan_date(
        "Semester end",
        "2026-11-28",
        minimum=start,
    )

    assert start.isoformat() == "2026-08-31"
    assert end.isoformat() == "2026-11-28"
    output = capsys.readouterr().out
    assert "valid date in YYYY-MM-DD format" in output
    assert "Semester end must be on or after semester start." in output


def test_plan_ask_reprompts_invalid_choices_and_output_path(
    monkeypatch,
    capsys,
    tmp_path,
):
    output_path = tmp_path / "chosen.ics"
    feed(
        monkeypatch,
        "1,99",
        "1",
        "999999",
        "1",
        str(tmp_path),
        "",
        "",
        str(output_path),
    )
    saved = []
    monkeypatch.setattr(cli, "_load_saved_bundles", list)
    monkeypatch.setattr(cli, "_save_bundles_to_disk", saved.extend)

    plan("--ask", "--no-travel-check")

    output = capsys.readouterr().out
    assert output_path.is_file()
    assert saved
    assert "Enter plan numbers from 1 to" in output
    assert "Enter a plan number from 1 to" in output
    assert "Could not export plan:" in output


def test_menu_runs_plan_generator(monkeypatch, capsys, tmp_path):
    """Option 8 asks for a semester along with the AIMS timetable and courses."""
    html = tmp_path / "aims.html"
    html.write_text(AIMS_HTML, encoding="utf-8")
    feed(monkeypatch, "8", "GE1102", "", "2627B", "0")
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: str(html))
    cli.interactive_menu()
    output = capsys.readouterr().out
    assert "8. Generate course plans" in output
    assert "11." not in output
    assert "JSON" not in output
    assert "GE1102 has 2 timeslots that fit your timetable" in output
    assert "Kept from your AIMS timetable: CS2311" in output
    assert "GE1102 C01+T01  (3 cr)" in output


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


def test_menu_option_8_q_returns_to_menu(monkeypatch):
    feed(monkeypatch, "", "q")
    with pytest.raises(cli._ReturnToMenu):
        cli._menu_command("8", None, cli.BasicSettings())


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
