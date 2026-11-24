# Innovation and design

`cityuschedule` combines timetable checking with course-plan exploration in a lightweight Python application available through an interactive command-line menu and a local web interface. Its focus is the transition from *what courses am I considering?* to *which complete section combinations fit the week I already have?*

## What is distinctive

- **AIMS-aware inputs:** The project reads a saved weekly AIMS timetable and can parse a copied course-offering table, reducing the need to re-enter schedule data manually.
- **Complete section-bundle checking:** When an offering has linked components such as lecture and tutorial sections, the tool checks candidate bundles rather than treating each meeting as an independent course choice.
- **Constraint-driven planning:** Candidate plans can be filtered or ranked using schedule preferences, including days, class-time boundaries, minimum gaps, lunch breaks, credit targets, and travel time between known buildings.
- **Credit-aware plan generation:** The planner includes both newly added courses and pre-registered AIMS courses when calculating a plan’s total study load, so credit limits are evaluated against the complete timetable.
- **Multiple ways to work:** Students can use an interactive menu, command-line options, AIMS HTML, or the local web interface.
- **Save and revisit plans:** Generated complete timetable plans can be saved, reviewed, and deleted later, making it easier to compare registration options across planning sessions.
- **Local-first workflow:** Core parsing and timetable checks operate on files on the student's machine. Network access may be used for some course-information lookups; the tool does not need students to provide their AIMS credentials.

## Web interface

The local web interface makes the planning workflow accessible without using command-line prompts. Students can upload or reuse a saved AIMS timetable, search GE courses, inspect course offerings, generate complete timetable plans, and save suitable plans for later review.

The web planner uses the same underlying plan generator and shared basic timetable settings as the command-line application. When no AIMS timetable is uploaded, it reuses the AIMS timetable previously saved through the application.

## Example use cases

1. **Avoid a clash:** inspect a saved timetable before finalizing registration and identify overlapping scheduled sessions.
2. **Choose a section bundle:** paste one course's AIMS offering and find combinations that do not overlap an existing timetable and satisfy selected day/time or break constraints.
3. **Compare candidate plans:** generate alternatives for a semester, with a fixed timetable and preferences such as avoiding Friday classes or limiting early starts.
4. **Check total study load:** add a GE course to an existing AIMS timetable and see plans whose total credits include both the kept pre-registered courses and the newly added course.
5. **Save suitable options:** generate several complete plans, select the ones worth keeping, and review them later before registering in AIMS.

## Scope and honest boundaries

The project assists with weekly timetable planning; it does not submit registration changes or guarantee eligibility or seats. Travel checks are limited to known buildings and the data available to the project. The tool does not currently export calendar events or provide a standalone analysis of every free gap. Minimum-gap and lunch-break options are constraints used when testing candidate plans, not a promise that every kind of gap is analyzed.
