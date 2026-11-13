import pytest

from cityuschedule.aims import load_aims_html


@pytest.fixture
def aims_html(tmp_path):
    path = tmp_path / "schedule.html"
    path.write_text(
        """
        <html><body>
        <table class="ctt-matrix">
          <tr>
            <th class="ctt-matrix-th-time">Time</th>
            <th class="ctt-matrix-th-day">Monday</th>
            <th class="ctt-matrix-th-day">Tuesday</th>
            <th class="ctt-matrix-th-day">Wednesday</th>
            <th class="ctt-matrix-th-day">Thursday</th>
            <th class="ctt-matrix-th-day">Friday</th>
            <th class="ctt-matrix-th-day">Saturday</th>
            <th class="ctt-matrix-th-day">Sunday</th>
          </tr>
          <tr>
            <td class="ctt-matrix-td-time">09:00-09:50</td>
            <td class="ctt-matrix-cell-class" rowspan="2">
              10001<br>CS1000-C01<br>AC LT-1
            </td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
          </tr>
          <tr>
            <td class="ctt-matrix-td-time">10:00-10:50</td>
            <td class="ctt-matrix-cell-class">
              10002<br>MA1000-T01<br>BOC R100
            </td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
            <td class="ctt-matrix-cell-blank">&nbsp;</td>
          </tr>
        </table>
        <p>Sections with no scheduled date and time:</p>
        <p>GE1000 A01</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    return path


def test_loads_scheduled_classes(aims_html):
    sessions = load_aims_html(str(aims_html))

    assert len(sessions) == 2
    assert sessions[0] == {
        "course_code": "CS1000",
        "course_title": "",
        "crn": "10001",
        "section": "C01",
        "type": "C01",
        "day": "Mon",
        "start_time": "09:00",
        "end_time": "10:50",
        "building": "AC",
        "room": "LT-1",
    }


def test_keeps_day_correct_after_merged_cell(aims_html):
    sessions = load_aims_html(str(aims_html))

    second = sessions[1]
    assert second["course_code"] == "MA1000"
    assert second["day"] == "Tue"
    assert second["start_time"] == "10:00"
    assert second["end_time"] == "10:50"


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_aims_html(str(tmp_path / "missing.html"))


def test_rejects_non_timetable_html(tmp_path):
    path = tmp_path / "wrong.html"
    path.write_text("<html><body>No timetable</body></html>", encoding="utf-8")

    with pytest.raises(ValueError, match="No AIMS weekly timetable"):
        load_aims_html(str(path))