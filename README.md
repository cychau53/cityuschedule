# cityuschedule

`cityuschedule` is a Python command-line tool for City University of Hong Kong (CityU) students who want to make course-registration decisions with fewer timetable surprises. It checks existing AIMS timetables for clashes, tests possible course sections against a fixed schedule, and generates course-plan suggestions from the project’s course data.

The project is motivated by a practical problem: a course list does not show whether its lectures, tutorials, or other scheduled sessions fit together as a usable week. Comparing section combinations by hand is tedious, and an overlooked overlap—or an impractical gap or trip between buildings—can make a plan difficult to follow. `cityuschedule` turns timetable data into checks and candidate plans students can review before registering.

## What it does

- Reads a saved AIMS weekly timetable and reports overlapping scheduled sessions.
- Checks a pasted AIMS course offering and suggests complete section bundles that fit an existing timetable.
- Generates course-plan suggestions from the bundled course catalogues, with optional constraints such as credit limits, preferred or avoided days, earliest start, latest end, minimum gaps, lunch breaks, and travel-time checks between known buildings.
- Searches and displays Gateway Education (GE) course information available to the project.
- Accepts a CSV timetable as a fixed schedule for course planning.
- Provides an interactive menu as well as command-line options.

The output is for planning—not registration. It does not confirm eligibility, current seat availability, or that a suggested plan will be approved. See [limitations and data notes](docs/usage.md#limitations-and-data-notes).

## Example use cases

1. **Check a timetable already in AIMS:** save the weekly timetable as HTML, then ask the tool to find overlaps.
2. **Compare sections for a new course:** paste its complete AIMS offering table and see which complete section combinations fit your saved schedule.
3. **Explore alternative plans:** ask the planner for combinations of courses and GE courses that meet your day, time, credit, break, and travel preferences.
4. **Try the planner with your own schedule:** create a CSV of fixed class sessions and use it as the starting timetable.

## Quick start

Requires Python 3.10 or later. From a clone of this repository, install the package and its development tools in editable mode:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Start the interactive menu:

```bash
cityuschedule
```

Or inspect the command-line options:

```bash
cityuschedule --help
```

For example, use the included sample timetable as the fixed schedule while exploring a course for semester `2627B`:

```bash
cityuschedule examples/sample_courses.csv --courses GE1102 --term 2627B
```

To check clashes in a saved AIMS weekly timetable:

```bash
cityuschedule --aims-html path/to/your_aims_timetable.html
```

See the [setup and usage guide](docs/usage.md) for installation details, CSV format, AIMS workflows, planner options, and troubleshooting.

## How the project is different

Rather than being only a timetable display, `cityuschedule` connects timetable checking with course exploration. It can parse a saved AIMS timetable, reason about complete registration section bundles, and use one set of schedule constraints to filter candidate plans. Its CLI and local-file inputs keep the basic checks straightforward to run; some data lookups and course-information updates do require network access.

## Documentation

- [Setup and usage](docs/usage.md)
- [Motivation](docs/motivation.md)
- [Innovation and design](docs/innovation.md)
- [Planning notes](docs/planning.md)

The documentation organization takes inspiration from student-developed package examples linked in the [CS1302 agentic-coding course material](https://ccha23.github.io/cs1302ai26a/#agentic-coding).

## Development

Run the test suite with:

```bash
python -m pytest
```

Run lint checks with:

```bash
ruff check .
```

## License

This project is distributed under the MIT License; see [LICENSE](LICENSE).
