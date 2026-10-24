"""Deterministic result checks. Each returns a flag name or None; run_checks collects the flags."""
import re
from datetime import date

_PCT = re.compile(r"percent|pct|rate|ratio|proportion", re.I)
_COUNT = re.compile(r"^count|count$|^num|number|total", re.I)


def zero_rows(cols, rows, **_):
    return "zero_rows" if not rows else None


def all_null_column(cols, rows, **_):
    if not rows:
        return None
    for i in range(len(cols)):
        if all(r[i] is None for r in rows):
            return "all_null_column"
    return None


def percentage_over_100(cols, rows, **_):
    for i, c in enumerate(cols):
        if _PCT.search(c or ""):
            for r in rows:
                if isinstance(r[i], (int, float)) and r[i] > 100:
                    return "percentage_over_100"
    return None


def negative_count(cols, rows, sql="", **_):
    for i, c in enumerate(cols):
        if _COUNT.search(c or "") or "count(" in (c or "").lower():
            for r in rows:
                if isinstance(r[i], (int, float)) and r[i] < 0:
                    return "negative_count"
    return None


def row_explosion(cols, rows, sql="", base_rows=None, **_):
    """base_rows: largest row count among the base tables in the query. Flags joins that
    return far more rows than any input table."""
    if base_rows and "join" in sql.lower() and len(rows) > 10 * base_rows:
        return "row_explosion"
    return None


def date_out_of_range(cols, rows, data_range=None, **_):
    """data_range: (min_year, max_year) seen in the DB's date columns."""
    if not data_range:
        return None
    lo, hi = data_range
    for r in rows:
        for v in r:
            if isinstance(v, str):
                m = re.match(r"^(\d{4})-\d{2}-\d{2}", v)
                if m and not (lo <= int(m.group(1)) <= hi):
                    return "date_out_of_range"
    return None


CHECKS = [zero_rows, all_null_column, percentage_over_100, negative_count,
          row_explosion, date_out_of_range]


def run_checks(cols, rows, sql="", base_rows=None, data_range=None) -> list[str]:
    kw = dict(cols=cols, rows=rows, sql=sql, base_rows=base_rows, data_range=data_range)
    return [f for c in CHECKS if (f := c(**kw))]
