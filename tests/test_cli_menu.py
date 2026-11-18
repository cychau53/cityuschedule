import sys

from cityuschedule import cli


def test_running_without_arguments_opens_menu_and_searches_ge(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(sys, "argv", ["cityuschedule"])
    inputs = iter(["4", "environment", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "search_ge_courses", lambda keyword: [])

    cli.main()

    output = capsys.readouterr().out
    assert "CityU Schedule" in output
    assert "No Gateway Education courses found for 'environment'." in output


def test_menu_dispatches_paste_aims_command(monkeypatch, capsys, tmp_path):
    inputs = iter(["3", r"C:\Schedules\current AIMS.html", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
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
    inputs = iter(["2", f'"{saved_path}"', "0", "3", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
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


def test_export_and_plan_menu_options_reuse_saved_aims_path(monkeypatch):
    saved_path = r"C:\Schedules\current AIMS.html"
    inputs = iter(["AIMS", "", "", "", "courses.json"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    export_command, export_path = cli._menu_command("6", saved_path)
    plan_command, plan_path = cli._menu_command("7", saved_path)

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
        "--timetable-catalog",
        "courses.json",
    ]
    assert plan_path == saved_path
