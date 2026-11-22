# \# cityuschedule

# 

# `cityuschedule` helps CityU students check AIMS course timetables for clashes

# and generate course plans.

# 

# Course-planning timetables can be loaded from CSV or AIMS HTML.

# 

# \## Features

# 

# \- Use a CSV or AIMS timetable as the fixed schedule for course planning

# \- Detect overlapping class sessions

# \- Display a weekly timetable



# 

# \## Installation

# 

# ```bash

# pip install cityuschedule

# ```

# 

# \## Quick start

# 

# Generate a course plan:

# 

# ```bash

# cityuschedule --courses GE1102 --term 2627B

# ```

# 


# 


# 


# 


## Generate course plans

The plan generator asks for a semester if `--term` is omitted. You can also
provide it directly:

```bash
cityuschedule --courses GE1102 --term 2627B
```

Accepted semester codes include `2627A`, `2627B`, and `2627S`.








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

# 

# \## Documentation

# 

# Documentation will be added in the `docs/` folder.

# 

# \## License

# 

# This project is licensed under the MIT License.

