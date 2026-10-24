"""Guarded SQLite execution: read-only, single SELECT/WITH, authorizer, timeout, row cap."""
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import sqlglot
from sqlglot import exp

from agent import guard


class GuardError(Exception):
    """Raised when SQL is refused before or during execution."""


@dataclass
class ExecResult:
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    truncated: bool = False


def validate_sql(sql: str) -> str:
    """Return the SQL if it is exactly one SELECT/WITH statement, else raise GuardError."""
    try:
        stmts = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"unparseable SQL: {e}") from e
    if len(stmts) != 1:
        raise GuardError("exactly one statement is allowed")
    root = stmts[0]
    if not isinstance(root, (exp.Select, exp.SetOperation, exp.With, exp.Subquery)):
        raise GuardError(f"only SELECT/WITH is allowed, got {type(root).__name__}")
    banned = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)
    if root.find(*banned):
        raise GuardError("write/DDL statement inside query")
    return sql


def execute(db_path: str | Path, sql: str, timeout_s: float = 10, max_rows: int = 1000,
            policy: guard.Policy | None = None, audit: list | None = None, ast_check: bool = True) -> ExecResult:
    """policy: optional column policy (AST check + authorizer allowlist) for a database that holds more than
    the role may see. audit: receives every authorizer decision, used as a structural leak oracle."""
    validate_sql(sql)
    if policy is not None and ast_check:
        try:
            guard.check(sql, policy)
        except guard.PolicyError as e:
            raise GuardError(str(e)) from e
    uri = f"file:{Path(db_path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    deadline = time.monotonic() + timeout_s
    # a non-zero return from the progress handler aborts the running query
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    conn.set_authorizer(guard.make_authorizer(audit, guard.allowed_map(policy) if policy else None))
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(max_rows + 1)
        cols = [d[0] for d in cur.description or []]
    except sqlite3.DatabaseError as e:
        if "interrupted" in str(e):
            raise GuardError(f"query exceeded {timeout_s}s timeout") from e
        if "not authorized" in str(e) or "prohibited" in str(e):
            raise GuardError("query touches data this role cannot access") from e
        raise
    finally:
        conn.close()
    return ExecResult(cols, rows[:max_rows], truncated=len(rows) > max_rows)
