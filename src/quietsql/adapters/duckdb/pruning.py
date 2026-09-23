import re

from quietsql.adapters.duckdb.naming import singular
from quietsql.adapters.duckdb.render import approx_tokens, render_ddl
from quietsql.core.models import Schema

WORD = re.compile(r"[a-z0-9_]+")


def _words(text: str) -> set[str]:
    return set(WORD.findall(text.lower()))


def _score(schema: Schema, words: set[str]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for table in schema.tables:
        score = 0
        name = table.name.lower()
        if name in words or singular(name) in words:
            score += 3
        for col in table.columns:
            if col.name.lower() in words:
                score += 1
            for example in col.examples:
                if example.lower() in words:
                    score += 1
        if score:
            scores[table.name] = score
    return scores


def select_tables(schema: Schema, question: str, budget_tokens: int) -> tuple[str, ...] | None:
    words = _words(question)
    scores = _score(schema, words)
    if not scores:
        return None
    chosen = dict(scores)
    for fk in schema.foreign_keys:
        if fk.table in scores and fk.referenced_table not in chosen:
            chosen[fk.referenced_table] = 0
        if fk.referenced_table in scores and fk.table not in chosen:
            chosen[fk.table] = 0
    ordered = sorted(chosen, key=lambda t: -chosen[t])
    while len(ordered) > 1 and approx_tokens(render_ddl(schema, ordered)) > budget_tokens:
        ordered.pop()
    return tuple(ordered)
