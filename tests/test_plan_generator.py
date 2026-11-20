import json
from pathlib import Path

import pytest

from cityuschedule import cli
from cityuschedule.course_catalog import (
    CatalogCourse,
    CatalogSection,
    load_course_catalog,
    load_ge_section_catalog,
)
from cityuschedule.plan_generator import (
    CourseRequirements,
    PlanOptions,
    build_course_options,
    course_requirements_from_records,
    format_plan,
    generate_course_plans,
    load_course_requirements,
    load_ge_areas,
    resolve_study_load,
    section_status,
    term_key,
    to_day,
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
    kwargs.setdefault("study_load", None)
    return generate_course_plans(courses, PlanOptions(**kwargs), travel_times=travel)


# --- helpers -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [("M", "Mon"), ("tue", "Tue"), ("W", "Wed"), ("R", "Thu"),
     ("thursday", "Thu"), ("F", "Fri"), ("S", "Sat"), ("U", "Sun")],
)
def test_day_aliases(raw, expected):
    assert to_day(raw) == expected


def test_unknown_day_is_rejected():
    with pytest.raises(ValueError):
        to_day("Someday")


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


def test_credit_limits():
    courses = [
        course(f"AAA10{i}0", 3, section("C01", day, "09:00", "09:50"))
        for i, day in enumerate(["Mon", "Tue", "Wed", "Thu"])
    ]
    report = plans(courses, max_credits=9, min_credits=9)
    assert report.plans and all(p.total_credits == 9 for p in report.plans)
    report = plans(courses, max_courses=2, max_results=3)
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
    a = course("AAA1000", 3, section("C01", "Mon", "09:00", "09:50", "LI 3508"))
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
    cli.main([
        "--timetable-catalog", str(EXAMPLE), "--required", "TEST101",
        "--avoid-days", "R", "--export-plan", "1", "--output", str(output),
        "--semester-start", "2027-01-11", "--semester-end", "2027-01-31",
    ])
    text = capsys.readouterr().out
    assert "Plan 1" in text and "Thu" not in text.split("Plan 1", 1)[1].split("\n\n")[0]
    assert output.is_file()


def test_bundles_come_from_the_aims_table_rule():
    """The planner uses ParsedAimsTable.registration_bundles, so menu
    option 4 and the plan generator always agree."""
    from cityuschedule.aims_table_parser import AimsSession, ParsedAimsTable

    sections = [
        section("C01", "Mon", "09:00", "09:50"), section("CA1", "Tue", "09:00", "09:50"),
        section("T01", "Wed", "09:00", "09:50"), section("TA1", "Thu", "09:00", "09:50"),
    ]
    table = ParsedAimsTable("AAA1000", tuple(
        AimsSession("AAA1000", "", s.section, 3, "M", "09:00", "09:50") for s in sections
    ))
    options = build_course_options(course("AAA1000", 3, *sections))
    assert [o.section_codes for o in options] == table.registration_bundles()


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


# --- CityU course registration rules ---------------------------------------


def sec(code, day, start, end, **fields):
    return dict(section=code, day=day, start=start, end=end, location="LI 3508", **fields)


def reg_course(code, credits, *sections):
    """Like course(), but sections are dicts with registration fields."""
    return CatalogCourse(
        code=code,
        title=f"{code} title",
        credits=credits,
        sections=tuple(CatalogSection(course_code=code, **s) for s in sections),
    )


def run(courses, fixed=(), requirements=None, ge_areas=None, **kwargs):
    kwargs.setdefault("max_results", 20)
    return generate_course_plans(
        courses,
        PlanOptions(**kwargs),
        fixed_sessions=fixed,
        travel_times={},
        requirements=requirements,
        ge_areas=ge_areas,
    )


def aims(code, section, day, start, end, crn=""):
    return {
        "course_code": code, "section": section, "crn": crn, "day": day,
        "start_time": start, "end_time": end, "building": "LI", "room": "3508",
    }


def six_courses():
    return [
        reg_course(f"CS{1000 + i}", 3, sec("C01", day, "09:00", "10:50"))
        for i, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    ]


# --- study load -----------------------------------------------------------


def test_study_load_values():
    assert resolve_study_load("full-time") == (12, 18)
    assert resolve_study_load("Part time") == (0, 11)
    assert resolve_study_load("summer") == (0, 7)
    assert resolve_study_load(None) is None
    assert resolve_study_load("none") is None
    with pytest.raises(ValueError):
        resolve_study_load("sometimes")


def test_full_time_maximum_is_enforced():
    best = run(six_courses(), study_load="full-time").plans[0]
    assert best.total_credits == 18


def test_user_maximum_above_limit_is_lowered_with_warning():
    report = run(six_courses(), study_load="full-time", max_credits=21)
    assert report.plans[0].total_credits == 18
    assert any("lowered from 21 to 18" in w for w in report.warnings)


def test_overload_can_be_allowed():
    report = run(six_courses(), study_load="full-time", max_credits=21, allow_overload=True)
    plan = report.plans[0]
    assert plan.total_credits == 21
    assert "over the 18-credit maximum" in plan.explain()
    assert any("overload needs approval" in s for s in plan.registration_steps())


def test_summer_term_limit():
    assert run(six_courses(), study_load="summer").plans[0].total_credits == 6


def test_below_minimum_is_listed_but_flagged():
    plan = run(six_courses()[:2], study_load="full-time").plans[0]
    assert plan.total_credits == 6
    assert "below the 12-credit minimum" in plan.explain()
    assert any("reduced load needs approval" in s for s in plan.registration_steps())


def test_non_credit_courses_do_not_count():
    courses = [
        reg_course("PED1001", 1, sec("C01", "Mon", "09:00", "10:50")),
        reg_course("LC2018", 1, sec("C01", "Tue", "09:00", "10:50")),
        reg_course("CS1000", 3, sec("C01", "Wed", "09:00", "10:50")),
    ]
    plan = run(courses, required_courses=("PED1001", "LC2018", "CS1000")).plans[0]
    assert set(plan.course_codes) == {"PED1001", "LC2018", "CS1000"}
    assert plan.total_credits == 3


def test_fixed_credits_count_towards_study_load():
    fixed = [aims("CS9000", "C01", "Mon", "14:00", "15:50")]
    report = generate_course_plans(
        six_courses(),
        PlanOptions(study_load="full-time"),
        fixed_sessions=fixed,
        credit_courses=[reg_course("CS9000", 6)],
        travel_times={},
    )
    assert report.plans[0].total_credits == 18
    assert report.plans[0].new_credits == 12


# --- pre-registered courses ----------------------------------------------


def preregistered_setup():
    cs = reg_course(
        "CS2311", 3,
        sec("C01", "Mon", "09:00", "10:50", crn="10001"),
        sec("C02", "Wed", "09:00", "10:50", crn="10011"),
    )
    other = reg_course("MA1200", 3, sec("C01", "Mon", "09:00", "11:50", crn="20001"))
    fixed = [aims("CS2311", "C01", "Mon", "09:00", "10:50", "10001")]
    return [cs, other], fixed


def test_preregistered_course_stays_fixed_by_default():
    courses, fixed = preregistered_setup()
    report = run(courses, fixed, min_courses=0)
    plan = report.plans[0]
    assert plan.course_codes == ()  # MA1200 clashes with the fixed CS2311
    assert plan.fixed_courses == ("CS2311",)
    assert any("already in your timetable" in w for w in report.warnings)


def test_section_change_frees_the_slot_and_lists_drop_and_add():
    courses, fixed = preregistered_setup()
    report = run(courses, fixed, allow_section_changes=True)
    plan = report.plans[0]
    assert set(plan.course_codes) == {"CS2311", "MA1200"}
    cs = next(o for o in plan.chosen if o.course_code == "CS2311")
    assert cs.section_codes == ("C02",)
    assert cs.replaces_sections == ("C01",)
    assert plan.score.section_changes == 1
    steps = "\n".join(plan.registration_steps())
    assert "in ONE request: drop CS2311 C01 and add C02 CRN 10011" in steps
    assert "change from C01" in format_plan(plan, 1)


def test_keeping_preregistered_sections_ranks_first():
    courses, fixed = preregistered_setup()
    report = run(courses[:1], fixed, allow_section_changes=True)
    first = report.plans[0].chosen[0]
    assert first.section_codes == ("C01",) and not first.replaces_sections
    assert report.plans[0].score.section_changes == 0
    assert "Keep pre-registered: CS2311 C01" in report.plans[0].registration_steps()


def test_preregistered_course_cannot_be_left_out():
    courses, fixed = preregistered_setup()
    report = run(courses, fixed, allow_section_changes=True)
    assert all("CS2311" in p.course_codes for p in report.plans)


def test_section_change_never_moves_into_a_full_section():
    cs = reg_course(
        "CS2311", 3,
        sec("C01", "Mon", "09:00", "10:50"),
        sec("C02", "Wed", "09:00", "10:50", availability="Full", waitlist="Y"),
    )
    fixed = [aims("CS2311", "C01", "Mon", "09:00", "10:50")]
    report = run([cs], fixed, allow_section_changes=True)
    assert [o.section_codes for p in report.plans for o in p.chosen] == [("C01",)]


def test_preregistered_course_missing_from_list_stays_fixed():
    _, fixed = preregistered_setup()
    report = run([reg_course("MA1200", 3, sec("C01", "Tue", "09:00", "10:50"))], fixed,
                 allow_section_changes=True)
    assert report.plans[0].fixed_courses == ("CS2311",)
    assert any("stay as they are: CS2311" in w for w in report.warnings)


# --- seats, waitlist, web-enabled and restrictions -----------------------


def test_section_status_parsing():
    full = CatalogSection("A", "C01", "Mon", "09:00", "09:50", "", availability="FULL",
                          waitlist="Yes", web="N")
    status = section_status(full)
    assert status.full and status.waitlist == "Y" and not status.web_enabled
    open_ = CatalogSection("A", "C01", "Mon", "09:00", "09:50", "", availability="12")
    assert section_status(open_).seats == 12 and not section_status(open_).full
    noted = CatalogSection("A", "C01", "Mon", "09:00", "09:50", "",
                           notes=("only for College: CB",))
    assert section_status(noted).restrictions == "only for College: CB"


def routes_course():
    return reg_course(
        "CS3000", 3,
        sec("C01", "Mon", "09:00", "10:50", availability="Full", waitlist="N", crn="1"),
        sec("C02", "Tue", "09:00", "10:50", availability="Full", waitlist="Y", crn="2"),
        sec("C03", "Wed", "09:00", "10:50", availability="20", web="N", crn="3"),
        sec("C04", "Thu", "09:00", "10:50", availability="2", crn="4"),
    )


def test_bundle_routes():
    routes = {o.section_codes[0]: o.route for o in build_course_options(routes_course())}
    assert routes == {"C01": "closed", "C02": "waitlist", "C03": "e-form", "C04": "web"}


def test_seat_policies():
    def sections(**kwargs):
        report = run([routes_course()], required_courses=("CS3000",), **kwargs)
        return {p.chosen[0].section_codes[0] for p in report.plans}

    assert sections() == {"C02", "C03", "C04"}
    assert sections(seat_policy="open") == {"C03", "C04"}
    assert sections(seat_policy="any") == {"C01", "C02", "C03", "C04"}
    assert sections(web_only=True) == {"C02", "C04"}


def test_easier_registration_ranks_first():
    report = run([routes_course()], required_courses=("CS3000",))
    assert report.plans[0].chosen[0].section_codes == ("C04",)
    notes = report.plans[0].registration_steps()
    assert any("only 2 seat(s) left" in n for n in notes)


def test_registration_steps_for_each_route():
    report = run([routes_course()], required_courses=("CS3000",))
    steps = {p.chosen[0].section_codes[0]: "\n".join(p.registration_steps())
             for p in report.plans}
    assert "Web Add/Drop: add CS3000 (C04 CRN 4)" in steps["C04"]
    assert "3rd time-ticket" in steps["C02"] and "not guaranteed" in steps["C02"]
    assert "AIMS e-form" in steps["C03"] and "last time-ticket" in steps["C03"]


def test_multi_component_course_is_added_together():
    db = reg_course(
        "CS3201", 3,
        sec("C01", "Mon", "09:00", "10:50", crn="40001"),
        sec("T01", "Tue", "09:00", "09:50", crn="40002"),
    )
    steps = run([db]).plans[0].registration_steps()
    assert "1. Web Add/Drop: add CS3201 (C01 CRN 40001, T01 CRN 40002), " \
           "all sections together" in steps


def test_restricted_section_is_flagged():
    restricted = reg_course(
        "MA2001", 3,
        sec("C01", "Mon", "09:00", "10:50", restrictions="only for College: CSCI"),
    )
    plan = run([restricted]).plans[0]
    assert plan.chosen[0].restricted
    assert "[restricted]" in format_plan(plan, 1)
    assert any("registration restrictions" in s for s in plan.registration_steps())


def test_crn_is_exported_with_sessions():
    db = reg_course("CS3201", 3, sec("C01", "Mon", "09:00", "10:50", crn="40001"))
    assert run([db]).plans[0].to_sessions()[0]["crn"] == "40001"


# --- prerequisites, exclusive and equivalent courses ---------------------


REQS = {
    "CS2312": CourseRequirements(prerequisites=("CS2311",)),
    "CS1302": CourseRequirements(exclusive=("CS1102",)),
    "CS2310": CourseRequirements(equivalent=("CS2311",)),
    "CS3103": CourseRequirements(precursors=("CS2310", "CS2311")),
}


def req_courses():
    return [
        reg_course(code, 3, sec("C01", day, "09:00", "10:50"))
        for code, day in [("CS2312", "Mon"), ("CS1302", "Tue"), ("CS2310", "Wed"),
                          ("CS3103", "Thu"), ("CS1102", "Fri")]
    ]


def test_completed_courses_drive_requirement_checks():
    report = run(req_courses(), requirements=REQS, completed_courses=("CS1102",))
    codes = set(report.plans[0].course_codes)
    assert codes == {"CS2310", "CS3103"}
    text = "\n".join(report.warnings)
    assert "CS1102 is already completed" in text
    assert "CS2312 skipped: missing prerequisite" in text
    assert "CS1302 skipped: exclusive with CS1102" in text
    notes = report.plans[0].registration_steps()
    assert any("recommended precursor" in n for n in notes)


def test_equivalent_course_completed():
    report = run(req_courses(), requirements=REQS, completed_courses=("CS2311",))
    assert "CS2310" not in report.plans[0].course_codes
    assert any("equivalent course CS2311" in w for w in report.warnings)


def test_without_completed_courses_prerequisites_are_only_noted():
    report = run(req_courses(), requirements=REQS)
    assert "CS2312" in report.plans[0].course_codes
    assert any("Check prerequisites" in w and "CS2312" in w for w in report.warnings)


def test_exclusive_courses_never_share_a_plan():
    report = run(req_courses(), requirements=REQS)
    for plan in report.plans:
        assert not {"CS1302", "CS1102"} <= set(plan.course_codes)
    assert report.rejections["exclusive"] > 0


def test_required_course_with_missing_prerequisite_is_kept():
    report = run(req_courses(), requirements=REQS, completed_courses=("CS1102",),
                 required_courses=("CS2312",))
    assert "CS2312" in report.plans[0].course_codes
    assert any("kept because it is required" in w for w in report.warnings)


def test_requirement_records_from_project_formats():
    records = [
        {"course_code": "CS2312", "prerequisites": [], "precursors": ["CS2310", "CS2311"],
         "exclusive_courses": ["CS2332"], "equivalent_courses": []},
        {"course_code": "CB2100", "prerequisites": "CB1000 or CB1001",
         "exclusions": "", "equivalents": ""},
        {"code": "GE1205", "credits": 3},
    ]
    result = course_requirements_from_records(records)
    assert result["CS2312"].precursors == ("CS2310", "CS2311")
    assert result["CS2312"].exclusive == ("CS2332",)
    assert result["CB2100"].prerequisites == ("CB1000", "CB1001")
    assert "GE1205" not in result


def test_project_data_loads():
    requirements = load_course_requirements()
    assert requirements["CS2311"].precursors
    assert load_ge_areas()["GE1102"] == "Area 1"


# --- GE quota control ----------------------------------------------------


def test_ge_quota_note_for_two_area_courses():
    ges = [
        reg_course("GE1102", 3, sec("C01", "Mon", "09:00", "10:50")),
        reg_course("GE1205", 3, sec("C01", "Tue", "09:00", "10:50")),
        reg_course("GE1401", 3, sec("C01", "Wed", "09:00", "10:50")),
    ]
    areas = {"GE1102": "Area 1", "GE1205": "Area 2", "GE1401": "University Req."}
    plan = run(ges, ge_areas=areas).plans[0]
    assert plan.ge_quota_courses == ("GE1102", "GE1205")
    assert any("GE quota control" in s for s in plan.registration_steps())


# --- search stays exact --------------------------------------------------


def test_pruning_with_registration_risk_keeps_the_best_plan():
    import random

    random.seed(11)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for _ in range(40):
        courses = []
        for i in range(5):
            sections = []
            for j in range(1, 4):
                hour = random.choice([9, 11, 14, 16])
                extra = random.choice([
                    {}, {"availability": "Full", "waitlist": "Y"}, {"web": "N"},
                    {"availability": "10"},
                ])
                sections.append(sec(f"C0{j}", random.choice(days), f"{hour}:00",
                                    f"{hour + 1}:50", **extra))
            courses.append(reg_course(f"CS{1000 + i}", random.choice([2, 3, 4]), *sections))
        one = run(courses, study_load="full-time", max_results=1).plans[0]
        many = run(courses, study_load="full-time", max_results=500,
                   search_limit=10**7).plans[0]
        assert one.score == many.score


# --- command line and menu -----------------------------------------------


def write_catalogue(path):
    path.write_text(json.dumps({"courses": [
        {"code": "CS2311", "title": "Computer Programming", "credits": 3, "sections": [
            {"section": "C01", "crn": "10001", "day": "Mon", "start": "09:00",
             "end": "10:50", "location": "LI 3508"},
            {"section": "C02", "crn": "10011", "day": "Wed", "start": "09:00",
             "end": "10:50", "location": "LI 3508"}]},
        {"code": "GE1102", "title": "Cinema", "credits": 3, "sections": [
            {"section": "C01", "crn": "20001", "day": "Mon", "start": "09:00",
             "end": "11:50", "location": "LI 1501", "availability": "Full",
             "waitlist": "Y"}]},
    ]}), encoding="utf-8")


def test_catalogue_loader_reads_registration_fields(tmp_path):
    path = tmp_path / "catalogue.json"
    write_catalogue(path)
    ge = next(c for c in load_course_catalog(path) if c.code == "GE1102")
    assert ge.sections[0].waitlist == "Y" and ge.sections[0].crn == "20001"


def test_command_line_registration_options(tmp_path, capsys, monkeypatch):
    path = tmp_path / "catalogue.json"
    write_catalogue(path)
    monkeypatch.setattr(
        "cityuschedule.cli.load_aims_html",
        lambda _: [aims("CS2311", "C01", "Mon", "09:00", "10:50", "10001")],
    )
    html = tmp_path / "aims.html"
    html.write_text("<html></html>", encoding="utf-8")
    cli.main([
        "--timetable-catalog", str(path), "--aims-html", str(html), "--allow-section-change",
        "--required", "GE1102", "--no-travel-check", "--max-results", "1",
        "--study-load", "full-time",
    ])
    text = capsys.readouterr().out
    assert "Registration steps:" in text
    assert "drop CS2311 C01 and add C02 CRN 10011" in text
    assert "3rd time-ticket" in text
    assert "below the 12-credit minimum" in text
    assert "planning only" in text


def test_command_line_open_seats_only(tmp_path, capsys):
    path = tmp_path / "catalogue.json"
    write_catalogue(path)
    cli.main(["--timetable-catalog", str(path), "--required", "GE1102",
              "--seats", "open", "--no-travel-check"])
    assert "section is full" in capsys.readouterr().out


def test_course_without_credits_uses_credit_catalogue_or_zero():
    no_credit = CatalogCourse("CS2311", "Programming", None, (
        CatalogSection("CS2311", "C01", "Mon", "09:00", "10:50", "LI 3508"),
    ))
    unknown = CatalogCourse("XX1000", "Unknown", None, (
        CatalogSection("XX1000", "C01", "Tue", "09:00", "10:50", "LI 3508"),
    ))
    report = generate_course_plans(
        [no_credit, unknown], PlanOptions(study_load="full-time"), travel_times={},
        credit_courses=[reg_course("CS2311", 3)],
    )
    assert report.plans[0].total_credits == 3
    assert any("Credits unknown (counted as 0): XX1000" in w for w in report.warnings)


# --- offering terms and GE section data -----------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [("2627A", ("26", "A")), ("Semester A 2026/27", ("26", "A")),
     ("2026-27 Sem A", ("26", "A")), ("2026-27 Sem B", ("26", "B")),
     ("Summer Term 2026/27", ("26", "S"))],
)
def test_term_key_formats(raw, expected):
    assert term_key(raw) == expected


def test_term_filter_leaves_out_courses_not_offered():
    a = reg_course("CS2311", 3, sec("C01", "Mon", "09:00", "10:50"))
    b = reg_course("CS3334", 3, sec("C01", "Tue", "09:00", "10:50"))
    reqs = {
        "CS2311": CourseRequirements(terms=("Semester A 2026/27",)),
        "CS3334": CourseRequirements(terms=("Semester B 2026/27",)),
    }
    report = run([a, b], requirements=reqs, term="2627B", study_load=None)
    assert all(p.course_codes == ("CS3334",) for p in report.plans)


def test_ge_section_catalog_from_project_data():
    courses = load_ge_section_catalog(term="2026-27 Sem B")
    ge = next(c for c in courses if c.code == "GE1102")
    assert ge.credits == 3
    first = ge.sections[0]
    assert first.section.startswith(("C", "T")) and len(first.section) == 3
    assert ":" in first.start and ":" in first.end


def test_ge_courses_adds_exact_number():
    a = reg_course("GE1101", 3, sec("C01", "Mon", "09:00", "10:50"))
    b = reg_course("GE1102", 3, sec("C01", "Tue", "09:00", "10:50"))
    c = reg_course("CS2311", 3, sec("C01", "Wed", "09:00", "10:50"))
    report = run([a, b, c], ge_courses=1, study_load=None)
    assert report.plans
    for plan in report.plans:
        assert sum(code.startswith("GE") for code in plan.course_codes) == 1


def test_no_credit_limit_means_no_credit_warning():
    """Without credit limits anyone can plan, even with no credit data."""
    unknown = CatalogCourse("XX1000", "Unknown", None, (
        CatalogSection("XX1000", "C01", "Tue", "09:00", "10:50", "LI 3508"),
    ))
    report = generate_course_plans([unknown], PlanOptions(), travel_times={})
    assert report.plans and not report.warnings
    assert report.plans[0].explain().startswith("1 course(s) added")


def test_more_courses_rank_before_more_credits():
    a = course("AAA1000", 9, section("C01", "Mon", "09:00", "11:50"))
    b = course("BBB1000", 3, section("C01", "Mon", "09:00", "09:50"))
    c = course("CCC1000", 3, section("C01", "Mon", "10:00", "10:50"))
    best = plans([a, b, c]).plans[0]
    assert set(best.course_codes) == {"BBB1000", "CCC1000"}


def test_fit_summary_counts_timeslots():
    ge = course("GE1111", 3, section("C01", "Tue", "15:00", "17:50"),
                section("C02", "Fri", "09:00", "11:50"))
    report = plans([ge], avoid_days=("Fri",))
    assert report.fit_summary() == [
        "GE1111 has one timeslot that fits your timetable: C01 Tue 15:00-17:50"
    ]
