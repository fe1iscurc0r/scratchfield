"""工单 261 §2 · token_ledger 验收用例（6 条）。

全部基于 `tests/fixtures/token_ledger/fixture.db`（**不依赖真实 state.db**）。
通过 subprocess 调 CLI，因此断言的是**真实退出码与 stdout/stderr**，不是内部函数。
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPT = os.path.join(REPO, "scripts", "token_ledger.py")
FIXTURE_DIR = os.path.join(HERE, "fixtures", "token_ledger")
FIXTURE_DB = os.path.join(FIXTURE_DIR, "fixture.db")
DUMPS_DIR = os.path.join(FIXTURE_DIR, "dumps")

# fixture 里写死的口径（与 make_fixture.py 保持一致）
EXPECTED_SESSIONS = 5
EXPECTED_INPUT = 14_000
EXPECTED_CACHE_READ = 45_000
EXPECTED_HIT_RATE = EXPECTED_CACHE_READ / (EXPECTED_CACHE_READ + EXPECTED_INPUT)  # 0.762712...


@pytest.fixture(scope="module")
def fixture_db() -> str:
    """确保 fixture（db + dumps）存在；缺失则现场生成，因此生成物无需入库。"""
    if not os.path.exists(FIXTURE_DB) or not os.path.isdir(DUMPS_DIR):
        subprocess.run(
            [sys.executable, os.path.join(FIXTURE_DIR, "make_fixture.py")],
            check=True,
            capture_output=True,
            text=True,
        )
    assert os.path.exists(FIXTURE_DB), "fixture.db 生成失败"
    assert os.path.isdir(DUMPS_DIR), "dumps 生成失败"
    return FIXTURE_DB


def run_cli(*args: str, db: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, SCRIPT, "--db", db, *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)


def as_json(proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode == 0, f"CLI 失败 rc={proc.returncode}\nstderr={proc.stderr}"
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - 便于定位
        raise AssertionError(f"stdout 不是合法 JSON:\n{proc.stdout[:800]}") from exc


def test_summary_requests_and_hit_rate(fixture_db: str) -> None:
    """用例 1：requests == 5，命中率与手算值误差 < 0.001。"""
    data = as_json(run_cli("summary", "--since", "2026-09-01", "--json", db=fixture_db))

    assert data["requests"] == EXPECTED_SESSIONS
    assert data["sessions"] == EXPECTED_SESSIONS
    assert data["tokens"]["input"] == EXPECTED_INPUT
    assert data["tokens"]["cache_read"] == EXPECTED_CACHE_READ
    assert abs(data["cache_hit_rate"] - EXPECTED_HIT_RATE) < 0.001


def test_cost_is_null_when_pricing_missing(fixture_db: str) -> None:
    """用例 2：单价缺失时 cost_breakdown 各项为 None，**不能是 0**。"""
    empty_pricing = os.path.join(FIXTURE_DIR, "_empty_pricing.json")
    with open(empty_pricing, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({}, fh)

    data = as_json(
        run_cli("summary", "--since", "2026-09-01", "--pricing", empty_pricing, "--json", db=fixture_db)
    )
    cb = data["cost_breakdown"]
    assert cb["output"] is None, f"单价缺失时必须为 null，实际 {cb['output']!r}"
    assert cb["input"] is None
    assert cb["cache_read"] is None
    assert cb["cache_write"] is None
    assert any("单价" in w for w in data["warnings"])


def test_tools_top1_is_largest(fixture_db: str) -> None:
    """用例 3：--top 1 返回字符量最大的工具（fixture 里是 read_file 90000）。"""
    data = as_json(run_cli("tools", "--since", "2026-09-01", "--top", "1", "--json", db=fixture_db))

    assert len(data["tools"]) == 1
    top = data["tools"][0]
    assert top["tool_name"] == "read_file"
    assert top["chars"] == 90_000
    # 确认它确实是 fixture 里的最大值（而不是碰巧第一个）
    conn = sqlite3.connect(fixture_db)
    try:
        rows = conn.execute(
            "SELECT COALESCE(tool_name,'(none)') t, SUM(LENGTH(content)) c"
            " FROM messages WHERE role='tool' GROUP BY t ORDER BY c DESC"
        ).fetchall()
    finally:
        conn.close()
    assert rows[0][0] == "read_file" and rows[0][1] == 90_000


def test_reflush_earliest_amortizes_more(fixture_db: str) -> None:
    """用例 4：同一 session 内，最早一条工具消息的摊销字符 > 最后一条。"""
    data = as_json(run_cli("reflush", "--since", "2026-09-01", "--json", db=fixture_db))

    samples = data["samples"]
    assert samples, "reflush 未输出 samples"
    sid = "s1"  # fixture 里 s1 有两条工具消息（idx 5 / 6）
    first, last = samples[sid]["first"], samples[sid]["last"]
    first_amort = first["chars"] * first["factor"]
    last_amort = last["chars"] * last["factor"]

    assert first["idx"] < last["idx"]
    assert first_amort > last_amort, (
        f"最早一条摊销 {first_amort} 应大于最后一条 {last_amort}"
        f"（first={first}, last={last}）"
    )


def test_loops_min_repeat_3(fixture_db: str) -> None:
    """用例 5：--min-repeat 3 命中 1 条，repeats == 3。"""
    data = as_json(
        run_cli("loops", "--dumps", DUMPS_DIR, "--min-repeat", "3", "--json", db=fixture_db)
    )

    assert data["files_scanned"] == 5
    assert len(data["loops"]) == 1, data["loops"]
    assert data["loops"][0]["repeats"] == 3
    assert data["loops"][0]["tool_name"] == "read_file"


def test_empty_db_exits_1_without_traceback(tmp_path) -> None:
    """用例 6：空库 ⇒ 退出码 1 + stderr 明确提示，**不抛 traceback**。"""
    empty = tmp_path / "empty.db"
    conn = sqlite3.connect(empty)
    try:
        conn.executescript(
            """
            CREATE TABLE sessions (id TEXT PRIMARY KEY, model TEXT, started_at REAL,
              api_call_count INTEGER, message_count INTEGER, input_tokens INTEGER,
              output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER,
              reasoning_tokens INTEGER, estimated_cost_usd REAL, actual_cost_usd REAL,
              cost_status TEXT, system_prompt_hash TEXT);
            CREATE TABLE messages (id INTEGER, session_id TEXT, role TEXT, content TEXT,
              tool_name TEXT, timestamp REAL, token_count INTEGER, compacted INTEGER, active INTEGER);
            """
        )
        conn.commit()
    finally:
        conn.close()

    proc = run_cli("summary", "--since", "2026-09-01", "--json", db=str(empty))

    assert proc.returncode == 1, f"期望退出码 1，实际 {proc.returncode}"
    assert "Traceback" not in proc.stderr, f"不应出现 traceback:\n{proc.stderr}"
    assert "session" in proc.stderr or "错误" in proc.stderr
