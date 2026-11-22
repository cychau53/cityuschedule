# Innovation and design

`cityuschedule` combines timetable checking with course-plan exploration in a lightweight Python command-line application. Its focus is the transition from *what courses am I considering?* to *which section combinations fit the week I already have?*

## What is distinctive

- **AIMS-aware inputs:** The project reads a saved weekly timetable and can parse a copied course-offering table, reducing the need to re-enter schedule data manually.
- **Complete section-bundle checking:** When an offering has linked components such as lecture and tutorial sections, the tool checks candidate bundles rather than treating each meeting as an independent course choice.
- **Constraint-driven planning:** Candidate plans can be filtered or ranked using schedule preferences, including days, class-time boundaries, minimum gaps, lunch breaks, credit targets, and travel time between known buildings.
- **Multiple ways to work:** Students can use an interactive menu, command-line options, AIMS HTML, or their own CSV timetable.
- **Local-first workflow:** Core parsing and timetable checks operate on files on the student's machine. Network access may be used for some course-information lookups; the tool does not need students to provide their AIMS credentials.

## Example use cases

1. **Avoid a clash:** inspect a saved timetable before finalizing registration and identify overlapping scheduled sessions.
2. **Choose a section bundle:** paste one course's AIMS offering and find combinations that do not overlap an existing timetable and satisfy selected day/time or break constraints.
3. **Compare candidate plans:** generate alternatives for a semester, with a fixed timetable and preferences such as avoiding Friday classes or limiting early starts.
4. **Check a custom schedule:** create a CSV for classes that are not in the supplied AIMS HTML and use it as the planner's fixed schedule.

## Scope and honest boundaries

The project assists with weekly timetable planning; it does not submit registration changes or guarantee eligibility or seats. Travel checks are limited to known buildings and the data available to the project. The tool does not currently export calendar events or provide a standalone analysis of every free gap. Minimum-gap and lunch-break options are constraints used when testing candidate plans, not a promise that every kind of gap is analyzed.
