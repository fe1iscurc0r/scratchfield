"""任务容器（卷123 W123-01）。

把「对话」升级为「可跟踪任务」：一个任务持有目标 / 步骤 / 文件引用 / 结果 / git 状态，
可 pause/resume，每一步留轨迹。ZCode 的 Goal Mode 底座就是它。

存储：**与 message_store 同库**（同一个 `message_store.db`，见 `message_store._default_db_path`），
独立表 `tasks` —— 不扩建 message_store 的既有 schema，避免影响 NEKO 侧读同表的逻辑
（NEKO 的 SQLChatMessageHistory 只认 `id/session_id/message` 三列）。

**任务状态 = SQLite 权威，内存只是缓存**：进程重启后 `get_task()` 仍能读到；
`status=paused` 的任务可 resume。写操作走参数化 SQL，失败只记日志不影响对话链路。

步骤结构（steps_json 里每项）：

    {"id": "s1", "desc": "跑测试", "status": "pending|running|done|blocked|skipped",
     "type": "explore|code|test|verify|review", "result_ref": "...", "ts": 1699...}

轨迹结构（trajectory_json 追加项）：

    {"ts": ..., "step_id": "s1", "tool": "test_run", "summary": "1 passed", "status": "done"}
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: 任务状态机（status 列取值）
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_REVIEW = "review"
STATUS_DONE = "done"
STATUS_BLOCKED = "blocked"
STATUS_FAILED = "failed"

VALID_STATUS = {
    STATUS_PENDING, STATUS_RUNNING, STATUS_PAUSED,
    STATUS_REVIEW, STATUS_DONE, STATUS_BLOCKED, STATUS_FAILED,
}

#: 执行模式（exec_mode 列取值）
EXEC_MODES = ("explore", "code", "test", "review")

#: 步骤状态
STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_DONE = "done"
STEP_BLOCKED = "blocked"
STEP_SKIPPED = "skipped"

VALID_STEP_STATUS = {STEP_PENDING, STEP_RUNNING, STEP_DONE, STEP_BLOCKED, STEP_SKIPPED}

_MAX_TRAJECTORY = 200


def active_task_lookup_statuses() -> tuple:
    """「活动任务」判定用的状态（查上下文/继续时认可的状态）。"""
    return (STATUS_RUNNING, STATUS_PAUSED, STATUS_BLOCKED, STATUS_REVIEW, STATUS_PENDING)


def _default_db_path() -> Path:
    """与 message_store 同库（任务与消息共享 session_id 维度）。"""
    from apiserver.message_store import _default_db_path as _msg_db_path

    return _msg_db_path()


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tasks ("
        " task_id TEXT PRIMARY KEY,"
        " session_id TEXT NOT NULL,"
        " goal TEXT NOT NULL,"
        " status TEXT NOT NULL,"
        " exec_mode TEXT DEFAULT 'code',"
        " steps_json TEXT,"
        " file_refs_json TEXT,"
        " git_state TEXT,"
        " trajectory_json TEXT,"
        " review_json TEXT,"
        " created_at REAL,"
        " updated_at REAL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    # 卷123 W123-05：用户维度（跨通道继续任务用）。老库缺列时补列，不重建表。
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "user_id" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN user_id TEXT DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id)")
    return conn


# ---------------------------------------------------------------------------
# 序列化助手
# ---------------------------------------------------------------------------


def _loads(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def _row_to_task(row: sqlite3.Row) -> Dict[str, Any]:
    keys = row.keys()
    return {
        "task_id": row["task_id"],
        "session_id": row["session_id"],
        "goal": row["goal"],
        "status": row["status"],
        "exec_mode": row["exec_mode"],
        "steps": _loads(row["steps_json"], []),
        "file_refs": _loads(row["file_refs_json"], []),
        "git_state": row["git_state"] or "",
        "trajectory": _loads(row["trajectory_json"], []),
        "review": _loads(row["review_json"], {}),
        "user_id": (row["user_id"] if "user_id" in keys else "") or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _normalize_steps(steps: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, item in enumerate(steps or [], start=1):
        if isinstance(item, str):
            out.append({"id": f"s{idx}", "desc": item, "status": STEP_PENDING,
                        "type": "code", "result_ref": ""})
            continue
        if not isinstance(item, dict):
            continue
        step = dict(item)
        step.setdefault("id", f"s{idx}")
        step.setdefault("desc", "")
        step.setdefault("status", STEP_PENDING)
        step.setdefault("type", "code")
        step.setdefault("result_ref", "")
        if step["status"] not in VALID_STEP_STATUS:
            step["status"] = STEP_PENDING
        out.append(step)
    return out


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_task(
    session_id: str,
    goal: str,
    *,
    steps: List[Any] | None = None,
    exec_mode: str = "code",
    git_state: str = "",
    file_refs: List[str] | None = None,
    status: str = STATUS_PENDING,
    task_id: str | None = None,
    user_id: str = "",
    db_path: Path | None = None,
) -> Dict[str, Any]:
    """建任务并返回任务字典（task_id 缺省用 uuid4 十六进制）。"""
    tid = task_id or uuid.uuid4().hex
    now = time.time()
    if status not in VALID_STATUS:
        status = STATUS_PENDING
    if exec_mode not in EXEC_MODES:
        exec_mode = "code"
    steps_list = _normalize_steps(steps)
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO tasks (task_id, session_id, goal, status, exec_mode, steps_json,"
            " file_refs_json, git_state, trajectory_json, review_json, user_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                tid, str(session_id), str(goal), status, exec_mode,
                json.dumps(steps_list, ensure_ascii=False),
                json.dumps(list(file_refs or []), ensure_ascii=False),
                str(git_state or ""), "[]", "{}", str(user_id or ""), now, now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("[task_store] 建任务 %s（会话 %s，%d 步，模式 %s）", tid, session_id, len(steps_list), exec_mode)
    return get_task(tid, db_path=db_path) or {}


def set_user(task_id: str, user_id: str, *, db_path: Path | None = None) -> Dict[str, Any] | None:
    """绑定任务归属用户（跨通道可见性判断用）。"""
    return _update_fields(task_id, {"user_id": str(user_id or "")}, db_path=db_path)


def list_tasks_by_user(
    user_id: str, *, status: str | None = None, limit: int = 50, db_path: Path | None = None
) -> List[Dict[str, Any]]:
    """按用户列任务（跨通道：同一用户的任意会话建的任务都能捞到）。"""
    if not user_id:
        return []
    sql = "SELECT * FROM tasks WHERE user_id = ?"
    params: List[Any] = [str(user_id)]
    if status:
        sql += " AND status = ?"
        params.append(str(status))
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, int(limit)))
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
    finally:
        conn.close()
    return [_row_to_task(r) for r in rows]


def get_task(task_id: str, *, db_path: Path | None = None) -> Dict[str, Any] | None:
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (str(task_id),)).fetchone()
    finally:
        conn.close()
    return _row_to_task(row) if row else None


def list_tasks(
    session_id: str | None = None,
    *,
    status: str | None = None,
    limit: int = 50,
    db_path: Path | None = None,
) -> List[Dict[str, Any]]:
    """按会话（可选）与状态（可选）列任务，按 updated_at 倒序。"""
    sql = "SELECT * FROM tasks"
    clauses: List[str] = []
    params: List[Any] = []
    if session_id:
        clauses.append("session_id = ?")
        params.append(str(session_id))
    if status:
        clauses.append("status = ?")
        params.append(str(status))
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, int(limit)))
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
    finally:
        conn.close()
    return [_row_to_task(r) for r in rows]


def _update_fields(
    task_id: str, fields: Dict[str, Any], *, touch: bool = True, db_path: Path | None = None
) -> Dict[str, Any] | None:
    """更新字段。`touch=True`（默认）刷新 updated_at；测试/回填历史时间可传 False。"""
    if not fields:
        return get_task(task_id, db_path=db_path)
    fields = dict(fields)
    if touch:
        fields["updated_at"] = time.time()
    sets = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [str(task_id)]
    conn = _connect(db_path)
    try:
        cur = conn.execute(f"UPDATE tasks SET {sets} WHERE task_id = ?", tuple(params))
        conn.commit()
        if cur.rowcount == 0:
            return None
    finally:
        conn.close()
    return get_task(task_id, db_path=db_path)


def set_status(task_id: str, status: str, *, db_path: Path | None = None) -> Dict[str, Any] | None:
    if status not in VALID_STATUS:
        raise ValueError(f"未知任务状态: {status}")
    return _update_fields(task_id, {"status": status}, db_path=db_path)


def set_steps(task_id: str, steps: List[Any], *, db_path: Path | None = None) -> Dict[str, Any] | None:
    return _update_fields(
        task_id, {"steps_json": json.dumps(_normalize_steps(steps), ensure_ascii=False)}, db_path=db_path
    )


def set_exec_mode(task_id: str, exec_mode: str, *, db_path: Path | None = None) -> Dict[str, Any] | None:
    if exec_mode not in EXEC_MODES:
        raise ValueError(f"未知执行模式: {exec_mode}")
    return _update_fields(task_id, {"exec_mode": exec_mode}, db_path=db_path)


def set_git_state(task_id: str, git_state: str, *, db_path: Path | None = None) -> Dict[str, Any] | None:
    return _update_fields(task_id, {"git_state": str(git_state or "")}, db_path=db_path)


def add_file_refs(task_id: str, paths: List[str], *, db_path: Path | None = None) -> Dict[str, Any] | None:
    """合并文件引用（去重保序）。"""
    task = get_task(task_id, db_path=db_path)
    if task is None:
        return None
    merged = list(dict.fromkeys([*task.get("file_refs", []), *[str(p) for p in paths if str(p).strip()]]))
    return _update_fields(task_id, {"file_refs_json": json.dumps(merged, ensure_ascii=False)}, db_path=db_path)


def update_step(
    task_id: str,
    step_id: str,
    status: str,
    *,
    result_ref: str | None = None,
    desc: str | None = None,
    step_type: str | None = None,
    db_path: Path | None = None,
) -> Dict[str, Any] | None:
    """更新某步状态（可选改结果引用 / 描述 / 类型）。

    Returns:
        更新后的任务；任务或步骤不存在返回 None。
    """
    task = get_task(task_id, db_path=db_path)
    if task is None:
        return None
    steps = task.get("steps") or []
    hit = False
    for step in steps:
        if str(step.get("id")) != str(step_id):
            continue
        if status not in VALID_STEP_STATUS:
            raise ValueError(f"未知步骤状态: {status}")
        step["status"] = status
        if result_ref is not None:
            step["result_ref"] = str(result_ref)
        if desc is not None:
            step["desc"] = str(desc)
        if step_type is not None:
            step["type"] = str(step_type)
        step["ts"] = time.time()
        hit = True
        break
    if not hit:
        return None
    return _update_fields(
        task_id, {"steps_json": json.dumps(steps, ensure_ascii=False)}, db_path=db_path
    )


def pause_task(task_id: str, *, db_path: Path | None = None) -> Dict[str, Any] | None:
    """暂停：记录暂停前状态，便于原样恢复。"""
    task = get_task(task_id, db_path=db_path)
    if task is None:
        return None
    if task["status"] == STATUS_PAUSED:
        return task
    return _update_fields(
        task_id,
        {"status": STATUS_PAUSED, "exec_mode": task.get("exec_mode") or "code"},
        db_path=db_path,
    )


def resume_task(task_id: str, *, db_path: Path | None = None) -> Dict[str, Any] | None:
    """恢复：paused → running；已处于 running/done 等状态则原样返回。"""
    task = get_task(task_id, db_path=db_path)
    if task is None:
        return None
    if task["status"] != STATUS_PAUSED:
        return task
    return _update_fields(task_id, {"status": STATUS_RUNNING}, db_path=db_path)


def append_trajectory(
    task_id: str,
    *,
    step_id: str = "",
    tool: str = "",
    summary: str = "",
    status: str = "",
    ts: float | None = None,
    extra: Dict[str, Any] | None = None,
    db_path: Path | None = None,
) -> Dict[str, Any] | None:
    """追加一条轨迹记录（保留最近 _MAX_TRAJECTORY 条）。"""
    task = get_task(task_id, db_path=db_path)
    if task is None:
        return None
    entry: Dict[str, Any] = {
        "ts": float(ts if ts is not None else time.time()),
        "step_id": str(step_id or ""),
        "tool": str(tool or ""),
        "summary": str(summary or "")[:400],
        "status": str(status or ""),
    }
    if extra:
        entry["extra"] = extra
    traj = list(task.get("trajectory") or [])
    traj.append(entry)
    if len(traj) > _MAX_TRAJECTORY:
        traj = traj[-_MAX_TRAJECTORY:]
    return _update_fields(
        task_id, {"trajectory_json": json.dumps(traj, ensure_ascii=False)}, db_path=db_path
    )


def set_review(task_id: str, review: Dict[str, Any], *, db_path: Path | None = None) -> Dict[str, Any] | None:
    """写入 review 汇总（W123-04 用）。"""
    return _update_fields(
        task_id, {"review_json": json.dumps(review or {}, ensure_ascii=False)}, db_path=db_path
    )


def task_summary(task: Dict[str, Any], *, max_steps: int = 12) -> str:
    """给 LLM 看的一句话任务摘要（goal + 步骤进度 + 当前状态）。"""
    if not task:
        return ""
    steps = task.get("steps") or []
    done = sum(1 for s in steps if s.get("status") in (STEP_DONE, STEP_SKIPPED))
    lines = [
        f"任务 {task.get('task_id')}｜目标：{task.get('goal')}",
        f"状态：{task.get('status')}｜模式：{task.get('exec_mode')}｜进度：{done}/{len(steps)}",
    ]
    for step in steps[:max_steps]:
        lines.append(f"  [{step.get('status')}] {step.get('id')} {step.get('desc')}")
    if len(steps) > max_steps:
        lines.append(f"  …（另有 {len(steps) - max_steps} 步）")
    if task.get("file_refs"):
        lines.append(f"涉及文件：{', '.join(task['file_refs'][:8])}")
    return "\n".join(lines)


def stats(db_path: Path | None = None) -> Dict[str, Any]:
    """任务统计（按状态分档 + 表是否存在），供调试端点用。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status").fetchall()
    finally:
        conn.close()
    return {"by_status": {str(r[0]): int(r[1]) for r in rows}, "db": str(db_path or _default_db_path())}
