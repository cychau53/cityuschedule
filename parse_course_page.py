from pathlib import Path
import argparse
import json
import re
from html import unescape
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

parser = argparse.ArgumentParser()
parser.add_argument("html_path")
parser.add_argument("output_path")
parser.add_argument("course_code")
args = parser.parse_args()

html_path = Path(args.html_path)
output_path = Path(args.output_path)
course_code = args.course_code

html = html_path.read_text(encoding="utf-8", errors="replace")


def extract_div(field_id: str) -> str:
    pattern = re.compile(
        rf'<div\s+id="{field_id}"\s+class="formValue">(.*?)</div>',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        return ""
    text = re.sub(r"<[^>]+>", " ", match.group(1))
    return " ".join(unescape(text).split())


def extract_course_codes(field_id: str) -> list[str]:
    div = extract_div(field_id)
    return re.findall(r"\b[A-Z]{2,4}\d{4}[A-Z]?\b", div)


title = extract_div("div_course_code_and_title")

title = re.sub(
    rf"^\s*{re.escape(course_code)}\s*[-–—]\s*",
    "",
    title,
).strip()

if not title or title == course_code:
    title = ""
pdf_match = re.search(
    r'<a\s+href="([^"]+\.pdf)"[^>]*>.*?id="pdf_url"',
    html,
    re.IGNORECASE | re.DOTALL,
)

course = {
    "course_code": course_code,
    "title": title,
    "credits": extract_div("div_course_credits"),
    "department": extract_div("div_offering_dept"),
    "prerequisites": [],
    "precursors": extract_course_codes("div_precursors"),
    "equivalent_courses": extract_course_codes("div_equivalent_courses"),
    "exclusive_courses": extract_course_codes("div_exclusive_courses"),
    "offering_terms": extract_div("div_course_offering_term"),
    "course_aims": extract_div("div_course_aims"),
    "detail_pdf_url": pdf_match.group(1) if pdf_match else "",
}

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(
    json.dumps(course, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(json.dumps(course, indent=2, ensure_ascii=False))