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


def test_standalone_csv_check_is_not_supported(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["courses.csv"])

    assert error.value.code == 2
    assert "only be used with course-planning options" in capsys.readouterr().err


def test_ge_html_import_arguments_are_not_supported(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--ge-html", "ge_courses.html"])

    assert error.value.code == 2
    assert "unrecognized arguments: --ge-html" in capsys.readouterr().err


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


def test_saved_aims_path_default_is_purple(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    prompts = []
    monkeypatch.setattr(cli.sys, "stdout", TerminalOutput())
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": prompts.append(prompt) or "",
    )

    path = r"C:\Users\Starry\Downloads\aims_semB_test.html"
    assert cli._prompt_path(
        "AIMS timetable HTML path (enter a new path to change it)",
        path,
    ) == path
    expected_prompt = (
        "AIMS timetable HTML path (enter a new path to change it) "
        + f"\033[95m[{path}]\033[0m: "
    )
    assert prompts == [expected_prompt]


def test_invalid_day_format_reprompts_same_setting_in_red(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    prompts = []
    answers = iter(["Munday", "Mon"])
    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": prompts.append(prompt) or next(answers),
    )

    assert cli._prompt_days("Prefer days", ()) == ("Mon",)
    assert len(prompts) == 2
    assert "\033[31mUnrecognized day" in output.getvalue()


def test_invalid_ge_details_code_reprompts_in_red(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    prompts = []
    answers = iter(["CS1102", "GE1102"])
    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": prompts.append(prompt) or next(answers),
    )

    assert cli._menu_command("6") == (["--ge-info", "GE1102"], None)
    assert len(prompts) == 2
    assert "\033[31mEnter a GE course code" in output.getvalue()


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
    assert "8. Saved timetable plan" in output.text
    assert "4. Saved course bundles" in output.text
    assert "Bundles saved" not in output.text
    assert "7. Generate timetable plans" in output.text
    assert "9." not in output.text
    assert "Check a CSV timetable" not in output.text
    assert "Import GE courses from HTML" not in output.text
    assert "calendar" not in output.text.lower()
    assert "Type delete plan" not in output.text
    assert "Type q to return to the menu, or 0 to exit the package." in output.text
    assert prompts == ["\033[33mChoose an option: \033[0m"]


def test_menu_option_8_shows_saved_plans(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    monkeypatch.setattr(cli, "_load_saved_bundles", lambda: [])
    answers = iter(["8", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cli.interactive_menu()

    assert "No saved plans were found." in capsys.readouterr().out


def test_menu_option_4_shows_saved_course_bundles(monkeypatch, capsys):
    bundles = [
        {
            "course_code": "GE1409",
            "sections": [
                {
                    "section": "C01",
                    "crn": "12443",
                    "day": "W",
                    "start_time": "09:00",
                    "end_time": "12:00",
                },
                {
                    "section": "L01",
                    "crn": "12324",
                    "day": "F",
                    "start_time": "09:00",
                    "end_time": "13:00",
                },
            ],
        },
        {
            "course_code": "GE1234",
            "sections": [{
                "section": "CA1",
                "crn": "12494",
                "day": "R",
                "start_time": "09:00",
                "end_time": "11:50",
            }],
        },
        {
            "course_code": "GE1234",
            "sections": [{
                "section": "CA2",
                "crn": "14222",
                "day": "R",
                "start_time": "09:00",
                "end_time": "11:50",
            }],
        },
    ]
    monkeypatch.setattr(cli, "_load_saved_course_bundles", lambda: bundles)
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    answers = iter(["4", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cli.interactive_menu()

    output = capsys.readouterr().out
    expected_bundles = (
        "Saved course bundles:\n\n"
        "1. GE1234 CA1\n"
        "   CRN 12494: CA1 R 09:00-11:50\n\n"
        "2. GE1234 CA2\n"
        "   CRN 14222: CA2 R 09:00-11:50\n\n"
        + "-" * 40
        + "\n3. GE1409 C01+L01\n"
        "   CRN 12443: C01 W 09:00-12:00\n"
        "   CRN 12324: L01 F 09:00-13:00"
    )
    assert expected_bundles in output


def test_saved_plan_is_displayed_in_readable_format(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_saved_bundles", lambda: [{
        "plan": {
            "total_credits": 16,
            "days_on_campus": 2,
            "summary": "1 course(s) added; 110 min waiting between classes",
            "courses": ["GE1234 L01+T01", "GE5678 LA1+TA4+CA9"],
            "sessions": [
                {
                    "course_code": "CS2402", "section": "C01", "day": "Mon",
                    "start_time": "09:00", "end_time": "11:50",
                    "building": "MMW", "room": "2450",
                },
                {
                    "course_code": "GE1205", "section": "S03", "day": "Mon",
                    "start_time": "12:00", "end_time": "14:50",
                    "building": "LI", "room": "2614",
                },
                {
                    "course_code": "CS2310", "section": "C01", "day": "Tue",
                    "start_time": "15:00", "end_time": "17:50",
                    "building": "MMW", "room": "2450",
                },
            ],
            "web_add_drop": [
                {
                    "course_code": "GE1234",
                    "add_sections": [
                        {"section": "S01", "crn": "12345"},
                        {"section": "T01", "crn": "23456"},
                    ],
                },
                {
                    "course_code": "GE5678",
                    "add_sections": [{"section": "T02", "crn": "34567"}],
                },
            ],
            "registration_steps": [
                "1. Web Add/Drop: add GE1205 (S03 CRN 12718)",
            ],
        },
    }])

    cli._show_saved_plans()

    output = capsys.readouterr().out
    assert "Plan 1\nTotal credit: 16" in output
    assert "Course(s) added: GE1234 L01+T01, GE5678 LA1+TA4+CA9" in output
    assert "Total day(s) on campus: 2" in output
    assert "  Mon\n    09:00-11:50  CS2402 C01  MMW 2450" in output
    assert "    12:00-14:50  GE1205 S03  LI 2614" in output
    assert "Web Add/Drop:\n  1. GE1234\n     add S01 CRN 12345" in output
    assert "     add T01 CRN 23456" in output
    assert "  2. GE5678\n     add T02 CRN 34567" in output
    assert "Other registration steps:" not in output
    assert "waiting between classes" not in output


def test_saved_plans_are_separated_by_dashed_line(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_saved_bundles", lambda: [
        {"plan": {"courses": ["GE1234 CA1"], "sections": []}},
        {"plan": {"courses": ["GE1409 C01"], "sections": []}},
    ])

    cli._show_saved_plans()

    output = capsys.readouterr().out
    assert f"Web Add/Drop:\n  None.\n\n{'-' * 40}\nPlan 2" in output


def test_saved_plan_colors_added_course_and_timetable_slot(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(cli, "_load_saved_bundles", lambda: [{
        "plan": {
            "courses": ["GE1205 S03"],
            "sections": [
                {
                    "course_code": "GE1205", "section": "S03",
                    "crn": "12718",
                },
            ],
            "web_add_drop": [
                {
                    "course_code": "GE1205",
                    "add_sections": [{"section": "S03", "crn": "12718"}],
                },
            ],
            "sessions": [
                {
                    "course_code": "CS2402", "section": "C01", "day": "Mon",
                    "start_time": "09:00", "end_time": "11:50",
                    "building": "MMW", "room": "2450",
                },
                {
                    "course_code": "GE1205", "section": "S03", "day": "Mon",
                    "start_time": "12:00", "end_time": "14:50",
                    "building": "LI", "room": "2614",
                },
            ],
        },
    }])

    cli._show_saved_plans()

    lines = output.getvalue().splitlines()
    assert "\033[33mPlan 1\033[0m" in lines
    assert any("\033[32mGE1205 S03\033[0m" in line for line in lines)
    assert (
        "\033[32m    12:00-14:50  GE1205 S03  LI 2614\033[0m"
        in lines
    )
    assert "\033[32m  1. GE1205\033[0m" in lines
    assert "\033[32m     add S03 CRN 12718\033[0m" in lines
    assert "    09:00-11:50  CS2402 C01  MMW 2450" in lines


def test_legacy_saved_plan_uses_sections_and_registration_steps():
    plan = {
        "total_credits": 3,
        "courses": ["GE1102 C01+T01"],
        "sections": [
            {
                "course_code": "GE1102", "section": "C01", "crn": "12345",
                "day": "Wed", "start": "09:00", "end": "10:50",
                "location": "LI 2610",
            },
        ],
        "registration_steps": [
            "Web Add/Drop: add GE1102 (C01 CRN 12345), all sections together",
        ],
    }

    text = cli._format_saved_plan(plan, 2)

    assert "Plan 2\nTotal credit: 3" in text
    assert "Total day(s) on campus: 1" in text
    assert "  Wed\n    09:00-10:50  GE1102 C01  LI 2610" in text
    assert "Web Add/Drop:\n  1. GE1102\n     add C01 CRN 12345" in text


@pytest.mark.parametrize("command", ["delete plan1", "delete plan 1"])
def test_delete_saved_plan_by_number(monkeypatch, command):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    saved = [{"plan": {"courses": ["GE1102 C01"]}}, {"plan": {"courses": ["CS2311 C01"]}}]
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    monkeypatch.setattr(cli, "_load_saved_bundles", lambda: saved)
    monkeypatch.setattr(
        cli,
        "_save_bundles_to_disk",
        lambda plans: saved.__setitem__(slice(None), plans),
    )
    inputs = iter([command, "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    cli.interactive_menu()

    assert len(saved) == 1
    assert saved[0]["plan"]["courses"] == ["CS2311 C01"]
    assert "\033[31mDeleted Plan 1.\033[0m" in output.getvalue()


def test_setting_deletion_confirmation_is_red(monkeypatch):
    class TerminalOutput(StringIO):
        def isatty(self):
            return True

    output = TerminalOutput()
    monkeypatch.setattr(cli.sys, "stdout", output)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    monkeypatch.setattr(cli, "_save_basic_settings", lambda settings: None)
    inputs = iter(["delete max", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    cli.interactive_menu()

    assert (
        "\033[31mSaved maximum credits deleted.\033[0m"
        in output.getvalue()
    )


def test_invalid_delete_command_explains_plan_syntax(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    inputs = iter(["delete plan", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    cli.interactive_menu()

    output = capsys.readouterr().out
    assert "delete plan 1" in output
    assert "delete plan1" in output


def test_menu_dispatches_paste_aims_command(monkeypatch, capsys, tmp_path):
    inputs = iter(["3", r"C:\Schedules\current AIMS.html", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    commands = []
    monkeypatch.setattr(
        cli,
        "main",
        lambda argv=None, **kwargs: commands.append(argv),
    )
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
    config_file.write_text("old.html", encoding="utf-8")
    aims_file = tmp_path / "current AIMS.html"
    aims_file.write_text("<html></html>", encoding="utf-8")
    saved_path = str(aims_file)
    inputs = iter(["2", f'"{saved_path}"', "0", "3", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    monkeypatch.setattr(
        cli,
        "_aims_path_config_file",
        lambda: config_file,
    )
    commands = []
    monkeypatch.setattr(
        cli,
        "main",
        lambda argv=None, **kwargs: commands.append(argv),
    )

    cli.interactive_menu()
    cli.interactive_menu()

    assert config_file.read_text(encoding="utf-8") == saved_path
    assert commands == [
        ["--aims-html", saved_path],
        ["--aims-html", saved_path, "--paste-aims"],
    ]


def test_menu_reprompts_same_option_after_task_error(monkeypatch, tmp_path, capsys):
    config_file = tmp_path / "aims_html_path.txt"
    inputs = iter(
        [
            "2",
            r"C:\Schedules\missing.html",
            r"C:\Schedules\current.html",
            "5",
            "environment",
            "q",
            "0",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(
        cli,
        "_aims_path_config_file",
        lambda: config_file,
    )
    commands = []

    def run_command(argv=None, **kwargs):
        commands.append(argv)
        if argv == ["--aims-html", r"C:\Schedules\missing.html"]:
            raise SystemExit(2)

    monkeypatch.setattr(cli, "main", run_command)

    cli.interactive_menu()

    assert commands == [
        ["--aims-html", r"C:\Schedules\missing.html"],
        ["--aims-html", r"C:\Schedules\current.html"],
        ["--ge-search", "environment"],
    ]
    assert config_file.read_text(encoding="utf-8") == r"C:\Schedules\current.html"
    assert "Please enter the inputs for option 2 again." in capsys.readouterr().out


def test_menu_reprompts_required_input_without_returning_to_menu(monkeypatch):
    inputs = iter(["2", "", "courses.html", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    monkeypatch.setattr(cli, "_load_saved_aims_path", lambda: None)
    commands = []
    monkeypatch.setattr(
        cli,
        "main",
        lambda argv=None, **kwargs: commands.append(argv),
    )

    cli.interactive_menu()

    assert commands == [["--aims-html", "courses.html"]]


def test_menu_exits_when_task_requests_exit(monkeypatch):
    inputs = iter(["3", r"C:\Schedules\current AIMS.html"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    monkeypatch.setattr(
        cli,
        "_load_saved_aims_path",
        lambda: None,
    )
    commands = []

    def exit_task(argv=None, **kwargs):
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
    aims_file = tmp_path / "current AIMS.html"
    aims_file.write_text("<html></html>", encoding="utf-8")
    saved_path = str(aims_file)
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
            "3",
            "0",
            "7",
            "2627A",
            "ge1105",
            "1",
            "q",
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
    monkeypatch.setattr(
        cli,
        "main",
        lambda argv=None, **kwargs: commands.append(argv),
    )

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
            "--add-ge",
            "1",
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


def test_plan_menu_option_reuses_saved_aims_path(monkeypatch, tmp_path):
    aims_file = tmp_path / "current AIMS.html"
    aims_file.write_text("<html></html>", encoding="utf-8")
    saved_path = str(aims_file)
    inputs = iter(["2627B", "ge1102", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    plan_command, plan_path = cli._menu_command(
        "7",
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
        "--add-ge",
        "1",
        "--ask",
    ]
    assert plan_path == saved_path


def test_plan_menu_prompts_when_saved_aims_path_is_missing(monkeypatch, capsys):
    inputs = iter(["2627B", "", "GE1102", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    plan_command, plan_path = cli._menu_command(
        "7",
        "courses.html",
        cli.BasicSettings(),
    )

    assert plan_command is not None
    assert "--aims-html" not in plan_command
    assert plan_path is None
    assert "Remembered AIMS HTML was not found: courses.html." in (
        capsys.readouterr().out
    )


def test_plan_menu_clears_missing_saved_aims_path_when_skipped(
    monkeypatch,
    tmp_path,
    capsys,
):
    config_file = tmp_path / "aims_html_path.txt"
    config_file.write_text("courses.html", encoding="utf-8")
    inputs = iter(["7", "2627B", "", "GE1102", "1", "q", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "_aims_path_config_file", lambda: config_file)
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: cli.BasicSettings())
    commands = []
    monkeypatch.setattr(
        cli,
        "main",
        lambda argv=None, **kwargs: commands.append(argv),
    )

    cli.interactive_menu()

    assert commands and "--aims-html" not in commands[0]
    assert not config_file.exists()
    assert "Remembered AIMS HTML was not found: courses.html." in (
        capsys.readouterr().out
    )
