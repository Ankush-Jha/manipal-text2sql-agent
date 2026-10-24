"""Auto-generated BIRD-style hints from the profile for the linked columns (SEED-like)."""

import re


def _trivial(desc: str, col: str) -> bool:
    norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    return norm(desc) == norm(col) or norm(desc) in norm(col)


def hint_lines(link_result: dict, profile: dict, max_lines: int = 14) -> list[str]:
    lines = []
    for t, c, v in link_result.get("values", []):
        lines.append(f"{t}.{c} contains the exact stored value '{v}'")
    for t, cols in link_result["core"].items():
        for c in cols:
            info = profile["tables"][t][c]
            d = info.get("description", {})
            if d.get("values"):
                lines.append(f"{t}.{c}: {' '.join(d['values'].split())[:220]}")
            elif d.get("description") and not _trivial(d["description"], c):
                lines.append(f"{t}.{c} means: {d['description'][:120]}")
            vals = [v for v, _ in info.get("top_values", []) if isinstance(v, str)]
            if vals and info.get("distinct", 99) <= 30 and not d.get("values"):
                lines.append(f"{t}.{c} stored values: " + ", ".join(repr(v) for v in vals[:12]))
            if info.get("date_formats"):
                lines.append(f"{t}.{c} is stored as text like {info.get('min')!r}; use SUBSTR/LIKE on it, not strftime, unless it is ISO YYYY-MM-DD")
            if info.get("dirty_tokens"):
                lines.append(f"{t}.{c} has placeholder values {info['dirty_tokens']}; exclude them when computing aggregates")
            if info.get("mixed_date_formats"):
                lines.append(f"{t}.{c} mixes date formats {info['date_formats']}")
            if info.get("null_rate", 0) > 0.5:
                lines.append(f"{t}.{c} is NULL in {info['null_rate']*100:.0f}% of rows")
    # coded columns of the two best tables, even if the question never names them ("Czech Republic" -> 'CZE')
    extra = []
    for t in link_result.get("tables", [])[:2]:
        for c, info in profile["tables"][t].items():
            vals = [v for v, _ in info.get("top_values", []) if isinstance(v, str)]
            if (vals and 2 <= info.get("distinct", 99) <= 8 and not info.get("description", {}).get("values")
                    and not c.lower().endswith(("id", "code")) and not any(l.startswith(f"{t}.{c} ") for l in lines)):
                extra.append(f"{t}.{c} stored values: " + ", ".join(repr(v) for v in vals[:8]))
    lines += extra[:4]
    return list(dict.fromkeys(lines))[:max_lines]


def hint_text(lines: list[str]) -> str:
    return ("Hints:\n- " + "\n- ".join(lines)) if lines else ""
