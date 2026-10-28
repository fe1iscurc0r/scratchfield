#!/usr/bin/env python3
"""生成 token_ledger 测试用的迷你 state.db（工单 261 §2）。

**不依赖真实 `~/.hermes/state.db`**：表结构与真实库一致，数据是构造的。

构造内容
--------
* 5 个 session × 20 条消息（共 100 条）。
* token 口径（便于手算）：
    s1..s4  input=1_000  cache_read=9_000
    s5      input=10_000 cache_read=9_000     ← 故意制造 input 突增（缓存失效事件）
  合计 input=14_000 / cache_read=45_000 ⇒ 命中率 = 45000/59000 ≈ 0.762712
* 5 条 `role='tool'` 大输出：read_file 50000 + 40000（合计最大）、web_search 30000、
  terminal 20000、execute_code 10000。
* `dumps/` 下 5 份 request_dump：其中 3 份连续同工具同参数（min-repeat=3 应命中 1 条）。

用法
----
    python3 tests/fixtures/token_ledger/make_fixture.py [--out <dir>]
默认输出到本文件同目录（fixture.db + dumps/）。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))

SCHEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    model TEXT,
    started_at REAL,
    api_call_count INTEGER,
    message_count INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    reasoning_tokens INTEGER,
    estimated_cost_usd REAL,
    actual_cost_usd REAL,
    cost_status TEXT,
    system_prompt_hash TEXT
);
CREATE TABLE session_model_usage (
    session_id TEXT,
    model TEXT,
    billing_provider TEXT,
    api_call_count INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    reasoning_tokens INTEGER
);
CREATE TABLE messages (
    id INTEGER,
    session_id TEXT,
    role TEXT,
    content TEXT,
    tool_name TEXT,
    timestamp REAL,
    token_count INTEGER,
    compacted INTEGER,
    active INTEGER
);
"""

SESSIONS = [
    # (id, input, cache_read, output)
    ("s1", 1000, 9000, 300),
    ("s2", 1000, 9000, 300),
    ("s3", 1000, 9000, 300),
    ("s4", 1000, 9000, 300),
    ("s5", 10000, 9000, 300),
]

# (session_id, 消息序号(0-based), tool_name, 输出字符数)
TOOL_MESSAGES = [
    ("s1", 5, "read_file", 50000),
    ("s1", 6, "read_file", 40000),
    ("s2", 7, "web_search", 30000),
    ("s3", 8, "terminal", 20000),
    ("s4", 9, "execute_code", 10000),
]

MSGS_PER_SESSION = 20


def build(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    db_path = os.path.join(out_dir, "fixture.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)

    base = 1_790_000_000.0  # 2026-09-22 附近，固定值保证可重现
    for idx, (sid, inp, cread, outp) in enumerate(SESSIONS):
        calls = 1
        con.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sid,
                "deepseek-flash",
                base + idx * 86_400,
                calls,
                MSGS_PER_SESSION,
                inp,
                outp,
                cread,
                0,  # cache_write
                0,  # reasoning
                None,  # estimated_cost_usd（真实库多为 unknown）
                None,
                "unknown",
                f"sp-hash-{'same' if idx != 4 else 'changed'}",
            ),
        )
        con.execute(
            "INSERT INTO session_model_usage VALUES (?,?,?,?,?,?,?,?,?)",
            (sid, "deepseek-flash", "deepseek", calls, inp, outp, cread, 0, 0),
        )

    big = {f"{s}:{i}": (t, n) for s, i, t, n in TOOL_MESSAGES}
    msg_id = 1
    for idx, (sid, _inp, _cread, _outp) in enumerate(SESSIONS):
        for pos in range(MSGS_PER_SESSION):
            key = f"{sid}:{pos}"
            if key in big:
                tool, nchars = big[key]
                role, name, content = "tool", tool, "x" * nchars
            elif pos % 3 == 0:
                role, name, content = "user", None, f"问题 {sid}-{pos}"
            else:
                role, name, content = "assistant", None, f"回答 {sid}-{pos}"
            con.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
                (msg_id, sid, role, content, name, base + idx * 86_400 + pos, None, 0, 1),
            )
            msg_id += 1

    con.commit()
    con.close()

    # ---- dumps：3 份连续同工具同参数 + 2 份其它 ----
    dumps_dir = os.path.join(out_dir, "dumps")
    os.makedirs(dumps_dir, exist_ok=True)
    same_args = {"path": "/etc/hosts"}
    plan = [
        ("request_dump_00.json", "s-loop", "read_file", same_args, None),
        ("request_dump_01.json", "s-loop", "read_file", same_args, None),
        ("request_dump_02.json", "s-loop", "read_file", same_args, None),
        ("request_dump_03.json", "s-loop", "web_search", {"q": "other"}, None),
        ("request_dump_04.json", "s-other", "terminal", {"cmd": "ls"}, None),
    ]
    for fn, sid, tool, args, _err in plan:
        payload = {
            "session_id": sid,
            "tool_calls": [{"name": tool, "arguments": args}],
            "error": {"type": "rate_limit", "message": "stub"},
        }
        with open(os.path.join(dumps_dir, fn), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)

    return db_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    path = build(args.out)
    print(f"已生成 {path}")
    print(f"已生成 {os.path.join(args.out, 'dumps')}/（5 份 dump）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
