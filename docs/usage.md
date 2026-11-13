\# Usage guide



\## Installation



Install `cityuschedule` from PyPI:



```bash

pip install cityuschedule

```



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

