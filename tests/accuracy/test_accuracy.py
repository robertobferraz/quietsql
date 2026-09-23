import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from quietsql.adapters.llm.registry import model_path
from quietsql.config import Config
from quietsql.wiring import build_services

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((Path(__file__).parent / "cases.json").read_text())
MODEL_READY = model_path(Config(), "xiyansql-3b").exists()


def flat(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    out = tmp_path_factory.mktemp("acc") / "demo.duckdb"
    script = ROOT / "scripts" / "make_dataset.py"
    subprocess.run(
        [sys.executable, str(script), "--rows", "10000", "--out", str(out)],
        check=True,
    )
    return out


def oracle_rows(path: Path) -> dict[str, list]:
    con = duckdb.connect(str(path), read_only=True)
    try:
        return {case["id"]: sorted(con.execute(case["expected_sql"]).fetchall()) for case in CASES}
    finally:
        con.close()


def test_cases_file_is_well_formed():
    assert len(CASES) == 30
    assert sum(c["language"] == "pt" for c in CASES) == 15
    assert all({"id", "question", "language", "expected_sql"} <= set(c) for c in CASES)
    assert len({c["id"] for c in CASES}) == 30


def test_every_expected_sql_returns_at_least_one_row(db_path):
    empty = [case_id for case_id, rows in oracle_rows(db_path).items() if not rows]
    assert empty == []


@pytest.mark.accuracy
@pytest.mark.skipif(not MODEL_READY, reason="run quietsql download-models first")
def test_generated_sql_matches_expected_results(db_path):
    expected_by_id = oracle_rows(db_path)
    services = build_services(Config())
    source = services.sources.open_file(str(db_path))
    passed = 0
    failures = []
    for case in CASES:
        answer = services.ask(source.id, case["question"])
        expected = expected_by_id[case["id"]]
        got = sorted(answer.result.rows) if answer.result else None
        ok = got == expected
        passed += ok
        if not ok:
            failures.append((case["id"], flat(answer.sql.text), str(answer.status), answer.error))
        print(
            f"{'ok ' if ok else 'BAD'} {case['id']:<26} "
            f"{answer.timings.generate_ms:7.0f} ms  {flat(answer.sql.text)}"
        )
    rate = passed / len(CASES)
    print(f"pass rate {rate:.0%} ({passed}/{len(CASES)})")
    for case_id, sql, status, error in failures:
        print(f"FAIL {case_id} [{status}] {sql} | {error}")
    assert rate >= 0.6
