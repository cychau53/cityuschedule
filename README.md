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

## Typical Workflow

1. Start CityUSchedule.
2. Import or load course and timetable information.
3. Select CS courses and available sections.
4. Generate possible course plans.
5. Review clashes, gaps, and travel time.
6. Choose a timetable plan that meets your study requirements.

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
