"""数据库备份模块验收（卷192 黄档 Y2 处置）。

覆盖：建快照可读且数据一致 / 同日幂等 / 源缺失跳过（不建空库）/ 轮转只删超期快照 /
不触碰非本模块命名文件 / 汇总计数正确 / 源库不被改写。
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from apiserver.db_backup import backup_all, backup_one, prune_old


def _make_db(path, rows=3):
    with sqlite3.connect(str(path)) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"v{i}",) for i in range(rows)])
        conn.commit()
    return path


def _read_rows(path):
    with sqlite3.connect(str(path)) as conn:
        return conn.execute("SELECT v FROM t ORDER BY id").fetchall()


def test_backup_creates_readable_snapshot(tmp_path):
    src = _make_db(tmp_path / "demo.db", rows=5)
    r = backup_one(src, tmp_path / "bk", today=dt.date(2026, 10, 6))
    assert r["status"] == "created", r
    snapshot = tmp_path / "bk" / "demo" / "demo-2026-10-06.db"
    assert snapshot.exists() and r["path"] == str(snapshot)
    assert r["bytes"] > 0
    assert _read_rows(snapshot) == _read_rows(src), "快照数据必须与源库一致"


def test_backup_is_idempotent_per_day(tmp_path):
    src = _make_db(tmp_path / "demo.db")
    day = dt.date(2026, 10, 6)
    first = backup_one(src, tmp_path / "bk", today=day)
    second = backup_one(src, tmp_path / "bk", today=day)
    assert first["status"] == "created"
    assert second["status"] == "skipped_exists", second


def test_missing_source_is_skipped_not_created(tmp_path):
    missing = tmp_path / "nope.db"
    r = backup_one(missing, tmp_path / "bk", today=dt.date(2026, 10, 6))
    assert r["status"] == "skipped_missing"
    assert not missing.exists(), "绝不因备份而创建空库"
    assert not (tmp_path / "bk" / "nope").exists()


def test_source_is_not_modified(tmp_path):
    src = _make_db(tmp_path / "demo.db", rows=4)
    before = _read_rows(src)
    backup_one(src, tmp_path / "bk", today=dt.date(2026, 10, 6))
    assert _read_rows(src) == before, "VACUUM INTO 不得改写源库"


def test_prune_removes_only_expired_snapshots(tmp_path):
    out = tmp_path / "demo"
    out.mkdir()
    today = dt.date(2026, 10, 10)
    for offset in range(0, 9):                       # 2026-10-10 ... 2026-10-02
        day = (today - dt.timedelta(days=offset)).isoformat()
        (out / f"demo-{day}.db").write_bytes(b"x")
    keepme = out / "unrelated-notes.txt"             # 非本模块命名 → 不碰
    keepme.write_text("kk", encoding="utf-8")

    removed = prune_old(out, keep_days=7, today=today)
    # cutoff = 10-10 - 7d = 10-03 → 仅 10-02（最旧一天）被删
    assert len(removed) == 1, [p.name for p in removed]
    assert (out / "demo-2026-10-02.db").exists() is False
    assert (out / "demo-2026-10-03.db").exists() is True, "cutoff 当天必须保留"
    assert keepme.exists(), "非本模块命名的文件绝不能被删"


def test_prune_ignores_unparsable_names(tmp_path):
    out = tmp_path / "demo"
    out.mkdir()
    weird = out / "demo-not-a-date.db"
    weird.write_bytes(b"x")
    assert prune_old(out, keep_days=0, today=dt.date(2026, 10, 10)) == []
    assert weird.exists()


def test_backup_all_summary_and_prune_integration(tmp_path):
    live = _make_db(tmp_path / "live.db", rows=2)
    gone = tmp_path / "gone.db"
    root = tmp_path / "bk"
    summary = backup_all(
        [("live", live), ("gone", gone)], root,
        keep_days=7, today=dt.date(2026, 10, 6))
    assert summary["total"] == 2
    assert summary["created"] == 1
    assert summary["skipped"] == 1
    assert summary["failed"] == 0
    assert summary["backup_root"] == str(root)
    names = {r["name"]: r["status"] for r in summary["results"]}
    assert names == {"live": "created", "gone": "skipped_missing"}


def test_backup_only_filter(tmp_path):
    a = _make_db(tmp_path / "a.db")
    b = _make_db(tmp_path / "b.db")
    summary = backup_all([("a", a), ("b", b)], tmp_path / "bk",
                         today=dt.date(2026, 10, 6), only="a")
    assert summary["total"] == 1
    assert summary["results"][0]["name"] == "a"


def test_failed_backup_reports_error_without_raising(tmp_path):
    """非 SQLite 文件（伪造 .db）→ failed 且带 error，不抛异常。"""
    bogus = tmp_path / "bogus.db"
    bogus.write_text("not a sqlite database", encoding="utf-8")
    r = backup_one(bogus, tmp_path / "bk", today=dt.date(2026, 10, 6))
    assert r["status"] == "failed"
    assert r["error"]
