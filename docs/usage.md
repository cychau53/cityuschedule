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

Choose option `1` to set preferred and avoided days, minimum and maximum
credits, lunch duration and time window, minimum minutes between classes,
earliest class start, and latest class end. These settings are saved across
launches and apply to newly pasted or planned courses. Saved AIMS classes are
used for clash and walking-time checks and for combined credit totals; day,
lunch, gap, and time settings do not reject a schedule because of those fixed
classes. Enter day names as `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, or `Sun`,
or use `M`, `T`, `W`, `R`, `F`, `S`, or `U`. Enter times as `HHMM` or
`HH:MM`; for example, set the lunch duration to `30` and the lunch window to
`1200-1400` to require a 30-minute break between noon and 2:00 pm. Press Enter
at a setting prompt to keep its current value; enter `none` to clear it (or
reset the lunch window). The lunch duration cannot exceed the window length.
AIMS paste warns if combined credits fall outside the configured limits but
still displays fitting bundles.

At the main menu prompt, type `delete avoid`, `delete prefer`, `delete min`,
`delete max`, `delete lunch`, `delete window`, `delete gap`, `delete earliest`,
`delete latest`, or `delete AIMS` to clear that saved value. Type `delete all`
to remove all basic settings and the remembered AIMS path. To clear multiple
values, join their names with `and`, such as `delete max and min` or
`delete AIMS and max`. Type `delete plan1` or `delete plan 1` to delete a saved
plan by its number.

Choose **7. Saved timetable plan** to review saved plans, including their timetable and
Web Add/Drop sections with CRNs.

The other numbered options check or change the saved AIMS timetable, paste an
AIMS offering, search or inspect GE courses, or generate course plans. The menu
asks for the required file paths and then runs the selected task. The AIMS HTML
path is remembered across launches and reused by other AIMS menu options.
Choose option `2` and enter a different path to
change the saved one; press Enter to keep using it. Press `0` to exit.
If a task reports an error, the menu stays open so you can choose another
option or correct the input; the saved AIMS path is updated only after a
successful task.

For advanced options, use `cityuschedule --help` or run a command directly.

In menu option 4, GE search repeats until you enter `q` to return to the main
menu or `0` to exit the package. Search is case-insensitive. Enter
`without exam` or `with exam` to filter by exam status, `cross` or `not cross`
to filter cross-institutional courses, or `Area 1`, `Area 2`, or `Area 3` to
show courses from one area. Enter `Level B` to include all B-level courses,
`Level B1` for an exact level, or a range such as `Level A1 to B1` (inclusive).
Other text searches course codes, titles, areas, and offering units. Combine
any filters and keywords with `+`; every part must match, and their order does
not matter. For example, `introduction + level B + with exam` finds courses
matching all three conditions. Spaces inside filter labels are optional:
`levelB` is equivalent to `level B`, and `area1` to `area 1`. Filter by 2026-27
semester availability with `2627A` (Sem A), `2627B` (Sem B), or `2627S`
(Summer); spaces and capitalization do not matter.

\## CSV timetable for planning

You can provide a CSV timetable as the fixed schedule when generating a course
plan:



```bash

cityuschedule examples/sample\_courses.csv --courses GE1102 --term 2627B

```


## CSV format


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


If a CSV timetable cannot be found or contains invalid class times, check the
file path and ensure that `end_time` is later than `start_time`.

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

If you press Enter before entering any table data, the paste prompt appears
again. If the table has no course heading and you leave the course-code prompt
blank, the package asks for the code again.
If the pasted text is not a complete course offering table, the package tells
you what table is needed and reopens the paste prompt before asking for a code.
At a retry prompt, enter `q` to leave the current input and return to the main
menu. Enter `0` only to exit the package.
In interactive prompts for other menu functions, `q` also returns to the main
menu. Enter `0` only to exit the package.
In an interactive terminal, menus and instructions are yellow, errors and
rejected bundles are red, suggested bundles are green, and complete credit
totals are blue. Colors are suppressed when output is redirected or
`NO_COLOR` is set.

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
Rejected bundles that fit the AIMS timetable except for an avoided day are
listed before bundles rejected for other reasons.

