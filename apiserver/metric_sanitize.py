"""指标/日志文本的脱敏工具（W120-04）。

为什么单独一个模块：`apiserver/telemetry.py` 里的脱敏只管**键名**（`api_key=...`、JSON 的 key），
反查/参数里裸奔的 token 值会漏出去（实测：错误摘要里的 `sk-xxx` 原样出现在指标输出里）。
这里补一层**按值特征**的掩码，供指标登记与错误摘要统一调用。

注意：不 import telemetry（避免循环依赖），键名脱敏规则在此自带一份最小实现。
"""
from __future__ import annotations

import re

#: 键名级敏感词（与 telemetry._SENSITIVE_KEYS 同源的最小集，避免循环 import）
SENSITIVE_KEYS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "cookie",
    "session_key",
)

#: 值特征级掩码规则
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(
        r"(?i)\b(api[_-]?key|apikey|token|secret|password|authorization)\b"
        r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9._\-]{6,}"
    ),
    re.compile(r"\b(?:sk|pk|ghp|gho|xoxb|xoxp|akia)[-_][A-Za-z0-9._\-]{6,}"),
)


def mask_secrets(text: str) -> str:
    """按值特征掩码：Bearer …、key=value、裸 token（sk-/ghp_/xoxb-…）。"""
    out = str(text or "")
    out = _SECRET_VALUE_PATTERNS[0].sub(lambda m: f"{m.group(1)} ***", out)
    out = _SECRET_VALUE_PATTERNS[1].sub(lambda m: f"{m.group(1)}=***", out)
    out = _SECRET_VALUE_PATTERNS[2].sub("***", out)
    return out


def _key_is_sensitive(key: str) -> bool:
    lowered = str(key).strip().lower()
    return any(flag in lowered for flag in SENSITIVE_KEYS)


def sanitize_value(value, *, key: str | None = None, depth: int = 0):
    """递归脱敏任意结构：敏感键的值替换为 ***，字符串再走值特征掩码。"""
    if depth > 4:
        return "<max-depth>"
    if key is not None and _key_is_sensitive(key):
        return "***"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return mask_secrets(value)
    if isinstance(value, dict):
        return {str(k): sanitize_value(v, key=str(k), depth=depth + 1) for k, v in list(value.items())[:50]}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_value(item, depth=depth + 1) for item in list(value)[:50]]
    return mask_secrets(str(value))


def sanitize_metric_text(text: str, *, limit: int = 200) -> str:
    """指标输出统一入口：值特征掩码 → 截断。"""
    return mask_secrets(str(text or ""))[: max(1, int(limit))]
