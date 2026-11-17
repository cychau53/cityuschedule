from pathlib import Path
import json
import re
from urllib.parse import urljoin

INDEX_PATH = Path("data/raw/cs_course_data.html")
OUTPUT_PATH = Path("data/catalogue/cs_courses.json")
BASE_URL = "https://www.cityu.edu.hk/catalogue/ug/current/catalogue/"

html = INDEX_PATH.read_text(encoding="utf-8", errors="replace")

pattern = re.compile(
    r'<A\s+HREF="\.\./course/([^"]+\.htm)"[^>]*>\s*'
    r'([A-Z]{2,4}\d{4}[A-Z]?)\s+(.*?)\s*</A>',
    re.IGNORECASE | re.DOTALL,
)

courses = []
for match in pattern.finditer(html):
    detail_filename, course_code, title = match.groups()
    courses.append(
        {
            "course_code": course_code.strip(),
            "title": " ".join(title.split()),
            "detail_url": urljoin(BASE_URL, f"course/{detail_filename}"),
            "department": "Department of Computer Science",
        }
    )

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text(
    json.dumps(courses, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(f"Extracted {len(courses)} courses to {OUTPUT_PATH}")