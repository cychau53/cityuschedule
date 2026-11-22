# Setup and usage

This guide explains how to install `cityuschedule` from its source repository and use its interactive menu and command-line workflows. It requires Python 3.10 or later.

## Install from source

Clone the repository, create and activate a virtual environment, and install the project with its development dependencies:

```bash
git clone https://github.com/cychau53/cityuschedule.git
cd cityuschedule
python -m venv .venv
```

Activate the environment:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Then install and verify the command:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cityuschedule --help
```

The editable install is convenient for development: changes in the checkout are immediately available. To install runtime dependencies only, use `python -m pip install -e .` instead. The project requires `beautifulsoup4` and `pypdf`; the `dev` extra adds pytest, pytest-cov, and Ruff.

## Interactive menu

Run the command without arguments to open the menu:

```bash
cityuschedule
```

The menu can check or change a saved AIMS timetable, accept a pasted AIMS course offering, search or inspect GE course information, generate course plans, and show saved plans. Choose **1. Basic settings** to configure preferences including preferred/avoided days, credit limits, lunch duration and window, a minimum gap between classes, and earliest/latest class times. Settings and the remembered AIMS path are stored locally in the application's configuration directory. The menu shows how to clear individual settings or saved data.

Type `cityuschedule --help` for all command-line flags. `q` returns to the menu at supported prompts; `0` exits.

## Check an AIMS timetable for clashes

Save your weekly AIMS timetable as an HTML file, then run:

```bash
cityuschedule --aims-html path/to/your_aims_timetable.html
```

The tool displays the parsed weekly timetable and reports overlapping scheduled sessions. Only scheduled grid classes are included; entries without dates/times are not included.

## Check a pasted AIMS offering against your timetable

First provide a saved AIMS weekly timetable. The interactive workflow prompts you to paste one complete course-offering table, finish with `END` on its own line, and optionally exclude sections you cannot register for:

```bash
cityuschedule --aims-html path/to/your_aims_timetable.html --paste-aims
```

You can also configure constraints on the command line. For example:

```bash
cityuschedule --aims-html path/to/your_aims_timetable.html \
  --paste-aims --prefer-days Mon Tue --avoid-days Fri \
  --lunch 30 --lunch-window 12:00 14:00 --min-gap 15
```

The command reports candidate complete section bundles that fit the weekly timetable and the supplied constraints. The pasted table should include the course heading and its complete section information; if the heading is missing, enter the course code when prompted. Use `--help` for the supported options and formats.

## Generate course plans

The planner uses the course catalogues included with the project. Give it course codes and a semester; add an existing schedule as an AIMS HTML file or CSV if you want to plan around fixed classes:

```bash
cityuschedule --courses GE1102 GE1401 --term 2627B
cityuschedule --aims-html path/to/your_aims_timetable.html \
  --courses GE1102 --term 2627B --add-ge 1 --avoid-days Fri
```

Semester codes include examples such as `2627A`, `2627B`, and `2627S`. The planner lists candidate plans and explains rejected constraints when no plan fits. Add `--ask` to interactively choose plans to save. Saved plans can be reviewed in the menu.

A CSV can be supplied as the positional fixed timetable:

```bash
cityuschedule examples/sample_courses.csv --courses GE1102 --term 2627B
```

Useful planning constraints include `--min-credits`, `--max-credits`, `--prefer-days`, `--avoid-days`, `--earliest`, `--latest`, `--min-gap`, `--lunch`, `--max-daily-hours`, `--no-travel-check`, `--study-load`, and `--seats`. See `cityuschedule --help` for the full option list and defaults.

## CSV timetable format

Each CSV row represents one class session. The header must contain these columns:

```csv
course_code,course_title,crn,section,type,day,start_time,end_time,building,room
CS1103,Introduction to Programming,12345,A,LEC,Mon,09:00,10:50,AC,LT-1
CS1103,Introduction to Programming,12346,A1,TUT,Wed,14:00,14:50,AC,Room-1
```

Use a 24-hour time such as `09:00` and a day name such as `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, or `Sun`. The repository includes [`examples/sample_courses.csv`](../examples/sample_courses.csv).

## Find GE courses

Search by keyword or supported filters:

```bash
cityuschedule --ge-search "introduction + level B + with exam"
cityuschedule --ge-info GE1102
```

GE data availability depends on the catalogue bundled with the project. Some course-information lookups or updates may access the network.

Sections with zero available seats (or marked `FULL`) and no waitlist are
rejected. Full sections with a waitlist remain candidates. This check is only
possible when the pasted table includes the availability and waitlist fields.

The pasted offering's section-credit values provide the candidate course's
credits. The built-in catalogues supply credits for courses already in the
AIMS HTML. `--credit-catalog credits.json` can supplement those catalogues.

## Troubleshooting

- **Command not found:** activate the virtual environment where you installed the package, or reinstall with `python -m pip install -e ".[dev]"`.
- **AIMS file not found or not recognized:** check the path and ensure the file is a saved weekly timetable HTML page, not a course-offering page.
- **CSV parsing errors:** check the required header, day names, 24-hour times, and that each row represents a class session.
- **No course plans found:** check semester/catalogue availability and course codes, then relax constraints or review the rejection details printed by the planner.

## Limitations and data notes

`cityuschedule` supports schedule planning; it does not register courses or guarantee that a plan is eligible, available, or accepted by CityU. In particular, weekly timetable fit and travel checks do not validate registration eligibility, live seat availability, date ranges, or multiple meeting rows. Course catalogues and building travel-time data are local project data and may not reflect the latest official information. Confirm important details with the official CityU systems before registration.

The project currently documents timetable checks, course planning, and GE lookup. It does not provide calendar export or a standalone report of all free gaps; gap-related planning is expressed through constraints such as minimum class gaps and lunch breaks.
