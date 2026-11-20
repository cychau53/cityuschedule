from pathlib import Path

import pytest

from cityuschedule.course_catalog import (
    CatalogCourse,
    CatalogSection,
    load_course_catalog,
)
from cityuschedule.plan_generator import (
    PlanOptions,
    build_course_options,
    format_plan,
    generate_course_plans,
    main,
    normalize_day,
    parse_time,
)

TRAVEL = {
    "LI": {"CMC": 15, "YEUNG": 7},
    "CMC": {"LI": 15, "YEUNG": 19},
    "YEUNG": {"LI": 7, "CMC": 19},
}


def section(code, day, start, end, location="LI 3508", course="CS1000"):
    return CatalogSection(
        course_code=course, section=code, day=day, start=start, end=end,
        location=location,
    )


def course(code, credits, *sections, title=""):
    return CatalogCourse(
        code=code,
        title=title or f"{code} title",
        credits=credits,
        sections=tuple(
            CatalogSection(
                course_code=code, section=s.section, day=s.day, start=s.start,
                end=s.end, location=s.location,
            )
            for s in sections
        ),
    )


def plans(courses, travel=TRAVEL, **kwargs):
    return generate_course_plans(courses, PlanOptions(**kwargs), travel_times=travel)


# --- helpers -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [("M", "Mon"), ("tue", "Tue"), ("W", "Wed"), ("R", "Thu"), ("Th", "Thu"),
     ("thursday", "Thu"), ("F", "Fri"), ("S", "Sat"), ("U", "Sun")],
)
def test_normalize_day_aliases(raw, expected):
    assert normalize_day(raw) == expected


def test_parse_time_accepts_short_and_seconds():
    assert parse_time("9:00") == 540
    assert parse_time("09:00:00") == 540
    with pytest.raises(ValueError):
        parse_time("25:00")


# --- bundles -------------------------------------------------------------


def test_bundle_has_one_lecture_and_one_tutorial():
    cs = course(
        "CS2311", 3,
        section("C01", "Mon", "09:00", "10:50"),
        section("T01", "Wed", "10:00", "10:50"),
        section("T02", "Thu", "10:00", "10:50"),
    )
    options = build_course_options(cs)
    assert sorted(o.section_codes for o in options) == [("C01", "T01"), ("C01", "T02")]


def test_section_with_two_meetings_stays_together():
    cs = course(
        "CS3334", 3,
        section("C01", "Mon", "09:00", "10:50"),
        section("C01", "Thu", "09:00", "09:50"),
    )
    (option,) = build_course_options(cs)
    assert {m.day for m in option.meetings} == {"Mon", "Thu"}


def test_families_are_not_mixed():
    ge = course(
        "GE1354", 3,
        section("CA1", "Mon", "09:00", "10:50"),
        section("LA1", "Tue", "09:00", "09:50"),
        section("LB1", "Wed", "09:00", "09:50"),
    )
    assert [o.section_codes for o in build_course_options(ge)] == [("CA1", "LA1")]


def test_explicit_bundle_definitions():
    ge = course(
        "GE1102", 3,
        section("C01", "Wed", "13:00", "14:20"),
        section("T01", "Wed", "14:30", "15:20"),
        section("T02", "Fri", "14:30", "15:20"),
    )
    options = build_course_options(ge, [["C01", "T02"]])
    assert [o.section_codes for o in options] == [("C01", "T02")]


# --- search --------------------------------------------------------------


def test_two_meeting_section_clash_on_second_day_is_detected():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50"),
               section("C01", "Thu", "14:00", "14:50"))
    b = course("BBB1000", 3, section("C01", "Thu", "14:30", "15:20"))
    report = plans([a, b], required_courses=("AAA1000", "BBB1000"))
    assert report.plans == []
    assert report.rejections["clash"] >= 1


def test_optional_course_can_be_skipped():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "10:50"))
    b = course("BBB1000", 3, section("C01", "Mon", "10:00", "11:50"))
    report = plans([a, b], required_courses=("AAA1000",))
    assert [p.course_codes for p in report.plans] == [("AAA1000",)]
    assert report.plans[0].skipped_courses == ("BBB1000",)


def test_required_section_only_limits_its_own_course():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50"),
               section("C02", "Tue", "09:00", "09:50"))
    b = course("BBB1000", 3, section("C01", "Wed", "09:00", "09:50"))
    report = plans([a, b], required_sections={"AAA1000": ["C02"]})
    best = report.plans[0]
    assert best.course_codes == ("AAA1000", "BBB1000")
    assert best.chosen[0].section_codes == ("C02",)


def test_avoid_days_accepts_aliases():
    a = course("AAA1000", 3, section("C01", "Thu", "09:00", "09:50"),
               section("C02", "Mon", "09:00", "09:50"))
    report = plans([a], avoid_days=("R",))
    assert [p.chosen[0].section_codes for p in report.plans] == [("C02",)]


def test_preferred_days_rank_first():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50"),
               section("C02", "Tue", "09:00", "09:50"))
    report = plans([a], preferred_days=("Tue",))
    assert report.plans[0].chosen[0].section_codes == ("C02",)


def test_credit_limits_and_target():
    courses = [
        course(f"AAA10{i}0", 3, section("C01", day, "09:00", "09:50"))
        for i, day in enumerate(["Mon", "Tue", "Wed", "Thu"])
    ]
    report = plans(courses, max_credits=9, min_credits=9)
    assert report.plans and all(p.total_credits == 9 for p in report.plans)
    report = plans(courses, target_credits=6, max_results=3)
    assert report.plans[0].total_credits == 6


def test_more_credits_ranked_first_without_target():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50"))
    b = course("BBB1000", 3, section("C01", "Mon", "10:00", "10:50"))
    report = plans([a, b])
    assert report.plans[0].course_codes == ("AAA1000", "BBB1000")


def test_fewer_days_ranked_first():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50"))
    b = course("BBB1000", 3, section("C01", "Mon", "10:00", "10:50"),
               section("C02", "Fri", "10:00", "10:50"))
    report = plans([a, b], required_courses=("AAA1000", "BBB1000"))
    assert report.plans[0].chosen[1].section_codes == ("C01",)
    assert report.plans[0].score.days_on_campus == 1


def test_travel_time_rejects_impossible_walk():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50", "LI 3508"))
    b = course("BBB1000", 3, section("C01", "Mon", "10:00", "10:50", "CMC 101"),
               section("C02", "Mon", "11:00", "11:50", "CMC 101"))
    report = plans([a, b], required_courses=("AAA1000", "BBB1000"))
    assert [p.chosen[1].section_codes for p in report.plans] == [("C02",)]
    assert report.rejections["travel"] == 1


def test_unknown_building_warns_instead_of_rejecting():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50", "AC LT-1"))
    b = course("BBB1000", 3, section("C01", "Mon", "10:00", "10:50", "CM Room-3"))
    report = plans([a, b], required_courses=("AAA1000", "BBB1000"))
    assert len(report.plans) == 1
    assert any("Walking time unknown" in w for w in report.warnings)


def test_old_building_codes_are_mapped():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50", "AC1 LT-1"))
    b = course("BBB1000", 3, section("C01", "Mon", "10:00", "10:50", "CMC 101"))
    report = plans([a, b], required_courses=("AAA1000", "BBB1000"))
    assert report.plans == []
    assert report.rejections["travel"] == 1


def test_min_gap_and_lunch_break():
    a = course("AAA1000", 3, section("C01", "Mon", "11:00", "12:50"))
    b = course("BBB1000", 3, section("C01", "Mon", "13:00", "14:50"),
               section("C02", "Mon", "14:00", "15:50"))
    report = plans([a, b], required_courses=("AAA1000", "BBB1000"), min_gap=30)
    assert [p.chosen[1].section_codes for p in report.plans] == [("C02",)]
    report = plans([a, b], required_courses=("AAA1000", "BBB1000"), lunch_minutes=60)
    assert [p.chosen[1].section_codes for p in report.plans] == [("C02",)]


def test_time_window_and_daily_hours():
    a = course("AAA1000", 3, section("C01", "Mon", "08:30", "09:50"),
               section("C02", "Tue", "10:00", "11:50"))
    report = plans([a], earliest_start="09:00")
    assert [p.chosen[0].section_codes for p in report.plans] == [("C02",)]
    report = plans([a], max_daily_hours=1.5)
    assert [p.chosen[0].section_codes for p in report.plans] == [("C01",)]


def test_fixed_timetable_is_respected_and_counted():
    fixed = [{
        "course_code": "CS2311", "section": "C01", "day": "Mon",
        "start_time": "09:00", "end_time": "10:50", "building": "LI", "room": "3508",
    }]
    ge = course("GE1102", 3, section("C01", "Mon", "10:00", "11:50"),
                section("C02", "Tue", "10:00", "11:50"))
    credits = [CatalogCourse("CS2311", "Computer Programming", 3, ())]
    report = generate_course_plans(
        [ge], PlanOptions(), fixed_sessions=fixed, credit_courses=credits,
        travel_times=TRAVEL,
    )
    best = report.plans[0]
    assert best.chosen[0].section_codes == ("C02",)
    assert best.total_credits == 6
    assert any(m.fixed for m in best.meetings)


def test_tight_transfer_in_fixed_timetable_does_not_block_new_courses():
    fixed = [
        {"course_code": "CS1", "section": "C01", "day": "Mon", "start_time": "09:00",
         "end_time": "09:50", "building": "LI", "room": "1"},
        {"course_code": "CS2", "section": "C01", "day": "Mon", "start_time": "10:00",
         "end_time": "10:50", "building": "CMC", "room": "1"},
    ]
    ge = course("GE1102", 3, section("C01", "Wed", "10:00", "11:50"))
    report = generate_course_plans(
        [ge], PlanOptions(), fixed_sessions=fixed, travel_times=TRAVEL,
    )
    assert len(report.plans) == 1


def test_avoid_day_ignores_fixed_classes():
    fixed = [{"course_code": "CS1", "section": "C01", "day": "Fri", "start_time": "09:00",
              "end_time": "09:50", "building": "LI", "room": "1"}]
    ge = course("GE1102", 3, section("C01", "Wed", "10:00", "11:50"))
    report = generate_course_plans(
        [ge], PlanOptions(avoid_days=("Fri",)), fixed_sessions=fixed, travel_times=TRAVEL,
    )
    assert len(report.plans) == 1


def test_missing_required_course_raises_clear_error():
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50"))
    with pytest.raises(ValueError, match="ZZZ9999"):
        plans([a], required_courses=("ZZZ9999",))


def test_no_plan_explanation_lists_reasons():
    a = course("AAA1000", 3, section("C01", "Fri", "09:00", "09:50"))
    report = plans([a], required_courses=("AAA1000",), avoid_days=("Fri",))
    assert report.plans == []
    assert "avoided day" in report.explain_no_plans()


def test_results_are_best_n_not_first_n():
    courses = [
        course("AAA1000", 3, *[section(f"C0{i}", "Fri", "09:00", "09:50") for i in range(1, 6)],
               section("C06", "Mon", "09:00", "09:50")),
    ]
    report = plans(courses, preferred_days=("Mon",), max_results=1)
    assert report.plans[0].chosen[0].section_codes == ("C06",)


def test_search_limit_marks_report_truncated():
    courses = [
        course(f"AAA10{i}0", 3, *[section(f"C0{j}", "Mon", f"{8 + j}:00", f"{8 + j}:50")
                                  for j in range(1, 5)])
        for i in range(5)
    ]
    report = plans(courses, search_limit=20)
    assert report.truncated


def test_to_sessions_matches_export_format():
    a = course("AAA1000", 3, section("C01", "Mon", "9:00", "9:50", "LI 3508"))
    plan = plans([a]).plans[0]
    (session,) = plan.to_sessions()
    assert session["day"] == "Mon"
    assert session["start_time"] == "09:00"
    assert session["building"] == "LI" and session["room"] == "3508"
    assert "AAA1000" in format_plan(plan, 1)


# --- example catalogue and command line ----------------------------------

EXAMPLE = Path(__file__).resolve().parents[1] / "course_catalog.json"


@pytest.mark.skipif(not EXAMPLE.is_file(), reason="example catalogue missing")
def test_example_catalogue_plans():
    report = generate_course_plans(
        load_course_catalog(EXAMPLE),
        PlanOptions(required_courses=("TEST101", "TEST201")),
        travel_times={},
    )
    best = report.plans[0]
    assert best.total_credits == 5
    assert best.score.days_on_campus == 1


@pytest.mark.skipif(not EXAMPLE.is_file(), reason="example catalogue missing")
def test_command_line_runs_and_exports(tmp_path, capsys):
    output = tmp_path / "out" / "plan.ics"
    code = main([
        str(EXAMPLE), "--required", "TEST101", "--avoid-days", "R",
        "--export", "1", "--output", str(output),
        "--semester-start", "2027-01-11", "--semester-end", "2027-01-31",
    ])
    text = capsys.readouterr().out
    assert code == 0
    assert "Plan 1" in text and "Thu" not in text.split("Plan 1", 1)[1].split("\n\n")[0]
    assert output.is_file()


def test_pruning_keeps_the_same_best_plan():
    import random

    random.seed(7)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    courses = []
    for i in range(6):
        code = f"CS{1000 + i}"
        lecture_hours = [random.choice([9, 11, 14]) for _ in range(2)]
        tutorial_hours = [random.choice([10, 13, 16]) for _ in range(3)]
        sections = [
            section(f"C0{j}", random.choice(days), f"{hour}:00", f"{hour + 1}:50")
            for j, hour in enumerate(lecture_hours, start=1)
        ] + [
            section(f"T0{j}", random.choice(days), f"{hour}:00", f"{hour}:50")
            for j, hour in enumerate(tutorial_hours, start=1)
        ]
        courses.append(course(code, 3, *sections))
    best_one = plans(courses, max_results=1, max_credits=12).plans[0]
    best_many = plans(courses, max_results=50, max_credits=12).plans[0]
    assert best_one.score == best_many.score


def test_section_ending_before_it_starts_is_rejected():
    bad = course("AAA1000", 3, section("C01", "Mon", "11:00", "10:00"))
    with pytest.raises(ValueError, match="ends before it starts"):
        plans([bad])
