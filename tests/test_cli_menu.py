import json
import sys
from io import StringIO

import pytest

from cityuschedule import cli


def test_running_without_arguments_opens_menu_and_searches_ge(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(sys, "argv", ["cityuschedule"])
    inputs = iter(["5", "environment", "AREA1", "q", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    searches = []

    def search_ge_courses(keyword):
        searches.append(keyword)
        return []

    monkeypatch.setattr(cli, "search_ge_courses", search_ge_courses)

    cli.main()

    output = capsys.readouterr().out
    assert searches == ["environment", "AREA1"]
    assert "CityU Schedule" in output
    assert "No Gateway Education courses found for 'environment'." in output
    assert "No Gateway Education courses found for 'AREA1'." in output


def test_ge_search_zero_exits_package(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cityuschedule"])
    inputs = iter(["5", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    searches = []
    monkeypatch.setattr(
        cli,
        "search_ge_courses",
        lambda keyword: searches.append(keyword) or [],
    )

    cli.main()

    assert searches == []
    assert capsys.readouterr().out.count("CityU Schedule") == 1


def test_menu_typing_q_does_not_exit(monkeypatch):
    inputs = iter(["q", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())

    cli.interactive_menu()


def test_menu_path_prompt_q_returns_to_menu(monkeypatch):
    inputs = iter(["2", "q", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())

    cli.interactive_menu()


def test_basic_settings_q_returns_to_menu(monkeypatch):
    inputs = iter(["1", "q", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())

    cli.interactive_menu()


def test_basic_settings_current_values_are_purple(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    output = TerminalOutput()
    prompts = []
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": prompts.append(prompt) or "",
    )

    cli._prompt_days("Prefer days", ("Mon",))
    cli._prompt_days("Avoid days", ("Fri",))
    cli._prompt_credit_limit("Minimum credits", 12)
    cli._prompt_minutes("Lunch minutes", 30)
    cli._prompt_lunch_window(("12:00", "14:00"))
    cli._prompt_clock_limit("Earliest start", "09:00")
    cli._prompt_clock_limit("Latest end", "18:00")

    for current in ("[Mon]", "[Fri]", "[12]", "[30]", "[12:00-14:00]",
                    "[09:00]", "[18:00]"):
        assert f"\033[95m{current}\033[0m" in prompts.pop(0)


def test_basic_settings_requires_lunch_length_to_fit_window(
    monkeypatch,
    capsys,
):
    invalid_attempt = ["", "", "", "", "31", "1200-1230", "", "", ""]
    valid_attempt = ["", "", "", "", "30", "1200-1230", "", "", ""]
    inputs = iter([*invalid_attempt, *valid_attempt])
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": next(inputs),
    )

    settings = cli._prompt_basic_settings(cli.BasicSettings())

    assert settings.lunch_minutes == 30
    assert settings.lunch_window == ("12:00", "12:30")
    assert "cannot exceed the lunch time window (30 minutes)" in (
        capsys.readouterr().out
    )


def test_menu_and_choice_prompt_are_yellow(monkeypatch):
    class TerminalOutput:
        def __init__(self):
            self.text = ""

        def isatty(self):
            return True

        def write(self, text):
            self.text += text

        def flush(self):
            pass

    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    prompts = []

    def choose_exit(prompt=""):
        prompts.append(prompt)
        return "0"

    monkeypatch.setattr("builtins.input", choose_exit)

    cli.interactive_menu()

    assert "\033[33m\nCityU Schedule\n1. Basic settings" in output.text
    assert "Type q to return to the menu, or 0 to exit the package." in output.text
    assert prompts == ["\033[33mChoose an option: \033[0m"]


def test_menu_dispatches_paste_aims_command(monkeypatch, capsys, tmp_path):
    inputs = iter(["4", r"C:\Schedules\current AIMS.html", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    commands = []
    monkeypatch.setattr(cli, "main", lambda argv=None: commands.append(argv))
    monkeypatch.setattr(
        cli,
        "_aims_path_config_file",
        lambda: tmp_path / "aims_html_path.txt",
    )

    cli.interactive_menu()

    assert commands == [
        [
            "--aims-html",
            r"C:\Schedules\current AIMS.html",
            "--paste-aims",
        ]
    ]
    assert "CityU Schedule" in capsys.readouterr().out


def test_menu_saves_aims_path_and_reuses_it(monkeypatch, tmp_path):
    config_file = tmp_path / "aims_html_path.txt"
    saved_path = r"C:\Schedules\current AIMS.html"
    inputs = iter(["3", f'"{saved_path}"', "0", "4", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    monkeypatch.setattr(
        cli,
        "_aims_path_config_file",
        lambda: config_file,
    )
    commands = []
    monkeypatch.setattr(cli, "main", lambda argv=None: commands.append(argv))

    cli.interactive_menu()
    cli.interactive_menu()

    assert config_file.read_text(encoding="utf-8") == saved_path
    assert commands == [
        ["--aims-html", saved_path],
        ["--aims-html", saved_path, "--paste-aims"],
    ]


def test_menu_returns_after_task_error(monkeypatch, tmp_path, capsys):
    config_file = tmp_path / "aims_html_path.txt"
    inputs = iter(
        ["3", r"C:\Schedules\missing.html", "5", "environment", "q", "0"]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(
        cli,
        "_aims_path_config_file",
        lambda: config_file,
    )
    commands = []

    def run_command(argv=None):
        commands.append(argv)
        if argv and argv[0] == "--aims-html":
            raise SystemExit(2)

    monkeypatch.setattr(cli, "main", run_command)

    cli.interactive_menu()

    assert commands == [
        ["--aims-html", r"C:\Schedules\missing.html"],
        ["--ge-search", "environment"],
    ]
    assert not config_file.exists()
    assert "Returning to the menu" in capsys.readouterr().out


def test_menu_exits_when_task_requests_exit(monkeypatch):
    inputs = iter(["4", r"C:\Schedules\current AIMS.html"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    monkeypatch.setattr(
        cli,
        "_load_saved_aims_path",
        lambda: None,
    )
    commands = []

    def exit_task(argv=None):
        commands.append(argv)
        raise SystemExit(0)

    monkeypatch.setattr(cli, "main", exit_task)

    cli.interactive_menu()

    assert commands == [
        [
            "--aims-html",
            r"C:\Schedules\current AIMS.html",
            "--paste-aims",
        ]
    ]


def test_basic_settings_persist_and_apply_to_paste_and_planning(
    monkeypatch,
    tmp_path,
):
    settings_file = tmp_path / "basic_settings.json"
    saved_path = r"C:\Schedules\current AIMS.html"
    inputs = iter(
        [
            "1",
            "R",
            "F",
            "15",
            "21",
            "30",
            "1200-1400",
            "10",
            "0900",
            "1800",
            "0",
            "4",
            "0",
            "8",
            "ge1105",
            "",
            "2627A",
            "0",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(
        cli,
        "_basic_settings_config_file",
        lambda: settings_file,
    )
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: saved_path)
    monkeypatch.setattr(cli, "_save_aims_path", lambda path: None)
    commands = []
    monkeypatch.setattr(cli, "main", lambda argv=None: commands.append(argv))

    cli.interactive_menu()
    cli.interactive_menu()
    cli.interactive_menu()

    assert json.loads(settings_file.read_text(encoding="utf-8")) == {
        "prefer_days": ["Thu"],
        "avoid_days": ["Fri"],
        "min_credits": 15,
        "max_credits": 21,
        "lunch_minutes": 30,
        "lunch_window": ["12:00", "14:00"],
        "min_gap": 10,
        "earliest_start": "09:00",
        "latest_end": "18:00",
    }
    settings_args = [
        "--prefer-days",
        "Thu",
        "--avoid-days",
        "Fri",
        "--min-credits",
        "15",
        "--max-credits",
        "21",
        "--lunch",
        "30",
        "--lunch-window",
        "12:00",
        "14:00",
        "--min-gap",
        "10",
        "--earliest",
        "09:00",
        "--latest",
        "18:00",
    ]
    assert commands == [
        [
            "--aims-html",
            saved_path,
            "--paste-aims",
            *settings_args,
        ],
        [
            "--aims-html",
            saved_path,
            *settings_args,
            "--term",
            "2627A",
            "--courses",
            "GE1105",
            "--ask",
        ],
    ]


@pytest.mark.parametrize(
    ("command", "expected_settings", "expect_aims_path"),
    [
        (
            "delete avoid",
            {
                "prefer_days": ["Wed"],
                "avoid_days": [],
                "min_credits": 12,
                "max_credits": 18,
            },
            True,
        ),
        ("delete lunch", {"lunch_minutes": 0}, True),
        ("delete window", {"lunch_window": ["11:30", "14:30"]}, True),
        ("delete gap", {"min_gap": 0}, True),
        ("delete earliest", {"earliest_start": None}, True),
        ("delete latest", {"latest_end": None}, True),
        (
            "delete prefer",
            {
                "prefer_days": [],
                "avoid_days": ["Fri"],
                "min_credits": 12,
                "max_credits": 18,
            },
            True,
        ),
        (
            "delete min",
            {
                "prefer_days": ["Wed"],
                "avoid_days": ["Fri"],
                "min_credits": None,
                "max_credits": 18,
            },
            True,
        ),
        (
            "delete max",
            {
                "prefer_days": ["Wed"],
                "avoid_days": ["Fri"],
                "min_credits": 12,
                "max_credits": None,
            },
            True,
        ),
        (
            "delete max and min",
            {
                "prefer_days": ["Wed"],
                "avoid_days": ["Fri"],
                "min_credits": None,
                "max_credits": None,
            },
            True,
        ),
        (
            "delete avoid and min",
            {
                "prefer_days": ["Wed"],
                "avoid_days": [],
                "min_credits": None,
                "max_credits": 18,
            },
            True,
        ),
        (
            "delete AIMS and max",
            {
                "prefer_days": ["Wed"],
                "avoid_days": ["Fri"],
                "min_credits": 12,
                "max_credits": None,
            },
            False,
        ),
        (
            "delete AIMS",
            {
                "prefer_days": ["Wed"],
                "avoid_days": ["Fri"],
                "min_credits": 12,
                "max_credits": 18,
            },
            False,
        ),
        ("delete all", None, False),
    ],
)
def test_menu_deletes_saved_information(
    monkeypatch,
    tmp_path,
    command,
    expected_settings,
    expect_aims_path,
):
    settings_file = tmp_path / "basic_settings.json"
    aims_file = tmp_path / "aims_html_path.txt"
    original_settings = {
        "prefer_days": ["Wed"],
        "avoid_days": ["Fri"],
        "min_credits": 12,
        "max_credits": 18,
        "lunch_minutes": 30,
        "lunch_window": ["12:00", "14:00"],
        "min_gap": 10,
        "earliest_start": "09:00",
        "latest_end": "18:00",
    }
    saved_path = r"C:\Schedules\current AIMS.html"
    settings_file.write_text(json.dumps(original_settings), encoding="utf-8")
    aims_file.write_text(saved_path, encoding="utf-8")
    inputs = iter([command, "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(
        cli,
        "_basic_settings_config_file",
        lambda: settings_file,
    )
    monkeypatch.setattr(
        cli,
        "_aims_path_config_file",
        lambda: aims_file,
    )

    cli.interactive_menu()

    if expected_settings is None:
        assert not settings_file.exists()
    else:
        actual_settings = json.loads(settings_file.read_text(encoding="utf-8"))
        for key, value in expected_settings.items():
            assert actual_settings[key] == value
        for key in {
            "lunch_minutes",
            "lunch_window",
            "min_gap",
            "earliest_start",
            "latest_end",
        } - expected_settings.keys():
            assert actual_settings[key] == original_settings[key]
    assert aims_file.exists() is expect_aims_path
    if expect_aims_path:
        assert aims_file.read_text(encoding="utf-8") == saved_path


def test_menu_reports_unknown_delete_command(monkeypatch, capsys):
    inputs = iter(["delete something", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)

    cli.interactive_menu()

    assert "Use delete all, delete avoid, delete prefer" in (
        capsys.readouterr().out
    )


def test_export_and_plan_menu_options_reuse_saved_aims_path(monkeypatch):
    saved_path = r"C:\Schedules\current AIMS.html"
    inputs = iter(["AIMS", "", "", "", "ge1102", "", "2627B"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    export_command, export_path = cli._menu_command("7", saved_path)
    plan_command, plan_path = cli._menu_command(
        "8",
        saved_path,
        cli.BasicSettings(
            prefer_days=("Thu",),
            avoid_days=("Fri",),
            min_credits=15,
            max_credits=21,
            lunch_minutes=30,
            lunch_window=("12:00", "14:00"),
            min_gap=10,
            earliest_start="09:00",
            latest_end="18:00",
        ),
    )

    assert export_command == [
        "--aims-html",
        saved_path,
        "--export",
        "--output",
        "cityu_timetable.ics",
    ]
    assert export_path == saved_path
    assert plan_command == [
        "--aims-html",
        saved_path,
        "--prefer-days",
        "Thu",
        "--avoid-days",
        "Fri",
        "--min-credits",
        "15",
        "--max-credits",
        "21",
        "--lunch",
        "30",
        "--lunch-window",
        "12:00",
        "14:00",
        "--min-gap",
        "10",
        "--earliest",
        "09:00",
        "--latest",
        "18:00",
        "--term",
        "2627B",
        "--courses",
        "GE1102",
        "--ask",
    ]
    assert plan_path == saved_path
