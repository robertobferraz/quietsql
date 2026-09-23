# quietsql

Ask questions about your local data in Portuguese or English and get SQL, a table and a chart back. Nothing leaves your machine.

## What it is

quietsql is a local text-to-SQL tool. You point it at a CSV file, a Parquet file, a folder of them or a `.duckdb` file, ask a question in plain Portuguese or English, and it writes the SQL, runs it against DuckDB and shows you the rows and a chart. The SQL is always visible and always editable before or after it runs.

Everything runs on your CPU. The SQL model is a GGUF file executed by llama.cpp; the Portuguese-to-English step is an opus-mt model executed by CTranslate2. There is no API key, no account and no server.

## Privacy guarantees

**What never leaves the machine at runtime:** your data, your schema, your questions, the generated SQL and the results. There is no outbound call anywhere in the code outside `download-models`, and the only socket the application listens on is the local HTTP port that serves the UI.

**The single online step** is `quietsql download-models`, which fetches the model files from Hugging Face and verifies each one against a sha256 digest recorded in `src/quietsql/adapters/llm/registry.py`. A digest mismatch always fails the command; for the two GGUF models the corrupt file is also deleted, while the translator's source download is left in the Hugging Face cache for you to inspect or clear. After that step the tool never needs the network again; you can disconnect and it still works.

**How to verify it yourself.** The whole test suite runs with `pytest-socket` active (`--disable-socket --allow-unix-socket` in `pyproject.toml`), so any attempt to open a network socket raises `SocketBlockedError` and fails the test. `tests/test_no_network.py` builds the real service graph and runs a full Portuguese question-to-answer flow under that block, and each of its tests asserts that the block was in force and that no socket was attempted:

```
uv run pytest tests/test_no_network.py -v
```

The first two tests need nothing but the checkout. The third loads the real SQL model and the real translator, so it needs `quietsql download-models` to have been run, otherwise it skips.

**What that proves, and what it does not.** It proves that no tested code path creates a Python-level socket — across the whole suite, including one real end-to-end Portuguese question through the real service graph. It does not prove the absence of a native connection: `pytest-socket` patches Python's `socket` module, so it cannot observe a `connect(2)` issued from inside llama.cpp, CTranslate2 or DuckDB. Nor does any test start the `serve` listening socket, since binding a port is itself a socket operation; that half of the claim rests on reading the code rather than on a test. The claim above is therefore architectural, established by review of the source, with the suite closing the Python-level half of it. If you want the stronger proof for your own machine, run `quietsql serve` disconnected, or watch it with `lsof`.

One related finding, since the proof is only as good as what was looked at: NiceGUI 2.x makes no startup version or telemetry call. Its only outbound client is `nicegui/air.py`, and `air.connect()` is a no-op unless `ui.run(on_air=...)` is passed. quietsql never passes it.

## Requirements

- Python 3.11 or newer
- A CPU; no GPU required
- RAM: 8 GB or more
- Disk: about 2.0 GB for the two models that are kept (1.8 GB for the SQL model, 230 MB for the converted translator), plus roughly 0.9 GB of transient Hugging Face cache during the translator conversion

## Install

quietsql is not on PyPI yet, so today the way to install it is from a checkout of this repository:

```
uv sync --extra dev --extra convert
```

Once it is published, these will work:

```
uv tool install quietsql
```

or, with pip and the CPU wheel index for llama-cpp-python:

```
pip install quietsql --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

The `convert` extra pulls `transformers` and `torch`. It is needed **at download time only**: the translator is published as a Hugging Face model and is converted locally to the CTranslate2 int8 format. Without it, `download-models` stops with a one-line message telling you to run `uv sync --extra convert` and try again. It is not needed to run the app afterwards.

## First run

```
quietsql download-models
quietsql serve --db path/to/data.duckdb
```

`download-models` fetches the model named by the `model` config key (`xiyansql-3b` by default) plus the translator, and nothing else. The fallback model `prem-1b` is configured but is **not** downloaded by default; pass `--only prem-1b` if you want it.

`serve` starts the local web app on port 8765 and opens a browser. Other ways to start it:

```
quietsql serve --folder path/to/csvs
quietsql serve --port 9000 --no-browser
quietsql serve --mock
```

`--mock` runs the whole screen against fake data with no models at all, which is a fast way to see the interface before downloading anything.

## Models and licenses

| key | kind | repository | local artifact | download size | size on disk | license |
|---|---|---|---|---:|---:|---|
| `xiyansql-3b` | gguf | `mradermacher/XiYanSQL-QwenCoder-3B-2504-GGUF` | `XiYanSQL-QwenCoder-3B-2504.Q4_K_M.gguf` | 1841 MB | 1841 MB | Apache-2.0 |
| `prem-1b` | gguf | `mradermacher/prem-1B-SQL-GGUF` | `prem-1B-SQL.Q4_K_M.gguf` | 833 MB | 833 MB | Apache-2.0 |
| `opus-mt-roa-en` | ct2 | `Helsinki-NLP/opus-mt-tc-bible-big-roa-en` | `opus-mt-roa-en-ct2/` | 890 MB | 230 MB | Apache-2.0 |

**Download size** is what `download-models` fetches, as recorded in the registry. **Size on disk** is what stays in `~/.cache/quietsql/models` afterwards. The two differ only for the translator: a GGUF file is used exactly as downloaded, while the 890 MB opus-mt repository is converted locally to a 230 MB CTranslate2 int8 directory. The download itself lands in the Hugging Face cache and can be deleted once the conversion succeeds. By default only `xiyansql-3b` and `opus-mt-roa-en` are fetched, so the default install keeps about 2.0 GB.

`xiyansql-3b` writes the SQL. `opus-mt-roa-en` translates a Portuguese question to English before the SQL model sees it; identifiers from your schema are masked during translation so they survive it unchanged. `prem-1b` is a smaller alternative you can select with the `model` config key.

## Measured latency

Reference machine: `arm64 · Apple M1 Max · 10 cores · 32 GB RAM`. Dataset: a generated DuckDB file with 1 000 000 sales rows. 30 questions, 15 Portuguese and 15 English.

| stage | p50 ms | p95 ms |
|---|---:|---:|
| detect | 0 | 7 |
| translate | 0 | 1071 |
| prefill | 333 | 1167 |
| generate | 1400 | 3735 |
| transpile | 0 | 1 |
| run | 2 | 8 |
| total | **2957** | **5170** |

Mean total: 2787 ms.

The design target was an answer in under 5 s on this machine. **It is met at the median and missed at the tail:** half the questions answer in under 3.0 s, while the p95 is 5.2 s, so the slowest questions run past the 5 s target. Both numbers belong together — the median alone would overstate the result and the p95 alone would understate it.

The p95 here is the nearest-rank value over 30 samples, which makes it close to the worst single observation rather than a stable tail estimate. Two runs of the same 30 questions on this machine produced 5897 ms and 5170 ms. The median moved by 161 ms between those same two runs. Treat the p50 as the number you can rely on and the p95 as evidence that the tail is real, not as a precise figure.

Reading the stages: generation dominates and prefill is second, so latency work belongs in the model. `translate` has a p50 of 0 ms because the 15 English questions never enter the translator; its p95 of about 1.1 s is the true cost of the Portuguese path. `run` stays in single-digit milliseconds over a million rows, so DuckDB is not the bottleneck at this scale.

Reproduce by building the dataset and running the benchmark:

```
uv run python scripts/make_dataset.py --rows 1000000 --out data/demo.duckdb
uv run python scripts/benchmark.py
```

The table above is copied from `docs/benchmark.md`, which the benchmark script writes. That file is not in the repository — `docs/` is excluded from version control — so a fresh clone does not contain it until you run the script.

## Accuracy

Measured on a 30-case suite (15 Portuguese, 15 English) against a 10 000-row generated dataset, comparing the result rows against a hand-written expected query for each case.

| set | passed | rate |
|---|---:|---:|
| English | 12 / 15 | 80 % |
| Portuguese | 7 / 15 | 47 % |
| **total** | **19 / 30** | **63 %** |

63 % is the measured rate, and the Portuguese half is materially weaker than the English half. Two runs produced the same rate with an identical failing set, so this is a stable measurement, not noise.

Where the 11 failures come from:

- **Aggregation dropped (4 cases, all Portuguese).** A counting question answered with a row listing. Every one of these has a passing English twin with the identical expected query, so the loss is in the translated question rather than in the schema or the prompt.
- **A pre-aggregated column ignored in favour of recomputing it through a join (2 cases).** The join multiplies rows and the sums differ.
- **`EXCEPT` rejected by the SQL validator (2 cases).** A product limitation, not a model error; see Limits below.
- **Top-1 without aggregation (2 cases).** Ordering by a single row's value instead of by the sum per group. The only failure shape that hit both languages equally.
- **A month rendered as a string instead of a date (1 case).** The grouping is correct and only the key type differs; the suite compares rows exactly, so it counts as a failure.

The suite asserts `rate >= 0.6`. That floor exists to catch a regression, and it is not a claim about how good 63 % is.

Reproduce with (needs downloaded models; takes about 70 s):

```
uv run pytest tests/accuracy -m accuracy -v -s
```

## Configuration

Settings are read from `~/.config/quietsql/config.toml`, then overridden by environment variables, then by command-line flags. Every key has an environment variable named `QUIETSQL_` plus the key in upper case, so `threads` is `QUIETSQL_THREADS`.

| key | default | meaning |
|---|---|---|
| `model` | `xiyansql-3b` | key from the model registry used to write SQL |
| `fallback_model` | `prem-1b` | smaller alternative, not downloaded by default |
| `threads` | unset | CPU threads. Unset (or `auto`) means the SQL model uses `cpu_count() - 1` and the translator uses 4 |
| `n_ctx` | `4096` | context window in tokens |
| `max_tokens` | `120` | maximum tokens generated per query |
| `query_timeout_s` | `30.0` | seconds before a running query is cancelled |
| `max_tables` | `30` | maximum tables accepted from one source |
| `schema_budget_tokens` | `1000` | token budget for the schema sent to the model |
| `port` | `8765` | local HTTP port for the UI |
| `cache_dir` | `~/.cache/quietsql` | models, session files and history |
| `config_dir` | `~/.config/quietsql` | location of `config.toml` |

Example `config.toml`:

```toml
model = "xiyansql-3b"
threads = 8
query_timeout_s = 60.0
port = 9000
```

## Limits in phase 1

- **Read-only.** Only `SELECT`, `WITH`, `DESCRIBE` and `SUMMARIZE` reach the database. Anything else is rejected before execution.
- **`EXCEPT` and `INTERSECT` are currently rejected too.** Both are read-only set operations and both are legitimate answers, but the validator only accepts `SELECT`, `UNION` and `DESCRIBE` roots. This is a known limitation and it costs 2 of the 11 accuracy failures above.
- **At most 30 tables per source.** A source with more is refused rather than silently truncated. The limit is the `max_tables` key.
- **Local files only.** CSV, Parquet, a folder of either, or a `.duckdb` file. No Postgres, MySQL or any remote source.
- **Single user.** No authentication, no profiles, no per-table permissions.
- **10 000 rows displayed** per result, and a 30 s query timeout.
- **Portuguese accuracy trails English.** See the Accuracy section.

## Roadmap

| phase | scope |
|---|---|
| 1 | Read-only core: local CSV, Parquet, folder and `.duckdb` sources; question to SQL to table and chart; visible SQL; history |
| 2 | Writes through natural language: `INSERT`/`UPDATE`/`DELETE` with SQL preview, explicit confirmation and a revertible transaction |
| 3 | Remote sources: Postgres, MySQL and SQLite through DuckDB extensions |
| 4 | Multi-user: authentication, profiles, per-table permissions, per-user history |
| 5 | Deployment: Docker self-hosting and an optional cloud deployment |
| 6 | Fine-tuning: a local pipeline using the history as question-to-SQL pairs |
| 7 | Optional providers: cloud LLMs, opt-in and off by default, with a clear warning that the schema would leave the machine; opt-in anonymous telemetry |

Phase 1 is the current phase.

## Development

```
uv run ruff check .
uv run ruff format --check src tests scripts
uv run pytest
uv run pytest -m accuracy
```

`uv run pytest` runs everything except the accuracy suite. Tests marked `slow` load a real model and run by default; each one skips itself when the model files are absent, so a fresh checkout without `quietsql download-models` still gets a green suite. The `accuracy` marker carries the 30-case accuracy suite, which takes about 70 s; `tests/conftest.py` skips it unless you select it with `-m accuracy`. The `network` marker is reserved for tests that would open the internet; `tests/conftest.py` skips them unconditionally, and no test currently carries it.

## License

MIT. See `LICENSE`. The models are downloaded separately and carry their own licenses, listed in the table above.
