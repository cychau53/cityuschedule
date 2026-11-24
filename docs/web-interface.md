# Local web interface

CityUSchedule includes a local, browser-based interface for timetable planning and review. It uses the same course catalogues and planning engine as the command-line application and does not require an account or student timetable to leave your computer.

## Start the web interface

Install CityUSchedule, then run:

```bash
cityuschedule --web
```

The server starts at `http://127.0.0.1:8000` and opens the homepage in your default browser.

To use another address or port:

```bash
cityuschedule --web --host 127.0.0.1 --port 8080
```

To print the address without opening a browser:

```bash
cityuschedule --web --no-browser
```

Keep the terminal process running while the browser interface is open. Stop the server with `Ctrl+C`.

## Available pages

- **Basic settings** — configure planning preferences shared with the command-line interface.
- **Check or change saved AIMS timetable** — upload or replace a saved AIMS weekly timetable HTML file.
- **Paste and check an AIMS course offering** — check complete section bundles against an existing timetable.
- **Saved course bundles** — review section combinations previously saved from an AIMS offering check.
- **Search GE courses** — search Gateway Education courses by code, title, area, or offering unit.
- **Show GE course details** — view course information and published section records.
- **Generate timetable plans** — generate complete, clash-free timetable alternatives.
- **Saved timetable plans** — review and delete previously generated plans.

## Generate a timetable plan

Open `/planner` or select **Generate timetable plans** from the navigation menu.

1. Enter the semester, for example `2627B`.
2. Enter interested course codes separated by commas or spaces, for example `GE1102 GE1401`.
3. Upload an AIMS timetable HTML file, or leave the field empty to reuse the timetable saved through the command-line application.
4. Choose how many GE courses the planner should add.
5. Set the maximum number of plans to display.
6. Choose a seat policy:
   - **Waitlist allowed** — accept sections with a waitlist if an exact seat is unavailable.
   - **Open seats only** — only use sections with open seats.
   - **Any availability** — do not filter sections by seat availability.
7. Optionally skip walking-time checks.
8. Select **Generate timetable plans**.

The generated plan includes the newly added sections, pre-registered AIMS courses that remain in the timetable, weekly meetings, credit totals, and suggested registration steps.

Pre-registered AIMS courses are included in the plan's credit total. For example, 13 AIMS credits plus a 3-credit GE course produce a 16-credit plan.

## Save plans

When complete plans are generated, select the checkbox for each plan to keep and choose **Save selected plans**. Saved plans appear at:

```text
http://127.0.0.1:8000/saved-plans
```

A plan can be deleted from the saved-plans page.

The “timeslots that fit your timetable” output is a set of alternatives for an individual course. It is not a complete timetable and cannot be saved as a timetable plan.

## Check an AIMS course offering

Open `/aims-offering` and provide:

- the course code;
- the complete copied AIMS course-offering table;
- the existing weekly timetable as an HTML file.

The page checks complete lecture/tutorial/laboratory bundles and reports combinations that fit the timetable and shared basic settings. Unscheduled sessions are not treated as fixed meetings.

## Shared basic settings

Open `/settings` to configure:

- preferred and avoided days;
- minimum and maximum credits;
- earliest class start and latest class end;
- minimum gap between classes;
- lunch-break duration and time window.

The web interface and command-line application read and update the same local settings file. The web planner uses these settings during generation.

## Local storage

The web interface stores saved plans, saved course bundles, the remembered AIMS timetable path, and basic settings in the operating user's CityUSchedule configuration directory. It does not upload timetable or course data to a remote service by itself.

## Limitations

The web interface is a local planning aid:

- it does not register courses or change AIMS;
- seat and timetable availability can change after publishing;
- travel checks depend on packaged building/location data;
- eligibility, registration restrictions, and semester dates are not fully validated.

Always verify the suggested courses and sections in the official AIMS and CityU systems before registration.
