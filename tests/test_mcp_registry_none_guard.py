"""`mcpserver.mcp_registry.create_agent_instance` 的入参健壮性回归（2026-10-16）。

背景：该函数的 `except` 处理器里写了 ``manifest.get('displayName', 'unknown')`` ——
当 ``manifest is None`` 时，**处理器自身会再抛 AttributeError**，把真实异常掩盖成
``'NoneType' object has no attribute 'get'``（2026-10-16 排查时实际踩到）。

可达性说明（写在这里免得后人当成"活 bug"）：
- 生产两条调用路都守住了 —— ``ensure_hot`` 写的是 ``cold.get("manifest") or … or {}``，
  扫描循环有 ``if not manifest: continue``；``_COLD_TABLE`` 只由这两条路写入；
- 但本函数在 ``__all__`` 里是**公共 API** ⇒ 任何直接调用方都可能踩到。
⇒ 这是健壮性修复，不是行为变更：对**真值** manifest，``(manifest or {})`` 与
  ``manifest`` 完全等价，日志输出一个字都不变。

只测纯逻辑：不启动服务、不联网；传 None/{} 走错误路径即返回。
"""
from __future__ import annotations

from mcpserver.mcp_registry import create_agent_instance


def test_none_manifest_returns_none_not_attributeerror() -> None:
    """`manifest=None` ⇒ 返回 None；不许在 except 处理器里再抛 AttributeError。"""
    assert create_agent_instance(None, "whatever") is None


def test_empty_manifest_returns_none() -> None:
    """`manifest={}` ⇒ 走 Format D 推导（导入不存在）⇒ 错误路径 ⇒ 返回 None。"""
    assert create_agent_instance({}, "whatever") is None


def test_missing_entrypoint_module_returns_none() -> None:
    """真值 manifest 但入口模块不存在 ⇒ 照旧走错误路径返回 None（处理器没被改坏）。"""
    manifest = {
        "name": "no_such_agent_xyz",
        "entryPoint": {"module": "mcpserver.no_such_agent_xyz.server", "class": "Bridge"},
    }
    assert create_agent_instance(manifest, "no_such_agent_xyz") is None
