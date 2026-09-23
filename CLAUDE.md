# Project rules

## Workflow
- Every feature or behavior change goes through `/sdd`. Never implement directly.
- Design first: screen contract and mock before any backend or query engine work.
- Never commit unless the user asks. No `Co-Authored-By` trailers in commit messages.
- Frontend work: load `impeccable` before creating or changing a screen.

## Code
- No comments in code. Names and structure carry the meaning.
- Documentation lives in `README.md` and `docs/`, written in standard English.

## Repository
- `docs/` and `.claude/` are excluded via `.git/info/exclude`, never `.gitignore`.
- Public repository: nothing sensitive, no sample data with real records.

## Stack
- Python 3.11+, uv, ruff, pytest
- DuckDB, llama-cpp-python (GGUF), CTranslate2, NiceGUI
- Commands: `uv run ruff check .` · `uv run pytest`

## Knowledge
- docs/04-conventions/README.md — conventions, read before coding
- docs/05-lessons/README.md — mistakes already paid for
- docs/06-roadmap/README.md — delivery phases
- Technical decisions → docs/02-adr/ · product → docs/03-pdr/ (via /sdd, not by hand)
