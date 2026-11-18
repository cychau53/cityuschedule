import unittest

from cityuschedule.travel_time import time


def make_session(
    day: str,
    start_time: str,
    end_time: str,
    course_code: str,
):
    return {
        "course_code": course_code,
        "course_title": "Test course",
        "crn": "12345",
        "section": "A",
        "type": "LEC",
        "day": day,
        "start_time": start_time,
        "end_time": end_time,
        "building": "YEUNG",
        "room": "LT-1",
    }


class TravelTimeTests(unittest.TestCase):
    def make_pair(self, first_end, second_start, starting_point="YEUNG", end_point="LI"):
        sessions = [
            make_session("Mon", "09:00", first_end, "CS1103"),
            make_session("Mon", second_start, "13:50", "MA1200"),
        ]

        sessions[0]["building"] = starting_point
        sessions[1]["building"] = end_point

        return sessions

    def test_sufficient_time(self):
        # Available: 70 minutes; required: 7 minutes.
        sessions = self.make_pair("10:50", "12:00")

        self.assertIsNone(time(sessions))

    def test_insufficient_time(self):
        # Available: 6 minutes; required: 7 minutes.
        sessions = self.make_pair("10:50", "10:56")

        with self.assertRaisesRegex(
            ValueError,
            "Requires 7 minutes, but only 6 minutes",
        ):
            time(sessions)

    def test_exact_time(self):
        # Available: 7 minutes; required: 7 minutes.
        sessions = self.make_pair("10:50", "10:57")

        self.assertIsNone(time(sessions))

    def test_same_building(self):
        sessions = self.make_pair("10:50", "10:50")
        sessions[1]["building"] = "YEUNG"

        self.assertIsNone(time(sessions))

    def test_overlap(self):
        sessions = self.make_pair("10:50", "10:40")

        with self.assertRaisesRegex(
            ValueError,
            "Mon: sessions overlap. CS1103 ends at 10:50, but MA1200 starts at 10:40."
        ):
            time(sessions)

    def test_same_building_overlap(self):
        sessions = self.make_pair("10:50", "10:40")
        sessions[1]["building"] = "YEUNG"

        with self.assertRaisesRegex(
            ValueError,
            "Mon: sessions overlap. CS1103 ends at 10:50, but MA1200 starts at 10:40."
        ):
            time(sessions)

    def test_different_days_are_not_compared(self):
        sessions = self.make_pair("10:00", "09:00")
        sessions[1]["day"] = "Tue"

        self.assertIsNone(time(sessions))

    def test_later_transfer_is_checked(self):
        sessions = self.make_pair("10:50", "12:00")

        third = make_session(
            "Mon", "14:00", "15:00", "CS2200"
        )
        third["building"] = "CMC"
        sessions.append(third)

        # LI -> CMC requires 15 minutes; the gap is 10.
        with self.assertRaisesRegex(
            ValueError,
            "Requires 15 minutes, but only 10 minutes",
        ):
            time(sessions)

    def test_unknown_building(self):
        sessions = self.make_pair("10:50", "12:00")
        sessions[0]["building"] = "AC"

        with self.assertRaisesRegex(
            ValueError,
            "Unknown building 'AC'",
        ):
            time(sessions)

    def test_empty_sessions(self):
        self.assertIsNone(time([]))

    def test_single_session(self):
        self.assertIsNone(time(self.make_pair("10:50", "12:00")[:1]))


if __name__ == "__main__":
    unittest.main()
