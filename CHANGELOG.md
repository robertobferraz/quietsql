# Changelog

## 0.1.0 — phase 1 core

- Ask questions in Portuguese or English about CSV, Parquet, folders or DuckDB files.
- Local text-to-SQL with XiYanSQL-QwenCoder-3B (Apache-2.0) on llama.cpp; PT→EN translation with opus-mt on CTranslate2.
- Streamed SQL, editable editor, automatic retry on DuckDB errors, table and chart, persisted history.
- Read-only execution with statement allowlist, 30 s timeout, 10 000-row display cap.
- No outbound call at runtime anywhere outside `download-models`, the one explicit online step, verified by sha256; the test suite proves no tested path opens a Python-level socket, with the caveats in the README.
- Measured on the reference machine: 63 % (19/30) on the 30-case accuracy suite, 80 % English and 47 % Portuguese; total latency p50 2957 ms and p95 5170 ms.
