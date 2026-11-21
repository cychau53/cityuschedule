from pathlib import Path
import json
import subprocess
import sys
import time
from urllib.request import Request, urlopen

CATALOGUE_PATH = Path("data/catalogue/cs_courses.json")
RAW_DIR = Path("data/raw")
PARSED_DIR = Path("data/catalogue/course_pages")
OUTPUT_PATH = Path("data/catalogue/cs_course_requirements.json")
BASE_COURSE_URL = "https://www.cityu.edu.hk/catalogue/ug/current/course/"
REQUEST_DELAY_SECONDS = 1.0

courses = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))

RAW_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)

for index, course in enumerate(courses, start=1):
    course_code = course["course_code"]
    html_path = RAW_DIR / f"{course_code}.html"
    json_path = PARSED_DIR / f"{course_code}.json"

    if not html_path.exists():
        url = BASE_COURSE_URL + f"{course_code}.htm"
        request = Request(
            url,
            headers={
                "User-Agent": "cityuschedule-course-catalogue-importer/1.0"
            },
        )
        with urlopen(request, timeout=30) as response:
            html_path.write_bytes(response.read())
        print(f"[{index}/{len(courses)}] Downloaded {course_code}")
        time.sleep(REQUEST_DELAY_SECONDS)
    else:
        print(f"[{index}/{len(courses)}] Already downloaded {course_code}")

    result = subprocess.run(
    [
        sys.executable,
        "parse_course_page.py",
        str(html_path),
        str(json_path),
        course_code,
    ],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)

    if result.returncode != 0:
        print(f"Failed to parse {course_code}: {result.stderr}")
        continue

all_courses = []

for json_path in sorted(PARSED_DIR.glob("*.json")):
    all_courses.append(json.loads(json_path.read_text(encoding="utf-8")))

OUTPUT_PATH.write_text(
    json.dumps(all_courses, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(f"Wrote {len(all_courses)} parsed courses to {OUTPUT_PATH}")