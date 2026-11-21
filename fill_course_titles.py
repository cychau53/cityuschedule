from pathlib import Path
import json
import re
import time
from io import BytesIO
from urllib.request import Request, urlopen
from pypdf import PdfReader

CATALOGUE_PATH = Path("data/catalogue/cs_course_requirements.json")
PDF_DIR = Path("data/raw/course_pdfs")
REQUEST_DELAY_SECONDS = 1.0

with CATALOGUE_PATH.open(encoding="utf-8") as file:
    courses = json.load(file)

PDF_DIR.mkdir(parents=True, exist_ok=True)

for index, course in enumerate(courses, start=1):
    course_code = course["course_code"]
    pdf_url = course.get("detail_pdf_url", "")

    if not pdf_url:
        print(f"[{index}/{len(courses)}] No PDF URL for {course_code}")
        continue

    pdf_path = PDF_DIR / f"{course_code}.pdf"

    if not pdf_path.exists():
        request = Request(
            pdf_url,
            headers={
                "User-Agent": "cityuschedule-course-catalogue-importer/1.0"
            },
        )
        with urlopen(request, timeout=30) as response:
            pdf_bytes = response.read()
        pdf_path.write_bytes(pdf_bytes)
        print(f"[{index}/{len(courses)}] Downloaded PDF for {course_code}")
        time.sleep(REQUEST_DELAY_SECONDS)
    else:
        pdf_bytes = pdf_path.read_bytes()
        print(f"[{index}/{len(courses)}] Using cached PDF for {course_code}")

    pdf_bytes = pdf_bytes.lstrip(b"\r\n\t ")

    if not pdf_bytes.startswith(b"%PDF-"):
        print(f"Downloaded file for {course_code} is not a valid PDF")
        continue

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        first_page_text = reader.pages[0].extract_text() or ""
    except Exception as error:
        print(f"Failed to read PDF for {course_code}: {error}")
        continue

    title_match = re.search(
        r"Course Title\s*\n\s*(.+?)\s*\n",
        first_page_text,
        re.IGNORECASE,
    )

    if title_match:
        course["title"] = " ".join(title_match.group(1).split())
    else:
        print(f"Could not find title in PDF for {course_code}")

CATALOGUE_PATH.write_text(
    json.dumps(courses, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

empty_titles = [
    course["course_code"]
    for course in courses
    if not course.get("title", "").strip()
]

print(f"Updated {len(courses) - len(empty_titles)} titles")
print(f"Remaining empty titles: {len(empty_titles)}")