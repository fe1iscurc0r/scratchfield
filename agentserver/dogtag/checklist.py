"""
军牌系统 Checklist — 持久化待办条目

条目来源：
- LLM 从对话中自动提取 (source="llm")
- 用户通过 API 手动增删 (source="user")

持久化路径：~/.naga/heartbeat_checklist.json
"""

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ChecklistItem(BaseModel):
    """单条 checklist 条目"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    content: str
    source: str = "llm"  # "llm" | "user"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"  # "pending" | "done" | "dismissed"
    priority: str = "normal"  # "low" | "normal" | "high"
    notes: str = ""


class HeartbeatChecklist(BaseModel):
    """整个 checklist 文件结构"""

    items: list[ChecklistItem] = []
    last_updated: str = ""


# ── 路径 ──


def get_checklist_path() -> Path:
    """~/.naga/heartbeat_checklist.json"""
    p = Path.home() / ".naga" / "heartbeat_checklist.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ── 读写 ──


def load_checklist() -> HeartbeatChecklist:
    """从磁盘加载 checklist，文件不存在返回空 checklist"""
    path = get_checklist_path()
    if not path.exists():
        return HeartbeatChecklist()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return HeartbeatChecklist(**data)
    except Exception as e:
        logger.warning(f"[Checklist] 加载失败，返回空 checklist: {e}")
        return HeartbeatChecklist()


def save_checklist(cl: HeartbeatChecklist) -> bool:
    """持久化 checklist 到磁盘"""
    try:
        cl.last_updated = datetime.now().isoformat()
        path = get_checklist_path()
        path.write_text(
            json.dumps(cl.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception as e:
        logger.error(f"[Checklist] 保存失败: {e}")
        return False


# ── 批量操作 ──

# 模块级别的批量操作状态
_batch_checklist: HeartbeatChecklist | None = None


@contextmanager
def batch_update():
    """批量操作上下文管理器 — 多次 add_item/update_item 只做一次 load + save

    用法：
        with batch_update():
            add_item("task1", source="llm")
            add_item("task2", source="llm")
            update_item("xxx", status="done")
        # 退出时自动保存一次
    """
    global _batch_checklist
    _batch_checklist = load_checklist()
    try:
        yield _batch_checklist
    finally:
        save_checklist(_batch_checklist)
        _batch_checklist = None


# ── CRUD ──


def add_item(
    content: str,
    source: str = "user",
    priority: str = "normal",
) -> ChecklistItem:
    """新增一条 checklist 条目并持久化

    在 batch_update() 上下文中，跳过独立的 load/save，共享同一份 checklist。
    """
    global _batch_checklist
    cl = _batch_checklist if _batch_checklist is not None else load_checklist()
    item = ChecklistItem(content=content, source=source, priority=priority)
    cl.items.append(item)
    if _batch_checklist is None:
        save_checklist(cl)
    logger.info(f"[Checklist] 新增条目: {item.id} ({source}) — {content[:50]}")
    return item


def update_item(item_id: str, **kwargs) -> bool:
    """更新指定条目的字段（status, notes, priority 等）

    在 batch_update() 上下文中，跳过独立的 load/save，共享同一份 checklist。
    """
    global _batch_checklist
    cl = _batch_checklist if _batch_checklist is not None else load_checklist()
    for item in cl.items:
        if item.id == item_id:
            for k, v in kwargs.items():
                if hasattr(item, k):
                    setattr(item, k, v)
            if _batch_checklist is None:
                save_checklist(cl)
            logger.info(f"[Checklist] 更新条目 {item_id}: {kwargs}")
            return True
    logger.warning(f"[Checklist] 条目不存在: {item_id}")
    return False


def remove_item(item_id: str) -> bool:
    """删除指定条目"""
    cl = load_checklist()
    original_len = len(cl.items)
    cl.items = [i for i in cl.items if i.id != item_id]
    if len(cl.items) < original_len:
        save_checklist(cl)
        logger.info(f"[Checklist] 删除条目: {item_id}")
        return True
    logger.warning(f"[Checklist] 条目不存在: {item_id}")
    return False


def get_pending_items() -> list[ChecklistItem]:
    """返回所有 status == 'pending' 的条目"""
    cl = load_checklist()
    return [i for i in cl.items if i.status == "pending"]
