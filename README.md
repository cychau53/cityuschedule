# CityUSchedule

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**CityUSchedule** helps undergraduate Computer Science students at City University of Hong Kong organise course information and plan their timetables. It can check for schedule clashes and gaps, generate course plans, and export course sessions as calendar events.

> Use CityUSchedule as a planning aid. Always verify course details, availability, and registration requirements using official CityU systems.

## What you can do

- Organise and review course catalogue information, including CS requirements and course exclusions.
- Import course and timetable information from AIMS.
- Check whether course sessions clash and examine gaps between classes.
- Generate possible course plans.
- Account for travel time between campus locations where location data is available.

## Requirements

- Python 3.10 or later
- `beautifulsoup4`
- `pypdf`

## Install

Clone the repository and install the package:

```bash
git clone https://github.com/cychau53/cityuschedule.git
cd cityuschedule
python -m pip install .
```

To install an editable development copy with development tools:

```bash
python -m pip install -e ".[dev]"
```

## Start CityUSchedule

Run the command-line application:

```bash
cityuschedule
```

Follow the interactive prompts to import or review course information and work with course plans. The command is installed by the package; if your shell cannot find it, check that your Python environment's scripts directory is on your `PATH`.

## Typical workflow

1. Start CityUSchedule and import or load your course information.
2. Select courses and available sections.
3. Generate possible course plans.
4. Review clashes, free periods, and travel time.
5. Export your chosen timetable to a calendar.

The repository also includes `examples/sample_courses.csv` as a sample input file. Import options and accepted formats may depend on the workflow you choose in the application.

## Course data

CityUSchedule works with structured course and timetable information. The repository includes data and catalogue files for CS requirements, GE requirements, other course requirements, course information, and travel times. Course information can change from semester to semester, so check the source and freshness of the data before relying on it.

Data-maintenance scripts in the repository include:

```bash
python extract_cs_courses.py
python build_cs_requirements.py
python fill_course_titles.py
python validate_cs_catalogue.py
```

These scripts support extracting CS courses, building requirement data, filling course titles, and validating the CS catalogue.

## Development

Create and activate a virtual environment:

```bash
python -m venv .venv
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the package with development dependencies and run the tests:

```bash
python -m pip install -e ".[dev]"
pytest
```

Run lint checks with:

```bash
ruff check .
```

## Contributing

Contributions are welcome. Please open an issue to discuss a substantial change, and include tests for changes to course parsing, timetable planning, or conflict detection. When updating course data, please document its source and semester.

## Important information

Course availability, timetable sessions, prerequisites, credits, exclusions, and registration restrictions may change. CityUSchedule does not guarantee real-time accuracy or course registration. Confirm all decisions with official CityU sources before registering.

## License

CityUSchedule is released under the [MIT License](LICENSE).
