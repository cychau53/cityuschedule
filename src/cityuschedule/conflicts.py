from itertools import combinations


def find_conflicts(sessions: list[dict[str, str]]) -> list[tuple[dict[str, str], dict[str, str]]]:
    conflicts = []

    for first, second in combinations(sessions, 2):
        if first["day"] != second["day"]:
            continue

        first_start = first["start_time"]
        first_end = first["end_time"]
        second_start = second["start_time"]
        second_end = second["end_time"]

        overlaps = first_start < second_end and second_start < first_end

        if overlaps:
            conflicts.append((first, second))

    return conflicts