"""Agent Loop 故障快照与恢复（卷131 W131-03）。

run_agentic_loop 崩溃后恢复到崩溃前状态（消息历史 + loop 进度），
不是从头重跑。

设计（工单 W131-03）：
- LoopCheckpoint.save(session_id, messages, round_num, tool_results, timestamp)
  JSONL append-only（一行一快照，天然审计友好）
- load(session_id) → CheckpointState | None（最新快照）
- clear(session_id)：任务成功后删除快照（安全擦除）
- 敏感信息纪律：messages 存"摘要"（role + 截断内容），不存完整 LLM 输出；
  绝不存任何密钥字段（api_key/token 逐字段剔除——工单验收点）
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 消息摘要截断（防快照膨胀 + 不落完整 LLM 输出——工单 W131-03 验收 5）
_MSG_SUMMARY_LIMIT = 200
# 敏感键名（正则，命中即剔除值）
_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|authorization|credential)", re.I)
# 值内敏感模式（"api_key=sk-xxx" / "Bearer yyy" 这类嵌在正文里的凭证）
_SENSITIVE_VALUE_RE = re.compile(
    r"((?:api[_-]?key|token|secret|password|authorization|credential)"
    r"\s*[=:]\s*)(\S{4,})", re.I)
_BEARER_RE = re.compile(r"(Bearer\s+)([A-Za-z0-9_.\-]{8,})", re.I)
# 单 session 快照文件上限（超出滚动删除最旧——防无限膨胀）
_MAX_SNAPSHOTS_PER_SESSION = 50


def _default_store_dir() -> Path:
    return Path.home() / ".lumo" / "loop_checkpoints"


@dataclass
class CheckpointState:
    """一次快照的完整状态。"""
    session_id: str
    round_num: int
    messages_summary: list[dict] = field(default_factory=list)  # [{role, content(截断)}]
    tool_results_digest: list[dict] = field(default_factory=list)  # [{tool, ok, brief}]
    timestamp: float = 0.0
    meta: dict = field(default_factory=dict)  # 额外进度信息（如 summary_reason）


def _sanitize_value(v: Any, depth: int = 0) -> Any:
    """递归剔除敏感键值 + 值内敏感模式擦除（"api_key=sk-xxx" 嵌在正文也擦）。"""
    if depth > 6:
        return "..."
    if isinstance(v, dict):
        return {
            k: ("[REDACTED]" if _SENSITIVE_KEY_RE.search(str(k)) else _sanitize_value(val, depth + 1))
            for k, val in v.items()
        }
    if isinstance(v, list):
        return [_sanitize_value(x, depth + 1) for x in v[:20]]
    if isinstance(v, str):
        s = v
        if len(s) > _MSG_SUMMARY_LIMIT:
            s = s[:_MSG_SUMMARY_LIMIT] + f"...[截断,len={len(s)}]"
        # 值内敏感模式：api_key=xxx / token: xxx → 保留键名擦值
        s = _SENSITIVE_VALUE_RE.sub(lambda m: m.group(1) + "[REDACTED]", s)
        s = _BEARER_RE.sub(lambda m: m.group(1) + "[REDACTED]", s)
        return s
    return v


class LoopCheckpoint:
    """JSONL append-only 快照存储。

    用法：
        cp = LoopCheckpoint()
        cp.save("sess-1", messages, round_num=3, tool_results=[...])
        st = cp.load("sess-1")            # 最新快照
        cp.clear("sess-1")                # 任务成功后清理
    """

    def __init__(self, store_dir: str | Path | None = None):
        self._dir = Path(store_dir) if store_dir else _default_store_dir()
        self._lock = threading.Lock()

    def _path(self, session_id: str) -> Path:
        # session_id 清洗（防路径穿越）
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)[:64]
        return self._dir / f"{safe}.jsonl"

    # ---------- save ----------
    def save(self, session_id: str, messages: list[dict], round_num: int,
             tool_results: list[dict] | None = None,
             timestamp: float | None = None, meta: dict | None = None) -> None:
        """追加一条快照（messages 存摘要不存全文，敏感键剔除）。"""
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            summary = [
                {"role": m.get("role", "?"),
                 "content": _sanitize_value(m.get("content", ""))}
                for m in (messages or [])[-30:]  # 只留最近 30 条（防膨胀）
            ]
            digest = [
                {"tool": t.get("tool", "?"), "ok": bool(t.get("ok", True)),
                 "brief": _sanitize_value(t.get("brief", ""))}
                for t in (tool_results or [])[-20:]
            ]
            rec = {
                "session_id": session_id,
                "round_num": round_num,
                "messages_summary": summary,
                "tool_results_digest": digest,
                "timestamp": timestamp or time.time(),
                "meta": _sanitize_value(meta or {}),
            }
            p = self._path(session_id)
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._rotate(p)

    @staticmethod
    def _rotate(p: Path) -> None:
        """超过上限时保留最新 N 条（重写文件）。"""
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
            if len(lines) > _MAX_SNAPSHOTS_PER_SESSION:
                keep = lines[-_MAX_SNAPSHOTS_PER_SESSION:]
                p.write_text("\n".join(keep) + "\n", encoding="utf-8")
        except OSError:
            pass  # 滚动失败不影响主流程（下次 save 再试）

    # ---------- load ----------
    def load(self, session_id: str) -> CheckpointState | None:
        """读最新快照；无快照返回 None（resume 判断用）。"""
        p = self._path(session_id)
        if not p.exists():
            return None
        try:
            lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
            if not lines:
                return None
            rec = json.loads(lines[-1])
            return CheckpointState(
                session_id=rec["session_id"],
                round_num=rec["round_num"],
                messages_summary=rec.get("messages_summary", []),
                tool_results_digest=rec.get("tool_results_digest", []),
                timestamp=rec.get("timestamp", 0.0),
                meta=rec.get("meta", {}),
            )
        except (json.JSONDecodeError, KeyError, OSError):
            return None  # 快照损坏 → 当无快照处理（resume 会从头跑，不崩）

    # ---------- clear ----------
    def clear(self, session_id: str) -> None:
        """任务成功后删除快照文件（安全擦除：先覆写再删）。"""
        with self._lock:
            p = self._path(session_id)
            if not p.exists():
                return
            try:
                # 覆写后删除（best-effort 安全擦除）
                size = p.stat().st_size
                with open(p, "wb") as f:
                    f.write(b"\x00" * min(size, 1 << 20))
                p.unlink()
            except OSError:
                pass

    def has_checkpoint(self, session_id: str) -> bool:
        return self.load(session_id) is not None

    def list_sessions(self) -> list[str]:
        """列出所有有快照的 session（运维/测试用）。"""
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.jsonl"))


# 进程级单例
_cp: LoopCheckpoint | None = None


def get_loop_checkpoint(store_dir: str | Path | None = None) -> LoopCheckpoint:
    global _cp
    if _cp is None:
        _cp = LoopCheckpoint(store_dir)
    return _cp
