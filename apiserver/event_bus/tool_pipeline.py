"""工具三段管道：guard → pre-execute → execute → post-execute（卷124 W124-03）。

卷119 已有 **pre-execute 门**（`TOOL_PRE_EXECUTE` waterfall：审计/敏感/熔断/确认）；
本模块补两端，构成 DeepSeek Harness 式的三段管道：

```
① guard        TOOL_GUARD（本模块）      参数合法性：路径/语言/数值范围/manifest 声明
② pre-execute  TOOL_PRE_EXECUTE（卷119） 政策：审计/敏感工具/熔断/写操作确认
③ execute      工具真正执行
④ post-execute TOOL_POST_EXECUTE（本模块）事实广播：审计上报 / 失败统计 / 结果归一化检查
```

- guard 被拒 → **不进** pre-execute，更不进执行（省一次策略判定）
- post-execute 用**正交字段**描述事实：`ok / exit_code / signal / error / duration`，
  timeout / aborted / exit 分开，不混编码（对齐 DSH 失败纪律）

guard 覆盖的规则（默认集，全部可关）：

| 工具 | 检查 | 依赖 |
| --- | --- | --- |
| `file_write` / `file_edit` | 路径必须落在会话工作区内（拒绝 `..`/绝对路径/链接逃逸） | 卷121 sandbox |
| `code_exec` | `language` 必须在白名单（python/javascript） | 本地常量 |
| `shell_exec` | `command` 非空且在沙箱白名单（预检，执行层还会再判一次） | 卷121 sandbox |
| 任意 MCP 工具 | manifest 声明的 `parameters`：必填项齐全 + 类型 + 数值范围 | mcpserver manifest |
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: code_exec 允许的语言（与 Code Workspace 的 `interpreter_for` 对齐）
ALLOWED_LANGUAGES = ("python", "python3", "javascript", "node", "js")

#: 需要校验路径落在工作区内的工具
_PATH_TOOLS = ("file_write", "file_edit", "file_read")


def _audit(record: Dict[str, Any]) -> None:
    """走卷119 同一个审计通道（tool_calls.ndjson，phase=guard/post_execute）。"""
    try:
        from .tool_gate import get_tool_gate_runtime

        get_tool_gate_runtime().audit({"ts": time.time(), **record})
    except Exception:  # noqa: BLE001 - 审计失败不影响工具回路
        logger.debug("[tool_pipeline] 审计落盘失败", exc_info=True)


def _short_args(args: Any, max_chars: int = 300) -> Any:
    try:
        from .tool_gate import _sanitize_args

        return _sanitize_args(args, max_chars=max_chars)
    except Exception:  # noqa: BLE001
        return str(args)[:max_chars]


# ---------------------------------------------------------------------------
# ① guard：参数合法性
# ---------------------------------------------------------------------------


def _guard_path(tool: str, args: Dict[str, Any]) -> str | None:
    from mcpserver.code_workspace.sandbox import SandboxError, resolve_in_workspace

    path = str(args.get("path") or "")
    if not path:
        return "缺少 path 参数"
    session_id = str(args.get("session_id") or "default")
    try:
        resolve_in_workspace(path, session_id)
    except SandboxError as e:
        return f"{e.code}: {e.message}"
    except Exception as e:  # noqa: BLE001
        return f"path_check_failed: {e}"
    return None


def _guard_language(tool: str, args: Dict[str, Any]) -> str | None:
    lang = str(args.get("language") or "python").strip().lower()
    if lang not in ALLOWED_LANGUAGES:
        return f"language 不支持: {lang}（允许 {', '.join(ALLOWED_LANGUAGES)}）"
    return None


def _guard_shell(tool: str, args: Dict[str, Any]) -> str | None:
    from mcpserver.code_workspace.sandbox import SandboxError, validate_command

    command = str(args.get("command") or "").strip()
    if not command:
        return "缺少 command 参数"
    try:
        validate_command(command)
    except SandboxError as e:
        return f"{e.code}: {e.message}"
    except Exception as e:  # noqa: BLE001
        return f"command_check_failed: {e}"
    return None


def _guard_manifest_params(tool: str, args: Dict[str, Any]) -> str | None:
    """按 manifest 声明校验：必填齐全 + 数值范围（声明了 minimum/maximum 才查）。"""
    try:
        from mcpserver.mcp_registry import MANIFEST_CACHE
    except Exception:  # noqa: BLE001
        return None
    for manifest in (MANIFEST_CACHE or {}).values():
        caps = manifest.get("capabilities") or {}
        for cmd in caps.get("invocationCommands") or []:
            if str(cmd.get("command") or "") != tool:
                continue
            params = cmd.get("parameters") or {}
            props = params.get("properties") or {}
            for name in params.get("required") or []:
                if name not in args or args.get(name) in (None, ""):
                    return f"缺少必填参数 {name}"
            for name, spec in props.items():
                if name not in args or not isinstance(spec, dict):
                    continue
                value = args.get(name)
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    low, high = spec.get("minimum"), spec.get("maximum")
                    if isinstance(low, (int, float)) and value < low:
                        return f"参数 {name}={value} 小于最小值 {low}"
                    if isinstance(high, (int, float)) and value > high:
                        return f"参数 {name}={value} 大于最大值 {high}"
            return None
    return None


_GUARD_RULES: Dict[str, List[Callable[[str, Dict[str, Any]], str | None]]] = {
    "file_write": [_guard_path],
    "file_edit": [_guard_path],
    "file_read": [_guard_path],
    "code_exec": [_guard_language],
    "shell_exec": [_guard_shell],
    "__all__": [_guard_manifest_params],
}


def check_args(tool: str, args: Dict[str, Any]) -> str | None:
    """跑该工具的全部 guard 规则；返回第一个失败原因（None = 通过）。"""
    clean = {k: v for k, v in (args or {}).items() if not str(k).startswith("_")}
    for rule in [*_GUARD_RULES.get(tool, []), *_GUARD_RULES["__all__"]]:
        try:
            reason = rule(tool, clean)
        except Exception as e:  # noqa: BLE001 - 规则自身异常不拦工具（fail-open）
            logger.warning("[tool_pipeline] guard 规则异常（%s），放行: %s", rule.__name__, e)
            continue
        if reason:
            return reason
    return None


def guard_tool(tool: str, args: Dict[str, Any]) -> Dict[str, Any] | None:
    """guard 阶段入口：非法返回 `{error:"invalid_args", reason}`，合法返回 None。"""
    reason = check_args(tool, args)
    if not reason:
        return None
    _audit({"phase": "guard", "tool": tool, "result": "rejected", "reason": reason,
            "args": _short_args(args)})
    logger.warning("[tool_pipeline] guard 拒绝 %s：%s", tool, reason)
    return {"error": "invalid_args", "reason": reason}


# ---------------------------------------------------------------------------
# ④ post-execute：事实广播 + 正交字段
# ---------------------------------------------------------------------------


def _embedded_payload(result: Any) -> Dict[str, Any]:
    """工具结果里可能嵌着 JSON（如 `{"ok": false, "exit_code": 1}`），抽出来用。"""
    import json

    text = str(result or "").strip()
    if not text.startswith("{"):
        return {}
    try:
        parsed = json.loads(text)
    except Exception:  # noqa: BLE001
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_result(result: Dict[str, Any], *, duration_s: float) -> Dict[str, Any]:
    """补齐正交事实字段：`ok / exit_code / signal / error / duration`。

    不覆盖工具自己给出的值；MCP 桥嵌在返回体里的 ok/exit_code 也会被提取。
    """
    payload = _embedded_payload(result.get("result"))
    out = dict(result)
    status = str(result.get("status") or "")
    ok = result.get("ok")
    if ok is None:
        ok = payload.get("ok")
    if ok is None:
        ok = status == "success" and not payload.get("error")
    out["ok"] = bool(ok)
    if "exit_code" not in out:
        out["exit_code"] = payload.get("exit_code")
    if "signal" not in out:
        out["signal"] = payload.get("signal")
    if "error" not in out:
        out["error"] = payload.get("error") or result.get("message")
    if "duration" not in out:
        out["duration"] = round(float(duration_s), 3)
    out["aborted"] = bool(payload.get("aborted") or result.get("error") == "timeout")
    return out


def emit_post_execute(
    *,
    tool: str,
    args: Any,
    result: Dict[str, Any],
    duration_s: float,
    session_id: str = "",
    ok: bool,
) -> Dict[str, Any] | None:
    """广播 `TOOL_POST_EXECUTE` 事实（审计 + 失败统计 + 归一化检查）。

    Returns:
        事件 payload（便于调用方/测试断言）；广播失败返回 None。
    """
    normalized = normalize_result(result, duration_s=duration_s)
    # 外层 status 可能说成功、返回体里却写着 ok=false（MCP 桥常见）——事实以两者都成立为准
    ok_final = bool(ok) and bool(normalized.get("ok", ok))
    event = {
        "tool": tool,
        "session_id": session_id,
        "args": _short_args(args),
        "status": str(result.get("status") or ""),
        "ok": ok_final,
        "exit_code": normalized.get("exit_code"),
        "signal": normalized.get("signal"),
        "error": normalized.get("error"),
        "aborted": normalized.get("aborted"),
        "duration": normalized.get("duration"),
        "result_digest": str(result.get("result") or "")[:300],
        "ts": time.time(),
    }
    _audit({"phase": "post_execute", **{k: v for k, v in event.items() if k != "ts"}})
    # 失败统计喂卷119 熔断门（成功清零、失败累加）
    try:
        from .tool_gate import get_tool_gate_runtime

        get_tool_gate_runtime().record_result(tool, ok_final)
    except Exception:  # noqa: BLE001
        logger.debug("[tool_pipeline] 失败统计回填失败", exc_info=True)
    try:
        from . import get_bus

        get_bus().emit("lumo.tool.post-execute", event)
    except Exception as e:  # noqa: BLE001 - 广播失败不影响结果返回
        logger.debug("[tool_pipeline] post-execute 广播失败: %s", e)
        return None
    return event


# ---------------------------------------------------------------------------
# guard 阶段的 bus 挂载（可选：不经 loop 的调用方也能享受同一套校验）
# ---------------------------------------------------------------------------


def register_guard(bus: Any) -> Any:
    """把 guard 挂到 `TOOL_GUARD`（串行链）：调用方用 `bus.bail(TOOL_GUARD, event)` 取判定，
    返回非 None 即「拒绝 + 原因」。

    说明：loop 里 guard 是直接调用（同步、省一次总线往返），这里的挂载是给
    「不走 loop 的调用方」用的同一条规则通道。
    """
    from .topics import Topics

    def _handler(event: Dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        tool = str(event.get("tool") or "")
        args_payload = event.get("args") or {}
        verdict = guard_tool(tool, args_payload if isinstance(args_payload, dict) else {})
        return verdict or None

    try:
        disposer = bus.on(Topics.TOOL_GUARD, _handler)
        logger.info("[tool_pipeline] guard 已挂到 TOOL_GUARD（阶段① 参数校验）")
        return disposer
    except Exception as e:  # noqa: BLE001
        logger.warning("[tool_pipeline] guard 挂载失败: %s", e)
        return None


def pipeline_summary() -> Dict[str, Any]:
    """调试用：当前管道阶段与 guard 规则表。"""
    return {
        "stages": ["guard", "pre-execute", "execute", "post-execute"],
        "topics": {
            "guard": "lumo.tool.guard",
            "pre_execute": "lumo.tool.pre-execute",
            "post_execute": "lumo.tool.post-execute",
        },
        "guard_rules": {tool: [r.__name__ for r in rules] for tool, rules in _GUARD_RULES.items()},
        "allowed_languages": list(ALLOWED_LANGUAGES),
    }
