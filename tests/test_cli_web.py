import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from types import SimpleNamespace

import pytest

from cityuschedule.web import create_web_server


@pytest.fixture
def web_url():
    server = create_web_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return urllib.request.urlopen(request, timeout=5)


def _post_file(url, fields, field_name, filename, content):
    boundary = "CityUScheduleTestBoundary"
    parts = []
    for name, value in fields.items():
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode(),
            b"\r\n",
        ])
    parts.extend([
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
        ).encode(),
        b"Content-Type: text/html\r\n\r\n",
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    request = urllib.request.Request(
        url,
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return urllib.request.urlopen(request, timeout=5)


def _aims_html():
    days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    headers = "".join(
        f'<th class="ctt-matrix-th-day">{day}</th>' for day in days
    )
    cells = [
        '<td class="ctt-matrix-cell-class">10001<br>CS1000-C01<br>AC LT-1</td>'
    ]
    cells.extend(
        '<td class="ctt-matrix-cell-blank">&nbsp;</td>' for _ in range(6)
    )
    return (
        '<html><body><table class="ctt-matrix"><tr>'
        '<th class="ctt-matrix-th-time">Time</th>'
        f"{headers}</tr><tr>"
        '<td class="ctt-matrix-td-time">09:00-09:50</td>'
        f'{"".join(cells)}</tr></table></body></html>'
    ).encode()


def test_web_page_is_served_with_navigation(web_url):
    with urllib.request.urlopen(web_url, timeout=5) as response:
        body = response.read().decode("utf-8")

    assert response.status == 200
    assert "CityUSchedule" in body

    navigation_paths = (
        "/settings",
        "/aims",
        "/aims-offering",
        "/saved-course-bundles",
        "/ge-search",
        "/ge-info",
        "/planner",
        "/saved-plans",
    )

    positions = []

    for path in navigation_paths:
        link = f'href="{path}"'
        assert link in body
        positions.append(body.index(link))

    assert positions == sorted(positions)


def test_web_form_rejects_invalid_term(web_url):
    with pytest.raises(urllib.error.HTTPError) as error:
        _post_form(web_url, {"action": "plan", "term": "invalid"})
    assert error.value.code == 400
    assert b"valid semester" in error.value.read()


def test_web_plan_requires_at_least_one_ge_course(web_url):
    with pytest.raises(urllib.error.HTTPError) as error:
        _post_form(
            web_url + "/planner",
            {"action": "plan", "term": "2627B", "add_ge": "0"},
        )
    assert error.value.code == 400
    assert b"must be at least 1" in error.value.read()


def test_planner_warns_and_continues_when_input_course_has_no_sections(
    web_url,
    monkeypatch,
):
    from cityuschedule import cli, web

    available_course = SimpleNamespace(code="GE1102")
    loaded = {}
    generated = {}

    def load_sections(term):
        loaded["term"] = term
        return [available_course]

    def generate(courses, options, **kwargs):
        generated["courses"] = courses
        return SimpleNamespace(plans=[], fit_summary=list)

    monkeypatch.setattr(cli, "_load_basic_settings", cli.BasicSettings)
    monkeypatch.setattr(web, "load_ge_section_catalog", load_sections)
    monkeypatch.setattr(web, "generate_course_plans", generate)

    with _post_form(
        web_url + "/planner",
        {
            "action": "plan",
            "term": "2627A",
            "courses": "GE1102 GE9999",
        },
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert loaded["term"] == "2026-27 Sem A"
    assert generated["courses"] == [available_course]
    assert "no section details for GE9999 in 2026-27 Sem A" in body
    assert "left out of planning" in body
    assert (
        '<div class="error" role="alert">'
        "No course plans matched the selected options."
        "</div>"
    ) in body


def test_web_plan_form_defaults_ge_count_to_one(web_url):
    with urllib.request.urlopen(web_url + "/planner", timeout=5) as response:
        body = response.read().decode("utf-8")
    assert 'id="add_ge" name="add_ge" type="number" min="1" value="1" required' in body


def test_basic_settings_post_saves_shared_cli_settings(web_url, monkeypatch):
    from cityuschedule import cli

    saved = []
    monkeypatch.setattr(cli, "_save_basic_settings", saved.append)
    monkeypatch.setattr(cli, "_load_basic_settings", cli.BasicSettings)
    with _post_form(
        web_url + "/settings",
        {
            "action": "save-settings",
            "prefer_days": "Mon, Wed",
            "avoid_days": "Fri",
            "min_credits": "12",
            "max_credits": "18",
            "earliest_start": "09:00",
            "latest_end": "18:00",
            "min_gap": "15",
            "lunch_minutes": "30",
            "lunch_start": "11:30",
            "lunch_end": "14:30",
        },
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "Basic settings saved." in body
    assert saved == [
        cli.BasicSettings(
            prefer_days=("Mon", "Wed"),
            avoid_days=("Fri",),
            min_credits=12,
            max_credits=18,
            lunch_minutes=30,
            lunch_window=("11:30", "14:30"),
            min_gap=15,
            earliest_start="09:00",
            latest_end="18:00",
        )
    ]


def test_basic_settings_reject_conflicting_days(web_url):
    with pytest.raises(urllib.error.HTTPError) as error:
        _post_form(
            web_url + "/settings",
            {
                "action": "save-settings",
                "prefer_days": "Mon",
                "avoid_days": "Monday",
            },
        )
    assert error.value.code == 400
    assert b"both preferred and avoided" in error.value.read()


def test_planner_uses_saved_basic_settings(web_url, monkeypatch):
    from cityuschedule import cli, web

    settings = cli.BasicSettings(
        prefer_days=("Mon",),
        avoid_days=("Fri",),
        min_credits=12,
        max_credits=18,
        lunch_minutes=30,
        lunch_window=("11:30", "14:30"),
        min_gap=15,
        earliest_start="09:00",
        latest_end="18:00",
    )
    captured = {}
    monkeypatch.setattr(cli, "_load_basic_settings", lambda: settings)
    monkeypatch.setattr(
        web,
        "load_ge_section_catalog",
        lambda term: [SimpleNamespace(code="GE1102")],
    )
    monkeypatch.setattr(
        web,
        "generate_course_plans",
        lambda courses, options, **kwargs: (
            captured.setdefault("options", options)
            and SimpleNamespace(plans=[], fit_summary=list)
        ),
    )

    with _post_form(
        web_url + "/planner",
        {"action": "plan", "term": "2627B", "courses": "GE1102"},
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    options = captured["options"]
    assert options.ge_courses == 1
    assert options.preferred_days == ("Mon",)
    assert options.avoid_days == ("Fri",)
    assert options.min_credits == 12
    assert options.max_credits == 18
    assert options.lunch_minutes == 30
    assert options.lunch_window == ("11:30", "14:30")
    assert options.min_gap == 15
    assert options.earliest_start == "09:00"
    assert options.latest_end == "18:00"
    assert "No course plans matched" in body


def test_added_courses_use_distinct_colors_in_plan_output(monkeypatch):
    from cityuschedule import web

    plan = SimpleNamespace(
        chosen=[
            SimpleNamespace(course_code="GE1102", preregistered=False),
            SimpleNamespace(course_code="GE1202", preregistered=False),
        ]
    )
    monkeypatch.setattr(
        web,
        "format_plan",
        lambda *args, **kwargs: "Plan 1\nGE1102 C01\nGE1202 C01",
    )
    output = web._format_plans_html([plan])
    colors = re.findall(r'<span style="color: ([^"]+)">', output)
    assert len(colors) == 2
    assert colors[0] != colors[1]
    assert "GE1102 C01" in output
    assert "GE1202 C01" in output


@pytest.mark.parametrize(
    ("path", "heading", "field"),
    [
        ("/ge-search", "Search Gateway Education courses", 'name="keyword"'),
        ("/settings", "Basic timetable settings", 'name="prefer_days"'),
        ("/ge-info", "Gateway Education course information", 'name="course_code"'),
        ("/aims", "Check an AIMS timetable", 'name="aims"'),
    ],
)
def test_web_feature_pages_are_available(web_url, path, heading, field):
    with urllib.request.urlopen(web_url + path, timeout=5) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert heading in body
    assert field in body


def test_ge_search_post_shows_search_results(web_url, monkeypatch):
    from cityuschedule import web

    monkeypatch.setattr(
        web,
        "search_ge_courses",
        lambda keyword: [
            {
                "course_code": "GE1102",
                "course_title": "Nature and Society",
                "area_name": "Area 1",
                "terms": ["2026-27 Sem B"],
                "with_exam": False,
            }
        ],
    )
    with _post_form(
        web_url + "/ge-search",
        {"action": "ge-search", "keyword": "nature"},
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "Found 1 Gateway Education course(s)" in body
    assert "GE1102 - Nature and Society" in body
    assert "2026-27 Sem B" in body


def test_ge_info_post_shows_course_information(web_url, monkeypatch):
    from cityuschedule import web

    course = {
        "course_code": "GE1102",
        "course_title": "Nature and Society",
        "area_name": "Area 1",
        "terms": ["2026-27 Sem B"],
        "cross_institutional": False,
        "with_exam": True,
        "partner_institutions": ["Example University"],
    }
    monkeypatch.setattr(
        web,
        "load_ge_courses",
        lambda: [
            {
                **course,
                "section": "A01",
                "crn": "12345",
                "term": "2026-27 Sem B",
                "capacity": 30,
                "day": "Mon",
                "time": "09:00-09:50",
                "type": "Lecture",
                "building": "AC",
                "room": "LT-1",
                "instructor": "Instructor",
            },
            {
                **course,
                "section": "A02",
                "crn": "12346",
                "term": "2026-27 Sem B",
                "capacity": 25,
                "day": "Tue",
                "time": "10:00-10:50",
                "type": "Lecture",
                "building": "AC",
                "room": "LT-2",
                "instructor": "Another Instructor",
            },
        ],
    )
    with _post_form(
        web_url + "/ge-info",
        {"action": "ge-info", "course_code": "ge1102"},
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "GE1102 - Nature and Society" in body
    assert "Partner institutions: Example University" in body
    assert "Section: A01" in body
    assert "Found 2 section meeting record(s)." in body
    assert "Section: A02" in body
    assert "CRN: 12346" in body
    assert "Capacity: 25" in body


def test_ge1202_page_lists_all_bundled_sections(web_url):
    with _post_form(
        web_url + "/ge-info",
        {"action": "ge-info", "course_code": "GE1202"},
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "GE1202 - Managing Your Personal Finance" in body
    assert "Found 6 section meeting record(s)." in body
    for section in (
        "13475C03",
        "10501C02",
        "10500C01",
        "13399C03",
        "13397C01",
        "13398C02",
    ):
        assert f"Section: {section}" in body


def test_aims_upload_post_displays_timetable_check(web_url):
    with _post_file(
        web_url + "/aims",
        {"action": "aims-check"},
        "aims",
        "timetable.html",
        _aims_html(),
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "CS1000 C01" in body
    assert "Loaded 1 class sessions." in body
    assert "Found 0 clash(es)." in body


def test_generated_plan_can_be_saved_from_webpage(web_url, monkeypatch):
    from cityuschedule import cli, web

    plan_data = {
        "courses": ["GE1102 C01"],
        "sections": [
            {
                "course_code": "GE1102",
                "section": "C01",
                "crn": "12345",
                "day": "Mon",
                "start": "09:00",
                "end": "09:50",
                "location": "AC LT-1",
            }
        ],
        "total_credits": 3,
    }
    second_plan_data = {
        "courses": ["GE1205 S04"],
        "sections": [
            {
                "course_code": "GE1205",
                "section": "S04",
                "crn": "12346",
                "day": "Tue",
                "start": "10:00",
                "end": "10:50",
                "location": "LI 1406",
            }
        ],
        "total_credits": 3,
    }

    class FakePlan:
        def __init__(self, data, course_code):
            self.data = data
            self.chosen = [
                SimpleNamespace(course_code=course_code, preregistered=False)
            ]

        def to_dict(self):
            return self.data

    report = SimpleNamespace(
        plans=[
            FakePlan(plan_data, "GE1102"),
            FakePlan(second_plan_data, "GE1205"),
        ],
        warnings=[],
        fit_summary=list,
    )
    monkeypatch.setattr(
        web,
        "load_ge_section_catalog",
        lambda term: [
            SimpleNamespace(code="GE1102"),
            SimpleNamespace(code="GE1205"),
        ],
    )
    monkeypatch.setattr(web, "generate_course_plans", lambda *args, **kwargs: report)
    monkeypatch.setattr(
        web,
        "format_plan",
        lambda plan, *args, **kwargs: (
            f"Plan 1: sample\n  {plan.chosen[0].course_code}"
        ),
    )
    saved = []
    monkeypatch.setattr(cli, "_load_saved_bundles", lambda: list(saved))
    monkeypatch.setattr(
        cli,
        "_save_bundles_to_disk",
        lambda plans: saved.__setitem__(slice(None), plans),
    )

    with _post_form(
        web_url + "/planner",
        {"action": "plan", "term": "2627B", "courses": "GE1102 GE1205"},
    ) as response:
        result_page = response.read().decode("utf-8")
    assert response.status == 200
    assert "Save selected plans" in result_page
    assert 'style="color: #008000"' in result_page
    assert "Save Plan 1: GE1102 C01" in result_page
    assert "Save Plan 2: GE1205 S04" in result_page

    token_match = re.search(r'name="plan_token" value="([^"]+)"', result_page)
    assert token_match is not None
    token = token_match.group(1)
    with _post_form(
        web_url + "/save-plans",
        {
            "action": "save-plans",
            "plan_token": token,
            "plan_1": "1",
        },
    ) as response:
        saved_page = response.read().decode("utf-8")
    assert response.status == 200
    assert "Saved 1 plan(s)." in saved_page
    assert saved == [{"plan": plan_data}]

    with _post_form(
        web_url + "/save-plans",
        {
            "action": "save-plans",
            "plan_token": token,
            "plan_1": "1",
        },
    ) as response:
        duplicate_page = response.read().decode("utf-8")
    assert response.status == 200
    assert "already saved" in duplicate_page
    assert "Choose another plan to save" in duplicate_page
    assert 'name="plan_2" value="1"' in duplicate_page
    assert len(saved) == 1

    with _post_form(
        web_url + "/save-plans",
        {
            "action": "save-plans",
            "plan_token": token,
            "plan_2": "1",
        },
    ) as response:
        second_saved_page = response.read().decode("utf-8")
    assert response.status == 200
    assert "Saved 1 plan(s)." in second_saved_page
    assert saved == [
        {"plan": plan_data},
        {"plan": second_plan_data},
    ]


def test_saved_bundles_page_lists_saved_plans_and_course_bundles(
    web_url,
    monkeypatch,
):
    from cityuschedule import cli

    monkeypatch.setattr(
        cli,
        "_load_saved_bundles",
        lambda: [
            {
                "plan": {
                    "courses": ["GE1102 C01"],
                    "sections": [],
                    "total_credits": 3,
                }
            }
        ],
    )
    monkeypatch.setattr(
        cli,
        "_load_saved_course_bundles",
        lambda: [
            {
                "course_code": "GE1202",
                "sections": [
                    {
                        "section": "C01",
                        "crn": "13397",
                        "day": "Wed",
                        "start_time": "12:00",
                        "end_time": "14:50",
                    }
                ],
            }
        ],
    )
    with urllib.request.urlopen(web_url + "/saved-bundles", timeout=5) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "Saved timetable plans" in body
    assert "Plan 1" in body
    assert 'action="/delete-plan"' in body
    assert 'name="plan_number" value="1"' in body
    assert "Delete Plan 1?" in body
    assert "Saved course bundles" in body
    assert "GE1202" in body
    assert "C01" in body
    assert "CRN 13397" in body


def test_saved_plan_can_be_deleted_from_webpage(web_url, monkeypatch):
    from cityuschedule import cli

    saved = [
        {"plan": {"courses": ["GE1102 C01"], "sections": [], "total_credits": 3}},
        {"plan": {"courses": ["GE1202 C01"], "sections": [], "total_credits": 3}},
    ]
    written = []

    def save_plans(plans):
        saved[:] = plans
        written.append(plans)

    monkeypatch.setattr(cli, "_load_saved_bundles", lambda: saved)
    monkeypatch.setattr(cli, "_save_bundles_to_disk", save_plans)
    monkeypatch.setattr(cli, "_load_saved_course_bundles", list)

    with _post_form(
        web_url + "/delete-plan",
        {"action": "delete-plan", "plan_number": "2"},
    ) as response:
        body = response.read().decode("utf-8")
    assert response.status == 200
    assert "Deleted Plan 2." in body
    assert "GE1102 C01" in body
    assert "GE1202 C01" not in body
    assert len(written) == 1
    assert len(saved) == 1


def test_delete_saved_plan_rejects_out_of_range_number(web_url, monkeypatch):
    from cityuschedule import cli

    monkeypatch.setattr(
        cli,
        "_load_saved_bundles",
        lambda: [{"plan": {"courses": ["GE1102 C01"], "sections": []}}],
    )
    monkeypatch.setattr(cli, "_load_saved_course_bundles", list)
    monkeypatch.setattr(
        cli,
        "_save_bundles_to_disk",
        lambda plans: pytest.fail("Invalid plan number must not delete plans"),
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        _post_form(
            web_url + "/delete-plan",
            {"action": "delete-plan", "plan_number": "2"},
        )
    assert error.value.code == 400
    body = error.value.read()
    assert b"Plan number must be from 1 to 1" in body

def test_saved_data_pages_are_separate(web_url):
    with urllib.request.urlopen(
        f"{web_url.rstrip('/')}/saved-course-bundles",
        timeout=5,
    ) as response:
        bundles_body = response.read().decode("utf-8")

    with urllib.request.urlopen(
        f"{web_url.rstrip('/')}/saved-plans",
        timeout=5,
    ) as response:
        plans_body = response.read().decode("utf-8")

    assert "<h2>Saved course bundles</h2>" in bundles_body
    assert "<h2>Saved timetable plans</h2>" not in bundles_body

    assert "<h2>Saved timetable plans</h2>" in plans_body
    assert "<h2>Saved course bundles</h2>" not in plans_body
