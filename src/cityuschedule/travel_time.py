import json
from datetime import datetime
from pathlib import Path
from cityuschedule.gaps import find_gaps


def time(sessions: list[dict[str, str]], time_file=None) -> None:

    if len(sessions) < 2:
        return

    path = (
        Path(time_file)
        if time_file is not None
        else Path(__file__).with_name("travel_time.json")
    )

    with path.open(encoding="utf-8") as f:
        travel_times = json.load(f)

    sessions_by_day = {}

    for session in sessions:
        sessions_by_day.setdefault(session["day"], []).append(session)

    for day, day_sessions in sessions_by_day.items():
        ordered_sessions = sorted(day_sessions, key=lambda session: datetime.strptime(session["start_time"], "%H:%M"),)

        for first, second in zip(ordered_sessions, ordered_sessions[1:]):

            if second['start_time'] < first['end_time']:
                raise ValueError(
                    f"{day}: sessions overlap. "
                    f"{first['course_code']} ends at "
                    f"{first['end_time']}, but "
                    f"{second['course_code']} starts at "
                    f"{second['start_time']}."
                )

            gap_list = find_gaps([first, second], minimum_minutes=0)
            if not gap_list:
                continue
            minutes = int(gap_list[0]["minutes"])

            start_building = first["building"]
            end_building = second["building"]

            for building in (start_building, end_building):
                if building not in travel_times:
                    raise ValueError(
                        f"Unknown building {building!r}: "
                        "not found in time.json"
                    )

            if start_building == end_building:
                required = 0
            else:
                try:
                    required = travel_times[start_building][end_building]
                except KeyError as exc:
                    raise ValueError(
                        f"No travel time from {start_building} "
                        f"to {end_building}"
                    ) from exc

            if required > minutes:
                raise ValueError(
                    f"{day}: cannot travel from "
                    f"{first['course_code']} ({start_building}) "
                    f"to {second['course_code']} ({end_building}). "
                    f"Requires {required} minutes, "
                    f"but only {minutes} minutes are available."
                )
