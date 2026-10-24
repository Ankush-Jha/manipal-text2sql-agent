"""Deterministic access control below the model: AST policy check, SQLite authorizer, SQL helpers.
Nothing here asks an LLM. The role database (agent/roles.py) is the strongest layer; this module adds the
authorizer that runs on every connection and an optional column policy for the full database."""
import sqlite3
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

HIDDEN, PUBLIC, AGGREGATE_ONLY = "hidden", "public", "aggregate_only"
DENIED_FUNCS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}
# the only authorizer actions a read-only SELECT needs
_OK_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}


class PolicyError(Exception):
    """A query was refused by the access policy. `kind` is one of table/column/star/aggregate/syntax."""
    def __init__(self, msg: str, kind: str = "policy"):
        super().__init__(msg)
        self.kind = kind


@dataclass
class Policy:
    """tables: {table: {column: mode}} for every table the role may see; columns absent from the map are hidden.
    full_schema: {table: [columns]} of the underlying database, used to resolve unqualified columns."""
    tables: dict[str, dict[str, str]]
    full_schema: dict[str, list[str]] = field(default_factory=dict)

    def mode(self, table: str, col: str) -> str:
        t = {k.lower(): v for k, v in self.tables.get(table.lower(), self.tables.get(table, {})).items()}
        return t.get(col.lower(), HIDDEN)

    def allows_table(self, table: str) -> bool:
        return table.lower() in {t.lower() for t in self.tables}


def _tables_in_scope(root: exp.Expression) -> tuple[dict[str, str], set[str]]:
    """({alias_or_name_lower: real_table_lower}, cte_names_lower)"""
    ctes = {c.alias.lower() for c in root.find_all(exp.CTE)}
    alias = {}
    for t in root.find_all(exp.Table):
        if t.name.lower() in ctes and not t.db:
            continue
        alias[(t.alias or t.name).lower()] = t.name.lower()
    return alias, ctes


def check(sql: str, policy: Policy) -> None:
    """Raise PolicyError unless the SQL reads only allowed tables and columns. Conservative: unknown or
    ambiguous columns that could be hidden are refused."""
    try:
        root = sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError as e:
        raise PolicyError(f"unparseable SQL: {e}", "syntax") from e
    alias, _ = _tables_in_scope(root)
    for real in set(alias.values()):
        if real.startswith("sqlite_") or not policy.allows_table(real):
            raise PolicyError(f"table '{real}' is not available to this role", "table")
    in_scope = set(alias.values())
    _, ctes = _tables_in_scope(root)
    for star in root.find_all(exp.Star):
        if isinstance(star.parent, exp.Count):
            continue
        sel = star.find_ancestor(exp.Select)
        direct = {(t.alias or t.name).lower(): t.name.lower() for t in sel.find_all(exp.Table)
                  if t.find_ancestor(exp.Select) is sel and t.name.lower() not in ctes}
        qual = star.parent.table.lower() if isinstance(star.parent, exp.Column) and star.parent.table else None
        for t in ([direct.get(qual, qual)] if qual else direct.values()):
            hidden = [c for c in policy.full_schema.get(t, []) if policy.mode(t, c) != PUBLIC]
            if hidden:
                raise PolicyError(f"'*' on '{t}' would include restricted columns ({', '.join(hidden[:3])}...)", "star")
    for col in root.find_all(exp.Column):
        name = col.name.lower()
        if col.table:
            cands = [alias[col.table.lower()]] if col.table.lower() in alias else []  # derived-table alias: checked inside
        else:
            cands = [t for t in in_scope if name in {c.lower() for c in policy.full_schema.get(t, [])}]
        for t in cands:
            m = policy.mode(t, name)
            if m == HIDDEN:
                raise PolicyError(f"column '{t}.{name}' is not available to this role", "column")
            if m == AGGREGATE_ONLY and not col.find_ancestor(exp.AggFunc):
                raise PolicyError(f"column '{t}.{name}' may only be used inside an aggregate", "aggregate")


def make_authorizer(log: list | None = None, allowed: dict[str, set[str]] | None = None):
    """SQLite authorizer: SELECT only, no sqlite_* tables, no dangerous functions. With `allowed`
    ({table_lower: {col_lower}}) it also denies reads of any other table or column. Every denial is logged."""
    def authorizer(action, a1, a2, dbname, source):
        verdict = sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            t, c = (a1 or "").lower(), (a2 or "").lower()
            if t.startswith("sqlite_"):
                verdict = sqlite3.SQLITE_DENY
            elif allowed is not None and t and c and (t not in allowed or c not in allowed[t]):
                verdict = sqlite3.SQLITE_DENY
        elif action == sqlite3.SQLITE_FUNCTION:
            if (a2 or "").lower() in DENIED_FUNCS:
                verdict = sqlite3.SQLITE_DENY
        elif action not in _OK_ACTIONS:
            verdict = sqlite3.SQLITE_DENY
        if log is not None:
            log.append({"action": action, "a1": a1, "a2": a2, "allowed": verdict == sqlite3.SQLITE_OK})
        return verdict
    return authorizer


def allowed_map(policy: Policy) -> dict[str, set[str]]:
    return {t.lower(): {c.lower() for c, m in cols.items() if m != HIDDEN} for t, cols in policy.tables.items()}


# ---- AST helpers shared by follow-up verification, clarification and drift repair ----
def constraints(sql: str) -> set[str]:
    """Normalised WHERE/HAVING/JOIN-ON atoms, e.g. {"county = 'alameda'", "year >= 2023"}; qualifiers stripped."""
    try:
        root = sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return set()
    out = set()
    for node in root.find_all(exp.Where, exp.Having):
        for atom in _atoms(node.this):
            a = atom.copy()
            for col in a.find_all(exp.Column):
                col.set("table", None)
            out.add(a.sql(dialect="sqlite").lower())
    return out


def _atoms(e: exp.Expression):
    if isinstance(e, (exp.And, exp.Paren)) and not isinstance(e, exp.Or):
        for child in e.args.values():
            if isinstance(child, exp.Expression):
                yield from _atoms(child)
    else:
        yield e


def diff(sql_a: str, sql_b: str) -> dict:
    """What differs between two queries: tables, constraint atoms, projections."""
    def facts(s):
        try:
            r = sqlglot.parse_one(s, read="sqlite")
        except sqlglot.errors.ParseError:
            return set(), set(), set()
        return ({t.name.lower() for t in r.find_all(exp.Table)}, constraints(s),
                {p.sql(dialect="sqlite").lower() for p in r.find(exp.Select).expressions} if r.find(exp.Select) else set())
    (ta, ca, pa), (tb, cb, pb) = facts(sql_a), facts(sql_b)
    return {"tables": sorted(ta ^ tb), "constraints_only_a": sorted(ca - cb), "constraints_only_b": sorted(cb - ca),
            "projections_only_a": sorted(pa - pb), "projections_only_b": sorted(pb - pa)}
