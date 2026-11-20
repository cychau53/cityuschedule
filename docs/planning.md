# Course plan generator

The plan generator (`cityuschedule plan`, menu option 11) builds every complete, clash-free combination of the courses you are considering and lists the best ones first, with a short reason for each ranking.

## What it does

- **Keeps bundles complete:** each chosen course gets one section of every activity type (for example lecture `C01` plus tutorial `T02`) from the same section family. A section that meets twice a week stays together.
- **Treats courses as optional unless you mark them required:** it tries plans with and without each optional course, so you see what fits.
- **Never clashes:** new classes may not overlap each other or the timetable you already have.
- **Checks your rules:**
  - days to avoid or prefer
  - earliest start and latest finish times
  - minimum minutes between classes
  - a lunch break (default window 11:30-14:30)
  - a daily-hours limit
  - walking time between buildings (from `data/travel_time.json`)
- **Checks rules only for new classes:** a fixed timetable that already breaks a rule (for example a tight walk) does not block every plan.
- **Explains empty results:** if no plan fits, it says how many options each rule rejected.

## Ranking

Plans are sorted by these criteria, in order:

1. Credits: closest to `--target-credits`, otherwise the most credits within `--max-credits`
2. Fewest classes on non-preferred days (only when `--prefer-days` is set)
3. Fewest days on campus
4. Least waiting time between classes
5. Fewest early (before 09:00) or late (after 19:00) classes
6. Earliest finish

## Menu

Run `cityuschedule` with no arguments and choose **11. Smart plan generator**. You will be asked for:

1. The course timetable catalogue JSON (default `course_catalog.json`)
2. Whether to plan around your remembered AIMS timetable, or a path to one (Enter to skip)
3. Courses that must be included
4. Lunch break minutes, minimum gap, earliest start and latest end (Enter to skip each)

Your **Basic settings** (option 1) are applied automatically: preferred days, avoided days, minimum and maximum credits. The top 5 plans are shown, and you can then export one to an `.ics` file. The AIMS path you use is remembered for next time.

## Command line

```bash
cityuschedule plan course_catalog.json \
  --required TEST101 \
  --avoid-days Thu \
  --lunch 45 \
  --max-credits 18 \
  --max-results 5
```

Plan around a saved AIMS timetable and export plan 1:

```bash
cityuschedule plan my_catalogue.json \
  --aims-html aims_schedule.html \
  --max-credits 18 --prefer-days Mon Tue Wed \
  --export 1 --output exports/plan.ics \
  --semester-start 2027-01-11 --semester-end 2027-04-24 \
  --exclusions exclusions.json
```

The semester dates default to the project's current values (2026-08-31 to 2026-11-28). Replace them with the official CityU teaching dates for the semester you are planning. `python -m cityuschedule.plan_generator` works the same way as `cityuschedule plan`.

Days accept `Mon`, `M`, `Thu`, `Th`, `R`, `Thursday` and so on.

| Option | Meaning |
|---|---|
| `--required CODE ...` | Courses every plan must include |
| `--require-section CODE:SEC[,SEC]` | Sections that must be used, e.g. `CS2311:C01,T02` |
| `--exclude CODE ...` | Courses to ignore |
| `--min-courses`, `--max-courses` | Number of new courses |
| `--min-credits`, `--max-credits`, `--target-credits` | Credit limits; totals include the AIMS timetable |
| `--prefer-days`, `--avoid-days` | Day preferences |
| `--earliest 09:00`, `--latest 18:00` | Allowed class times |
| `--min-gap 10` | Minimum minutes between consecutive classes |
| `--lunch 45` | Free minutes needed between 11:30 and 14:30 on class days |
| `--max-daily-hours 6` | Maximum class hours per day |
| `--no-travel-check` | Skip walking-time checks |
| `--export N` | Export plan N as `.ics` |
| `--ask-export` | After listing plans, ask which one to export |
| `--output`, `--semester-start`, `--semester-end`, `--exclusions` | Export settings |

## Python

```python
from cityuschedule.course_catalog import load_course_catalog
from cityuschedule.plan_generator import PlanOptions, format_plan, generate_course_plans

report = generate_course_plans(
    load_course_catalog("course_catalog.json"),
    PlanOptions(required_courses=("TEST101",), avoid_days=("Fri",), max_results=3),
)

for warning in report.warnings:
    print("Note:", warning)

if not report.plans:
    print(report.explain_no_plans())

for number, plan in enumerate(report.plans, start=1):
    print(format_plan(plan, number))
    sessions = plan.to_sessions()  # ready for timetable.format_timetable or export_ics
```

Use `PlanOptions(bundle_definitions={"GE1102": [["C01", "T01"], ["C01", "T02"]]})` when a course's valid section combinations are listed separately, as with `--ge-bundles`.

## Limits

- Buildings not in `travel_time.json` (for example `AC` in the sample CSV) are reported as a note and not checked. The old codes `AC1`, `AC2` and `AC3` are mapped to `YEUNG`, `LI` and `LAU`.
- Sections without a fixed time are kept in the plan but are not checked for clashes, and a note lists them.
- The search stops after `search_limit` combinations (default 200,000) and the report says so. Pruning keeps typical semesters of 6-8 candidate courses far below this.
