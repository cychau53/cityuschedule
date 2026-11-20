import json
from itertools import pairwise
from pathlib import Path

from .schedule_conflicts import time_to_minutes


def _default_time_file() -> Path:
    path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "travel_time.json"
    )
    if not path.is_file():
        path = (
            Path(__file__).resolve().parent
            / "data"
            / "travel_time.json"
        )
    return path


def load_travel_times(time_file=None) -> dict[str, dict[str, int]]:
    """Read the walking-time matrix (minutes between campus buildings)."""
    path = Path(time_file) if time_file is not None else _default_time_file()

    with path.open(encoding="utf-8") as f:
        return json.load(f)


def walking_minutes(
    start_building: str,
    end_building: str,
    travel_times: dict[str, dict[str, int]],
) -> int | None:
    """Minutes needed to walk between two buildings, or None if unknown."""
    if start_building not in travel_times or end_building not in travel_times:
        return None

    if start_building == end_building:
        return 0

    return travel_times[start_building].get(end_building)


def time(sessions: list[dict[str, str]], time_file=None) -> None:
    if len(sessions) < 2:
        return

    travel_times = load_travel_times(time_file)

    sessions_by_day = {}

    for session in sessions:
        sessions_by_day.setdefault(session["day"], []).append(session)

    for day, day_sessions in sessions_by_day.items():
        ordered_sessions = sorted(
            day_sessions,
            key=lambda session: time_to_minutes(session["start_time"]),
        )

        for first, second in pairwise(ordered_sessions):

            if time_to_minutes(second["start_time"]) < time_to_minutes(first["end_time"]):
                raise ValueError(
                    f"{day}: sessions overlap. "
                    f"{first['course_code']} ends at "
                    f"{first['end_time']}, but "
                    f"{second['course_code']} starts at "
                    f"{second['start_time']}."
                )

            minutes = (
                time_to_minutes(second["start_time"])
                - time_to_minutes(first["end_time"])
            )

            start_building = first["building"]
            end_building = second["building"]

            for building in (start_building, end_building):
                if building not in travel_times:
                    raise ValueError(
                        f"Unknown building {building!r}: "
                        "not found in time.json"
                    )

            required = walking_minutes(
                start_building,
                end_building,
                travel_times,
            )
            if required is None:
                raise ValueError(
                    f"No travel time from {start_building} "
                    f"to {end_building}"
                )

            if required > minutes:
                raise ValueError(
                    f"{day}: cannot travel from "
                    f"{first['course_code']} ({start_building}) "
                    f"to {second['course_code']} ({end_building}). "
                    f"Requires {required} minutes, "
                    f"but only {minutes} minutes are available."
                )
