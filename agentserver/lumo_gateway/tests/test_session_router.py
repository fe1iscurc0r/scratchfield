"""session_router 测试：SQLite 持久化 + session_id 合法性映射。"""

from __future__ import annotations

import re
from pathlib import Path

from agentserver.lumo_gateway.session_router import SessionRouter, make_session_id

_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def test_get_or_create_persists_and_reuses(tmp_path: Path) -> None:
    """同一路由键重复获取返回同一 session_id，且落盘可重读。"""
    db = str(tmp_path / "sessions.db")
    router = SessionRouter(db)
    a = router.get_or_create("qq", "user_123")
    b = router.get_or_create("qq", "user_123")
    assert a.route_key == "qq:user_123"
    assert a.session_id == b.session_id
    assert router.count() == 1
    assert _SESSION_ID_RE.match(a.session_id) is not None

    # 模拟重启：新实例读同一 DB
    router.close()
    router2 = SessionRouter(db)
    c = router2.get_or_create("qq", "user_123")
    assert c.session_id == a.session_id  # 重启不丢映射
    assert router2.count() == 1
    router2.close()


def test_make_session_id_colon_mapped_to_underscore() -> None:
    """冒号路由键 → 合法 session_id（冒号非法，替换为下划线）。"""
    sid = make_session_id("qq:user_123")
    assert sid == "qq_user_123"
    assert _SESSION_ID_RE.match(sid) is not None


def test_make_session_id_too_long_falls_back_to_sha1() -> None:
    """超长路由键 → sha1 摘要截断，确定性且合法。"""
    long_key = "qq:" + "x" * 100
    sid = make_session_id(long_key)
    assert len(sid) <= 64
    assert _SESSION_ID_RE.match(sid) is not None
    assert sid == make_session_id(long_key)  # 确定性


def test_distinct_users_get_distinct_sessions(tmp_path: Path) -> None:
    """不同 user_id 各得独立 session。"""
    db = str(tmp_path / "s.db")
    router = SessionRouter(db)
    u1 = router.get_or_create("qq", "u1")
    u2 = router.get_or_create("qq", "u2")
    assert u1.session_id != u2.session_id
    assert router.count() == 2
    router.close()
