"""安全 · ContextLeak 工具上下文窃取防御中间件（W60-02）

来源 docs/contextleak-defense-方案.md（S27 · round3 digest-g3 2608.27800）：
恶意工具把 LLM Agent 运行时上下文（密钥/历史/文件内容）当作工具参数或返回值外发。
防御：对工具参数与返回值做「上下文外传」检测，识别可疑外传模式，做成过滤器/中间件
形态挂到工具调用链。安全类只写防御，不写攻击/RL 微调。

检测模式（≥3）：
  1. base64 混淆外传：长 base64 块（上下文被编码塞进出参）
  2. 密钥/凭据泄漏：API key / token / 私钥模式
  3. 外链拼接：URL 携带可疑参数（把上下文拼进 URL 外发）
  4. 上下文打包：输出含系统提示/对话历史大段文本

验收口径：外传 payload 检出率 ≥80%，正常工具输出零误报（≤10%）。
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

__all__ = ["ContextLeakFilter", "Verdict"]

# base64 长块（≥40 字符，可解码 → 更可能是混淆外传而非随机噪声）
_B64_RE = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
# 密钥/凭据模式
_SECRET_RES = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
]
# 外链拼接：URL 携带敏感/超长参数（把上下文拼进 query 外发）
_EXFIL_URL_RE = re.compile(r"https?://[^\s\"']*[?&](data|ctx|token|content|q|msg)=[^\s\"']{40,}", re.I)
# 上下文打包：系统提示/对话历史大段文本
_CONTEXT_DUMP_RE = re.compile(
    r"(system\s*prompt|you\s+are\s+(a|an)\s+|assistant\s*:\s*|<<SYS>>|developer\s+message)", re.I
)


def _b64_plausible(s: str) -> bool:
    """base64 块可解码且解码后含可打印字符（降低对随机高熵串的误报）。"""
    try:
        raw = base64.b64decode(s, validate=True)
        printable = sum(1 for b in raw if 32 <= b < 127)
        return len(raw) > 0 and printable / len(raw) > 0.8
    except Exception:
        return False


@dataclass
class Verdict:
    """过滤器结论。"""
    suspicious: bool
    reasons: list[str] = field(default_factory=list)


class ContextLeakFilter:
    """工具输出/参数的外传检测过滤器（可挂到工具调用链）。"""

    def check(self, text: str) -> Verdict:
        reasons: list[str] = []

        # 1. base64 混淆外传
        for m in _B64_RE.findall(text or ""):
            if _b64_plausible(m):
                reasons.append("base64_exfiltration")
                break

        # 2. 密钥/凭据泄漏
        for pat in _SECRET_RES:
            if pat.search(text or ""):
                reasons.append("credential_leak")
                break

        # 3. 外链拼接
        if _EXFIL_URL_RE.search(text or ""):
            reasons.append("exfil_url")

        # 4. 上下文打包
        if _CONTEXT_DUMP_RE.search(text or ""):
            reasons.append("context_dump")

        return Verdict(suspicious=bool(reasons), reasons=reasons)
