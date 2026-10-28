"""anthropic SDK 1.x 兼容层（工单 228 任务三 · v5.2.9 起点 PoC）。

## 背景：1.x 相对 0.x 的三处破坏性变化

（对应 PR#263 `anthropic 0.94 → 1.11`，详见 `docs/DEPENDABOT-MAJOR-UPGRADE-SOP.md` S2）

1. **client 初始化收紧**：推荐 env-only ``Anthropic()``（读 ``ANTHROPIC_API_KEY``），
   sync / async 分离为 ``Anthropic`` / ``AsyncAnthropic``。
2. **``max_tokens`` 变必填**（0.x 可省；1.x 缺失即 400）。
3. **``system`` 提到顶层**（0.x 允许塞在 ``messages`` 列表里）；``messages[].content``
   从 ``str`` 扩到 list-of-blocks。

## 本层做什么 / 不做什么

**做**：提供一个「旧式 kwargs 进、1.x 形态出」的适配层，供 v5.2.9 决定是否整体切换时复用：

- :func:`get_client` —— 优先 env 模式 ``Anthropic()``，回退显式 ``api_key``（读仓内 config）；
- :func:`messages_create` —— 把旧式入参翻译成 1.x 形态后再调 ``client.messages.create``。

**不做**：**不替换任何现有调用点**（工单硬约束）。本仓现有 anthropic 调用集中在
``NEKO/N.E.K.O/utils/llm_client/`` —— 那是**上游同步代码**，本层只在旁边验证"这套翻译
逻辑跑得通"，真正的替换留给 v5.2.9。落点清单见
``docs/audit/anthropic-call-sites-2026-10-13.md``。

## 依赖缺失时的行为

真实 SDK 没装时 :func:`get_client` / :func:`load_sdk` 抛 :class:`AnthropicCompatError`
而**不是**裸 ``ImportError`` —— 调用方可据此降级，而不是崩在一句 import 上。
纯翻译函数（:func:`normalize_messages` / :func:`to_blocks`）**不碰 SDK**，故可离线单测。

## 与工单稿的命名偏差

工单稿把工厂写作 ``_get_client()``。本模块以**公开名** :func:`get_client` 导出
（同一实现）：兼容层是给 v5.2.9 复用的公共设施，私有下划线名不合适。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ENV_API_KEY = "ANTHROPIC_API_KEY"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MODEL = "claude-3-5-sonnet-latest"


class AnthropicCompatError(RuntimeError):
    """兼容层无法继续时抛出的统一异常（避免裸 ImportError 炸调用链）。"""


def load_sdk() -> Any:
    """返回 anthropic 模块；未安装时抛 :class:`AnthropicCompatError`。"""
    try:
        import anthropic
    except Exception as exc:  # noqa: BLE001 - 任何导入失败都归一为"不可用"
        raise AnthropicCompatError("未安装 anthropic SDK；兼容层无法工作") from exc
    return anthropic


def api_key_from_repo_config(config_path: str | Path | None = None) -> str | None:
    """从仓内 ``config.json`` 的 ``api.api_key`` 取 key（读不到返回 None）。

    ⚠️ 沿用本仓的**权威配置口径**：不是 ``~/.hermes/config.yaml``（该路径实测不存在，
    见 ``tools/switch_llm_provider.py`` 头注与工单 228 任务一）。
    """
    try:
        if config_path is None:
            from system.config import get_config_path

            cfg = Path(get_config_path())
        else:
            cfg = Path(config_path)
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 缺文件/坏 JSON 一律视为"取不到 key"
        return None
    raw_api = data.get("api") if isinstance(data, dict) else None
    api = raw_api if isinstance(raw_api, dict) else {}
    key = api.get("api_key")
    return key if isinstance(key, str) and key else None


def get_client(
    *,
    api_key: str | None = None,
    async_client: bool = False,
    config_path: str | Path | None = None,
    **kwargs: Any,
) -> Any:
    """构造 anthropic client：**显式 key / env 优先，仓内 config 兜底**。

    :param api_key: 显式 key；None 时依次看 ``ANTHROPIC_API_KEY`` 与仓内 config
    :param async_client: True → ``AsyncAnthropic``（1.x 起 sync/async 是分离的类）
    :param config_path: 注入配置路径（测试用）
    """
    sdk = load_sdk()
    cls_name = "AsyncAnthropic" if async_client else "Anthropic"
    cls = getattr(sdk, cls_name, None)
    if cls is None:
        raise AnthropicCompatError(f"anthropic SDK 缺少 {cls_name}（版本过旧？）")

    key = api_key or os.environ.get(ENV_API_KEY) or api_key_from_repo_config(config_path)
    if key:
        return cls(api_key=key, **kwargs)
    return cls(**kwargs)  # env-only 模式（1.x 推荐）


def to_blocks(content: Any) -> Any:
    """``str`` → ``[{"type": "text", "text": ...}]``；其它类型原样返回。

    1.x 把 ``messages[].content`` 从"仅 str"扩到"str 或 block 列表"。本函数提供
    单向转换，供需要显式 block 形态的调用方使用（默认不启用，见 ``messages_create``）。
    """
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content


def normalize_messages(
    messages: Any,
    *,
    system: Any = None,
    wrap_text_blocks: bool = False,
) -> tuple[list[Any], str | None]:
    """旧式 ``messages`` → ``(1.x messages, 顶层 system)``。

    处理 0.x 的两种旧写法：

    - ``{"role": "system"}`` 混在 ``messages`` 里 → 抽出来并入顶层 ``system``；
    - ``content`` 为 ``str`` → 可选包成 block 列表（``wrap_text_blocks=True``）。

    ``system`` 参数的优先级最高（显式传的排在最前）。
    """
    out: list[Any] = []
    collected: list[Any] = []

    for msg in messages or []:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        if msg.get("role") == "system":
            collected.append(msg.get("content"))
            continue
        content = msg.get("content")
        out.append({
            "role": msg.get("role"),
            "content": to_blocks(content) if wrap_text_blocks else content,
        })

    if system is not None:
        collected.insert(0, system)

    merged = "\n\n".join(str(s) for s in collected if s) if collected else None
    return out, merged


def messages_create(
    client: Any,
    *,
    messages: Any,
    model: str | None = None,
    max_tokens: int | None = None,
    system: Any = None,
    wrap_text_blocks: bool = False,
    **kwargs: Any,
) -> Any:
    """旧式入参 → 1.x 形态后调用 ``client.messages.create(...)``。

    三处强制翻译（对应 1.x 的破坏性变更）：

    1. ``system`` 提到**顶层**（从 ``messages`` 里抽出来，见 :func:`normalize_messages`）；
    2. ``max_tokens`` **必填**（未传则用 :data:`DEFAULT_MAX_TOKENS`）；
    3. ``model`` 未传则用 :data:`DEFAULT_MODEL`。
    """
    normalized, merged_system = normalize_messages(
        messages, system=system, wrap_text_blocks=wrap_text_blocks,
    )
    payload: dict[str, Any] = dict(kwargs)
    payload["messages"] = normalized
    payload["model"] = model or DEFAULT_MODEL
    payload["max_tokens"] = max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS
    if merged_system is not None:
        payload["system"] = merged_system
    return client.messages.create(**payload)


def extract_text(response: Any) -> str:
    """从 SDK 响应里抽出纯文本（容忍 SDK 对象与纯 dict 两种形态）。"""
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
            else:
                parts.append(str(getattr(block, "text", "") or ""))
        return "".join(parts)
    return content if isinstance(content, str) else ""
