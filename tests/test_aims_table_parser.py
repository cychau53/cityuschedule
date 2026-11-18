from cityuschedule.aims_table_parser import parse_aims_table


SAMPLE = """
GE1401
CRNSectionCreditCampusWEBLevelAvailCapWaitlist
AvailDateDayTimeBldgRoomInstructorMedium of
Instruction
10767
A01
0
Main Campus
N
B
200
200
N
English
Section for administrative use only.
10253
T01
3
Main Campus
Y
B
25
25
N
11/01/2027 - 17/04/2027
F
09:00 - 11:50
LI
2409
DENG Haojie
English
"""


def test_parse_course_code_and_scheduled_session():
    table = parse_aims_table(SAMPLE)

    assert table.course_code == "GE1401"
    assert len(table.sessions) == 2

    admin = table.sessions[0]
    assert admin.section == "A01"
    assert admin.credit == 0
    assert not admin.is_scheduled

    tutorial = table.sessions[1]
    assert tutorial.crn == "10253"
    assert tutorial.section == "T01"
    assert tutorial.credit == 3
    assert tutorial.day == "F"
    assert tutorial.start_time == "09:00"
    assert tutorial.end_time == "11:50"
    assert tutorial.building == "LI"
    assert tutorial.is_scheduled
    assert table.course_credit == 3

def test_parse_c_and_t_course():
    sample = """
EXAMPLE1001
CRNSectionCreditCampusWEBLevelAvailCapWaitlist
AvailDateDayTimeBldgRoomInstructorMedium of
Instruction
13401
C01
3
Main Campus
Y
B
150
150
N
11/01/2027 - 17/04/2027
W
12:00 - 13:50
BOC
LT401
ZHONG Yiming, WONG Sung Ching Sam
English
13402
T01
0
Main Campus
Y
B
150
150
N
11/01/2027 - 17/04/2027
W
14:00 - 14:50
BOC
LT401
WONG Sung Ching Sam
English
"""

    table = parse_aims_table(sample)

    assert table.course_code == "EXAMPLE1001"
    assert len(table.sessions) == 2
    assert [session.section for session in table.sessions] == ["C01", "T01"]
    assert [session.activity_type for session in table.sessions] == ["C", "T"]
    assert all(session.is_scheduled for session in table.sessions)

def test_parse_grouped_c_l_course():
    sample = """
GE1354
CRNSectionCreditCampusWEBLevelAvailCapWaitlist
AvailDateDayTimeBldgRoomInstructorMedium of
Instruction
11485
CA1
3
Main Campus
Y
B
17
21
N
11/01/2027 - 17/04/2027
R
09:00 - 11:50
BOC
LT401
LI Kerui
English
11487
LA1
0
Main Campus
Y
B
3
7
N
11/01/2027 - 17/04/2027
M
15:00 - 16:50
YEUNG
G7610
LI Kerui
English
11488
LB1
0
Main Campus
Y
B
5
5
N
11/01/2027 - 17/04/2027
M
15:00 - 16:50
YEUNG
G7610
LI Kerui
English
"""

    table = parse_aims_table(sample)

    assert table.course_code == "GE1354"
    assert [session.section for session in table.sessions] == ["CA1", "LA1", "LB1"]
    assert [session.activity_type for session in table.sessions] == ["C", "L", "L"]
    assert all(session.is_scheduled for session in table.sessions)

def test_detect_registration_groups():
    sample = """
GE1354
CRNSectionCreditCampusWEBLevelAvailCapWaitlist
AvailDateDayTimeBldgRoomInstructorMedium of
Instruction
11485
CA1
3
Main Campus
Y
B
17
21
N
11/01/2027 - 17/04/2027
R
09:00 - 11:50
BOC
LT401
LI Kerui
English
11487
LA1
0
Main Campus
Y
B
3
7
N
11/01/2027 - 17/04/2027
M
15:00 - 16:50
YEUNG
G7610
LI Kerui
English
11488
LB1
0
Main Campus
Y
B
5
5
N
11/01/2027 - 17/04/2027
M
15:00 - 16:50
YEUNG
G7610
LI Kerui
English
"""

    table = parse_aims_table(sample)

    assert table.registration_groups() == {
        "A": ("CA1", "LA1"),
        "B": ("LB1",),
    }

def test_generate_complete_registration_bundles():
    sample = """
GE1354
CRNSectionCreditCampusWEBLevelAvailCapWaitlist
AvailDateDayTimeBldgRoomInstructorMedium of
Instruction
11485
CA1
3
Main Campus
Y
B
17
21
N
11/01/2027 - 17/04/2027
R
09:00 - 11:50
BOC
LT401
LI Kerui
English
11487
LA1
0
Main Campus
Y
B
3
7
N
11/01/2027 - 17/04/2027
M
15:00 - 16:50
YEUNG
G7610
LI Kerui
English
11488
LB1
0
Main Campus
Y
B
5
5
N
11/01/2027 - 17/04/2027
M
15:00 - 16:50
YEUNG
G7610
LI Kerui
English
"""

    table = parse_aims_table(sample)

    assert table.registration_bundles() == [
        ("CA1", "LA1"),
    ]

def test_generate_c_t_l_bundles():
    sample = """
TEST1001
CRNSectionCreditCampusWEBLevelAvailCapWaitlist
AvailDateDayTimeBldgRoomInstructorMedium of
Instruction
1001
CA1
3
Main Campus
Y
B
10
10
N
11/01/2027 - 17/04/2027
M
09:00 - 10:50
LI
1001
English
1002
TA1
0
Main Campus
Y
B
10
10
N
11/01/2027 - 17/04/2027
M
11:00 - 11:50
LI
1001
English
1003
LA1
0
Main Campus
Y
B
10
10
N
11/01/2027 - 17/04/2027
M
12:00 - 12:50
LI
1001
English
1004
C01
3
Main Campus
Y
B
10
10
N
11/01/2027 - 17/04/2027
T
09:00 - 10:50
LI
1002
English
1005
T12
0
Main Campus
Y
B
10
10
N
11/01/2027 - 17/04/2027
T
11:00 - 11:50
LI
1002
English
1006
L02
0
Main Campus
Y
B
10
10
N
11/01/2027 - 17/04/2027
T
12:00 - 12:50
LI
1002
English
"""

    table = parse_aims_table(sample)


    assert table.registration_bundles() == [
        ("C01", "L02", "T12"),
        ("CA1", "LA1", "TA1"),
    ]

def test_cs3481_registration_bundles():
    from cityuschedule.aims_table_parser import AimsSession, ParsedAimsTable

    rows = [
        ("10568", "C61", 3, "18:30", "21:20"),
        ("11475", "CP1", 3, "18:30", "21:20"),
        ("10779", "CQ1", 3, "18:30", "21:20"),
        ("10899", "T61", 0, "21:30", "22:20"),
        ("10900", "T62", 0, "15:00", "15:50"),
        ("11476", "TP2", 0, "15:00", "15:50"),
        ("10901", "TQ2", 0, "15:00", "15:50"),
    ]

    table = ParsedAimsTable(
        course_code="CS3481",
        sessions=tuple(
            AimsSession(
                course_code="CS3481",
                crn=crn,
                section=section,
                credit=credit,
                day="M",
                start_time=start,
                end_time=end,
            )
            for crn, section, credit, start, end in rows
        ),
    )

    assert table.registration_bundles() == [
        ("C61", "T61"),
        ("C61", "T62"),
        ("CP1", "TP2"),
        ("CQ1", "TQ2"),
    ]

def test_extract_course_code_from_title():
    text = SAMPLE.replace(
        "GE1401",
        "CS3481 Fundamentals of Data Science",
        1,
    )

    table = parse_aims_table(text)

    assert table.course_code == "CS3481"
    assert all(
        session.course_code == "CS3481"
        for session in table.sessions
    )


def test_normalize_spaced_course_code():
    text = SAMPLE.replace("GE1401", "GE 2301", 1)

    table = parse_aims_table(text)

    assert table.course_code == "GE2301"


def test_unscheduled_section_does_not_borrow_next_section_time():
    sample = """
GE1401
10767
A01
0
Main Campus
10253
T01
3
Main Campus
Y
B
25
25
N
11/01/2027 - 17/04/2027
F
09:00 - 11:50
LI
2409
English
"""

    table = parse_aims_table(sample)

    assert len(table.sessions) == 2

    admin, tutorial = table.sessions

    assert admin.section == "A01"
    assert admin.day is None
    assert admin.start_time is None
    assert admin.end_time is None
    assert not admin.is_scheduled

    assert tutorial.section == "T01"
    assert tutorial.day == "F"
    assert tutorial.start_time == "09:00"
    assert tutorial.end_time == "11:50"
    assert tutorial.is_scheduled