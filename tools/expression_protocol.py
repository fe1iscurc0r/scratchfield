# -*- coding: utf-8 -*-
"""NEKO 表情协议骨架（W65-01 · 脑/皮分离的表情事件映射，参考不抄 ACP）。

`<<expression>>` 事件 → 渲染层动作/表情映射。脑（Hermes/Naga）经 MCP + 事件总线
下发表情事件，皮（NEKO）只渲染。纯标准库。
"""
from __future__ import annotations

import re

# 表情事件 → 渲染动作映射（参考结构）
EXPRESSION_MAP = {
    "happy": "smile",
    "thinking": "blink",
    "alert": "raise_brow",
    "sleepy": "half_close",
}

_EVENT_RE = re.compile(r"<<(\w+)>>")


def extract_expressions(text: str) -> list[str]:
    """从文本提取 `<<expression>>` 事件。"""
    return _EVENT_RE.findall(text)


def map_expression(expr: str) -> str:
    """表情 → 渲染动作（未知名回退 neutral）。"""
    return EXPRESSION_MAP.get(expr, "neutral")


def render_actions(text: str) -> list[tuple[str, str]]:
    """文本 → [(表情, 动作)] 列表。"""
    return [(e, map_expression(e)) for e in extract_expressions(text)]


if __name__ == "__main__":
    print(render_actions("你好 <<happy>>，我在思考 <<thinking>>"))
