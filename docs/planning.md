# Course plan generator

The plan generator (menu option 6, or `cityuschedule --courses ...`) works like this:

1. You type the course codes you are interested in, for example `GE1102 GE1401 GE2410`.
2. It takes their sections from the GE course details (the data shown by menu option 5, `data/ge_course_information.json`). You never need to write a JSON file.
3. It fits them around the AIMS timetable you saved in menu option 2, which stays fixed.
4. It says how many timeslots of each course fit your timetable, for example "GE1111 has one timeslot that fits your timetable".
5. It prints one weekly timetable per plan. If GE1234 can be taken on Tuesday 15:00-17:50 or Friday 09:00-11:50, plan 1 puts it on Tuesday and plan 2 on Friday (or the other way round, by ranking).

For one requested GE course, a fit is green and no fit is red. When you enter
multiple GE course codes, each course receives a distinct cyan-to-blue color in
the fit summary and plan details.

You can choose how many of the GE courses to add (`--add-ge N`), days to avoid or prefer, and credit limits. Credit limits are optional. GE courses count as 3 credit units (GE1601 as 1); the credits of your AIMS courses come from the project's credit catalogues. The best plans come first, with the reason for each ranking and the AIMS registration steps.

Each generated result ends with a blue reminder to check live seat availability
using **3. Paste and check an AIMS course offering**.

It is built on the project's existing modules, so it gives the same answers as the rest of the program:

| Job | Module reused |
|---|---|
| Read GE sections (`--add-ge`) | `course_catalog.load_ge_section_catalog` (from `data/ge_course_information.json`) |
| Lecture/tutorial/lab bundles | `aims_table_parser.ParsedAimsTable.registration_bundles` (same rule as menu option 3) |
| Clash test and time parsing | `schedule_conflicts.slots_overlap`, `time_to_minutes` |
| Walking time between buildings | `travel_time.walking_minutes` (`data/travel_time.json`) |
| Credits of your AIMS courses | `planner.calculate_course_credits` and `data/catalogue/*_credits.json` |
| GE areas and terms | `ge_courses.load_ge_courses` (`data/ge_courses.json`) |
| Plan sections to timetable rows | `planner.planned_sections_to_sessions` |

## What it does

- **Keeps bundles complete:** each chosen course gets one section of every activity type (for example lecture `C01` plus tutorial `T02`) from the same section family (`C01`/`T01` and `CA1`/`TA1` are never mixed). A section that meets twice a week stays together.
- **Treats courses as optional unless you mark them required:** it tries plans with and without each optional course, so you see what fits.
- **Never clashes:** new classes may not overlap each other or the timetable you already have.
- **Checks your rules:**
  - days to avoid or prefer
  - earliest start and latest finish times
  - minimum minutes between classes
  - a lunch break (default window 11:30-14:30)
  - a daily-hours limit
  - walking time between buildings
- **Checks rules only for new classes:** a fixed timetable that already breaks a rule (for example a tight walk) does not block every plan.
- **Explains empty results:** if no plan fits, it says how many options each rule rejected.

## Ranking

Plans are sorted by these criteria, in order:

1. Most of your courses fitted in
2. Most credits within the limits (only matters when credits are known)
3. Fewest courses that are harder to register: a waitlist, the AIMS e-form, a registration restriction, or a change of a pre-registered section
4. Fewest classes on non-preferred days (only when `--prefer-days` is set)
5. Fewest days on campus
6. Least waiting time between classes
7. Fewest early (before 09:00) or late (after 19:00) classes
8. Earliest finish

The search uses branch and bound: it stops following a partial plan as soon as it cannot beat the worst of the best plans found so far on criteria 1-5. The result is the true best `--max-results` plans, not the first ones found.

## Menu

Run `cityuschedule` with no arguments and choose **6. Generate timetable plans**. You will be asked for:

1. The semester to check, e.g. `2627A`, `2627B`, or `2627S`
2. Your AIMS timetable HTML: the one saved in option 2 is used if you have one; otherwise type a path, or press Enter to plan without one
3. The course codes you are interested in, e.g. `GE1102 GE1401 GE2410`
4. How many GE courses the generator should add (a positive integer; Enter uses the number of course codes entered)

At least one course code is required in the menu. If the package has no GE
section data for the selected semester, it asks you to enter another semester.
Course codes without section details for a semester that does have data must be
re-entered. The GE count must be at least 1 and no greater than the number of
course codes entered; otherwise, you will be asked for the count again.

Your **Basic settings** (option 1) are applied automatically to newly planned courses: preferred and avoided days, lunch duration and window, minimum gap, and earliest/latest class times. Minimum and maximum credits include the courses in your AIMS timetable. AIMS classes are used for clash and walking-time checks, but are not rejected for violating the day or timing settings. Advanced planner filters remain available when running the planner directly from the command line. After the plans are listed you can save one to **7. Saved timetable plan**. Saved plans show their timetable and Web Add/Drop sections with CRNs. Delete a saved plan from the main menu with `delete plan1` or `delete plan 1`. The AIMS path you use is remembered for next time.

## Command line

```bash
cityuschedule --aims-html aims_schedule.html \
  --courses GE1111 GE2222 GE3333 --add-ge 2 \
  --avoid-days Fri --prefer-days Mon Tue
```

Example output (shortened; GE1111-GE3333 are made-up courses):

```
Timeslots that fit your timetable:
  GE1111 has 2 timeslots that fit your timetable: C01 Tue 15:00-17:50; C02 Fri 09:00-11:50
  GE2222 has one timeslot that fits your timetable: C01 Wed 09:00-11:50
  GE3333 has no timeslot that fits your timetable

Plan 1: 2 course(s) added; 3 day(s) on campus; ...
  GE1111 C01  (? cr)  ...
  GE2222 C01  (? cr)  ...
  Kept from your AIMS timetable: CS2311, MA1200
  Weekly timetable
  Mon
    09:00-10:50  CS2311 C01  LI 3508
  Tue
    15:00-17:50  GE1111 C01  LI 3508
  ...
```

`(? cr)` means the credits are not in the project data; this only matters if you set a credit limit. Course codes without section details (only GE1102 has them at the moment) are listed in a note; import more with the "Import GE course information" GitHub workflow.

If every timeslot of a course clashes with your timetable, it says so:

```
Timeslots that fit your timetable:
  GE1102 has no timeslot that fits your timetable

No plan satisfies all settings.
       2 option(s) rejected: classes clash
```

Plan around a saved AIMS timetable and add one GE course for Semester B 2026/27:

```bash
cityuschedule --aims-html aims_schedule.html \
  --courses GE1102 --add-ge 1 --term 2627B \
  --prefer-days Mon Tue Wed
```

A CSV timetable such as `examples/sample_courses.csv` can be given instead of `--aims-html` for the fixed timetable: `cityuschedule examples/sample_courses.csv --courses GE1102 --term 2627B`.

Days accept `Mon`, `M`, `Thu`, `R`, `Thursday` and so on.

| Option | Meaning |
|---|---|
| `--courses CODE ...` | Course codes you are interested in; sections come from the GE course details (option 5) |
| `--add-ge N` | Add exactly N GE courses: from your `--courses`, or from all GE section data if no codes are given |
| `--ge-bundles FILE` | Valid section combinations listed by hand, e.g. `{"GE1102": [["C01", "T01"]]}` |
| `--aims-html FILE` | Your current timetable; its classes are kept fixed |
| `--required CODE ...` | Courses every plan must include |
| `--require-section CODE SEC ...` | Sections that must be used, e.g. `TEST101 C01` |
| `--exclude CODE ...` | Courses to ignore |
| `--max-courses N` | Most new courses |
| `--min-credits`, `--max-credits` | Credit limits; totals include the AIMS timetable |
| `--credit-catalog FILE ...` | Extra credit lists for your courses (added to `data/catalogue/*_course_requirements.json`) |
| `--prefer-days`, `--avoid-days` | Day preferences |
| `--earliest 0900`, `--latest 1800` | Allowed class times (also accept `HH:MM`) |
| `--min-gap 10` | Minimum minutes between consecutive classes |
| `--lunch 30 --lunch-window 1200 1400` | Free minutes needed in a lunch window on class days |
| `--max-daily-hours 6` | Maximum class hours per day |
| `--no-travel-check` | Skip walking-time checks |
| `--max-results N` | Number of plans to show (default 5) |
| `--ask` | After listing plans, ask which ones to save |
| `--study-load full-time\|part-time\|summer\|none` | CityU study-load credit limit (default `none`: no credit limit) |
| `--allow-overload` | Allow more credits than the study-load maximum |
| `--allow-section-change` | Let pre-registered courses move to other sections |
| `--seats open\|waitlist\|any` | Which full sections may be used (default `waitlist`) |
| `--web-only` | Leave out non-web-enabled and restricted sections |
| `--term 2627A` | Only courses offered in that term |
| `--no-steps` | Hide the registration steps |

## CityU registration rules

The planner follows the course registration rules of CityU's Academic Regulations and Records Office ([Course Registration](https://www.cityu.edu.hk/arro/creg/creg_main.htm)). It only plans: you still register yourself in AIMS during your time-ticket. It never adds courses, holds seats or watches section capacity, which CityU forbids ([Web Add/Drop](https://www.cityu.edu.hk/arro/creg/wadp_main.htm)).

| CityU rule | What the planner does |
|---|---|
| Core courses are pre-registered by your home academic unit ([Course Registration](https://www.cityu.edu.hk/arro/creg/creg_main.htm)) | Classes from your AIMS timetable are kept as they are. With `--allow-section-change`, a pre-registered course that is also in your course list may move to another section. It is never dropped, plans that keep your sections rank higher, and it never moves into a full or e-form section. |
| Change sections by dropping and adding in the same request, with no clash ([Web Add/Drop](https://www.cityu.edu.hk/arro/creg/wadp_main.htm)) | The steps say "Web Add/Drop, in ONE request: drop ... and add ..." with the new CRNs. |
| Courses with lecture, tutorial and lab sections are added together as a matching group ([Web Add/Drop](https://www.cityu.edu.hk/arro/creg/wadp_main.htm)) | One section of each required type from the same section family, listed together with their CRNs. Family letters must match (`CA1` pairs with `LA3` and `TA2`); digit-only suffixes share the `0` family (`C32`, `L20`, `T12`). Incomplete families are rejected as “no class bundles fit.” |
| Study load: full-time 12-18 credits, part-time at most 11, Summer Term at most 7 ([Study Load](https://www.cityu.edu.hk/arro/creg/creg_sdfu.htm)) | Only with `--study-load` (off by default, so students whose courses have no credit data can still plan). The maximum is a hard limit (a higher `--max-credits` is lowered, unless `--allow-overload`). Plans below 12 credits are still shown but marked as needing reduced-load approval. Totals include your AIMS courses. |
| LC2018, LC2031 and PED courses do not count towards the study load ([Course Registration](https://www.cityu.edu.hk/arro/creg/creg_main.htm)) | They count as 0 credits. |
| Full sections can only be waitlisted, from 8:45 am on the first day of the 3rd time-ticket; a seat is not guaranteed ([Waitlist](https://www.cityu.edu.hk/arro/creg/wadp_wlst.htm)) | Full sections with `waitlist` `Y` are marked `[waitlist]` and rank lower; full sections without a waitlist are left out. Use `--seats` to change this. |
| Avoid swapping into a section that is almost full ([Personal Class Schedule](https://www.cityu.edu.hk/arro/creg/schd_main.htm)) | Sections with 3 or fewer seats get a "have a backup plan" note. |
| Non-web-enabled courses, or bypassing a restriction, need the AIMS e-form during the last time-ticket and approval from the course-offering unit ([Non-web-enabled Course](https://www.cityu.edu.hk/arro/creg/nweb_main.htm), [Registration Restrictions](https://www.cityu.edu.hk/arro/creg/wadp_rstr.htm)) | Marked `[e-form]` or `[restricted]` and rank lower; `--web-only` leaves them out. |
| GE quota control: only a limited number of GE Area 1-3 courses in the 2nd time-ticket ([Time-ticket](https://www.cityu.edu.hk/arro/creg/wadp_ttkt.htm), [GE Quota](https://www.cityu.edu.hk/arro/creg/wadp_geqt.htm)) | A plan with two or more Area 1-3 courses says to add the others in the 3rd time-ticket. |
| Courses are offered in particular terms (offering terms in `data/catalogue/*_course_requirements.json` and `data/ge_courses.json`) | With `--term 2627A` (or `Semester A 2026/27`, `2026-27 Sem A`), courses not offered in that term are left out. Courses with no term data are kept. |
| Check prerequisites yourself; DegreeWorks study plans do not ([DegreeWorks](https://www.cityu.edu.hk/arro/dgwk/dgwk_main.htm)) | Prerequisites and precursors are listed for you to verify in DegreeWorks or the course catalogue. The planner does not track courses you have completed. Two exclusive courses are never in the same plan, and a candidate exclusive with a course already on your timetable is skipped. Requirements come from `data/catalogue/*_course_requirements.json` and your course list. |

### Optional section fields

Copy these from the Master Class Schedule to get the registration checks ([Personal Class Schedule](https://www.cityu.edu.hk/arro/creg/schd_main.htm)):

```json
{"section": "C01", "day": "Mon", "start": "09:00", "end": "10:50", "location": "LI 3508",
 "crn": "10001", "availability": "12", "waitlist": "Y", "web": "Y",
 "restrictions": "only for College: CB"}
```

- `crn`: shown in the registration steps.
- `availability`: seats left, or `Full`.
- `waitlist`: `Y`, `N` or `Full`, from the Waitlist Avail column.
- `web`: `N` if the course is not web-enabled.
- `restrictions`: registration restriction text. Notes containing "only for" or "not for" are also treated as restrictions.

A course can also list `prerequisites`, `precursors` and `exclusive_courses`.

### Not covered

- Your exact time-ticket times, cohort GE limits and eligibility for restricted sections: check them in AIMS.
- Live seat numbers: the planner only knows what you copy into the course list.
- Degree requirements: use DegreeWorks to choose which courses you need.

## Python

```python
from cityuschedule.aims import load_aims_html
from cityuschedule.course_catalog import load_ge_section_catalog
from cityuschedule.plan_generator import PlanOptions, format_plan, generate_course_plans

report = generate_course_plans(
    [c for c in load_ge_section_catalog() if c.code == "GE1102"],
    PlanOptions(avoid_days=("Fri",), max_results=3),
    fixed_sessions=load_aims_html("aims_schedule.html"),
)

for warning in report.warnings:
    print("Note:", warning)

if not report.plans:
    print(report.explain_no_plans())

for number, plan in enumerate(report.plans, start=1):
    print(format_plan(plan, number))
    sessions = plan.to_sessions()  # ready for timetable.format_timetable
```

Use `PlanOptions(bundle_definitions={"GE1102": [["C01", "T01"], ["C01", "T02"]]})` when a course's valid section combinations are listed separately, as with `--ge-bundles`.

## Limits

- Buildings not in `travel_time.json` (for example `AC` in the sample CSV) are reported as a note and not checked.
- Sections without a fixed time are kept in the plan but are not checked for clashes, and a note lists them.
- The search stops after `search_limit` combinations (default 200,000) and the report says so. Pruning keeps typical semesters of 6-8 candidate courses far below this.
