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


def test_menu_dispatches_paste_aims_command(monkeypatch, capsys):
    inputs = iter(["3", r"C:\Schedules\current AIMS.html", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    commands = []
    monkeypatch.setattr(cli, "main", lambda argv=None: commands.append(argv))

    cli.interactive_menu()

    assert commands == [[
        "--aims-html",
        r"C:\Schedules\current AIMS.html",
        "--paste-aims",
    ]]
    assert "CityU Schedule" in capsys.readouterr().out
