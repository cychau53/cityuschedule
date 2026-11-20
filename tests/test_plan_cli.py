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


def test_plan_command_lists_ranked_plans(capsys):
    cli.main(["plan", str(EXAMPLE), "--required", "TEST101", "--no-travel-check"])
    output = capsys.readouterr().out
    assert "Plan 1: 5 credits; 1 day(s) on campus" in output
    assert "TEST101 C02" in output


def test_plan_command_plans_around_aims_timetable(tmp_path, capsys):
    aims = tmp_path / "aims.html"
    aims.write_text(AIMS_HTML, encoding="utf-8")
    cli.main([
        "plan", str(EXAMPLE), "--aims-html", str(aims),
        "--required", "TEST101", "--no-travel-check",
    ])
    output = capsys.readouterr().out
    first_plan = output.split("Plan 1", 1)[1].split("\n\n", 1)[0]
    assert "CS2311 C01" in first_plan and "(fixed)" in first_plan
    # TEST101 C01 (Thu 10:00) clashes with the fixed CS2311 class.
    assert "TEST101 C01" not in output


def test_plan_command_exports_selected_plan(tmp_path):
    output = tmp_path / "nested" / "plan.ics"
    cli.main([
        "plan", str(EXAMPLE), "--export", "1", "--output", str(output),
        "--no-travel-check",
    ])
    assert "BEGIN:VEVENT" in output.read_text(encoding="utf-8")


def test_plan_command_reports_when_nothing_fits(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main([
            "plan", str(EXAMPLE), "--required", "TEST101",
            "--avoid-days", "Thu", "Fri",
        ])
    assert error.value.code == 1
    assert "uses an avoided day" in capsys.readouterr().out


def test_plan_command_rejects_unknown_required_course(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["plan", str(EXAMPLE), "--required", "ZZZ9999"])
    assert error.value.code == 2
    assert "ZZZ9999" in capsys.readouterr().err


def test_plan_command_asks_before_exporting(monkeypatch, tmp_path):
    output = tmp_path / "chosen.ics"
    feed(monkeypatch, "2", str(output), "", "")
    cli.main(["plan", str(EXAMPLE), "--ask-export", "--no-travel-check"])
    assert output.is_file()


def test_menu_option_11_builds_plan_command(monkeypatch):
    feed(monkeypatch, "my_catalogue.json", "", "cs2311, ge1401", "45", "", "09:00", "")
    settings = cli.BasicSettings(prefer_days=("Mon",), avoid_days=("Fri",), max_credits=18)
    command, aims_path = cli._menu_command("11", "saved.html", settings)
    assert command == [
        "plan", "my_catalogue.json",
        "--aims-html", "saved.html",
        "--required", "CS2311", "GE1401",
        "--lunch", "45",
        "--earliest", "09:00",
        "--prefer-days", "Mon",
        "--avoid-days", "Fri",
        "--max-credits", "18",
        "--max-results", "5",
        "--ask-export",
    ]
    assert aims_path == "saved.html"


def test_menu_option_11_can_skip_saved_aims(monkeypatch):
    feed(monkeypatch, "", "n", "", "", "", "", "", "")
    command, aims_path = cli._menu_command("11", "saved.html", cli.BasicSettings())
    assert command[:2] == ["plan", "course_catalog.json"]
    assert "--aims-html" not in command
    assert aims_path is None


def test_menu_runs_plan_generator(monkeypatch, capsys):
    feed(monkeypatch, "11", str(EXAMPLE), "", "TEST101", "", "", "", "", "", "0")
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    cli.interactive_menu()
    output = capsys.readouterr().out
    assert "11. Smart plan generator" in output
    assert "Plan 1:" in output
