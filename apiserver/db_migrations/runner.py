"""db_migrations.runner — 轻量 schema 版本表 + 迁移执行器（卷192-C 档2）。

设计（工单"三档方案"里的档 2，自研 ≤150 行、零依赖）：

- 版本表 ``schema_version(version, name, applied_at)``：每库一张，记录已应用的迁移；
- 执行器 ``apply(db_path, migrations)``：读当前版本 → 依次执行**挂起**迁移 → 记录；
- **幂等**：已应用的版本跳过（重跑不重复、不改数据）；
- **并发防双跑**：``BEGIN IMMEDIATE`` 抢写锁 + 版本表主键唯一约束兜底；
- **fail-fast**：迁移失败即回滚该次事务并抛 ``MigrationError``（带 db/版本/原因），不静默；
- **回滚检测**：库里版本高于代码已知版本时拒绝执行（防止旧代码操作新库）。

硬约束（工单红线）：**绝不 DROP/ALTER 任何现有表**——runner 只写 version 表；
真正的结构变更由未来的 002+ 迁移显式携带 DDL。

纯 Python 标准库。
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

VERSION_TABLE = "schema_version"

_CREATE_VERSION_TABLE = f"""
CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at REAL NOT NULL
)
"""


class MigrationError(RuntimeError):
    """迁移失败（fail-fast，错误信息含库与版本，便于定位）。"""


@dataclass(frozen=True)
class Migration:
    """一条迁移。``apply_sql`` 为 None 表示只登记版本号、不执行 DDL。"""

    version: int
    name: str
    apply_sql: str | None = None
    note: str = ""

    def __post_init__(self):
        if self.version < 1:
            raise ValueError(f"migration version 必须 >= 1，得到 {self.version}")


@dataclass
class ApplyResult:
    db: str
    from_version: int
    to_version: int
    applied: list[int] = field(default_factory=list)
    skipped: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "db": self.db, "from_version": self.from_version,
            "to_version": self.to_version, "applied": self.applied,
            "skipped": self.skipped, "note": self.note,
        }


def current_version(conn: sqlite3.Connection) -> int:
    """当前版本号；无版本表或空表 → 0。"""
    has = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (VERSION_TABLE,)).fetchone()
    if not has:
        return 0
    row = conn.execute(f"SELECT MAX(version) FROM {VERSION_TABLE}").fetchone()
    return int(row[0] or 0)


def _split_statements(sql: str) -> list[str]:
    """把多语句 DDL 拆成单条（保留事务原子性）。

    为什么不用 `executescript`：sqlite3 的 executescript 会**先隐式提交**当前事务，
    导致外层 BEGIN IMMEDIATE 失效（后续 COMMIT 报 "no transaction is active"）。
    用 `sqlite3.complete_statement` 逐行累积判断，既支持多行语句、又不会被字符串里的
    分号骗到。
    """
    stmts: list[str] = []
    buf = ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            s = buf.strip()
            if s:
                stmts.append(s)
            buf = ""
    tail = buf.strip()
    if tail:
        stmts.append(tail)
    return stmts


def _connect(db_path: Path) -> sqlite3.Connection:
    """打开迁移用连接。

    刻意**不设 journal_mode=WAL**：迁移只在启动期跑、并发度极低，而实测（Windows）
    多线程同时对一个**新建库**开 WAL 会争抢 `-wal`/`-shm` 边车文件、报
    `attempt to write a readonly database`。保持默认 DELETE 日志 + busy_timeout
    即可满足"并发启动防双跑"，且不受该竞态影响。
    """
    conn = sqlite3.connect(str(db_path), timeout=20.0, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def _coerce(m: "Migration | dict") -> Migration:
    """dict → Migration（迁移定义文件用纯数据，避免与执行器互相导入）。"""
    if isinstance(m, Migration):
        return m
    if isinstance(m, dict):
        return Migration(
            version=int(m["version"]),
            name=str(m.get("name") or f"v{m['version']}"),
            apply_sql=m.get("apply_sql"),
            note=str(m.get("note") or ""),
        )
    raise TypeError(f"迁移定义必须是 Migration 或 dict，得到 {type(m).__name__}")


def apply(db_path: str | Path, migrations: Sequence[Migration | dict] | None = None) -> ApplyResult:
    """对一个库执行挂起的迁移（幂等）。

    参数：
        db_path    —— 库文件路径（不存在则创建）。
        migrations —— 迁移序列（Migration 或等价 dict）；None 时用 ``001_initial_baseline.MIGRATIONS``。

    返回 ApplyResult。异常：
        MigrationError —— 迁移失败（已回滚）；版本回滚检测不通过。
    """
    if migrations is None:
        migrations = _default_migrations()

    tasks = sorted((_coerce(m) for m in migrations), key=lambda m: m.version)
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = _connect(path)
    try:
        # ① 短事务：确保版本表存在 + 回滚检测
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(_CREATE_VERSION_TABLE)
            cur = current_version(conn)
            known_max = max((m.version for m in tasks), default=0)

            # 回滚检测：库比代码新 → 拒绝（旧代码不该操作新库）
            if cur > known_max:
                raise MigrationError(
                    f"{path.name}: 库版本 {cur} 高于代码已知最高版本 {known_max}——"
                    f"疑似代码回滚，拒绝执行（防旧代码破坏新库）")
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

        pending = [m for m in tasks if m.version > cur]
        if not pending:
            return ApplyResult(str(path), cur, cur, [], skipped=True, note="无挂起迁移")

        # ② 逐迁移一个事务：失败只回滚本条，已成功的保留（可修复后续跑）
        applied: list[int] = []
        for m in pending:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # 抢到锁后复检（防并发双跑：别的进程可能刚应用完）
                if current_version(conn) >= m.version:
                    conn.execute("COMMIT")
                    continue
                if m.apply_sql:
                    for stmt in _split_statements(m.apply_sql):
                        conn.execute(stmt)
                conn.execute(
                    f"INSERT INTO {VERSION_TABLE}(version, name, applied_at) VALUES (?,?,?)",
                    (m.version, m.name, time.time()))
                conn.execute("COMMIT")
            except Exception as e:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                if isinstance(e, MigrationError):
                    raise
                raise MigrationError(
                    f"{path.name}: 迁移 v{m.version}({m.name}) 失败并已回滚: {e}") from e
            applied.append(m.version)

        return ApplyResult(str(path), cur, max(applied) if applied else cur, applied)
    finally:
        conn.close()


def _default_migrations() -> list[Migration]:
    """延迟导入基线定义（避免测试加载包时触发 apiserver/__init__ 重依赖）。"""
    import importlib.util
    p = Path(__file__).with_name("001_initial_baseline.py")
    spec = importlib.util.spec_from_file_location("_db_migrations_baseline", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.MIGRATIONS)


def apply_all(targets: Iterable[tuple[str, str | Path]] | None = None) -> list[ApplyResult]:
    """对注册的全部库执行迁移（启动链调用）。

    targets: (库名, 路径) 序列；None 时用 registry.DATABASES。
    单个库失败**不阻断其余库**，失败库在结果里带 note（fail-fast 在库内，不在库间）。
    """
    if targets is None:
        targets = _default_targets()
    out: list[ApplyResult] = []
    for name, path in targets:
        try:
            r = apply(path)
            r.db = f"{name} ({r.db})"
            out.append(r)
        except MigrationError as e:
            out.append(ApplyResult(db=f"{name} ({path})", from_version=-1, to_version=-1,
                                   note=f"FAILED: {e}"))
        except Exception as e:  # 路径不可写等
            out.append(ApplyResult(db=f"{name} ({path})", from_version=-1, to_version=-1,
                                   note=f"ERROR: {type(e).__name__}: {e}"))
    return out


def _default_targets() -> list[tuple[str, Path]]:
    import importlib.util
    p = Path(__file__).with_name("registry.py")
    spec = importlib.util.spec_from_file_location("_db_migrations_registry", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.databases())
