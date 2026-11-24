# CityUSchedule

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

CityUSchedule is a Python package for undergraduate Computer Science students at City University of Hong Kong. It helps students save, organise, and review CS course information when planning their timetables.

> CityUSchedule is a planning aid. Always verify course details and registration requirements through official CityU systems.

## Features

- Store and review CS course information
- Browse course codes, titles, and credits
- Support CS programme requirements and course exclusions
- Check whether course sessions clash
- Identify gaps in a timetable
- Generate possible course plans
- Import timetable information from AIMS
- Consider travel time between campus locations
- Validate and maintain course catalogue data

## Requirements

- Python 3.10 or later
- Beautiful Soup 4
- pypdf

## Installation

Clone the repository:

```bash
git clone https://github.com/cychau53/cityuschedule.git
cd cityuschedule
```

Install the package:

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e ".[dev]"
```

## Quick Start

Start the interactive command-line application:

```bash
cityuschedule
```

Follow the prompts to load course information and generate a timetable plan.

Start the local webpage interface:

```bash
cityuschedule --web
```

This opens a browser at `http://127.0.0.1:8000`. Use `--host` and `--port`
to change the local address, for example:

```bash
cityuschedule --web --host 127.0.0.1 --port 8080
```

Keep the terminal open while using the webpage. Add `--no-browser` to
print the link without opening a browser automatically.

## Web Interface

The webpage provides the same core timetable-planning features as the
command-line application:

- Search Gateway Education (GE) courses
- View GE course details
- Check or change a saved AIMS timetable
- Paste an AIMS course offering and check complete section bundles
- Generate complete timetable plans
- Save generated timetable plans
- View and delete saved timetable plans
- View saved course bundles

Open the planner at:

```text
http://127.0.0.1:8000/planner
```

### Generate a timetable plan

1. Choose the semester, such as `2627B`.
2. Enter the course codes you want to add, such as `GE1352`.
3. Upload an AIMS timetable HTML file, or leave it blank to reuse the
   AIMS timetable saved through the command-line application.
4. Choose how many GE courses the planner should add.
5. Choose the maximum number of plans to display.
6. Select a seat policy and choose whether to check walking time.
7. Select **Generate timetable plans**.

The planner displays complete, clash-free timetable plans. Each plan
includes the newly added course, the pre-registered AIMS courses that
remain in the timetable, the weekly timetable, total credits, and
suggested registration steps.

Pre-registered courses from the AIMS timetable are included in the
total credit calculation. For example, if your AIMS timetable contains
13 credits and you add a 3-credit GE course, the generated plan shows
16 total credits.

### Save a generated plan

When one or more complete plans are generated, the page shows a
**Save plans** section. Select one or more plans and choose
**Save selected plans**.

Saved plans are available at:

```text
http://127.0.0.1:8000/saved-plans
```

You can also open **Saved timetable plan** from the navigation menu.
Each saved plan can be deleted from that page.

The individual “timeslots that fit your timetable” results are
alternatives for one course. They are not complete timetable plans and
cannot be saved directly as timetable plans.

### Shared settings

Use **Basic settings** to configure preferences shared by the
command-line and web interfaces:

- Preferred and avoided days
- Minimum and maximum credits
- Earliest class start and latest class end
- Minimum gap between classes
- Lunch-break duration and window
- Walking-time checks

The web planner uses these settings when generating plans.

## Typical Workflow

1. Start CityUSchedule.
2. Import or load course and timetable information.
3. Select CS courses and available sections.
4. Generate possible course plans.
5. Review clashes, gaps, travel time, and total credits.
6. Save one or more suitable complete timetable plans.
7. Register the selected sections in AIMS during your time ticket.

## Course Data

CityUSchedule uses structured JSON course catalogue and requirement data, including:

- Course codes and titles
- Credits
- Course requirements
- Course exclusions
- Available sessions
- Session times and locations
- Travel-time information

The data-maintenance scripts include:

```bash
python extract_cs_courses.py
python build_cs_requirements.py
python fill_course_titles.py
python validate_cs_catalogue.py
```

## Development

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the tests:

```bash
pytest
```

Run lint checks:

```bash
ruff check .
```

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Add or update course-processing functionality.
4. Add tests for parsing, planning, or timetable changes.
5. Submit a pull request.

Please document the source and semester when updating course data.

## Data Accuracy

Course information can change between semesters. Before registering, verify:

- Course availability
- Timetable times and locations
- Credits
- Prerequisites
- Exclusions
- Registration restrictions
- Semester-specific sessions

Use official CityU course catalogue and timetable systems as the source of truth.

## Limitations

- Course information may require periodic updates.
- Session availability is not guaranteed in real time.
- Imported timetable formats may change.
- Travel-time estimates depend on packaged location data.
- Scheduling suggestions must be checked against official registration systems.

## License

This project is licensed under the [MIT License](LICENSE).
