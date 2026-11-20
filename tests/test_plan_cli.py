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
    assert "Plan 1: 5 credits; 1 day(s) on campus" in output
    assert "TEST101 C02" in output
    assert "planning only" in output


def test_plan_command_plans_around_aims_timetable(tmp_path, capsys):
    aims = tmp_path / "aims.html"
    aims.write_text(AIMS_HTML, encoding="utf-8")
    plan("--aims-html", str(aims), "--required", "TEST101", "--no-travel-check")
    output = capsys.readouterr().out
    first_plan = output.split("Plan 1", 1)[1].split("\n\n", 1)[0]
    assert "CS2311 C01" in first_plan and "(fixed)" in first_plan
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
        monkeypatch, "my_catalogue.json", "1", "y",
        "cs2311, ge1401", "2627A", "", "cs1102", "45", "", "09:00", "", "y",
    )
    settings = cli.BasicSettings(prefer_days=("Mon",), avoid_days=("Fri",), max_credits=18)
    command, aims_path = cli._menu_command("8", "saved.html", settings)
    assert command == [
        "--aims-html", "saved.html",
        "--timetable-catalog", "my_catalogue.json",
        "--add-ge", "1",
        "--required", "CS2311", "GE1401",
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


def test_menu_option_8_without_aims_or_courses(monkeypatch):
    feed(monkeypatch, "", "", "")
    assert cli._menu_command("8", None, cli.BasicSettings()) == (None, None)
    feed(monkeypatch, "", "", "two")
    assert cli._menu_command("8", None, cli.BasicSettings()) == (None, None)


def test_menu_runs_plan_generator(monkeypatch, capsys):
    feed(monkeypatch, "8", "", str(EXAMPLE), "", "", "", "", "0")
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    cli.interactive_menu()
    output = capsys.readouterr().out
    assert "8. Generate course plans" in output
    assert "11." not in output
    assert "Plan 1:" in output


def test_menu_option_8_q_returns_to_menu(monkeypatch):
    feed(monkeypatch, "", "my_catalogue.json", "q")
    with pytest.raises(cli._ReturnToMenu):
        cli._menu_command("8", None, cli.BasicSettings())
