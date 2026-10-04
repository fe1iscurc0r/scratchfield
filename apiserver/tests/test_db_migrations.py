"""卷192-C 验收测试：schema 版本机制（幂等 / 并发防双跑 / fail-fast / 零丢失）。

刻意**不经 apiserver 包**（用 importlib 直接加载 runner.py）——避免拉起
apiserver/__init__ 的重依赖链，也让本测试可在裸解释器下跑。
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # tests -> apiserver -> 仓库根
PKG = ROOT / "apiserver" / "db_migrations"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PKG / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


runner = _load("_dbm_runner_test", "runner.py")
baseline = _load("_dbm_baseline_test", "001_initial_baseline.py")

Migration = runner.Migration
apply = runner.apply
current_version = runner.current_version


def _fresh_db(tmp_path, name="t.db") -> Path:
    return tmp_path / name


# ---------------------------------------------------------------- 1. 新建库跑基线

def test_new_db_gets_baseline_version(tmp_path):
    db = _fresh_db(tmp_path)
    r = apply(db, baseline.MIGRATIONS)
    assert r.applied == [1]
    assert r.from_version == 0 and r.to_version == 1
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT version, name FROM schema_version").fetchall()
    finally:
        conn.close()
    assert rows == [(1, "initial_baseline")]


# ---------------------------------------------------------------- 2. 幂等重跑

def test_rerun_is_idempotent(tmp_path):
    db = _fresh_db(tmp_path)
    apply(db, baseline.MIGRATIONS)
    r2 = apply(db, baseline.MIGRATIONS)
    assert r2.skipped is True and r2.applied == []
    conn = sqlite3.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    finally:
        conn.close()
    assert n == 1                       # 没有重复登记


# ---------------------------------------------------------------- 3. 增量迁移

def test_pending_migration_applied_in_order(tmp_path):
    db = _fresh_db(tmp_path)
    migs = [
        Migration(1, "base", None),
        Migration(2, "add_table", "CREATE TABLE IF NOT EXISTS demo(id INTEGER);"),
        Migration(3, "add_index", "CREATE INDEX IF NOT EXISTS ix_demo ON demo(id);"),
    ]
    r = apply(db, migs)
    assert r.applied == [1, 2, 3] and r.to_version == 3
    # 再跑：无挂起
    assert apply(db, migs).skipped is True


# ---------------------------------------------------------------- 4. 回滚检测

def test_rollback_detection_rejects_older_code(tmp_path):
    db = _fresh_db(tmp_path)
    apply(db, [Migration(1, "a"), Migration(2, "b")])
    with pytest.raises(runner.MigrationError) as e:
        apply(db, [Migration(1, "a")])   # 代码只知 v1，库已是 v2
    assert "高于代码已知最高版本" in str(e.value)


# ---------------------------------------------------------------- 5. fail-fast + 回滚

def test_failed_migration_rolls_back_and_raises(tmp_path):
    db = _fresh_db(tmp_path)
    migs = [
        Migration(1, "base", None),
        Migration(2, "broken", "CREATE TABLE x(y INTEGER); INVALID SQL HERE;"),
    ]
    with pytest.raises(runner.MigrationError) as e:
        apply(db, migs)
    assert "已回滚" in str(e.value)
    # v2 未登记、且 x 表不存在（整批回滚）
    conn = sqlite3.connect(db)
    try:
        assert current_version(conn) == 1
        has_x = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='x'").fetchone()
    finally:
        conn.close()
    assert has_x is None


# ---------------------------------------------------------------- 6. 并发启动防双跑

def test_concurrent_apply_runs_once(tmp_path):
    db = _fresh_db(tmp_path)
    migs = [Migration(1, "base", None),
            Migration(2, "t", "CREATE TABLE IF NOT EXISTS c(id INTEGER);")]
    results: list = []
    barrier = threading.Barrier(6)

    def worker():
        barrier.wait()
        try:
            results.append(apply(db, migs))
        except Exception as e:          # 抢锁失败也不应崩，最多等锁
            results.append(e)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == [1, 2]          # 无重复登记
    assert all(not isinstance(r, Exception) for r in results)


# ---------------------------------------------------------------- 7. 用户数据零丢失

def test_existing_user_data_preserved(tmp_path):
    db = _fresh_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE message_store (id INTEGER PRIMARY KEY, session_id TEXT, message TEXT)")
    conn.executemany("INSERT INTO message_store VALUES (?,?,?)",
                     [(i, "s1", f"m{i}") for i in range(1, 51)])
    conn.commit()
    conn.close()

    r = apply(db, baseline.MIGRATIONS)
    assert r.to_version == 1

    conn = sqlite3.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM message_store").fetchone()[0]
    finally:
        conn.close()
    assert n == 50                                 # 基线不动现有表


# ---------------------------------------------------------------- 8. 库间隔离（一库失败不阻断）

def test_apply_all_isolates_failures(tmp_path, monkeypatch):
    good = tmp_path / "good.db"
    bad = tmp_path / "nodir" / "x.db"
    # 让 bad 的父目录不可写：改为指向一个目录路径
    bad.mkdir(parents=True)
    results = runner.apply_all([("good", good), ("bad", bad)])
    by_name = {r.db.split(" (")[0]: r for r in results}
    assert by_name["good"].to_version == 1
    assert by_name["bad"].note.startswith(("ERROR", "FAILED"))


# ---------------------------------------------------------------- 9. registry 形状

def test_registry_lists_databases():
    reg = _load("_dbm_registry_test", "registry.py")
    dbs = reg.databases()
    names = [n for n, _ in dbs]
    assert "message_store" in names and "tool_calls" in names
    assert all(isinstance(p, Path) for _, p in dbs)
    assert len(names) == len(set(names))           # 无重名
