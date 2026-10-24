"""Resolve relative time phrases ("last 30 days", "last fiscal year") to explicit half-open date ranges [start, end).
Done once, deterministically, before any SQL is written, so the writer, checks and UI all use the same boundaries.
Conventions (reference date, timezone, fiscal-year start, week start) come from the rules registry."""
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

UNIT_DAYS = {"day": 1, "week": 7}


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def reference(conv: dict, profile: dict | None = None) -> tuple[date, str]:
    ref = conv.get("reference_date", "today")
    if ref == "data_max" and profile and conv.get("date_column"):
        t, c = conv["date_column"].split(".", 1)
        mx = profile["tables"].get(t, {}).get(c, {}).get("max")
        if mx:
            return date.fromisoformat(str(mx)[:10]), f"latest {conv['date_column']} in the data"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ref)):
        return date.fromisoformat(ref), "fixed reference date"
    return datetime.now(ZoneInfo(conv.get("timezone", "UTC"))).date(), f"today in {conv.get('timezone', 'UTC')}"


def windows(question: str, conv: dict, profile: dict | None = None) -> list[dict]:
    q = question.lower()
    ref, source = reference(conv, profile)
    fy = int(conv.get("fiscal_year_start_month", 1))
    week0 = ref - timedelta(days=ref.weekday() if conv.get("week_start", "monday") == "monday" else (ref.weekday() + 1) % 7)
    month0, year0 = ref.replace(day=1), date(ref.year, 1, 1)
    fy0 = date(ref.year if ref.month >= fy else ref.year - 1, fy, 1)
    q0 = date(ref.year, 3 * ((ref.month - 1) // 3) + 1, 1)
    nxt = ref + timedelta(days=1)
    out = []

    def add(phrase, start, end, meaning):
        out.append({"phrase": phrase, "start": start.isoformat(), "end": end.isoformat(), "meaning": meaning,
                    "reference": ref.isoformat(), "reference_source": source})

    for m in re.finditer(r"\b(?:last|past|previous)\s+(\d+)\s+(day|week|month|year)s?\b", q):
        n, unit = int(m.group(1)), m.group(2)
        start = ref - timedelta(days=n * UNIT_DAYS[unit]) if unit in UNIT_DAYS else (
            _add_months(ref, -n).replace(day=min(ref.day, 28)) if unit == "month" else ref.replace(year=ref.year - n))
        add(m.group(0), start, ref, f"rolling {n} {unit}s before the reference date")
    fixed = [
        (r"\b(?:last|previous)\s+calendar\s+month\b|\b(?:last|previous)\s+month\b", lambda: (_add_months(month0, -1), month0, "the previous calendar month")),
        (r"\bthis\s+month\b|\bmonth\s+to\s+date\b|\bmtd\b", lambda: (month0, nxt, "this month up to and including the reference date")),
        (r"\b(?:last|previous)\s+fiscal\s+year\b", lambda: (fy0.replace(year=fy0.year - 1), fy0, f"the previous fiscal year (starts month {fy})")),
        (r"\bthis\s+fiscal\s+year\b|\bfiscal\s+year\s+to\s+date\b", lambda: (fy0, nxt, f"this fiscal year to date (starts month {fy})")),
        (r"\b(?:last|previous)\s+calendar\s+year\b|\b(?:last|previous)\s+year\b", lambda: (year0.replace(year=year0.year - 1), year0, "the previous calendar year")),
        (r"\bthis\s+year\b|\byear\s+to\s+date\b|\bytd\b", lambda: (year0, nxt, "this calendar year to date")),
        (r"\b(?:last|previous)\s+quarter\b", lambda: (_add_months(q0, -3), q0, "the previous calendar quarter")),
        (r"\b(?:last|previous)\s+week\b", lambda: (week0 - timedelta(days=7), week0, f"the previous full week ({conv.get('week_start', 'monday')} start)")),
        (r"\byesterday\b", lambda: (ref - timedelta(days=1), ref, "the day before the reference date")),
    ]
    taken = " ".join(w["phrase"] for w in out)
    for rx, fn in fixed:
        m = re.search(rx, q)
        if m and m.group(0) not in taken:
            s, e, meaning = fn()
            add(m.group(0), s, e, meaning)
            taken += " " + m.group(0)
    return out


def window_line(w: dict, conv: dict) -> str:
    col = conv.get("date_column") or "the relevant date column"
    return (f"Time window: '{w['phrase']}' means {col} >= '{w['start']}' AND {col} < '{w['end']}' "
            f"(end exclusive; {w['meaning']}; reference date {w['reference']} = {w['reference_source']}).")
