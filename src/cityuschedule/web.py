"""Small local web interface for CityUSchedule."""

import colorsys
import html
import re
import secrets
import tempfile
import threading
import webbrowser
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .aims import load_aims_html
from .conflicts import find_conflicts
from .course_catalog import load_ge_section_catalog
from .ge_courses import load_ge_courses, search_ge_courses
from .plan_generator import (
    PLANNING_ONLY_NOTICE,
    PlanOptions,
    format_plan,
    generate_course_plans,
)
from .timetable import format_timetable


def _term_label(term: str) -> str | None:
    term = term.strip().upper()
    if len(term) != 5:
        return None
    year = term[:4]
    part = term[4:]
    if not year.isdigit() or part not in {"A", "B", "S"}:
        return None
    season = "Summer" if part == "S" else f"Sem {part}"
    return f"20{year[:2]}-{int(year[:2]) + 1:02d} {season}"


def _page(title: str, body: str) -> bytes:
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, sans-serif; }}
    body {{ max-width: 980px; margin: 0 auto; padding: 24px; background: #f6f8fb; color: #172033; }}
    h1 {{ margin-top: 0; }}
    nav {{ display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }}
    nav a {{ padding: 9px 12px; background: #e8eefb; border-radius: 7px; color: #172033; text-decoration: none; font-weight: 700; }}
    nav a:hover {{ background: #d8e4ff; }}
    form {{ display: grid; gap: 12px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 12px #0001; }}
    label {{ font-weight: 650; }}
    input, select {{ width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #bbc3d1; border-radius: 7px; }}
    button {{ border: 0; border-radius: 7px; padding: 11px 16px; background: #155eef; color: white; font-weight: 700; cursor: pointer; }}
    button.delete {{ background: #b42318; }}
    .error {{ background: #fff1f0; border: 1px solid #ffccc7; padding: 12px; border-radius: 8px; }}
    .notice {{ background: #eef4ff; border: 1px solid #b2c9ff; padding: 12px; border-radius: 8px; }}
    pre {{ white-space: pre-wrap; background: #fff; border: 1px solid #dde2ea; padding: 16px; border-radius: 8px; }}
    pre.course-plan {{ margin: 12px 0; }}
  </style>
</head>
<body>
  <h1>CityUSchedule</h1>
  <nav>
    <a href="/settings">Basic settings</a>
    <a href="/planner">Plan timetable</a>
    <a href="/ge-search">Search GE courses</a>
    <a href="/ge-info">GE course information</a>
    <a href="/aims">Check AIMS timetable</a>
    <a href="/saved-bundles">Saved plans &amp; bundles</a>
  </nav>
  {body}
</body>
</html>"""
    return document.encode("utf-8")


def _form() -> str:
    return """<form method="post" enctype="multipart/form-data">
  <input type="hidden" name="action" value="plan">
  <label for="term">Semester</label>
  <input id="term" name="term" placeholder="2627B" required>
  <label for="courses">Course codes (comma or space separated)</label>
  <input id="courses" name="courses" placeholder="GE1102 GE1401">
  <label for="aims">Saved AIMS timetable HTML</label>
  <input id="aims" name="aims" type="file" accept=".html,text/html">
  <label for="add_ge">Number of GE courses to add</label>
  <input id="add_ge" name="add_ge" type="number" min="1" value="1" required>
  <label for="max_results">Maximum plans</label>
  <input id="max_results" name="max_results" type="number" min="1" value="5">
  <label for="seats">Seat policy</label>
  <select id="seats" name="seats">
    <option value="waitlist">Waitlist allowed</option>
    <option value="open">Open seats only</option>
    <option value="any">Any availability</option>
  </select>
  <label><input name="no_travel" type="checkbox" value="1" style="width:auto"> Skip walking-time checks</label>
  <button type="submit">Generate timetable plans</button>
</form>
<p class="notice">This is a planning aid. Verify availability and registration requirements in AIMS.</p>"""


def _basic_settings_form() -> str:
    from .cli import _load_basic_settings

    settings = _load_basic_settings()
    return f"""<h2>Basic timetable settings</h2>
<form method="post" action="/settings">
  <input type="hidden" name="action" value="save-settings">
  <label for="prefer_days">Preferred days</label>
  <input id="prefer_days" name="prefer_days" value="{html.escape(', '.join(settings.prefer_days))}" placeholder="Mon, Tue">
  <label for="avoid_days">Days to avoid</label>
  <input id="avoid_days" name="avoid_days" value="{html.escape(', '.join(settings.avoid_days))}" placeholder="Fri">
  <label for="min_credits">Minimum credits (optional)</label>
  <input id="min_credits" name="min_credits" type="number" min="0" value="{'' if settings.min_credits is None else settings.min_credits}">
  <label for="max_credits">Maximum credits (optional)</label>
  <input id="max_credits" name="max_credits" type="number" min="0" value="{'' if settings.max_credits is None else settings.max_credits}">
  <label for="earliest_start">Earliest class start (optional)</label>
  <input id="earliest_start" name="earliest_start" value="{html.escape(settings.earliest_start or '')}" placeholder="09:00">
  <label for="latest_end">Latest class end (optional)</label>
  <input id="latest_end" name="latest_end" value="{html.escape(settings.latest_end or '')}" placeholder="18:00">
  <label for="min_gap">Minimum gap between classes (minutes)</label>
  <input id="min_gap" name="min_gap" type="number" min="0" value="{settings.min_gap}">
  <label for="lunch_minutes">Lunch break needed (minutes)</label>
  <input id="lunch_minutes" name="lunch_minutes" type="number" min="0" value="{settings.lunch_minutes}">
  <label for="lunch_start">Lunch window start</label>
  <input id="lunch_start" name="lunch_start" value="{html.escape(settings.lunch_window[0])}" placeholder="11:30">
  <label for="lunch_end">Lunch window end</label>
  <input id="lunch_end" name="lunch_end" value="{html.escape(settings.lunch_window[1])}" placeholder="14:30">
  <button type="submit">Save basic settings</button>
</form>
<p class="notice">Saved settings are used when generating plans and are shared with the command-line app.</p>"""


def _save_basic_settings(fields: dict[str, str]) -> str:
    from .cli import (
        BasicSettings,
        _parse_clock_time,
        _parse_day_list,
        _parse_lunch_window,
        _validate_lunch_duration,
    )
    from .cli import _save_basic_settings as save_settings

    prefer_days = _parse_day_list(fields.get("prefer_days", ""))
    avoid_days = _parse_day_list(fields.get("avoid_days", ""))
    if set(prefer_days) & set(avoid_days):
        raise ValueError("A day cannot be both preferred and avoided.")

    def optional_credits(field: str) -> int | None:
        value = fields.get(field, "").strip()
        if not value:
            return None
        try:
            credits = int(value)
        except ValueError:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be a non-negative integer.") from None
        if credits < 0:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be a non-negative integer.")
        return credits

    def nonnegative_minutes(field: str) -> int:
        value = fields.get(field, "").strip() or "0"
        try:
            minutes = int(value)
        except ValueError:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be a non-negative integer.") from None
        if minutes < 0:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} must be a non-negative integer.")
        return minutes

    min_credits = optional_credits("min_credits")
    max_credits = optional_credits("max_credits")
    if (
        min_credits is not None
        and max_credits is not None
        and min_credits > max_credits
    ):
        raise ValueError("Minimum credits cannot exceed maximum credits.")

    lunch_minutes = nonnegative_minutes("lunch_minutes")
    lunch_window = _parse_lunch_window(
        f"{fields.get('lunch_start', '11:30') or '11:30'}-"
        f"{fields.get('lunch_end', '14:30') or '14:30'}"
    )
    _validate_lunch_duration(lunch_minutes, lunch_window)

    earliest = fields.get("earliest_start", "").strip()
    latest = fields.get("latest_end", "").strip()
    earliest_start = (
        _parse_clock_time(earliest, "Earliest class start")
        if earliest else None
    )
    latest_end = (
        _parse_clock_time(latest, "Latest class end", allow_24=True)
        if latest else None
    )
    if (
        earliest_start is not None
        and latest_end is not None
        and earliest_start > latest_end
    ):
        raise ValueError("Earliest class start cannot be later than latest class end.")

    settings = BasicSettings(
        prefer_days=prefer_days,
        avoid_days=avoid_days,
        min_credits=min_credits,
        max_credits=max_credits,
        lunch_minutes=lunch_minutes,
        lunch_window=lunch_window,
        min_gap=nonnegative_minutes("min_gap"),
        earliest_start=earliest_start,
        latest_end=latest_end,
    )
    save_settings(settings)
    return "Basic settings saved."


def _saved_bundles_link() -> str:
    return '<p><a href="/saved-bundles">View saved plans and course bundles</a></p>'


def _save_plan_form(token: str, plans: list[dict]) -> str:
    choices = "\n".join(
        f'<label><input type="checkbox" name="plan_{index}" value="1" '
        f'style="width:auto"> Save Plan {index}</label>'
        for index in range(1, len(plans) + 1)
    )
    return f"""<form method="post" action="/save-plans">
  <input type="hidden" name="action" value="save-plans">
  <input type="hidden" name="plan_token" value="{html.escape(token)}">
  <h2>Save plans</h2>
  {choices}
  <button type="submit">Save selected plans</button>
</form>"""


def _delete_saved_timetable_plan(number_value: str) -> str:
    from .cli import _load_saved_bundles, _save_bundles_to_disk

    try:
        number = int(number_value)
    except ValueError:
        raise ValueError("Choose a valid saved plan number.") from None

    saved_plans = _load_saved_bundles()
    if not saved_plans:
        raise ValueError("No saved plans were found.")
    if not 1 <= number <= len(saved_plans):
        raise ValueError(f"Plan number must be from 1 to {len(saved_plans)}.")

    del saved_plans[number - 1]
    _save_bundles_to_disk(saved_plans)
    return f"Deleted Plan {number}."


def _saved_bundles_page(notice: str | None = None) -> str:
    from .cli import (
        _format_saved_plan,
        _load_saved_bundles,
        _load_saved_course_bundles,
        _saved_plan_data,
    )

    saved_plans = _load_saved_bundles()
    saved_course_bundles = _load_saved_course_bundles()
    sections = []
    if notice:
        sections.append(f'<p class="notice">{html.escape(notice)}</p>')
    sections.append("<h2>Saved timetable plans</h2>")
    if saved_plans:
        sections.append(f"<p>Found {len(saved_plans)} saved plan(s).</p>")
        for index, entry in enumerate(saved_plans, start=1):
            plan = _saved_plan_data(entry)
            sections.append(
                f"<pre>{html.escape(_format_saved_plan(plan, index))}</pre>"
            )
            sections.append(
                '<form method="post" action="/delete-plan" '
                f'onsubmit="return confirm(\'Delete Plan {index}?\');">'
                '<input type="hidden" name="action" value="delete-plan">'
                f'<input type="hidden" name="plan_number" value="{index}">'
                f'<button class="delete" type="submit">Delete Plan {index}</button>'
                "</form>"
            )
    else:
        sections.append("<p>No saved timetable plans.</p>")

    sections.append("<h2>Saved course bundles</h2>")
    if saved_course_bundles:
        sections.append(f"<p>Found {len(saved_course_bundles)} saved course bundle(s).</p>")
        for bundle in saved_course_bundles:
            course_code = str(bundle.get("course_code") or "Unknown")
            lines = [course_code]
            for section in bundle.get("sections", []):
                if not isinstance(section, dict):
                    continue
                lines.append(
                    "  "
                    + " ".join(
                        value for value in (
                            str(section.get("section") or ""),
                            f"CRN {section.get('crn')}" if section.get("crn") else "",
                            str(section.get("day") or ""),
                            (
                                f"{section.get('start_time', '')}-"
                                f"{section.get('end_time', '')}"
                            ).strip("-"),
                        )
                        if value
                    )
                )
            sections.append(f"<pre>{html.escape(chr(10).join(lines))}</pre>")
    else:
        sections.append("<p>No saved course bundles.</p>")
    return "\n".join(sections)


def _ge_search_form(keyword: str = "") -> str:
    return f"""<h2>Search Gateway Education courses</h2>
<form method="post" enctype="application/x-www-form-urlencoded">
  <input type="hidden" name="action" value="ge-search">
  <label for="keyword">Course code, title, area, offering unit, or filter</label>
  <input id="keyword" name="keyword" value="{html.escape(keyword)}" placeholder="GE1102 or management">
  <button type="submit">Search</button>
</form>"""


def _ge_info_form(course_code: str = "") -> str:
    return f"""<h2>Gateway Education course information</h2>
<form method="post" enctype="application/x-www-form-urlencoded">
  <input type="hidden" name="action" value="ge-info">
  <label for="course_code">Course code</label>
  <input id="course_code" name="course_code" value="{html.escape(course_code)}" placeholder="GE1102">
  <button type="submit">Show course</button>
</form>"""


def _aims_form() -> str:
    return """<h2>Check an AIMS timetable</h2>
<form method="post" enctype="multipart/form-data">
  <input type="hidden" name="action" value="aims-check">
  <label for="aims">Saved AIMS timetable HTML</label>
  <input id="aims" name="aims" type="file" accept=".html,text/html" required>
  <button type="submit">Check timetable</button>
</form>"""


def _generate(
    fields: dict[str, str],
    upload: bytes | None,
    plan_cache: dict[str, list[dict]],
    plan_cache_lock: threading.Lock,
) -> tuple[str, str | None, str]:
    term = fields.get("term", "").strip().upper()
    if len(term) != 5:
        raise ValueError("Enter a valid semester, for example 2627B.")

    wanted = []
    for item in fields.get("courses", "").replace(",", " ").upper().split():
        if item and item not in wanted:
            wanted.append(item)
    add_ge = int(fields.get("add_ge", "1") or "1")
    max_results = int(fields.get("max_results", "5") or "5")
    if add_ge < 1:
        raise ValueError("The GE course count must be at least 1.")
    if max_results < 1:
        raise ValueError("Maximum plans must be at least 1.")

    ge_term = _term_label(term)
    courses = load_ge_section_catalog(term=ge_term)
    if wanted:
        keep = set(wanted)
        courses = [course for course in courses if course.code.upper() in keep]
        found = {course.code.upper() for course in courses}
        missing = sorted(keep - found)
        if missing:
            raise ValueError("No section details are available for: " + ", ".join(missing))
    if not courses and not add_ge:
        raise ValueError(f"Currently, we don't have data for {term}.")

    fixed_sessions = []
    if upload:
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as temporary:
            temporary.write(upload)
            temporary_path = temporary.name
        try:
            fixed_sessions = load_aims_html(temporary_path)
        finally:
            Path(temporary_path).unlink(missing_ok=True)

    from .cli import _load_basic_settings

    basic_settings = _load_basic_settings()
    options = PlanOptions(
        ge_courses=add_ge,
        max_results=max_results,
        check_travel=fields.get("no_travel") != "1",
        seat_policy=fields.get("seats", "waitlist"),
        term=term,
        min_credits=basic_settings.min_credits,
        max_credits=basic_settings.max_credits,
        preferred_days=basic_settings.prefer_days,
        avoid_days=basic_settings.avoid_days,
        earliest_start=basic_settings.earliest_start,
        latest_end=basic_settings.latest_end,
        min_gap=basic_settings.min_gap,
        lunch_minutes=basic_settings.lunch_minutes,
        lunch_window=basic_settings.lunch_window,
    )
    report = generate_course_plans(
        courses,
        options,
        fixed_sessions=fixed_sessions,
    )

    pieces = []
    fit_lines = report.fit_summary()
    if fit_lines:
        pieces.append("Timeslots that fit your timetable:\n" + "\n".join(fit_lines))
    token = None
    plans_html = ""
    if not report.plans:
        pieces.append("No course plans matched the selected options.")
    else:
        pieces.append(f"Found {len(report.plans)} course plan(s):")
        plans_html = _format_plans_html(report.plans)
        token = secrets.token_urlsafe(24)
        with plan_cache_lock:
            plan_cache[token] = [plan.to_dict() for plan in report.plans]
            while len(plan_cache) > 64:
                del plan_cache[next(iter(plan_cache))]
    pieces.append(PLANNING_ONLY_NOTICE)
    return "\n\n".join(pieces), token, plans_html


def _format_plans_html(plans) -> str:
    rendered = []
    for number, plan in enumerate(plans, start=1):
        added_codes = list(dict.fromkeys(
            option.course_code
            for option in plan.chosen
            if not option.preregistered
        ))
        colors = {}
        if len(added_codes) == 1:
            colors[added_codes[0].upper()] = "#008000"
        elif len(added_codes) > 1:
            for index, code in enumerate(added_codes):
                hue = 0.5 + 0.13 * index / (len(added_codes) - 1)
                rgb = colorsys.hsv_to_rgb(hue, 0.88, 0.95)
                colors[code.upper()] = "rgb(" + ", ".join(
                    str(round(channel * 255)) for channel in rgb
                ) + ")"

        lines = []
        for line in format_plan(plan, number, steps=True).splitlines():
            course_color = next(
                (
                    color
                    for code, color in colors.items()
                    if re.search(
                        rf"(?<![A-Z0-9]){re.escape(code)}(?![A-Z0-9])",
                        line,
                        re.IGNORECASE,
                    )
                ),
                None,
            )
            escaped_line = html.escape(line)
            if course_color:
                escaped_line = (
                    f'<span style="color: {course_color}">{escaped_line}</span>'
                )
            lines.append(escaped_line)
        lines_text = "\n".join(lines)
        rendered.append(f'<pre class="course-plan">{lines_text}</pre>')
    return "\n".join(rendered)


def _save_selected_plans(
    fields: dict[str, str],
    plan_cache: dict[str, list[dict]],
    plan_cache_lock: threading.Lock,
) -> str:
    from .cli import (
        _load_saved_bundles,
        _save_bundles_to_disk,
        _saved_plan_data,
        _saved_plan_signature,
    )

    token = fields.get("plan_token", "")
    with plan_cache_lock:
        plans = plan_cache.get(token)
    if not plans:
        raise ValueError("These generated plans are no longer available. Generate them again.")

    selected = []
    for key, value in fields.items():
        if not key.startswith("plan_") or value != "1":
            continue
        try:
            index = int(key.removeprefix("plan_")) - 1
        except ValueError:
            continue
        if 0 <= index < len(plans):
            selected.append(index)
    if not selected:
        raise ValueError("Select at least one plan to save.")

    saved = _load_saved_bundles()
    signatures = {
        _saved_plan_signature(_saved_plan_data(entry))
        for entry in saved
    }
    new_entries = []
    already_saved = 0
    for index in dict.fromkeys(selected):
        plan = plans[index]
        signature = _saved_plan_signature(plan)
        if signature in signatures:
            already_saved += 1
            continue
        signatures.add(signature)
        new_entries.append({"plan": plan})
    if new_entries:
        _save_bundles_to_disk(saved + new_entries)
    message = f"Saved {len(new_entries)} plan(s)."
    if already_saved:
        message += f" {already_saved} selected plan(s) were already saved."
    return message


def _search_ge(keyword: str) -> str:
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("Enter a keyword to search.")
    results = search_ge_courses(keyword)
    if not results:
        return f"No Gateway Education courses found for '{keyword}'."

    unique: dict[str, dict] = {}
    for course in results:
        unique.setdefault(str(course.get("course_code") or "").upper(), course)

    lines = [f"Found {len(unique)} Gateway Education course(s):"]
    for course in unique.values():
        area = str(course.get("area_name") or course.get("area") or "Not specified")
        lines.extend([
            "",
            f"{course.get('course_code')} - {course.get('course_title')}",
            f"Area: {area}",
            f"Offering unit: {course.get('offering_unit') or 'Not specified'}",
            f"Level: {course.get('level') or 'Not specified'}",
            f"Terms: {', '.join(course.get('terms') or []) or 'Not specified'}",
            f"Cross-institutional: {'Yes' if course.get('cross_institutional') else 'No'}",
            f"With exam: {'Yes' if course.get('with_exam') else 'No'}",
        ])
    return "\n".join(lines)


def _get_ge_info(course_code: str) -> str:
    course_code = course_code.strip().upper()
    if not course_code:
        raise ValueError("Enter a course code.")
    course_records = [
        course for course in load_ge_courses()
        if str(course.get("course_code") or "").strip().upper() == course_code
    ]
    if not course_records:
        return f"No information found for '{course_code}'."
    course = course_records[0]
    lines = [
        f"{course_code} - {course.get('course_title') or 'No title'}",
        f"Area: {course.get('area_name') or course.get('area') or 'Not specified'}",
        f"Offering unit: {course.get('offering_unit') or 'Not specified'}",
        f"Level: {course.get('level') or 'Not specified'}",
        f"Terms: {', '.join(course.get('terms') or []) or 'Not specified'}",
        f"Cross-institutional: {'Yes' if course.get('cross_institutional') else 'No'}",
        f"Partner institutions: {', '.join(course.get('partner_institutions') or []) or 'None'}",
        f"With exam: {'Yes' if course.get('with_exam') else 'No'}",
    ]
    section_fields = (
        ("crn", "CRN"),
        ("section", "Section"),
        ("term", "Term"),
        ("capacity", "Capacity"),
        ("day", "Day"),
        ("time", "Time"),
        ("type", "Type"),
        ("building", "Building"),
        ("room", "Room"),
        ("instructor", "Instructor"),
    )
    sections = [record for record in course_records if record.get("section")]
    meeting_type_order = {"lecture": 0, "tutorial": 1, "laboratory": 2}
    sections.sort(
        key=lambda record: meeting_type_order.get(
            str(record.get("type") or "").strip().casefold(),
            len(meeting_type_order),
        )
    )
    if sections:
        lines.extend([
            "",
            f"Found {len(sections)} section meeting record(s).",
            "",
            "Section information:",
        ])
        meeting_numbers: dict[str, int] = {}
        for record in sections:
            raw_type = record.get("type")
            meeting_type = (
                " ".join(raw_type.split())
                if isinstance(raw_type, str) and raw_type.strip()
                else "Meeting"
            )
            type_key = meeting_type.casefold()
            meeting_numbers[type_key] = meeting_numbers.get(type_key, 0) + 1
            lines.append(f"{meeting_type} {meeting_numbers[type_key]}")
            for field, label in section_fields:
                value = record.get(field)
                if value is None:
                    text = "Not specified"
                elif isinstance(value, list):
                    text = ", ".join(str(item) for item in value) or "Not specified"
                else:
                    text = str(value).strip() or "Not specified"
                lines.append(f"  {label}: {text}")
            lines.append("")
    else:
        lines.extend(["", "Section information: Not specified"])
    return "\n".join(lines)


def _check_aims(upload: bytes | None) -> str:
    if not upload:
        raise ValueError("Choose a saved AIMS HTML file.")
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as temporary:
        temporary.write(upload)
        temporary_path = temporary.name
    try:
        sessions = load_aims_html(temporary_path)
    finally:
        Path(temporary_path).unlink(missing_ok=True)
    conflicts = find_conflicts(sessions)
    lines = [
        format_timetable(sessions),
        "",
        f"Loaded {len(sessions)} class sessions.",
        f"Found {len(conflicts)} clash(es).",
    ]
    for first, second in conflicts:
        lines.append(
            f"CLASH: {first['course_code']} {first['type']} "
            f"({first['day']} {first['start_time']}-{first['end_time']}) overlaps "
            f"{second['course_code']} {second['type']} "
            f"({second['day']} {second['start_time']}-{second['end_time']})"
        )
    return "\n".join(lines)


def _parse_multipart(body: bytes, content_type: str) -> tuple[dict[str, str], bytes | None]:
    if content_type.lower().startswith("application/x-www-form-urlencoded"):
        values = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
        fields = {key: items[0] if items else "" for key, items in values.items()}
        return fields, None
    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii", "replace")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    fields: dict[str, str] = {}
    upload = None
    if not message.is_multipart():
        return fields, upload
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        if 'name="aims"' in disposition:
            payload = part.get_payload(decode=True)
            if payload:
                upload = payload
            continue
        name = part.get_param("name", header="content-disposition")
        if name:
            payload = part.get_payload(decode=True)
            if payload is not None:
                fields[str(name)] = payload.decode(part.get_content_charset() or "utf-8", "replace")
    return fields, upload


class CityUScheduleHTTPServer(ThreadingHTTPServer):
    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.plan_results: dict[str, list[dict]] = {}
        self.plan_results_lock = threading.Lock()


class CityUScheduleWebHandler(BaseHTTPRequestHandler):
    server_version = "CityUSchedule/0.3"
    server: CityUScheduleHTTPServer

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"", "/", "/planner"}:
            self._send(_page("CityUSchedule", _form()))
            return
        if path == "/settings":
            self._send(_page("Basic settings", _basic_settings_form()))
            return
        if path == "/ge-search":
            self._send(_page("Search GE courses", _ge_search_form()))
            return
        if path == "/ge-info":
            self._send(_page("GE course information", _ge_info_form()))
            return
        if path == "/aims":
            self._send(_page("Check AIMS timetable", _aims_form()))
            return
        if path == "/saved-bundles":
            try:
                body = _saved_bundles_page()
            except (OSError, ValueError) as error:
                self._send(
                    _page(
                        "Saved plans and bundles",
                        f'<div class="error">{html.escape(str(error))}</div>',
                    ),
                    status=500,
                )
                return
            self._send(_page("Saved plans and bundles", body))
            return
        else:
            self.send_error(404)
            return

    def do_POST(self):
        if urlparse(self.path).path not in {
            "", "/", "/planner", "/settings", "/ge-search", "/ge-info",
            "/aims", "/save-plans", "/delete-plan",
        }:
            self.send_error(404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")
            fields, upload = _parse_multipart(body, content_type)
            action = fields.get("action", "")
            if action == "save-settings":
                result = _save_basic_settings(fields)
                body = (
                    f'<p class="notice">{html.escape(result)}</p>'
                    f'{_basic_settings_form()}'
                )
                self._send(_page("Basic settings saved", body))
            elif action == "ge-search":
                keyword = fields.get("keyword", "")
                result = _search_ge(keyword)
                body = _ge_search_form(keyword) + f"\n<pre>{html.escape(result)}</pre>"
                self._send(_page("GE search results", body))
            elif action == "ge-info":
                course_code = fields.get("course_code", "")
                result = _get_ge_info(course_code)
                body = _ge_info_form(course_code) + f"\n<pre>{html.escape(result)}</pre>"
                self._send(_page("GE course information", body))
            elif action == "aims-check":
                result = _check_aims(upload)
                body = _aims_form() + f"\n<pre>{html.escape(result)}</pre>"
                self._send(_page("AIMS timetable results", body))
            elif action == "save-plans":
                result = _save_selected_plans(
                    fields,
                    self.server.plan_results,
                    self.server.plan_results_lock,
                )
                body = f'<p class="notice">{html.escape(result)}</p>{_saved_bundles_link()}'
                self._send(_page("Plans saved", body))
            elif action == "delete-plan":
                result = _delete_saved_timetable_plan(
                    fields.get("plan_number", "")
                )
                self._send(
                    _page(
                        "Saved plans and bundles",
                        _saved_bundles_page(result),
                    )
                )
            else:
                result, token, plans_html = _generate(
                    fields,
                    upload,
                    self.server.plan_results,
                    self.server.plan_results_lock,
                )
                body = _form() + f"\n<pre>{html.escape(result)}</pre>"
                body += plans_html
                if token:
                    body += _save_plan_form(
                        token,
                        self.server.plan_results[token],
                    )
                self._send(_page("CityUSchedule results", body))
        except (ValueError, OSError) as error:
            path = urlparse(self.path).path
            if path == "/delete-plan":
                body = (
                    f'<div class="error">{html.escape(str(error))}</div>'
                    f'{_saved_bundles_page()}'
                )
                self._send(_page("Saved plans and bundles", body), status=400)
                return
            form = (
                _ge_search_form()
                if path == "/ge-search"
                else _ge_info_form()
                if path == "/ge-info"
                else _basic_settings_form()
                if path == "/settings"
                else _aims_form()
                if path == "/aims"
                else _form()
            )
            body = f'<div class="error">{html.escape(str(error))}</div>\n{form}'
            self._send(_page("CityUSchedule", body), status=400)

    def _send(self, body: bytes, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args):
        return


def create_web_server(host: str = "127.0.0.1", port: int = 8000):
    return CityUScheduleHTTPServer((host, port), CityUScheduleWebHandler)


def run_web_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = True,
) -> None:
    server = create_web_server(host, port)
    url_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{url_host}:{server.server_port}"
    print(f"CityUSchedule web app is running at {url}", flush=True)
    print("Press Ctrl+C to stop it.", flush=True)
    if open_browser:
        webbrowser.open(url, new=2)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
