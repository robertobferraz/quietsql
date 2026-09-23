from collections.abc import Sequence

from quietsql.core.models import Attempt

SYSTEM = (
    "You write DuckDB SQL. Output exactly one SELECT statement and nothing else: "
    "no explanation, no markdown.\n"
    "Use only the tables and columns in the schema. "
    "Use DuckDB syntax, not Postgres, MySQL or SQLite: "
    "strftime, date_trunc, list functions, QUALIFY, EXCLUDE, ILIKE are available.\n"
    "Quote identifiers with double quotes only when they contain spaces or capitals.\n"
    "Add LIMIT 100 unless the query aggregates."
)
ERROR_LIMIT = 300


def build_prompt(schema_ddl: str, question: str, previous: Sequence[Attempt]) -> str:
    user = f"-- schema\n{schema_ddl}\n\n-- question\n{question}"
    for attempt in previous:
        truncated_error = attempt.error[:ERROR_LIMIT]
        user += (
            f"\n\n-- your previous SQL\n{attempt.sql}\n-- duckdb error\n{truncated_error}"
            "\n-- fix the query, output only SQL"
        )
    return (
        f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\n{user}<|im_end|>\n"
        "<|im_start|>assistant\nSELECT"
    )
