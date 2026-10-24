"""Run candidate SQLs, one repair pass on error, group by result set, majority vote."""
from collections import defaultdict
from typing import Callable

from agent.executor import ExecResult, GuardError, execute


def result_key(sql: str, res: ExecResult):
    """Order-insensitive unless the SQL has ORDER BY."""
    rows = [tuple(map(repr, r)) for r in res.rows]
    return ("ordered", tuple(rows)) if "order by" in sql.lower() else ("set", tuple(sorted(set(rows))))


def run_candidates(db_path, sqls: list[str | None], repair: Callable[[str, str], str | None] | None = None,
                   timeout_s: float = 10, max_rows: int = 1000) -> dict:
    """repair(sql, error_text) -> new sql or None. Returns groups, per-candidate log and the winning group."""
    log, groups = [], defaultdict(list)
    for sql in sqls:
        entry = {"sql": sql, "error": None, "repaired": False, "rows": 0}
        res = None
        for attempt in range(2):
            if not sql:
                entry["error"] = "no_sql"
                break
            try:
                res = execute(db_path, sql, timeout_s, max_rows)
                entry["error"] = None
                break
            except (GuardError, Exception) as e:  # sqlite3 errors included
                entry["error"] = str(e)[:300]
                if attempt == 0 and repair and not isinstance(e, GuardError):
                    fixed = repair(sql, entry["error"])
                    if fixed and fixed != sql:
                        sql, entry["repaired"], entry["sql"] = fixed, True, fixed
                        continue
                break
        if res is not None:
            entry["rows"] = len(res.rows)
            groups[result_key(sql, res)].append((sql, res))
        log.append(entry)
    ranked = sorted(groups.values(), key=lambda g: (len(g), len(g[0][1].rows) > 0), reverse=True)
    out_groups = [{"size": len(g), "rows": len(g[0][1].rows), "sqls": [s for s, _ in g]} for g in ranked]
    winner = ranked[0] if ranked else None
    n_ok = sum(len(g) for g in ranked)
    return {
        "candidates": log, "groups": out_groups, "n_groups": len(ranked),
        "vote_share": (len(winner) / len(sqls)) if winner and sqls else 0.0,
        "winner_sql": winner[0][0] if winner else None,
        "winner_result": winner[0][1] if winner else None,
        "n_executed": n_ok,
    }
