# \# cityuschedule

# 

# `cityuschedule` helps CityU students check a proposed course timetable for

# clashes and export it as a calendar file.

# 

# It reads a simple CSV file containing lectures, tutorials, and laboratory

# sessions, detects overlapping classes, identifies free gaps, and creates an

# `.ics` calendar file that can be imported into Google Calendar, Apple Calendar,

# or Outlook.

# 

# \## Features

# 

# \- Load a CityU course timetable from CSV

# \- Detect overlapping class sessions

# \- Display a weekly timetable

# \- Identify free gaps between classes

# \- Export the timetable as an `.ics` calendar file

# 

# \## Installation

# 

# ```bash

# pip install cityuschedule

# ```

# 

# \## Quick start

# 

# Check a timetable:

# 

# ```bash

# cityuschedule examples/sample\_courses.csv

# ```

# 

# Export a calendar file:

# 

# ```bash

# cityuschedule examples/sample\_courses.csv --export

# ```

# 

# Use a custom output file and semester dates:

# 

# ```bash

# cityuschedule examples/sample\_courses.csv --export --output my\_timetable.ics --semester-start 2026-08-31 --semester-end 2026-11-28

# ```

# 

# \## CSV format

# 

# Create a CSV file with one row for each class session:

# 

# ```csv

# course\_code,course\_title,crn,section,type,day,start\_time,end\_time,building,room

# CS1103,Introduction to Programming,12345,A,LEC,Mon,09:00,10:50,AC,LT-1

# CS1103,Introduction to Programming,12346,A1,TUT,Wed,14:00,14:50,AC,Room-1

# MA1200,Calculus and Linear Algebra,23456,B,LEC,Tue,11:00,12:50,AC,LT-2

# GE1401,University English,34567,C1,SEM,Wed,15:00,16:50,CM,Room-3

# ```

# 

# The required columns are:

# 

# \- `course\_code`

# \- `course\_title`

# \- `crn`

# \- `section`

# \- `type`

# \- `day`

# \- `start\_time`

# \- `end\_time`

# \- `building`

# \- `room`

# 

# Use `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, or `Sun` for the `day` column.

# 

# \## Example output

# 

# ```text

# Weekly timetable

# 

# Mon

# &#x20; 09:00-10:50  CS1103 LEC  AC LT-1

# 

# Tue

# &#x20; 11:00-12:50  MA1200 LEC  AC LT-2

# 

# Wed

# &#x20; 14:00-14:50  CS1103 TUT  AC Room-1

# &#x20; 15:00-16:50  GE1401 SEM  CM Room-3

# 

# Loaded 4 class sessions.

# Found 0 clash(es).

# No free gaps of at least 45 minutes found.

# ```

# 

# \## Documentation

# 

# Documentation will be added in the `docs/` folder.

# 

# \## License

# 

# This project is licensed under the MIT License.

