import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TextIO

from .aims import load_aims_html
from .aims_fit import (
    DAY_NAMES,
    bundle_preferred_day_count,
    convert_aims_sessions,
    fitting_registration_bundles,
    registration_bundle_conflicts,
)
from .aims_table_parser import parse_aims_table
from .conflicts import find_conflicts
from .course_catalog import (
    load_course_catalog,
    load_credit_catalogs,
    load_ge_section_catalog,
)
from .ge_course_information_importer import (
    merge_ge_course_information_from_web,
)
from .ge_courses import (
    SECTION_DATA_PATH,
    get_ge_course_info,
    load_ge_courses,
    search_ge_courses,
)
from .planner import calculate_course_credits
from .timetable import WEEKDAYS, format_timetable


@dataclass(frozen=True)
class BasicSettings:
    prefer_days: tuple[str, ...] = ()
    avoid_days: tuple[str, ...] = ()
    min_credits: int | None = None
    max_credits: int | None = None
    lunch_minutes: int = 0
    lunch_window: tuple[str, str] = ("11:30", "14:30")
    min_gap: int = 0
    earliest_start: str | None = None
    latest_end: str | None = None


def load_sessions(csv_path: str) -> list[dict[str, str]]:
    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        sessions = list(reader)

    if not sessions:
        raise ValueError("The CSV file contains no class sessions")

    return sessions


def _cityuschedule_config_dir() -> Path:
    config_root = Path(
        os.environ.get("APPDATA")
        or str(Path.home() / ".config")
    )
    return config_root / "cityuschedule"


def _aims_path_config_file() -> Path:
    return _cityuschedule_config_dir() / "aims_html_path.txt"


def _basic_settings_config_file() -> Path:
    return _cityuschedule_config_dir() / "basic_settings.json"


def _saved_bundles_file() -> Path:
    return _cityuschedule_config_dir() / "saved_bundles.json"


def _load_saved_bundles() -> list[dict]:
    path = _saved_bundles_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _saved_plan_data(entry: object) -> dict:
    if not isinstance(entry, dict):
        return {}
    plan = entry.get("plan", entry)
    return plan if isinstance(plan, dict) else {}


def _saved_plan_sessions(plan: dict) -> list[dict]:
    sessions = plan.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        sessions = plan.get("sections", [])

    result = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        location = str(session.get("location") or "")
        building = str(session.get("building") or "")
        room = str(session.get("room") or "")
        if not building and location:
            building, _, location_room = location.partition(" ")
            room = room or location_room
        result.append({
            "course_code": str(session.get("course_code") or ""),
            "section": str(session.get("section") or session.get("type") or ""),
            "day": str(session.get("day") or ""),
            "start_time": str(
                session.get("start_time") or session.get("start") or ""
            ),
            "end_time": str(session.get("end_time") or session.get("end") or ""),
            "building": building,
            "room": room,
        })
    return result


def _saved_web_add_drop(plan: dict) -> list[dict]:
    saved = plan.get("web_add_drop")
    if isinstance(saved, list):
        return [item for item in saved if isinstance(item, dict)]

    registration_steps = plan.get("registration_steps", [])
    web_codes = []
    if isinstance(registration_steps, list):
        for step in registration_steps:
            if "Web Add/Drop" in str(step):
                web_codes.extend(
                    code.upper()
                    for code in re.findall(
                        r"\badd\s+([A-Z]{2,4}\d{4}[A-Z]?)\b",
                        str(step),
                        flags=re.IGNORECASE,
                    )
                )
    sections_by_course: dict[str, list[dict]] = {}
    for section in plan.get("sections", []):
        if isinstance(section, dict):
            code = str(section.get("course_code") or "").upper()
            sections_by_course.setdefault(code, []).append({
                "section": section.get("section", ""),
                "crn": section.get("crn", ""),
            })
    return [
        {
            "course_code": code,
            "add_sections": sections_by_course.get(code, []),
        }
        for code in dict.fromkeys(web_codes)
    ]


def _format_saved_plan(plan: dict, number: int) -> str:
    sessions = _saved_plan_sessions(plan)
    courses = plan.get("courses", [])
    courses = [str(course) for course in courses] if isinstance(courses, list) else []
    days = plan.get("days_on_campus")
    if not isinstance(days, int):
        days = len({session["day"] for session in sessions if session["day"]})

    lines = [
        f"Plan {number}",
        f"Total credit: {plan.get('total_credits', 'Unknown')}",
        "Course(s) added: " + (", ".join(courses) if courses else "None"),
        f"Total day(s) on campus: {days}",
        "",
    ]
    sessions_by_day: dict[str, list[dict]] = {day: [] for day in WEEKDAYS}
    for session in sessions:
        if session["day"] in sessions_by_day:
            sessions_by_day[session["day"]].append(session)
    for day in WEEKDAYS:
        day_sessions = sorted(
            sessions_by_day[day],
            key=lambda session: session["start_time"],
        )
        if not day_sessions:
            continue
        lines.append(f"  {day}")
        for session in day_sessions:
            location = " ".join(
                part for part in (session["building"], session["room"]) if part
            )
            row = (
                f"    {session['start_time']}-{session['end_time']}  "
                f"{session['course_code']} {session['section']}  {location}"
            )
            lines.append(row.rstrip())

    lines.extend(["", "Web Add/Drop:"])
    web_add_drop = _saved_web_add_drop(plan)
    if not web_add_drop:
        lines.append("  None.")
    for index, item in enumerate(web_add_drop, start=1):
        lines.append(f"  {index}. {item.get('course_code', 'Unknown')}")
        drop_sections = item.get("drop_sections", [])
        if not isinstance(drop_sections, list):
            drop_sections = []
        for section in drop_sections:
            lines.append(f"     drop {section}")
        add_sections = item.get("add_sections", [])
        if not isinstance(add_sections, list):
            add_sections = []
        for section in add_sections:
            if not isinstance(section, dict):
                continue
            line = f"     add {section.get('section', 'Unknown')}"
            crn = section.get("crn")
            if crn:
                line += f" CRN {crn}"
            lines.append(line)

    registration_steps = plan.get("registration_steps", [])
    other_steps = []
    if isinstance(registration_steps, list):
        for step in registration_steps:
            text = str(step)
            unnumbered = re.sub(r"^\s*\d+\.\s*", "", text)
            if not unnumbered.startswith((
                "Study load:",
                "Keep pre-registered:",
                "Web Add/Drop",
            )):
                other_steps.append(text)
    if other_steps:
        lines.extend(["", "Other registration steps:"])
        lines.extend(f"  {step}" for step in other_steps)
    return "\n".join(lines)


def _saved_plan_added_sections(plan: dict) -> set[tuple[str, str]]:
    added_sections = set()
    sections = plan.get("sections", [])
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            code = str(section.get("course_code") or "").upper()
            name = str(section.get("section") or section.get("type") or "").upper()
            if code and name:
                added_sections.add((code, name))
    if added_sections:
        return added_sections

    courses = plan.get("courses", [])
    if isinstance(courses, list):
        for course in courses:
            match = re.match(
                r"\s*([A-Z]{2,4}\s?\d{4}[A-Z]?)\s+(.+)",
                str(course).upper(),
            )
            if not match:
                continue
            code = match.group(1).replace(" ", "")
            added_sections.update(
                (code, section)
                for section in match.group(2).split("+")
                if section
            )
    return added_sections


def _saved_plan_signature(plan: dict) -> tuple:
    courses = plan.get("courses", [])
    normalized_courses = tuple(sorted(
        str(course).strip().upper()
        for course in courses
    )) if isinstance(courses, list) else ()
    sections = plan.get("sections", [])
    normalized_sections = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            normalized_sections.append((
                str(section.get("course_code") or "").strip().upper(),
                str(section.get("section") or section.get("type") or "").strip().upper(),
                str(section.get("crn") or "").strip(),
                str(section.get("day") or "").strip().casefold(),
                str(section.get("start") or section.get("start_time") or "").strip(),
                str(section.get("end") or section.get("end_time") or "").strip(),
                str(section.get("location") or "").strip().casefold(),
            ))
    return normalized_courses, tuple(sorted(normalized_sections))


def _print_saved_plan(plan: dict, number: int) -> None:
    added_sections = _saved_plan_added_sections(plan)
    added_course_codes = {code for code, _ in added_sections}
    in_web_add_drop = False
    web_course_code = None
    for line in _format_saved_plan(plan, number).splitlines():
        if line == f"Plan {number}":
            _print_yellow(line)
            continue
        if line == "Web Add/Drop:":
            in_web_add_drop = True
            print(line)
            continue
        if line == "Other registration steps:":
            in_web_add_drop = False
        if in_web_add_drop:
            web_course = re.match(
                r"^\s+\d+\.\s+([A-Z]{2,4}\s?\d{4}[A-Z]?)\s*$",
                line.upper(),
            )
            if web_course:
                web_course_code = web_course.group(1).replace(" ", "")
            if web_course_code in added_course_codes and (
                web_course
                or re.match(r"^\s+(?:add|drop)\s+", line, re.IGNORECASE)
            ):
                _print_green(line)
                continue
        prefix = "Course(s) added: "
        if line.startswith(prefix) and line[len(prefix):] != "None":
            print(prefix + _colorize(line[len(prefix):], "32"))
            continue
        session = re.match(
            r"^\s+\d{2}:\d{2}-\d{2}:\d{2}\s+"
            r"([A-Z]{2,4}\s?\d{4}[A-Z]?)\s+(\S+)",
            line.upper(),
        )
        if session and (
            session.group(1).replace(" ", ""),
            session.group(2),
        ) in added_sections:
            _print_green(line)
        else:
            print(line)


def _show_saved_plans() -> None:
    saved_plans = _load_saved_bundles()

    if not saved_plans:
        print("No saved plans were found.")
        return

    print(f"Found {len(saved_plans)} saved plan(s).\n")

    for number, entry in enumerate(saved_plans, start=1):
        _print_saved_plan(_saved_plan_data(entry), number)
        print()


def _delete_saved_plan(number: int) -> None:
    saved_plans = _load_saved_bundles()
    if not saved_plans:
        _print_red("No saved plans were found.")
        return
    if not 1 <= number <= len(saved_plans):
        _print_red(f"Plan number must be from 1 to {len(saved_plans)}.")
        return
    del saved_plans[number - 1]
    try:
        _save_bundles_to_disk(saved_plans)
    except OSError as error:
        _print_red(f"Could not delete Plan {number}: {error}")
        return
    _print_red(f"Deleted Plan {number}.")


def _save_bundles_to_disk(bundles: list[dict]) -> None:
    path = _saved_bundles_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


_DAY_ALIASES = {
    "m": "Mon",
    "mon": "Mon",
    "monday": "Mon",
    "t": "Tue",
    "tue": "Tue",
    "tuesday": "Tue",
    "w": "Wed",
    "wed": "Wed",
    "wednesday": "Wed",
    "r": "Thu",
    "thu": "Thu",
    "thursday": "Thu",
    "f": "Fri",
    "fri": "Fri",
    "friday": "Fri",
    "s": "Sat",
    "sat": "Sat",
    "saturday": "Sat",
    "u": "Sun",
    "sun": "Sun",
    "sunday": "Sun",
}


def _parse_day_list(value: str) -> tuple[str, ...]:
    days = []
    for token in value.replace(",", " ").split():
        day = _DAY_ALIASES.get(token.casefold())
        if day is None:
            raise ValueError(
                f"Unrecognized day {token!r}. Use Mon, Tue, Wed, Thu, "
                "Fri, Sat, or Sun."
            )
        if day not in days:
            days.append(day)
    return tuple(days)


def _parse_clock_time(
    value: str,
    label: str,
    *,
    allow_24: bool = False,
) -> str:
    value = value.strip()
    if re.fullmatch(r"\d{4}", value):
        hours, minutes = int(value[:2]), int(value[2:])
    elif re.fullmatch(r"\d{1,2}:\d{2}", value):
        hour_text, minute_text = value.split(":")
        hours, minutes = int(hour_text), int(minute_text)
    else:
        raise ValueError(f"{label} must use HHMM or HH:MM format.")

    if minutes > 59 or hours > 24 or (hours == 24 and (minutes or not allow_24)):
        raise ValueError(f"{label} must be a valid 24-hour time.")
    return f"{hours:02d}:{minutes:02d}"


def _parse_lunch_window(value: str) -> tuple[str, str]:
    parts = re.split(r"\s*-\s*", value.strip())
    if len(parts) != 2:
        raise ValueError("Lunch time window must look like 1200-1400.")
    start = _parse_clock_time(parts[0], "Lunch window start")
    end = _parse_clock_time(parts[1], "Lunch window end", allow_24=True)
    if start >= end:
        raise ValueError("Lunch window end must be later than its start.")
    return start, end


def _validate_lunch_duration(
    lunch_minutes: int,
    lunch_window: tuple[str, str],
) -> None:
    window_minutes = (
        _minutes_from_clock(lunch_window[1])
        - _minutes_from_clock(lunch_window[0])
    )
    if lunch_minutes > window_minutes:
        raise ValueError(
            f"Lunch break length ({lunch_minutes} minutes) cannot exceed "
            f"the lunch time window ({window_minutes} minutes)."
        )


def _minutes_from_clock(value: str) -> int:
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def _load_basic_settings() -> BasicSettings:
    settings_file = _basic_settings_config_file()
    try:
        values = json.loads(settings_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return BasicSettings()
    except (OSError, json.JSONDecodeError) as error:
        _print_red(f"Could not read basic settings: {error}")
        return BasicSettings()

    try:
        if not isinstance(values, dict):
            raise TypeError("Basic settings must be a JSON object.")

        prefer_days = values.get("prefer_days", [])
        avoid_days = values.get("avoid_days", [])
        min_credits = values.get("min_credits")
        max_credits = values.get("max_credits")
        lunch_minutes = values.get("lunch_minutes", 0)
        lunch_window_value = values.get("lunch_window", ["11:30", "14:30"])
        min_gap = values.get("min_gap", 0)
        earliest_start = values.get("earliest_start")
        latest_end = values.get("latest_end")
        if not isinstance(prefer_days, list) or not all(
            isinstance(day, str) for day in prefer_days
        ):
            raise ValueError("Preferred days in saved settings must be a list.")
        if not isinstance(avoid_days, list) or not all(
            isinstance(day, str) for day in avoid_days
        ):
            raise ValueError("Avoided days in saved settings must be a list.")

        normalized_prefer = _parse_day_list(" ".join(prefer_days))
        normalized_avoid = _parse_day_list(" ".join(avoid_days))
        for label, credits in (
            ("minimum", min_credits),
            ("maximum", max_credits),
        ):
            if credits is not None and (
                type(credits) is not int or credits < 0
            ):
                raise ValueError(
                    f"Saved {label} credits must be a non-negative integer."
                )
        if (
            min_credits is not None
            and max_credits is not None
            and min_credits > max_credits
        ):
            raise ValueError(
                "Saved minimum credits exceed maximum credits."
            )
        for label, minutes in (
            ("lunch duration", lunch_minutes),
            ("minimum gap", min_gap),
        ):
            if type(minutes) is not int or minutes < 0:
                raise ValueError(
                    f"Saved {label} must be a non-negative integer."
                )
        if (
            not isinstance(lunch_window_value, list)
            or len(lunch_window_value) != 2
            or not all(isinstance(value, str) for value in lunch_window_value)
        ):
            raise ValueError("Saved lunch window must contain two times.")
        lunch_window = _parse_lunch_window(
            "-".join(lunch_window_value)
        )
        _validate_lunch_duration(lunch_minutes, lunch_window)
        if earliest_start is not None:
            if not isinstance(earliest_start, str):
                raise ValueError("Saved earliest start must be a time.")
            earliest_start = _parse_clock_time(
                earliest_start,
                "Saved earliest start",
            )
        if latest_end is not None:
            if not isinstance(latest_end, str):
                raise ValueError("Saved latest end must be a time.")
            latest_end = _parse_clock_time(
                latest_end,
                "Saved latest end",
                allow_24=True,
            )
        if (
            earliest_start is not None
            and latest_end is not None
            and earliest_start > latest_end
        ):
            raise ValueError(
                "Saved earliest start is later than latest end."
            )
        if set(normalized_prefer) & set(normalized_avoid):
            raise ValueError(
                "A day cannot be both preferred and avoided."
            )
    except (TypeError, ValueError) as error:
        _print_red(f"Invalid basic settings: {error}")
        return BasicSettings()

    return BasicSettings(
        prefer_days=normalized_prefer,
        avoid_days=normalized_avoid,
        min_credits=min_credits,
        max_credits=max_credits,
        lunch_minutes=lunch_minutes,
        lunch_window=lunch_window,
        min_gap=min_gap,
        earliest_start=earliest_start,
        latest_end=latest_end,
    )


def _save_basic_settings(settings: BasicSettings) -> None:
    values = {
        "prefer_days": list(settings.prefer_days),
        "avoid_days": list(settings.avoid_days),
        "min_credits": settings.min_credits,
        "max_credits": settings.max_credits,
        "lunch_minutes": settings.lunch_minutes,
        "lunch_window": list(settings.lunch_window),
        "min_gap": settings.min_gap,
        "earliest_start": settings.earliest_start,
        "latest_end": settings.latest_end,
    }
    settings_file = _basic_settings_config_file()
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(
        json.dumps(values, indent=2) + "\n",
        encoding="utf-8",
    )


def _prompt_days(label: str, current: tuple[str, ...]) -> tuple[str, ...]:
    while True:
        current_value = ", ".join(current) or "none"
        response = input(
            f"{label} {_colorize(f'[{current_value}]', '95')} "
            "(blank keeps, none clears): "
        ).strip()
        _exit_if_requested(response)
        if not response:
            return current
        if response.casefold() in {"none", "clear"}:
            return ()
        try:
            return _parse_day_list(response)
        except ValueError as error:
            _print_red(str(error))


def _prompt_credit_limit(
    label: str,
    current: int | None,
) -> int | None:
    while True:
        current_value = str(current) if current is not None else "none"
        response = input(
            f"{label} {_colorize(f'[{current_value}]', '95')} "
            "(blank keeps, none clears): "
        ).strip()
        _exit_if_requested(response)
        if not response:
            return current
        if response.casefold() in {"none", "clear"}:
            return None
        try:
            credits = int(response)
        except ValueError:
            _print_red(f"{label} must be a non-negative integer.")
            continue
        if credits < 0:
            _print_red(f"{label} must be a non-negative integer.")
            continue
        return credits


def _prompt_minutes(label: str, current: int) -> int:
    while True:
        response = input(
            f"{label} {_colorize(f'[{current}]', '95')} "
            "(blank keeps, none clears): "
        ).strip()
        _exit_if_requested(response)
        if not response:
            return current
        if response.casefold() in {"none", "clear"}:
            return 0
        try:
            minutes = int(response)
        except ValueError:
            _print_red(f"{label} must be a non-negative integer.")
            continue
        if minutes < 0:
            _print_red(f"{label} must be a non-negative integer.")
            continue
        return minutes


def _prompt_lunch_window(
    current: tuple[str, str],
) -> tuple[str, str]:
    while True:
        current_value = f"{current[0]}-{current[1]}"
        response = input(
            "Lunch time window (e.g. 1200-1400) "
            f"{_colorize(f'[{current_value}]', '95')} "
            "(blank keeps, none resets): "
        ).strip()
        _exit_if_requested(response)
        if not response:
            return current
        if response.casefold() in {"none", "clear"}:
            return ("11:30", "14:30")
        try:
            return _parse_lunch_window(response)
        except ValueError as error:
            _print_red(str(error))


def _prompt_clock_limit(
    label: str,
    current: str | None,
    *,
    allow_24: bool = False,
) -> str | None:
    while True:
        current_value = current or "none"
        response = input(
            f"{label} (HHMM or HH:MM) "
            f"{_colorize(f'[{current_value}]', '95')} "
            "(blank keeps, none clears): "
        ).strip()
        _exit_if_requested(response)
        if not response:
            return current
        if response.casefold() in {"none", "clear"}:
            return None
        try:
            return _parse_clock_time(response, label, allow_24=allow_24)
        except ValueError as error:
            _print_red(str(error))


def _prompt_basic_settings(current: BasicSettings) -> BasicSettings:
    while True:
        _print_yellow(
            "Basic settings: days may be entered as Mon/Tue/Wed/Thu/Fri/Sat/Sun "
            "or M/T/W/R/F/S/U. Times accept HHMM or HH:MM; lunch windows "
            "use start-end, e.g. 1200-1400."
        )
        try:
            prefer_days = _prompt_days("Prefer days", current.prefer_days)
            avoid_days = _prompt_days("Avoid days", current.avoid_days)
            min_credits = _prompt_credit_limit(
                "Minimum credits",
                current.min_credits,
            )
            max_credits = _prompt_credit_limit(
                "Maximum credits",
                current.max_credits,
            )
            lunch_minutes = _prompt_minutes(
                "Lunch break length in minutes",
                current.lunch_minutes,
            )
            lunch_window = _prompt_lunch_window(current.lunch_window)
            min_gap = _prompt_minutes(
                "Minimum minutes between classes",
                current.min_gap,
            )
            earliest_start = _prompt_clock_limit(
                "Earliest class start",
                current.earliest_start,
            )
            latest_end = _prompt_clock_limit(
                "Latest class end",
                current.latest_end,
                allow_24=True,
            )
            _validate_lunch_duration(lunch_minutes, lunch_window)
            if set(prefer_days) & set(avoid_days):
                raise ValueError(
                    "A day cannot be both preferred and avoided."
                )
            if (
                min_credits is not None
                and max_credits is not None
                and min_credits > max_credits
            ):
                raise ValueError(
                    "Minimum credits cannot exceed maximum credits."
                )
            if (
                earliest_start is not None
                and latest_end is not None
                and earliest_start > latest_end
            ):
                raise ValueError(
                    "Earliest class start cannot be later than latest class end."
                )
        except ValueError as error:
            _print_red(str(error))
            continue

        return BasicSettings(
            prefer_days=prefer_days,
            avoid_days=avoid_days,
            min_credits=min_credits,
            max_credits=max_credits,
            lunch_minutes=lunch_minutes,
            lunch_window=lunch_window,
            min_gap=min_gap,
            earliest_start=earliest_start,
            latest_end=latest_end,
        )


def _basic_settings_arguments(settings: BasicSettings) -> list[str]:
    arguments = []
    if settings.prefer_days:
        arguments.extend(["--prefer-days", *settings.prefer_days])
    if settings.avoid_days:
        arguments.extend(["--avoid-days", *settings.avoid_days])
    if settings.min_credits is not None:
        arguments.extend(["--min-credits", str(settings.min_credits)])
    if settings.max_credits is not None:
        arguments.extend(["--max-credits", str(settings.max_credits)])
    if settings.lunch_minutes:
        arguments.extend(["--lunch", str(settings.lunch_minutes)])
    if settings.lunch_window != ("11:30", "14:30"):
        arguments.extend(["--lunch-window", *settings.lunch_window])
    if settings.min_gap:
        arguments.extend(["--min-gap", str(settings.min_gap)])
    if settings.earliest_start:
        arguments.extend(["--earliest", settings.earliest_start])
    if settings.latest_end:
        arguments.extend(["--latest", settings.latest_end])
    return arguments


def _load_saved_aims_path() -> str | None:
    config_file = _aims_path_config_file()
    try:
        saved_path = config_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as error:
        _print_red(f"Could not read saved AIMS path: {error}")
        return None
    return saved_path or None


def _save_aims_path(path: str) -> None:
    config_file = _aims_path_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(path, encoding="utf-8")


def _prompt_path(label: str, default: str | None = None) -> str | None:
    default_text = f" [{default}]" if default else ""
    value = input(f"{label}{default_text}: ").strip()
    _exit_if_requested(value)
    if not value:
        return default
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


class _ReturnToMenu(Exception):
    pass


def _exit_if_requested(value: str) -> None:
    entered = value.strip().casefold()
    if entered == "q":
        raise _ReturnToMenu
    if entered == "0":
        raise SystemExit(0)


def _colorize(
    text: str,
    color: str,
    file: TextIO | None = None,
) -> str:
    output = sys.stdout if file is None else file
    if output.isatty() and "NO_COLOR" not in os.environ:
        return f"\033[{color}m{text}\033[0m"
    return text


def _colorize_added_course_lines(text: str, course_codes: set[str]) -> str:
    codes = {code.upper() for code in course_codes}
    lines = []
    for line in text.splitlines():
        for code in codes:
            escaped = re.escape(code)
            if (
                re.match(rf"^\s+{escaped}\s", line)
                or re.match(
                    rf"^\s+\d{{2}}:\d{{2}}-\d{{2}}:\d{{2}}\s+{escaped}\s",
                    line,
                )
            ):
                line = _colorize(line, "32")
                break
        lines.append(line)
    return "\n".join(lines)


def _print_color(
    text: str,
    color: str,
    file: TextIO | None = None,
) -> None:
    output = sys.stdout if file is None else file
    print(_colorize(text, color, output), file=output)


def _print_green(text: str) -> None:
    _print_color(text, "32")


def _print_yellow(text: str) -> None:
    _print_color(text, "33")


def _print_blue(text: str) -> None:
    _print_color(text, "34")


def _print_purple(text: str) -> None:
    _print_color(text, "95")


def _print_red(text: str, file: TextIO | None = None) -> None:
    _print_color(text, "31", file)


def _is_basic_setting_conflict(reason: str) -> bool:
    return (
        reason.startswith((
            "Uses avoided day(s):",
            "Outside allowed time window:",
            "Minimum gap of ",
        ))
        or (
            reason.startswith("No ")
            and " lunch break between " in reason
        )
    )


_BASIC_PLAN_REJECTIONS = {"avoid_day", "time_window", "min_gap", "lunch"}


def _print_plan_rejections(report, no_plans: bool) -> None:
    rejection_lines = report.rejection_summary()
    if no_plans:
        _print_red("No plan satisfies all settings.")
    elif rejection_lines:
        print("Options rejected:")

    for key, line in rejection_lines:
        if key in _BASIC_PLAN_REJECTIONS:
            _print_purple(line)
        else:
            _print_red(line)

    if report.truncated:
        _print_red("  Search stopped early; narrow the course list.")


class _CityUScheduleArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        _print_red(
            f"{self.prog}: error: {message}",
            file=sys.stderr,
        )
        self.exit(2)


def _menu_command(
    choice: str,
    saved_aims_path: str | None = None,
    settings: BasicSettings | None = None,
) -> tuple[list[str] | None, str | None]:
    settings = settings or BasicSettings()

    if choice == "2":
        path = _prompt_path(
            "AIMS timetable HTML path (enter a new path to change it)",
            saved_aims_path,
        )
        return (
            (["--aims-html", path], path)
            if path
            else (None, None)
        )

    if choice == "3":
        path = saved_aims_path or _prompt_path(
            "Saved AIMS timetable HTML path"
        )
        if not path:
            return None, None
        command = ["--aims-html", path, "--paste-aims"]
        command.extend(_basic_settings_arguments(settings))
        return command, path

    if choice == "5":
        while True:
            course_code = input("GE course code: ").strip().upper()
            _exit_if_requested(course_code)
            if re.fullmatch(r"GE\d{4}[A-Z]?", course_code):
                break
            _print_red("Enter a GE course code such as GE1102.")
        return ["--ge-info", course_code], None

    if choice == "6":
        return _plan_menu_command(saved_aims_path, settings)

    return None, None


def _ask_menu(label: str) -> str:
    value = input(f"{label}: ").strip()
    _exit_if_requested(value)
    return value


def _prompt_plan_aims_path() -> str | None:
    while True:
        path = _prompt_path(
            "AIMS timetable HTML path to plan around (Enter to skip)"
        )
        if not path:
            return None
        try:
            load_aims_html(path)
        except (OSError, ValueError) as error:
            _print_red(f"Invalid AIMS timetable: {error}")
            continue
        return path


def _prompt_plan_course_codes() -> list[str]:
    while True:
        response = _ask_menu(
            "Course codes you are interested in, e.g. GE1102 GE1401 GE2410"
        )
        codes = response.replace(",", " ").upper().split()
        invalid = [
            code
            for code in codes
            if not re.fullmatch(r"[A-Z]{2,4}\d{4}[A-Z]?", code)
        ]
        if invalid:
            _print_red(
                "Invalid course code(s): "
                + ", ".join(invalid)
                + ". Enter codes such as GE1102 or CS1102."
            )
            continue
        return list(dict.fromkeys(codes))


def _prompt_required_plan_course_codes() -> list[str]:
    while True:
        codes = _prompt_plan_course_codes()
        if codes:
            return codes
        _print_red("Enter at least one course code.")


def _prompt_plan_ge_count(maximum: int) -> str:
    while True:
        count = input(
            "How many GE courses should the generator add? "
            "(enter a positive integer): "
        ).strip()
        if count.casefold() == "q":
            raise _ReturnToMenu
        if not count:
            return str(maximum)
        if re.fullmatch(r"[0-9]+", count):
            try:
                number = int(count)
            except ValueError:
                pass
            else:
                if 1 <= number <= maximum:
                    return str(number)
        _print_red(
            f"Enter a whole number of GE courses from 1 to {maximum}."
        )


def _prompt_plan_save_choices(plan_count: int) -> list[int]:
    while True:
        response = input(
            "Save plans (e.g. 1 or 1,2, or Enter to skip): "
        ).strip()
        _exit_if_requested(response)
        if not response:
            return []
        choices = [item.strip() for item in response.split(",")]
        if all(re.fullmatch(r"[0-9]+", item) for item in choices):
            try:
                numbers = [int(item) for item in choices]
            except ValueError:
                numbers = []
            if numbers and all(1 <= number <= plan_count for number in numbers):
                return sorted({number - 1 for number in numbers})
        _print_red(
            f"Enter plan numbers from 1 to {plan_count}, separated by commas, "
            "or press Enter to skip."
        )


def _prompt_plan_term() -> str:
    """Require a valid CityU semester for course-plan generation."""
    from .plan_generator import term_key

    while True:
        try:
            semester = input("Semester to check (e.g. 2627A, 2627B, 2627S): ").strip()
        except EOFError:
            raise ValueError(
                "A semester is required for course-plan generation; use --term 2627A."
            ) from None
        if term_key(semester):
            return semester
        _print_red("Enter a valid semester, e.g. 2627A, 2627B, or 2627S.")


def _ge_catalog_term(term: str) -> str | None:
    from .plan_generator import term_key

    key = term_key(term)
    if not key:
        return None
    year, part = key
    label = "Summer" if part == "S" else f"Sem {part}"
    return f"20{year}-{int(year) + 1:02d} {label}"


def _plan_menu_command(
    saved_aims_path: str | None,
    settings: BasicSettings,
) -> tuple[list[str] | None, str | None]:
    """Ask for course plan generator inputs (menu option 6)."""
    from .plan_generator import term_key

    semester = _ask_menu("Semester to check, e.g. 2627A, 2627B, or 2627S")
    while not term_key(semester):
        _print_red("Enter a valid semester, e.g. 2627A, 2627B, or 2627S.")
        semester = _ask_menu("Semester to check, e.g. 2627A, 2627B, or 2627S")

    aims_path = saved_aims_path or _prompt_plan_aims_path()
    codes = _prompt_required_plan_course_codes()
    ge_count = _prompt_plan_ge_count(len(codes))

    ge_term = _ge_catalog_term(semester)
    available_codes = {
        course.code.upper()
        for course in load_ge_section_catalog(term=ge_term)
    }
    while True:
        unavailable = [code for code in codes if code not in available_codes]
        if not unavailable:
            break
        _print_red(
            "No section details for "
            + ", ".join(unavailable)
            + f" in {semester}. Enter available course code(s)."
        )
        codes = _prompt_required_plan_course_codes()
        if int(ge_count or 0) > len(codes):
            _print_red(
                f"The GE course count cannot exceed the {len(codes)} "
                "course code(s) entered."
            )
            ge_count = _prompt_plan_ge_count(len(codes))

    command = ["--aims-html", aims_path] if aims_path else []
    command.extend(_basic_settings_arguments(settings))
    command.extend(["--term", semester])
    if codes:
        command.extend(["--courses", *codes])
    if int(ge_count or 0):
        command.extend(["--add-ge", ge_count])
    command.append("--ask")
    return command, aims_path


def interactive_menu() -> None:
    saved_aims_path = _load_saved_aims_path()
    basic_settings = _load_basic_settings()
    while True:
        if saved_aims_path:
            _print_yellow(f"\nRemembered AIMS HTML: {saved_aims_path}")
        _print_yellow(
            "\nCityU Schedule\n"
            "1. Basic settings\n"
            "2. Check or change saved AIMS timetable\n"
            "3. Paste and check an AIMS course offering\n"
            "4. Search GE courses\n"
            "5. Show GE course details\n"
            "6. Generate timetable plans\n"
            "7. Saved timetable plan\n"
            "0. Exit\n"
            "Type q to return to the menu, or 0 to exit the package.\n"
            "Type delete all or delete names joined by 'and' to clear data."
        )
        try:
            choice = input(
                _colorize("Choose an option: ", "33")
            ).strip()
            if choice.casefold() == "0":
                return

            if choice == "4":
                while True:
                    try:
                        keyword = input(
                            "GE search keyword or filter "
                            "(q = menu, 0 = exit): "
                        ).strip()
                    except EOFError:
                        return

                    if keyword.casefold() == "q":
                        break
                    if keyword == "0":
                        return
                    if not keyword:
                        _print_red(
                            "Enter a keyword or filter, q, or 0."
                        )
                        continue

                    try:
                        main(["--ge-search", keyword])
                    except SystemExit as error:
                        if error.code:
                            print(
                                "\nSearch failed. Enter another "
                                "query, q to return to the menu, "
                                "or 0 to exit."
                            )
                continue

            delete_command = choice.casefold()
            delete_plan = re.fullmatch(r"delete\s+plan\s*(\d+)", delete_command)
            if delete_plan:
                try:
                    plan_number = int(delete_plan.group(1))
                except ValueError:
                    _print_red("Enter a valid saved plan number.")
                else:
                    _delete_saved_plan(plan_number)
                continue

            if delete_command.startswith("delete"):
                try:
                    if delete_command == "delete all":
                        _basic_settings_config_file().unlink(
                            missing_ok=True
                        )
                        _aims_path_config_file().unlink(missing_ok=True)
                        basic_settings = BasicSettings()
                        saved_aims_path = None
                        message = (
                            "All saved settings and AIMS path deleted."
                        )
                    else:
                        setting_fields = {
                            "avoid": (
                                "avoid_days",
                                (),
                                "avoid days",
                            ),
                            "prefer": (
                                "prefer_days",
                                (),
                                "preferred days",
                            ),
                            "min": (
                                "min_credits",
                                None,
                                "minimum credits",
                            ),
                            "max": (
                                "max_credits",
                                None,
                                "maximum credits",
                            ),
                            "lunch": (
                                "lunch_minutes",
                                0,
                                "lunch break length",
                            ),
                            "window": (
                                "lunch_window",
                                ("11:30", "14:30"),
                                "lunch time window",
                            ),
                            "gap": (
                                "min_gap",
                                0,
                                "minimum gap",
                            ),
                            "earliest": (
                                "earliest_start",
                                None,
                                "earliest class start",
                            ),
                            "latest": (
                                "latest_end",
                                None,
                                "latest class end",
                            ),
                        }
                        targets = list(
                            dict.fromkeys(
                                target.strip()
                                for target in delete_command[
                                    len("delete"):
                                ].split("and")
                            )
                        )
                        if not targets or any(
                            target not in {*setting_fields, "aims"}
                            for target in targets
                        ):
                            raise ValueError(
                                "Use delete all, delete avoid, delete "
                                "prefer, delete min, delete max, delete "
                                "lunch, delete window, delete gap, delete "
                                "earliest, delete latest, delete AIMS, "
                                "delete plan 1, or delete plan1. "
                                "Join multiple names with 'and'."
                            )

                        if "aims" in targets:
                            _aims_path_config_file().unlink(
                                missing_ok=True
                            )
                            saved_aims_path = None

                        labels = []
                        for target in targets:
                            if target == "aims":
                                labels.append("AIMS path")
                                continue
                            field, empty_value, label = setting_fields[
                                target
                            ]
                            basic_settings = replace(
                                basic_settings,
                                **{field: empty_value},
                            )
                            labels.append(label)
                        if any(target != "aims" for target in targets):
                            _save_basic_settings(basic_settings)
                        message = (
                            "Saved " + " and ".join(labels) + " deleted."
                        )
                except OSError as error:
                    basic_settings = _load_basic_settings()
                    saved_aims_path = _load_saved_aims_path()
                    _print_red(
                        f"Could not delete saved information: {error}"
                    )
                except ValueError as error:
                    _print_red(str(error))
                else:
                    _print_red(message)
                continue

            if choice == "1":
                basic_settings = _prompt_basic_settings(basic_settings)
                try:
                    _save_basic_settings(basic_settings)
                except OSError as error:
                    _print_red(f"Could not save basic settings: {error}")
                else:
                    _print_green("Basic settings saved.")
                continue
            if choice == "7":
                _show_saved_plans()
                continue

            task_options = {"2", "3", "5", "6"}
            if choice not in task_options:
                _print_red("Choose an option from 0 to 7.")
                continue

            while True:
                command, aims_path_to_save = _menu_command(
                    choice,
                    saved_aims_path,
                    basic_settings,
                )
                if command is None:
                    _print_red(
                        "Required input was not provided. "
                        f"Please enter the inputs for option {choice} again."
                    )
                    continue

                try:
                    main(command)
                except SystemExit as error:
                    if error.code == 0:
                        return
                    if error.code:
                        _print_red(
                            "\nTask failed. Please enter the inputs for "
                            f"option {choice} again."
                        )
                    continue

                if aims_path_to_save:
                    saved_aims_path = aims_path_to_save
                    try:
                        _save_aims_path(aims_path_to_save)
                    except OSError as error:
                        _print_red(f"Could not save AIMS path: {error}")
                break
        except EOFError:
            return
        except _ReturnToMenu:
            continue


def _required_section_pairs(values: list[str] | None) -> dict[str, list[str]]:
    values = list(values or [])
    if len(values) % 2:
        raise ValueError(
            "Invalid --require-section arguments. Provide course code and "
            "section pairs, such as: --require-section TEST101 C01"
        )
    pairs: dict[str, list[str]] = {}
    for code, section in zip(values[::2], values[1::2]):
        pairs.setdefault(code.upper(), []).append(section.upper())
    return pairs


def _run_course_planner(args: argparse.Namespace, parser) -> None:
    """List course plans from the plan generator, then optionally save."""
    from .plan_generator import (
        PLANNING_ONLY_NOTICE,
        PlanOptions,
        format_plan,
        generate_course_plans,
        load_course_requirements,
        load_ge_areas,
    )

    try:
        if not args.term:
            args.term = _prompt_plan_term()
        courses = [
            course
            for path in args.timetable_catalog or []
            for course in load_course_catalog(path)
        ]
        wanted = list(dict.fromkeys(
            code for item in args.courses or []
            for code in item.replace(",", " ").upper().split()
        ))
        if args.add_ge < 0:
            raise ValueError("--add-ge cannot be negative")
        if wanted or args.add_ge:
            # Course details shown by menu option 5 (data/ge_course_information.json).
            ge_term = _ge_catalog_term(args.term) if args.term else None
            known = {course.code.upper() for course in courses}
            courses.extend(
                course
                for course in load_ge_section_catalog(term=ge_term)
                if course.code.upper() not in known
            )
        if wanted:
            keep = set(wanted) | {code.upper() for code in args.required or []}
            courses = [c for c in courses if c.code.upper() in keep]
            found = {c.code.upper() for c in courses}
            missing = [code for code in wanted if code not in found]
            if missing:
                _print_yellow(
                    "Note: no section details for " + ", ".join(missing)
                    + " (menu option 5 has none), so they cannot be "
                    "planned yet. Import them with the 'Import GE course "
                    "information' GitHub workflow."
                )
            if not courses:
                raise ValueError("None of the courses you entered have section details.")
        bundles = {}
        if args.ge_bundles:
            with open(args.ge_bundles, "r", encoding="utf-8-sig") as file:
                bundles = json.load(file)
        fixed_sessions = []
        if args.aims_html:
            fixed_sessions = load_aims_html(args.aims_html)
        elif args.csv_file:
            fixed_sessions = load_sessions(args.csv_file)
        options = PlanOptions(
            required_courses=tuple(code.upper() for code in args.required or []),
            required_sections=_required_section_pairs(args.require_section),
            exclude_courses=tuple(args.exclude),
            max_courses=args.max_courses,
            ge_courses=args.add_ge or None,
            min_credits=args.min_credits,
            max_credits=args.max_credits,
            preferred_days=tuple(args.prefer_days or []),
            avoid_days=tuple(args.avoid_days or []),
            earliest_start=args.earliest,
            latest_end=args.latest,
            min_gap=args.min_gap,
            lunch_minutes=args.lunch,
            max_daily_hours=args.max_daily_hours,
            check_travel=not args.no_travel_check,
            max_results=args.max_results,
            bundle_definitions=bundles,
            study_load=None if args.study_load == "none" else args.study_load,
            allow_overload=args.allow_overload,
            allow_section_changes=args.allow_section_change,
            seat_policy=args.seats,
            web_only=args.web_only,
            term=args.term,
            lunch_window=tuple(args.lunch_window),
        )
        report = generate_course_plans(
            courses,
            options,
            fixed_sessions=fixed_sessions,
            credit_courses=load_credit_catalogs(args.credit_catalog),
            requirements=load_course_requirements(args.timetable_catalog or []),
            ge_areas=load_ge_areas(),
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    for warning in report.warnings:
        _print_yellow(f"Note: {warning}")
    fit_lines = report.fit_summary()
    if fit_lines:
        print("\nTimeslots that fit your timetable:")
        for line in fit_lines:
            if (
                "no timeslot that fits your timetable" in line
                or "no class bundles fit" in line
            ):
                _print_red(f"  {line}")
            else:
                _print_green(f"  {line}")
        print()
    if not report.plans:
        _print_plan_rejections(report, no_plans=True)
        return

    if report.rejection_summary():
        _print_plan_rejections(report, no_plans=False)
        print()

    plans = report.plans
    print(
        f"Found {len(plans)} course plan(s) "
        f"(checked {report.explored} combinations):\n"
    )
    for number, plan in enumerate(plans, start=1):
        plan_lines = format_plan(plan, number, steps=not args.no_steps).splitlines()
        _print_yellow(plan_lines[0])
        added_courses = {
            option.course_code
            for option in plan.chosen
            if not option.preregistered
        }
        if len(plan_lines) > 1:
            print(
                _colorize_added_course_lines(
                    "\n".join(plan_lines[1:]),
                    added_courses,
                )
            )
        print()
    _print_blue(PLANNING_ONLY_NOTICE)

    if not args.ask:
        return

    try:
        chosen = _prompt_plan_save_choices(len(plans))
        if chosen:
            saved_bundles = _load_saved_bundles()
            saved_signatures = {
                _saved_plan_signature(_saved_plan_data(entry))
                for entry in saved_bundles
            }
            new_plans = []
            for index in chosen:
                plan_data = plans[index].to_dict()
                signature = _saved_plan_signature(plan_data)
                if signature in saved_signatures:
                    _print_red(f"Plan {index + 1} has already been saved.")
                    continue
                saved_signatures.add(signature)
                new_plans.append({"plan": plan_data})
            saved_bundles.extend(new_plans)
            if new_plans:
                try:
                    _save_bundles_to_disk(saved_bundles)
                    _print_green(f"Saved {len(new_plans)} plan(s).")
                except OSError as error:
                    _print_red(f"Could not save plans: {error}")
    except (EOFError, _ReturnToMenu):
        return


def main(argv: list[str] | None = None) -> None:
    command_line = sys.argv[1:] if argv is None else argv

    if not command_line:
        interactive_menu()
        return

    parser = _CityUScheduleArgumentParser(
        prog="cityuschedule",
        description="Check CityU course timetables and generate course plans.",
        epilog=(
            "Course plans: give --courses and/or --add-ge with your saved "
            "AIMS timetable (--aims-html), or choose option 6 in the menu."
        ),
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        help="CSV timetable to use as the fixed schedule for course planning",
    )
    parser.add_argument(
        "--aims-html",
        help="Path to a saved AIMS weekly timetable HTML page",
    )
    parser.add_argument(
        "--timetable-catalog",
        nargs="+",
        help="JSON timetable catalogue(s) containing course sections for planning",
    )

    parser.add_argument(
        "--credit-catalog",
        nargs="+",
        help="JSON credit catalogue(s) containing course credits",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum number of course plans to display (default 5)",
    )
    parser.add_argument(
        "--min-credits",
        type=int,
        help="Minimum total credits for generated course plans",
    )

    parser.add_argument(
        "--add-ge",
        type=int,
        default=0,
        help=(
            "Number of GE courses to add; GE sections come from the "
            "catalogue and data/ge_course_information.json"
        ),
    )

    parser.add_argument(
        "--ge-bundles",
        help=(
            "JSON file listing complete section bundles by hand, "
            'e.g. {"GE1102": [["C01", "T01"]]}'
        ),
    )

    parser.add_argument(
        "--max-credits",
        type=int,
        help="Maximum total credits for generated course plans",
    )
    parser.add_argument(
        "--required",
        nargs="+",
        help="Course codes that must appear in every generated plan",
    )
    parser.add_argument(
        "--prefer-days",
        nargs="+",
        help=(
            "Days to prefer when ranking plans or AIMS paste bundles, "
            "such as Mon Tue Wed"
        ),
    )
    parser.add_argument(
        "--require-section",
        nargs="+",
        help="Exact course sections that must appear, such as TEST101 C01",
    )
    parser.add_argument(
        "--avoid-days",
        nargs="+",
        help=(
            "Days that plans or AIMS paste bundles must not use, "
            "such as Fri Sat"
        ),
    )

    planning = parser.add_argument_group(
        "course plan generator (with --courses or --add-ge)"
    )
    planning.add_argument(
        "--courses", nargs="+", metavar="CODE",
        help="Course codes you are interested in, e.g. GE1102 GE1401; "
        "their sections come from the GE course details (menu option 5)",
    )
    planning.add_argument(
        "--exclude", nargs="+", default=[], metavar="CODE",
        help="Courses to leave out",
    )
    planning.add_argument(
        "--max-courses", type=int, help="Most new courses in a plan",
    )
    planning.add_argument(
        "--earliest", help="Earliest class start, e.g. 0900 or 09:00",
    )
    planning.add_argument(
        "--latest", help="Latest class end, e.g. 1800 or 18:00",
    )
    planning.add_argument(
        "--min-gap", type=int, default=0,
        help="Minimum minutes between classes",
    )
    planning.add_argument(
        "--lunch", type=int, default=0,
        help="Minutes of lunch break needed within --lunch-window",
    )
    planning.add_argument(
        "--lunch-window",
        nargs=2,
        metavar=("START", "END"),
        default=("11:30", "14:30"),
        help="Lunch time window (default: 11:30 14:30)",
    )
    planning.add_argument(
        "--max-daily-hours", type=float, help="Most class hours in one day",
    )
    planning.add_argument(
        "--no-travel-check", action="store_true",
        help="Do not check walking time between buildings",
    )
    planning.add_argument(
        "--study-load", default="none",
        choices=("full-time", "part-time", "summer", "none"),
        help=(
            "CityU study load: full-time 12-18 credits, part-time max 11, "
            "summer max 7 (default none: no credit limit)"
        ),
    )
    planning.add_argument(
        "--allow-overload", action="store_true",
        help="Allow more credits than the study-load maximum (needs approval)",
    )
    planning.add_argument(
        "--allow-section-change", action="store_true",
        help="Let the planner move pre-registered courses to other sections",
    )
    planning.add_argument(
        "--seats", default="waitlist", choices=("open", "waitlist", "any"),
        help=(
            "Full sections: open = never use, waitlist = only with a "
            "waitlist (default), any = always"
        ),
    )
    planning.add_argument(
        "--web-only", action="store_true",
        help="Leave out sections that are not web-enabled or are restricted",
    )
    planning.add_argument(
        "--term",
        help=(
            "Semester to plan for, e.g. 2627A, 2627B or 2627S "
            "(prompted for if omitted)"
        ),
    )
    planning.add_argument(
        "--no-steps", action="store_true",
        help="Do not print the registration steps of each plan",
    )
    planning.add_argument(
        "--ask", action="store_true",
        help="After listing plans, ask which to save",
    )

    parser.add_argument(
        "--ge-info",
        metavar="COURSE_CODE",
        help="Show basic information for a Gateway Education course, e.g. GE2230",
    )
    parser.add_argument(
        "--ge-search",
        metavar="KEYWORD",
        help="Search Gateway Education courses by course code, title, area, or offering unit",
    )

    parser.add_argument(
        "--paste-aims",
        action="store_true",
        help="Paste one AIMS course table and check weekly timetable fit",
    )

    args = parser.parse_args(command_line)

    if args.csv_file and not (
        args.aims_html
        or args.courses
        or args.timetable_catalog
        or args.add_ge
        or args.paste_aims
    ):
        parser.error(
            "A CSV timetable can only be used with course-planning options."
        )

    if (
        args.min_credits is not None
        and args.max_credits is not None
        and args.min_credits > args.max_credits
    ):
        parser.error("--min-credits cannot exceed --max-credits.")
    if args.min_gap < 0:
        parser.error("--min-gap cannot be negative.")
    if args.lunch < 0:
        parser.error("--lunch cannot be negative.")
    try:
        if args.earliest:
            args.earliest = _parse_clock_time(
                args.earliest,
                "Earliest class start",
            )
        if args.latest:
            args.latest = _parse_clock_time(
                args.latest,
                "Latest class end",
                allow_24=True,
            )
        lunch_start, lunch_end = args.lunch_window
        args.lunch_window = _parse_lunch_window(
            f"{lunch_start}-{lunch_end}"
        )
        _validate_lunch_duration(args.lunch, args.lunch_window)
        if (
            args.earliest is not None
            and args.latest is not None
            and args.earliest > args.latest
        ):
            raise ValueError(
                "Earliest class start cannot be later than latest class end."
            )
    except ValueError as error:
        parser.error(str(error))

    if args.paste_aims:
        if not args.aims_html:
            parser.error("--paste-aims requires --aims-html.")

        if args.csv_file:
            parser.error(
                "--paste-aims uses --aims-html, not a CSV timetable."
            )

        if (
            args.timetable_catalog
            or args.add_ge
            or args.ge_bundles
            or args.ge_info
            or args.ge_search
        ):
            parser.error(
                "Run --paste-aims separately from timetable catalogue planning, "
                "and GE lookup."
            )

        try:
            base_rows = load_aims_html(args.aims_html)
            base_sessions = convert_aims_sessions(base_rows)
            credit_courses = load_credit_catalogs(args.credit_catalog)

            while True:
                _print_yellow("Paste ONE course's complete AIMS offering table.")
                _print_yellow(
                    "Finish by typing END on a new line and pressing Enter."
                )
                print()

                lines = []
                empty_paste = False
                while True:
                    try:
                        line = input()
                    except EOFError:
                        raise ValueError(
                            "Input ended before END. Paste again and finish "
                            "with END on its own line."
                        ) from None

                    if not lines:
                        _exit_if_requested(line)
                    if line.strip() == "END":
                        break
                    if not line.strip() and not lines:
                        empty_paste = True
                        break

                    if line.strip():
                        lines.append(line)

                if empty_paste or not any(line.strip() for line in lines):
                    _print_red(
                        "No table was entered. Please paste the AIMS table "
                        "and try again."
                    )
                    continue

                pasted_table = "\n".join(lines)
                try:
                    parse_aims_table(pasted_table)
                except ValueError as error:
                    if not str(error).startswith("Course code is required."):
                        _print_red(
                            "That doesn't look like a complete AIMS course "
                            "offering table. Paste the full table, including "
                            "its CRN, Section, and Credit rows, and try again."
                        )
                        continue

                while True:
                    _print_yellow(
                        "If the copied table did not include the course "
                        "heading, enter its course code (for example GE2130); "
                        "otherwise press Enter:"
                    )
                    try:
                        course_code_input = input()
                    except EOFError:
                        raise ValueError(
                            "Input ended before the course code was confirmed."
                        ) from None
                    _exit_if_requested(course_code_input)
                    course_code = course_code_input.strip() or None

                    try:
                        table = parse_aims_table(
                            pasted_table,
                            course_code=course_code,
                        )
                    except ValueError as error:
                        if (
                            course_code is None
                            and str(error).startswith("Course code is required.")
                        ):
                            _print_red(
                                "A course code is required for this table. "
                                "Enter it now; do not press Enter."
                            )
                            continue
                        raise
                    break

                break
            _print_yellow(
                "Enter unavailable section codes separated by spaces or "
                "commas, or press Enter for none:"
            )
            try:
                unavailable_input = input()
            except EOFError:
                raise ValueError(
                    "Input ended before unavailable sections were "
                    "confirmed. Press Enter to continue without exclusions."
                ) from None
            _exit_if_requested(unavailable_input)
            unavailable_sections = list({
                section.upper()
                for section in unavailable_input.replace(",", " ").split()
            })

            known_sections = {
                session.section.upper()
                for session in table.sessions
            }
            unknown_sections = (
                set(unavailable_sections) - known_sections
            )
            if unknown_sections:
                raise ValueError(
                    "Unknown section code(s): "
                    + ", ".join(sorted(unknown_sections))
                )

            pasted_course_credits = table.course_credit
            aims_credits, unknown_aims_courses = calculate_course_credits(
                {
                    row["course_code"]
                    for row in base_rows
                },
                credit_courses,
            )
            candidates = table.registration_bundles()
            fitting = fitting_registration_bundles(
                table,
                base_sessions,
                preferred_days=args.prefer_days,
                avoid_days=args.avoid_days,
                unavailable_sections=unavailable_sections,
                min_gap=args.min_gap,
                earliest_start=args.earliest,
                latest_end=args.latest,
                lunch_minutes=args.lunch,
                lunch_window=tuple(args.lunch_window),
            )

        except _ReturnToMenu:
            return
        except (OSError, ValueError) as error:
            parser.error(str(error))

        print()
        print(f"Course: {table.course_code}")
        print(f"Parsed sections: {len(table.sessions)}")
        print(f"Scheduled sections: {len(table.scheduled_sessions)}")
        print(
            "Ignored unscheduled sections: "
            f"{len(table.sessions) - len(table.scheduled_sessions)}"
        )
        print(f"Candidate complete bundles: {len(candidates)}")
        print(f"Bundles fitting weekly timetable: {len(fitting)}")
        preferred_days = {
            day.capitalize() for day in (args.prefer_days or [])
        }
        avoided_days = {
            day.capitalize() for day in (args.avoid_days or [])
        }
        if (
            preferred_days
            or avoided_days
            or args.lunch
            or args.min_gap
            or args.earliest
            or args.latest
        ):
            print()
            if preferred_days:
                _print_purple(
                    "Current prefer days: "
                    + ", ".join(sorted(preferred_days))
                )
            if avoided_days:
                _print_purple(
                    "Current avoid days: "
                    + ", ".join(sorted(avoided_days))
                )
            if args.lunch:
                _print_purple(
                    f"Current lunch: {args.lunch} minutes between "
                    f"{args.lunch_window[0]} and {args.lunch_window[1]}"
                )
            if args.min_gap:
                _print_purple(
                    f"Current minimum gap: {args.min_gap} minutes"
                )
            if args.earliest or args.latest:
                _print_purple(
                    "Current class time limits: "
                    f"{args.earliest or 'any start'} to "
                    f"{args.latest or 'any end'}"
                )
        if unavailable_sections:
            print(
                "Unavailable sections excluded: "
                + ", ".join(sorted(unavailable_sections))
            )
        print()
        _print_blue(f"Pasted course credits: {pasted_course_credits}")
        if unknown_aims_courses:
            missing_codes = ", ".join(unknown_aims_courses)
            print(
                "AIMS timetable credits: incomplete "
                f"(known subtotal {aims_credits}; missing: "
                f"{missing_codes})"
            )
            print(
                "Combined total if added: incomplete "
                f"(known subtotal "
                f"{aims_credits + pasted_course_credits}; "
                f"missing: {missing_codes})"
            )
            if (
                args.min_credits is not None
                or args.max_credits is not None
            ):
                _print_red(
                    "Warning: credit limits could not be checked because "
                    "some AIMS course credits are missing."
                )
        else:
            combined_credits = aims_credits + pasted_course_credits
            _print_blue(f"AIMS timetable credits: {aims_credits}")
            _print_blue(
                f"Combined total if added: {combined_credits}"
            )
            if (
                args.min_credits is not None
                and combined_credits < args.min_credits
            ):
                _print_red(
                    f"Warning: combined credits ({combined_credits}) are "
                    f"below the minimum ({args.min_credits})."
                )
            if (
                args.max_credits is not None
                and combined_credits > args.max_credits
            ):
                _print_red(
                    f"Warning: combined credits ({combined_credits}) exceed "
                    f"the maximum ({args.max_credits})."
                )

        fitting_set = set(fitting)
        rejected_bundles = [
            bundle
            for bundle in candidates
            if bundle not in fitting_set
        ]
        rejected = [
            (
                bundle,
                registration_bundle_conflicts(
                    table,
                    bundle,
                    base_sessions,
                    avoid_days=args.avoid_days,
                    unavailable_sections=unavailable_sections,
                    min_gap=args.min_gap,
                    earliest_start=args.earliest,
                    latest_end=args.latest,
                    lunch_minutes=args.lunch,
                    lunch_window=tuple(args.lunch_window),
                ),
            )
            for bundle in rejected_bundles
        ]
        rejected.sort(
            key=lambda item: not (
                len(item[1]) == 1
                and item[1][0].startswith("Uses avoided day(s):")
            )
        )

        print()
        by_section = {
            session.section: session
            for session in table.scheduled_sessions
        }
        if not candidates:
            _print_red(
                "No complete scheduled bundle was generated. "
                "Check the pasted table and section-family rules."
            )
        elif not fitting:
            no_fit_for_basic_settings = bool(rejected) and all(
                reasons
                and all(_is_basic_setting_conflict(reason) for reason in reasons)
                for _, reasons in rejected
            )
            message = (
                "No complete bundle fits: each has an internal overlap, "
                "overlaps the base timetable, fails a time, gap or lunch "
                "requirement, lacks sufficient travel time, or uses an "
                "avoided day."
            )
            if no_fit_for_basic_settings:
                _print_purple(message)
            else:
                _print_red(message)
        else:
            _print_green("Suggested bundles:")
            for number, bundle in enumerate(fitting, start=1):
                preferred_count = bundle_preferred_day_count(
                    table,
                    bundle,
                    args.prefer_days,
                )
                print()
                bundle_label = f"{number}. {' + '.join(bundle)}"
                if preferred_count:
                    print(
                        _colorize(bundle_label, "32")
                        + " "
                        + _colorize("(match with prefer days)", "95")
                    )
                else:
                    _print_green(bundle_label)

                for section in bundle:
                    session = by_section[section]
                    session_label = (
                        f"   CRN {session.crn}: {session.section} "
                        f"{session.day} "
                        f"{session.start_time}-{session.end_time}"
                    )
                    day_name = DAY_NAMES.get(session.day or "")
                    if day_name in preferred_days:
                        _print_purple(session_label)
                    else:
                        _print_green(session_label)

        if rejected:
            _print_red("\nRejected bundles:")

            for number, (bundle, reasons) in enumerate(rejected, start=1):
                has_avoided_day = any(
                    reason.startswith("Uses avoided day(s):")
                    for reason in reasons
                )
                if has_avoided_day:
                    bundle_label = _colorize(
                        f"{number}. {' + '.join(bundle)}",
                        "31",
                    )
                    print(
                        f"\n{bundle_label} "
                        f"{_colorize('(crash with avoid days)', '95')}"
                    )
                    for section in bundle:
                        session = by_section[section]
                        session_label = (
                            f"   CRN {session.crn}: {session.section} "
                            f"{session.day} "
                            f"{session.start_time}-{session.end_time}"
                        )
                        if DAY_NAMES.get(session.day or "") in avoided_days:
                            _print_purple(session_label)
                        else:
                            _print_red(session_label)
                else:
                    bundle_label = f"\n{number}. {' + '.join(bundle)}"
                    if reasons and all(
                        _is_basic_setting_conflict(reason)
                        for reason in reasons
                    ):
                        _print_purple(bundle_label)
                    else:
                        _print_red(bundle_label)

                for reason in reasons:
                    if _is_basic_setting_conflict(reason):
                        _print_purple(f"   - {reason}")
                    else:
                        _print_red(f"   - {reason}")

        print()
        print(
            "Weekly time-fit and travel between known buildings only. "
            "Eligibility, seat availability, date ranges, and multiple "
            "meeting rows are not validated."
        )
        return

    if args.ge_info:
        course_code = args.ge_info.strip().upper()

        try:
            with SECTION_DATA_PATH.open(
                "r",
                encoding="utf-8-sig",
            ) as file:
                section_records = json.load(file)

            if not isinstance(section_records, list):
                raise ValueError(
                    "The GE section file must contain a JSON list."
                )

            if not all(
                isinstance(record, dict)
                for record in section_records
            ):
                raise ValueError(
                    "Every GE section record must be a JSON object."
                )

        except FileNotFoundError:
            section_records = []
        except (OSError, ValueError) as error:
            parser.error(
                f"Could not read GE section information: {error}"
            )

        matching_sections = [
            record
            for record in section_records
            if str(record.get("course_code") or "")
            .strip()
            .upper() == course_code
        ]

        if not matching_sections:
            try:
                merge_ge_course_information_from_web(
                    [course_code],
                    output_path=SECTION_DATA_PATH,
                )
            except ValueError as error:
                if (
                    "No recognizable Course Section table found"
                    in str(error)
                    or "no section rows were extracted"
                    in str(error)
                ):
                    print(
                        f"No published section information is "
                        f"available for '{course_code}'. CityU may "
                        "not currently offer sections for this course."
                    )
                    return

                parser.error(
                    f"Could not update section information for "
                    f"{course_code}: {error}"
                )
            except (OSError, RuntimeError) as error:
                parser.error(
                    f"Could not update section information for "
                    f"{course_code}: {error}"
                )

            try:
                with SECTION_DATA_PATH.open(
                    "r",
                    encoding="utf-8-sig",
                ) as file:
                    section_records = json.load(file)
            except (OSError, ValueError) as error:
                parser.error(
                    f"Could not read GE section information: {error}"
                )

            matching_sections = [
                record
                for record in section_records
                if str(record.get("course_code") or "")
                .strip()
                .upper() == course_code
            ]

        if not matching_sections:
            print(
                f"No section information found for '{course_code}'."
            )
            return

        print(
            f"\n{course_code}\n"
            f"Found {len(matching_sections)} "
            "section meeting record(s).\n"
        )

        section_fields = (
            ("crn", "CRN"),
            ("section", "Section"),
            ("term", "Term"),
            ("capacity", "Capacity"),
            ("day", "Day"),
            ("time", "Time"),
            ("type", "Type"),
            ("building", "Building"),
            ("room", "Room"),
            ("instructor", "Instructor"),
        )

        for number, record in enumerate(
            matching_sections,
            start=1,
        ):
            print(f"Meeting {number}")

            for field, label in section_fields:
                value = record.get(field)

                if value is None:
                    text = "Not specified"
                elif isinstance(value, list):
                    text = (
                        ", ".join(str(item) for item in value)
                        or "Not specified"
                    )
                else:
                    text = str(value).strip() or "Not specified"

                print(f"  {label}: {text}")

            print()

        return

    if args.ge_search:
        results = search_ge_courses(args.ge_search)

        unique_courses = {}

        for course in results:
            course_code = course["course_code"].strip().upper()
            unique_courses.setdefault(course_code, course)

        results = list(unique_courses.values())

        if not results:
            print(
                f"No Gateway Education courses found for "
                f"'{args.ge_search}'."
            )
            return

        print(
            f"Found {len(results)} Gateway Education course(s) "
            f"for '{args.ge_search}':\n"
        )

        for course in results:
            area_name = course.get("area_name", "")
            area_text = course.get("area", "")

            if area_name:
                area_text = f"{area_text} — {area_name}"

            print(
                f"{course['course_code']} — {course['course_title']}\n"
                f"Area: {area_text}\n"
                f"Offering unit: {course.get('offering_unit', '')}\n"
                f"Level: {course.get('level', '')}\n"
                f"Available in: {', '.join(course.get('terms', [])) or 'Not specified'}\n"
                f"Cross-institutional: {'Yes' if course.get('cross_institutional') else 'No'}\n"
                f"Partner institutions: {', '.join(course.get('partner_institutions', [])) or 'None'}\n"
                f"With exam: {'Yes' if course.get('with_exam') else 'No'}\n"
            )

        return

    if args.csv_file and args.aims_html:
        parser.error("Choose either a CSV file or --aims-html, not both.")

    if args.courses or args.timetable_catalog or args.add_ge:
        _run_course_planner(args, parser)
        return

    if not args.aims_html:
        parser.print_help()
        return
    try:
        sessions = load_aims_html(args.aims_html)
        print(
            "AIMS import: only scheduled grid classes are included. "
            "Sections without dates/times are not included."
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    conflicts = find_conflicts(sessions)

    print(format_timetable(sessions))
    print(f"\nLoaded {len(sessions)} class sessions.")
    print(f"Found {len(conflicts)} clash(es).")

    for first, second in conflicts:
        print(
            f"CLASH: {first['course_code']} {first['type']} "
            f"({first['day']} {first['start_time']}-{first['end_time']}) overlaps "
            f"{second['course_code']} {second['type']} "
            f"({second['day']} {second['start_time']}-{second['end_time']})"
        )

if __name__ == "__main__":
    main()
