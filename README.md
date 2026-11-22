# cityuschedule
CityUSchedule is a Python package designed for undergraduate Computer Science students at City University of Hong Kong.

It saves CS course information and helps students:

Check whether course sessions clash
Identify gaps in a timetable
Review course details and requirements
Export compatible sessions as calendar events
CityUSchedule is a planning tool. Students should always verify final timetables and registration details through official CityU systems.
Features

Save and organise CS course information
Store course titles and catalogue data locally
Identify timetable clashes
Find gaps between scheduled sessions
Support CS course requirement processing
Export timetable events to calendar-compatible formats
Validate and maintain the course catalogue
How It Works

CityUSchedule processes course and session information into structured local data.

A typical workflow is:

Load or update course information.
Select the courses you want to take.
Check session combinations for clashes.
Find gaps and unavailable periods.
Export the selected timetable to a calendar.
Installation

Python 3.11 or later is required.

bash
git clone https://github.com/cychau53/cityuschedule.git
cd cityuschedule
python -m pip install .
For development:

bash
python -m pip install -e .
python -m pip install -r requirements.txt
Quick Start

Run the package from the project directory:

bash
python -m cityuschedule
``>

## Course Data

CityUSchedule includes structured course information such as:

- Course code
- Course title
- Required credits
- Available sessions
- Session times and locations
- Course exclusions
- CS programme requirements

The primary catalogue file is:

```text
course_catalog.json
Example Course Record

JSON
{
  "course_code": "CS3334",
  "title": "Data Structures",
  "credits": 3
}
The exact fields may vary depending on the course and the data source.

Data Utilities

The repository provides scripts for building, enriching, and validating CS course data.

Extract CS Courses

bash
python extract_cs_courses.py
Build CS Requirements

bash
python build_cs_requirements.py
Fill Missing Course Titles

bash
python fill_course_titles.py
Validate the CS Catalogue

bash
python validate_cs_catalogue.py
Checking a Timetable

Use the package APIs or an example script to inspect course combinations and identify scheduling conflicts.

Python
selected_courses = [
    {
        "code": "CS3334",
        "sessions": [
            {"day": "Monday", "start": "10:00", "end": "11:50"}
        ],
    },
    {
        "code": "CS4336",
        "sessions": [
            {"day": "Monday", "start": "11:30", "end": "13:20"}
        ],
    },
]

print("Selected courses:", [course["code"] for course in selected_courses])
The timetable calculation should compare session dates and times before the courses are added to the saved schedule.

Example API names may change while the package is under active development.
Exporting Calendar Events

CityUSchedule can export compatible timetable information as calendar events.

A calendar export allows students to:

View lectures and tutorials in Google Calendar, Apple Calendar, or Outlook
Receive timetable reminders
Keep course locations alongside scheduled sessions
Save a course timetable for later reference
The exported format is designed to be imported into a calendar application.

Project Structure

Text
cityuschedule/
├── src/cityuschedule/       Package source code
├── tests/                   Unit and integration tests
├── data/                    Generated and source course data
├── docs/                    Documentation
├── examples/                Example usage
├── scripts/                 Maintenance utilities
├── course_catalog.json      CS course catalogue
├── exclusions.json          Course exclusions
├── requirements.txt         Python dependencies
├── pyproject.toml           Package configuration
├── README.md                Project documentation
└── LICENSE                  MIT licence
``>

## Development

Create a virtual environment:

```bash
python -m venv .venv
Activate it on macOS or Linux:

bash
source .venv/bin/activate
Activate it on Windows:

PowerShell
.venv\Scripts\Activate.ps1
Install the package and dependencies:

bash
python -m pip install -e .
python -m pip install pytest ruff
Run tests:

bash
pytest
Run lint checks:

bash
ruff check .
``>

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Add or update course-processing functionality.
4. Add tests for timetable or catalogue changes.
5. Submit a pull request.

Please include the source or reason for updates to course data.

## Data Accuracy

Course information can change between semesters.

Before registering or exporting a final timetable, verify:

- Course availability
- Timetable times and locations
- Credits
- Prerequisites
- Exclusions
- Registration restrictions
- Semester-specific sessions

Use the official CityU course catalogue and timetable systems as the source of truth.

## Limitations

- Course information may require manual updating.
- Some sessions may not contain complete historical or future data.
- Calendar applications may interpret recurring events differently.
- The package does not guarantee real-time course availability.
- Scheduling suggestions must be checked against official registration systems.

## License

This project is licensed under the [MIT License](LICENSE).
