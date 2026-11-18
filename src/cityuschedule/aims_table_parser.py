from __future__ import annotations

from dataclasses import dataclass
import re

from itertools import product


@dataclass(frozen=True)
class AimsSession:
    course_code: str
    crn: str
    section: str
    credit: int
    day: str | None
    start_time: str | None
    end_time: str | None
    building: str = ""

    @property
    def activity_type(self) -> str:
        return self.section[0].upper()

    @property
    def is_scheduled(self) -> bool:
        return bool(self.day and self.start_time and self.end_time)


@dataclass(frozen=True)
class ParsedAimsTable:
    course_code: str
    sessions: tuple[AimsSession, ...]

    @property
    def scheduled_sessions(self) -> tuple[AimsSession, ...]:
        return tuple(session for session in self.sessions if session.is_scheduled)

    @property
    def course_credit(self) -> int:
        credits = {
            session.credit
            for session in self.scheduled_sessions
            if session.credit > 0
        }
        if len(credits) != 1:
            raise ValueError(
                "Could not determine a single course-credit value. "
                f"Found: {sorted(credits)}"
            )
        return credits.pop()

    @staticmethod
    def _group_key(section: str) -> str:
        """Group by letters after the activity prefix, ignoring digits."""
        match = re.fullmatch(r"[A-Z]([A-Z]*)\d+", section.upper())
        if not match:
            raise ValueError(f"Unsupported section code: {section!r}")

        return match.group(1) or "NUMERIC"

    def registration_groups(self) -> dict[str, tuple[str, ...]]:
        """Collect scheduled sections by their section-code family."""
        groups: dict[str, list[str]] = {}

        for session in self.scheduled_sessions:
            key = self._group_key(session.section)
            groups.setdefault(key, []).append(session.section)

        return {
            key: tuple(sections)
            for key, sections in sorted(groups.items())
        }

    def registration_bundles(self) -> list[tuple[str, ...]]:
        """Choose exactly one section per required activity in each family."""
        required_types = sorted({
            session.activity_type
            for session in self.scheduled_sessions
        })

        if not required_types:
            return []

        bundles: set[tuple[str, ...]] = set()

        for sections in self.registration_groups().values():
            options = [
                [
                    section
                    for section in sections
                    if section[0].upper() == activity
                ]
                for activity in required_types
            ]

            if any(not choices for choices in options):
                continue

            for combination in product(*options):
                bundles.add(tuple(combination))

        return sorted(bundles)


def parse_aims_table(
    text: str,
    course_code: str | None = None,
) -> ParsedAimsTable:
    """Parse one course's AIMS table in copied-table or field-per-line form."""
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:
        raise ValueError("The pasted AIMS table is empty.")

    heading = re.match(
        r"^(?:Course\s*:\s*)?([A-Z]+)\s*(\d{4}[A-Z]?)\b",
        lines[0],
        flags=re.IGNORECASE,
    )
    if heading:
        parsed_course_code = "".join(heading.groups()).upper()
    elif course_code:
        code_match = re.fullmatch(
            r"([A-Z]+)\s*(\d{4}[A-Z]?)",
            course_code.strip(),
            flags=re.IGNORECASE,
        )
        if code_match is None:
            raise ValueError(
                f"Invalid course code {course_code!r}. "
                "Enter a code such as GE2130."
            )
        parsed_course_code = "".join(code_match.groups()).upper()
    else:
        raise ValueError(
            "Course code is required. Enter a code such as GE2130."
        )

    section_pattern = re.compile(r"[A-Z]{1,2}\d+")
    time_pattern = re.compile(
        r"([01]\d|2[0-3]):([0-5]\d)\s*[-–]\s*"
        r"([01]\d|2[0-3]):([0-5]\d)"
    )

    if any("\t" in line for line in lines):
        sessions = _parse_tabular_sessions(
            lines,
            parsed_course_code,
            section_pattern,
            time_pattern,
        )
        if not sessions:
            raise ValueError(
                "No section records were found in the copied AIMS table."
            )
        return ParsedAimsTable(
            course_code=parsed_course_code,
            sessions=tuple(sessions),
        )

    record_lines = lines[1:] if heading else lines

    section_indices = [
        index for index in range(1, len(record_lines) - 1)
        if section_pattern.fullmatch(record_lines[index])
        and re.fullmatch(r"\d+", record_lines[index - 1])
        and re.fullmatch(r"\d+", record_lines[index + 1])
    ]

    if not section_indices:
        raise ValueError("No section records were found in the pasted table.")

    sessions: list[AimsSession] = []

    for position, index in enumerate(section_indices):
        # The next section's preceding line is its CRN.
        stop = (
            section_indices[position + 1] - 1
            if position + 1 < len(section_indices)
            else len(record_lines)
        )
        record = record_lines[index + 2:stop]

        day = None
        start_time = None
        end_time = None
        building = ""

        for offset in range(len(record) - 1):
            if not re.fullmatch(r"[MTWRFSU]", record[offset]):
                continue

            time_match = time_pattern.fullmatch(record[offset + 1])
            if time_match is None:
                continue

            start_hour, start_minute, end_hour, end_minute = (
                time_match.groups()
            )
            day = record[offset]
            start_time = f"{start_hour}:{start_minute}"
            end_time = f"{end_hour}:{end_minute}"
            if offset + 2 < len(record):
                building = record[offset + 2]
            break

        sessions.append(
            AimsSession(
                course_code=parsed_course_code,
                crn=record_lines[index - 1],
                section=record_lines[index],
                credit=int(record_lines[index + 1]),
                day=day,
                start_time=start_time,
                end_time=end_time,
                building=building,
            )
        )

    return ParsedAimsTable(
        course_code=parsed_course_code,
        sessions=tuple(sessions),
    )


def _parse_tabular_sessions(
    lines: list[str],
    course_code: str,
    section_pattern: re.Pattern[str],
    time_pattern: re.Pattern[str],
) -> list[AimsSession]:
    sessions = []
    for line in lines:
        fields = [field.strip() for field in line.split("\t")]
        if (
            len(fields) < 3
            or not fields[0].isdigit()
            or not section_pattern.fullmatch(fields[1])
            or not re.fullmatch(r"\d+", fields[2])
        ):
            continue

        day = None
        start_time = None
        end_time = None
        building = ""
        for index in range(len(fields) - 1):
            if not re.fullmatch(r"[MTWRFSU]", fields[index]):
                continue
            match = time_pattern.fullmatch(fields[index + 1])
            if match is None:
                continue
            start_hour, start_minute, end_hour, end_minute = (
                match.groups()
            )
            day = fields[index]
            start_time = f"{start_hour}:{start_minute}"
            end_time = f"{end_hour}:{end_minute}"
            if index + 2 < len(fields):
                building = fields[index + 2]
            break

        sessions.append(
            AimsSession(
                course_code=course_code,
                crn=fields[0],
                section=fields[1],
                credit=int(fields[2]),
                day=day,
                start_time=start_time,
                end_time=end_time,
                building=building,
            )
        )

    return sessions

