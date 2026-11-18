\# Usage guide



\## Installation



Install `cityuschedule` from PyPI:



```bash

pip install cityuschedule

```

\## Interactive menu

Run the command without arguments to open a menu:

```bash
cityuschedule
```

Choose a numbered option to check a CSV or AIMS timetable, paste an AIMS
offering, search or inspect GE courses, export a calendar, generate course
plans, or import GE course HTML. The menu asks for the required file paths and
then runs the selected task. Press `0` to exit.

For advanced options, use `cityuschedule --help` or run a command directly.

\## Check a timetable



Provide a CSV file containing the class sessions you want to check:



```bash

cityuschedule examples/sample\_courses.csv

```



The package displays:



\- A weekly timetable

\- The number of class sessions

\- The number of clashes

\- Free gaps of at least 45 minutes



\## Change the minimum gap



To report only gaps of at least 60 minutes:



```bash

cityuschedule examples/sample\_courses.csv --min-gap 60

```



\## Export a calendar



Create an `.ics` calendar file:



```bash

cityuschedule examples/sample\_courses.csv --export

```



By default, the output file is `cityu\_timetable.ics`.



To choose a different output file:



```bash

cityuschedule examples/sample\_courses.csv --export --output my\_timetable.ics

```



\## Set semester dates



Use the first and last teaching days of the semester:



```bash

cityuschedule examples/sample\_courses.csv --export --semester-start 2026-08-31 --semester-end 2026-11-28

```



\## CSV format



Each row represents one class session.



```csv

course\_code,course\_title,crn,section,type,day,start\_time,end\_time,building,room

CS1103,Introduction to Programming,12345,A,LEC,Mon,09:00,10:50,AC,LT-1

```



Use one of the following values in the `day` column:



\- `Mon`

\- `Tue`

\- `Wed`

\- `Thu`

\- `Fri`

\- `Sat`

\- `Sun`



Use 24-hour time in the `start\_time` and `end\_time` columns, for example

`09:00` and `10:50`.



\## Troubleshooting



If the CSV file cannot be found, check the file path.



If the CSV contains no class sessions, add at least one row beneath the header

row.



If a class time is invalid, ensure that `end\_time` is later than `start\_time`.

\## AIMS course paste and credit totals

The weekly AIMS timetable contains course codes but not credit values. The
package looks them up in its built-in CS, GE, and other-course credit
catalogues. If a course is not covered by those catalogues, provide an
additional credit catalogue:

```json
[
  {
    "course_code": "BASE1001",
    "title": "Base course",
    "credits": 12,
    "sections": []
  }
]
```

Then paste one course's complete AIMS offering table (the tab-separated table
copied from AIMS is supported) and finish with `END`. If the copied selection
does not include the course heading, enter the course code when prompted. At
the next prompt, enter any section codes you cannot register for, separated
by spaces or commas, or press Enter for none:

```bash
cityuschedule --aims-html aims_schedule.html --paste-aims \
  --prefer-days Mon Tue --avoid-days Fri
```

For example, enter `T35 T90` at the unavailable-sections prompt to exclude
those sections from all candidate bundles.

The pasted offering's section-credit values provide the candidate course's
credits. The built-in catalogues supply credits for courses already in the
AIMS HTML. `--credit-catalog credits.json` can supplement those catalogues.
For example:

```text
Pasted course credits: 3
AIMS timetable credits: 12
Combined total if added: 15
```

If a course is missing from all catalogues, the output reports an incomplete
total and lists the missing course code(s).

