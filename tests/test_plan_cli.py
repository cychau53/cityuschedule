from pathlib import Path

import pytest

from cityuschedule import cli

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
    cli.main(["--timetable-catalog", str(EXAMPLE), *args])


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


def test_add_ge_uses_ge_section_data(capsys):
    cli.main(["--add-ge", "1", "--no-travel-check", "--study-load", "none"])
    output = capsys.readouterr().out
    assert "GE1102 C01+T0" in output
    assert "CRN 15453" in output


def test_menu_option_8_builds_plan_command(monkeypatch):
    feed(
        monkeypatch, "ge1102, ge1401", "1", "y", "my_catalogue.json",
        "cs2311", "2627A", "", "cs1102", "45", "", "09:00", "", "y",
    )
    settings = cli.BasicSettings(prefer_days=("Mon",), avoid_days=("Fri",), max_credits=18)
    command, aims_path = cli._menu_command("8", "saved.html", settings)
    assert command == [
        "--aims-html", "saved.html",
        "--courses", "GE1102", "GE1401",
        "--add-ge", "1",
        "--timetable-catalog", "my_catalogue.json",
        "--required", "CS2311",
        "--term", "2627A",
        "--completed", "CS1102",
        "--lunch", "45",
        "--earliest", "09:00",
        "--allow-section-change",
        "--prefer-days", "Mon",
        "--avoid-days", "Fri",
        "--max-credits", "18",
        "--ask",
    ]
    assert aims_path == "saved.html"


def test_menu_option_8_without_aims_or_courses(monkeypatch, capsys):
    feed(monkeypatch, "", "", "", "")
    assert cli._menu_command("8", None, cli.BasicSettings()) == (None, None)
    assert "at least one course code" in capsys.readouterr().out
    feed(monkeypatch, "", "GE1102", "two")
    assert cli._menu_command("8", None, cli.BasicSettings()) == (None, None)


def test_menu_runs_plan_generator(monkeypatch, capsys):
    feed(
        monkeypatch, "8", "", "TEST101", "", "y", str(EXAMPLE),
        "", "", "", "", "", "", "", "", "", "", "0",
    )
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    cli.interactive_menu()
    output = capsys.readouterr().out
    assert "8. Generate course plans" in output
    assert "11." not in output
    assert "TEST101 has 2 timeslots that fit your timetable" in output
    assert "Plan 1:" in output and "TEST201" not in output.split("Plan 1:", 1)[1]


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
    cli.main(["--courses", "GE1111", "--no-travel-check"])
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
        "--avoid-days", "Fri", "--no-travel-check",
    ])
    output = capsys.readouterr().out
    # Friday is avoided, so only the Tuesday class of GE1111 is left;
    # GE3333 (Thu 10:00) clashes with CS2311 in the saved AIMS timetable.
    assert "GE1111 has one timeslot that fits your timetable: C01 Tue 15:00-17:50" in output
    assert "GE3333 has no timeslot that fits your timetable" in output


def test_choose_how_many_ge_courses(ge_data, capsys):
    cli.main(["--courses", "GE1111", "GE2222", "GE3333", "--add-ge", "2",
              "--no-travel-check", "--max-results", "10"])
    output = capsys.readouterr().out
    plans = output.split("Plan ")[1:]
    assert plans
    for plan in plans:
        header = plan.split("\n", 1)[0]
        assert header.split(": ", 1)[1].startswith("2 course(s) added")


def test_unknown_course_code_is_reported(ge_data, capsys):
    cli.main(["--courses", "GE1111", "GE9999", "--no-travel-check"])
    output = capsys.readouterr().out
    assert "no section details for GE9999" in output
    assert "Plan 1:" in output
