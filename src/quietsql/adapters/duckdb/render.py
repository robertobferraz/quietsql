import re
from collections.abc import Iterable

import duckdb

from quietsql.core.models import Schema

PLAIN = re.compile(r"^[a-z_][a-z0-9_]*$")


def _duckdb_keywords_needing_quotes() -> frozenset[str]:
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT keyword_name FROM duckdb_keywords() "
            "WHERE keyword_category IN ('reserved', 'type_function')"
        ).fetchall()
    finally:
        con.close()
    return frozenset(name.lower() for (name,) in rows)


RESERVED = _duckdb_keywords_needing_quotes()


def quote(identifier: str) -> str:
    if PLAIN.match(identifier) and identifier not in RESERVED:
        return identifier
    return '"' + identifier.replace('"', '""') + '"'


def approx_tokens(text: str) -> int:
    return len(text) // 4 + 1


def render_ddl(schema: Schema, tables: Iterable[str] | None = None) -> str:
    wanted = set(tables) if tables is not None else None
    fks = {(fk.table, fk.column): fk for fk in schema.foreign_keys}
    blocks = []
    for table in schema.tables:
        if wanted is not None and table.name not in wanted:
            continue
        lines = []
        for col in table.columns:
            parts = [f"  {quote(col.name)} {col.data_type.lower()}"]
            if col.is_primary_key:
                parts.append("primary key")
            fk = fks.get((table.name, col.name))
            if fk and (wanted is None or fk.referenced_table in wanted):
                parts.append(
                    f"references {quote(fk.referenced_table)}({quote(fk.referenced_column)})"
                )
            lines.append((" ".join(parts), ", ".join(col.examples)))
        rendered = []
        for i, (decl, examples) in enumerate(lines):
            comma = "," if i < len(lines) - 1 else ""
            comment = f" -- {examples}" if examples else ""
            rendered.append(f"{decl}{comma}{comment}")
        blocks.append(f"create table {quote(table.name)} (\n" + "\n".join(rendered) + "\n);")
    return "\n".join(blocks)
