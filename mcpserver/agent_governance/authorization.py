"""授权令牌层 —— agent 间调用走短期 token，token 与 provider/key 绑定，到期失效。

工单 241 §2 任务一第 1 条。默认 TTL 1 小时（``DEFAULT_TTL_S``），可逐个 token 覆写。

token 形态（三段点分，便于无依赖解析）::

    v1.<b64url(payload_json)>.<b64url(hmac_sha256)>

payload = ``{v, agent_id, provider, key_id, iat, exp, nonce}``，全部字段参与 HMAC。

失败一律以**稳定错误码**表达（工单 §2 任务二 场景 B/C 直接断言这些码）：

===================  ================================
错误码               触发条件
===================  ================================
``GOV_MALFORMED``    段数不对 / base64 坏 / payload 非 JSON / 缺字段
``GOV_BAD_SIGNATURE`` key_id 不符或 HMAC 不符（伪造 agent ID 落这里）
``GOV_TOKEN_EXPIRED`` 签名有效但 ``exp <= now``
``GOV_AGENT_MISMATCH`` 签名有效但 agent_id 不是被要求的那个
``GOV_PROVIDER_MISMATCH`` 签名有效但 provider 不是被要求的那个
===================  ================================
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mcpserver.agent_governance.errors import (
    E_AGENT_MISMATCH,
    E_BAD_SIGNATURE,
    E_MALFORMED,
    E_MISSING_KEY,
    E_PROVIDER_MISMATCH,
    E_TOKEN_EXPIRED,
    GovernanceError,
)
from mcpserver.agent_governance.identity import (
    canonical_json,
    key_fingerprint,
    normalize_key,
)

ENV_ID_KEY = "HERMES_AGENT_ID_KEY"
TOKEN_VERSION = "v1"
DEFAULT_TTL_S = 3600
CLAIM_FIELDS: tuple[str, ...] = ("v", "agent_id", "provider", "key_id", "iat", "exp", "nonce")


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


@dataclass(frozen=True)
class TokenClaims:
    """校验通过的令牌载荷。"""

    agent_id: str
    provider: str
    key_id: str
    iat: int
    exp: int
    nonce: str
    version: str = TOKEN_VERSION

    @property
    def ttl_s(self) -> int:
        return self.exp - self.iat

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.version,
            "agent_id": self.agent_id,
            "provider": self.provider,
            "key_id": self.key_id,
            "iat": self.iat,
            "exp": self.exp,
            "nonce": self.nonce,
        }


def _as_epoch(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise GovernanceError(E_MALFORMED, f"令牌字段 {field} 类型非法: {value!r}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError(E_MALFORMED, f"令牌字段 {field} 不是整数: {value!r}") from exc


class AuthorizationAuthority:
    """令牌签发 / 校验器。密钥与身份层同源（``HERMES_AGENT_ID_KEY``）。"""

    def __init__(self, key: str | bytes, *, ttl_s: int = DEFAULT_TTL_S, key_id: str | None = None) -> None:
        self._key = normalize_key(key)
        self.key_id = key_id or key_fingerprint(self._key)
        self.ttl_s = int(ttl_s)
        if self.ttl_s < 0:
            raise GovernanceError(E_MALFORMED, f"ttl_s 不能为负: {ttl_s}")

    @classmethod
    def from_env(
        cls,
        var: str = ENV_ID_KEY,
        *,
        ttl_s: int = DEFAULT_TTL_S,
        environ: dict[str, str] | None = None,
    ) -> AuthorizationAuthority:
        env = os.environ if environ is None else environ
        raw = env.get(var, "")
        if not raw:
            raise GovernanceError(E_MISSING_KEY, f"环境变量 {var} 未设置", env_var=var)
        return cls(raw, ttl_s=ttl_s)

    # ------------------------------------------------------------------ 签发
    def issue(
        self,
        agent_id: str,
        provider: str,
        *,
        ttl_s: int | None = None,
        now: datetime | None = None,
        nonce: str | None = None,
    ) -> str:
        """签发一枚短期 token。``ttl_s=0`` 得到即刻过期的令牌（场景 B 用）。"""
        if not agent_id:
            raise GovernanceError(E_MALFORMED, "agent_id 不能为空")
        if not provider:
            raise GovernanceError(E_MALFORMED, "provider 不能为空")
        issued_at = int((now or datetime.now().astimezone()).timestamp())
        ttl = self.ttl_s if ttl_s is None else int(ttl_s)
        claims = TokenClaims(
            agent_id=agent_id,
            provider=provider,
            key_id=self.key_id,
            iat=issued_at,
            exp=issued_at + ttl,
            nonce=nonce or secrets.token_hex(8),
        )
        body = _b64u_encode(canonical_json(claims.to_dict()).encode("utf-8"))
        sig = hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest()
        return f"{TOKEN_VERSION}.{body}.{_b64u_encode(sig)}"

    # ------------------------------------------------------------------ 校验
    def verify(
        self,
        token: str,
        *,
        agent_id: str | None = None,
        provider: str | None = None,
        now: datetime | None = None,
    ) -> TokenClaims:
        """校验 token；成功返回 ``TokenClaims``，失败抛带错误码的 ``GovernanceError``。"""
        claims = self._parse(token)
        expected = hmac.new(self._key, self._body_of(token).encode("ascii"), hashlib.sha256).digest()
        if claims.key_id != self.key_id or not hmac.compare_digest(expected, self._sig_of(token)):
            raise GovernanceError(
                E_BAD_SIGNATURE,
                "令牌签名无效（伪造 agent ID / 拿别的密钥签的）",
                got_key_id=claims.key_id,
                expected_key_id=self.key_id,
            )
        if claims.exp <= int((now or datetime.now().astimezone()).timestamp()):
            raise GovernanceError(
                E_TOKEN_EXPIRED,
                f"令牌已于 {claims.exp} 过期（ttl={claims.ttl_s}s）",
                exp=claims.exp,
                agent_id=claims.agent_id,
            )
        if agent_id is not None and claims.agent_id != agent_id:
            raise GovernanceError(
                E_AGENT_MISMATCH,
                "令牌 agent_id 与本次调用者不符",
                expected=agent_id,
                got=claims.agent_id,
            )
        if provider is not None and claims.provider != provider:
            raise GovernanceError(
                E_PROVIDER_MISMATCH,
                "令牌 provider 与本次调用 provider 不符",
                expected=provider,
                got=claims.provider,
            )
        return claims

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _parts(token: str) -> list[str]:
        parts = token.split(".") if isinstance(token, str) else []
        if len(parts) != 3 or parts[0] != TOKEN_VERSION:
            raise GovernanceError(E_MALFORMED, f"令牌段数/版本非法: {token!r}")
        return parts

    @classmethod
    def _body_of(cls, token: str) -> str:
        return cls._parts(token)[1]

    @classmethod
    def _sig_of(cls, token: str) -> bytes:
        try:
            return _b64u_decode(cls._parts(token)[2])
        except (ValueError, TypeError) as exc:
            raise GovernanceError(E_MALFORMED, "令牌签名段不是合法 base64url") from exc

    @classmethod
    def _parse(cls, token: str) -> TokenClaims:
        parts = cls._parts(token)
        try:
            payload = json.loads(_b64u_decode(parts[1]))
        except (ValueError, TypeError) as exc:
            raise GovernanceError(E_MALFORMED, "令牌载荷不是合法 base64url/JSON") from exc
        if not isinstance(payload, dict):
            raise GovernanceError(E_MALFORMED, "令牌载荷不是 JSON 对象")
        missing = [f for f in CLAIM_FIELDS if f not in payload]
        if missing:
            raise GovernanceError(E_MALFORMED, "令牌缺少字段", missing=missing)
        if payload["v"] != TOKEN_VERSION:
            raise GovernanceError(E_MALFORMED, f"令牌版本非法: {payload['v']!r}")
        return TokenClaims(
            agent_id=str(payload["agent_id"]),
            provider=str(payload["provider"]),
            key_id=str(payload["key_id"]),
            iat=_as_epoch(payload["iat"], "iat"),
            exp=_as_epoch(payload["exp"], "exp"),
            nonce=str(payload["nonce"]),
        )


def issue_token(key: str | bytes, agent_id: str, provider: str, *, ttl_s: int | None = None) -> str:
    """无状态便捷入口：签发一枚 token。"""
    return AuthorizationAuthority(key).issue(agent_id, provider, ttl_s=ttl_s)


def verify_token(
    key: str | bytes,
    token: str,
    *,
    agent_id: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """无状态便捷入口：校验通过返回载荷 dict，失败抛 ``GovernanceError``。"""
    return AuthorizationAuthority(key).verify(token, agent_id=agent_id, provider=provider).to_dict()


__all__ = [
    "DEFAULT_TTL_S",
    "ENV_ID_KEY",
    "TOKEN_VERSION",
    "AuthorizationAuthority",
    "TokenClaims",
    "issue_token",
    "verify_token",
]
