"""agent_governance 的统一错误与错误码（工单 241）。

调用方与测试**按错误码断言**，不按文案 —— 文案可以改，码是契约。
"""

from __future__ import annotations

from typing import Any

# --- 密钥 / 签名（身份证明层）---
E_MISSING_KEY = "GOV_MISSING_KEY"
E_BAD_SIGNATURE = "GOV_BAD_SIGNATURE"
E_CONTENT_MISMATCH = "GOV_CONTENT_MISMATCH"
E_MALFORMED = "GOV_MALFORMED"

# --- 令牌（授权层）---
E_TOKEN_MISSING = "GOV_TOKEN_MISSING"
E_TOKEN_EXPIRED = "GOV_TOKEN_EXPIRED"
E_AGENT_MISMATCH = "GOV_AGENT_MISMATCH"
E_PROVIDER_MISMATCH = "GOV_PROVIDER_MISMATCH"

# --- 审计（运行时层）---
E_AUDIT_UNWRITABLE = "GOV_AUDIT_UNWRITABLE"

# --- 接线层 ---
E_INTERNAL = "GOV_INTERNAL_ERROR"

ALL_CODES: frozenset[str] = frozenset(
    {
        E_MISSING_KEY,
        E_BAD_SIGNATURE,
        E_CONTENT_MISMATCH,
        E_MALFORMED,
        E_TOKEN_MISSING,
        E_TOKEN_EXPIRED,
        E_AGENT_MISMATCH,
        E_PROVIDER_MISMATCH,
        E_AUDIT_UNWRITABLE,
        E_INTERNAL,
    }
)


class GovernanceError(Exception):
    """治理层统一异常：携带稳定 ``code`` + 人类可读 ``message`` + 结构化 ``detail``。"""

    def __init__(self, code: str, message: str, **detail: Any) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.detail: dict[str, Any] = detail

    def to_dict(self) -> dict[str, Any]:
        """序列化为 MCP 标准错误 JSON 的载荷（不含 status 包装）。"""
        out: dict[str, Any] = {"error_type": "governance_error", "code": self.code, "message": self.message}
        if self.detail:
            out["detail"] = self.detail
        return out

    def __str__(self) -> str:  # pragma: no cover - 仅调试可读性
        return f"{self.code}: {self.message}"
