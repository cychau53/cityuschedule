from pathlib import Path
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CATALOGUE_PATH = Path("data/catalogue/cs_course_requirements.json")

with CATALOGUE_PATH.open(encoding="utf-8") as file:
    courses = json.load(file)

empty_titles = [
    course["course_code"]
    for course in courses
    if not course.get("title", "").strip()
]

empty_credits = [
    course["course_code"]
    for course in courses
    if not course.get("credits", "").strip()
]

print(f"Total courses: {len(courses)}")
print(f"Empty titles: {len(empty_titles)}")
print(f"Empty credits: {len(empty_credits)}")

if empty_titles:
    print("Courses with empty titles:")
    for course_code in empty_titles:
        print(f"  {course_code}")

if empty_credits:
    print("Courses with empty credits:")
    for course_code in empty_credits:
        print(f"  {course_code}")

cs2311 = next(
    (course for course in courses if course["course_code"] == "CS2311"),
    None,
)

if cs2311:
    print("\nSample record — CS2311:")
    print(json.dumps(cs2311, indent=2, ensure_ascii=False))