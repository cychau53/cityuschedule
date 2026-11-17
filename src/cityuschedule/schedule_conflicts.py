from dataclasses import dataclass


@dataclass(frozen=True)
class TimeSlot:
    day: str
    start: str
    end: str
    label: str


def time_to_minutes(time_text: str) -> int:
    hours, minutes = time_text.split(":")
    return int(hours) * 60 + int(minutes)


def slots_overlap(first: TimeSlot, second: TimeSlot) -> bool:
    if first.day != second.day:
        return False

    first_start = time_to_minutes(first.start)
    first_end = time_to_minutes(first.end)
    second_start = time_to_minutes(second.start)
    second_end = time_to_minutes(second.end)

    return first_start < second_end and second_start < first_end


def find_conflicts(
    existing_slots: list[TimeSlot],
    candidate_slots: list[TimeSlot],
) -> list[tuple[TimeSlot, TimeSlot]]:
    conflicts = []

    for existing in existing_slots:
        for candidate in candidate_slots:
            if slots_overlap(existing, candidate):
                conflicts.append((existing, candidate))

    return conflicts