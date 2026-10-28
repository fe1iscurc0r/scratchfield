"""身份证明层 —— 每次 agent 输出携带 HMAC-SHA256 签名，接收方可独立验签。

工单 241 §2 任务一第 1 条。密钥只从环境变量 ``HERMES_AGENT_ID_KEY`` 读（**只读，不落盘**）。

签名把四件事绑在一起，缺一不可：

1. ``agent_id`` —— 谁产的（防「伪造 agent ID」）
2. ``provider`` / ``model`` —— 用哪个模型产的（防「降级模型冒充 M3」）
3. ``timestamp`` —— 什么时候产的（跨 provider 传递时可回溯）
4. ``content_sha256`` —— 内容是什么（防「输出被第三方模型注入污染实验结论」）

纯 stdlib（``hmac`` / ``hashlib`` / ``json``），单次签名与验签均 < 0.1 ms ——
不改变 M3 调用的时效性（工单 §4 第 5 条）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from mcpserver.agent_governance.errors import (
    E_BAD_SIGNATURE,
    E_CONTENT_MISMATCH,
    E_MALFORMED,
    E_MISSING_KEY,
    GovernanceError,
)

ENV_ID_KEY = "HERMES_AGENT_ID_KEY"
ENVELOPE_VERSION = 1
_KEY_ID_LEN = 12

# 参与签名的字段（顺序无关 —— 签的是 canonical JSON，键已排序）
SIGNED_FIELDS: tuple[str, ...] = (
    "version",
    "agent_id",
    "provider",
    "model",
    "timestamp",
    "content_sha256",
    "key_id",
)


def normalize_key(key: str | bytes) -> bytes:
    """把密钥归一化成 bytes（str 按 UTF-8）。空值抛 ``E_MISSING_KEY``。"""
    if isinstance(key, str):
        key = key.encode("utf-8")
    if not isinstance(key, bytes) or not key:
        raise GovernanceError(E_MISSING_KEY, "agent 身份密钥为空")
    return key


def content_digest(content: str | bytes) -> str:
    """内容摘要（sha256 hex）。str 按 UTF-8 编码。"""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def key_fingerprint(key: bytes) -> str:
    """密钥指纹（sha256 前 12 位 hex）—— 允许公开展示，用于定位「用哪把密钥签的」。"""
    return hashlib.sha256(key).hexdigest()[:_KEY_ID_LEN]


def canonical_json(obj: Any) -> str:
    """稳定序列化：键排序 + 无多余空白 + 不转义非 ASCII。

    签名/验签两侧必须走同一函数，否则得到不同字节 —— 这是本层唯一的序列化契约。
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def utc_now_iso(now: datetime | None = None) -> str:
    """UTC ISO-8601 秒级时间戳（``...+00:00``），可被 ``datetime.fromisoformat`` 解析。"""
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SignedOutput:
    """一条带签名的 agent 输出信封。``sig`` 覆盖其余全部字段。"""

    agent_id: str
    provider: str
    model: str
    timestamp: str
    content_sha256: str
    key_id: str
    sig: str
    version: int = ENVELOPE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "agent_id": self.agent_id,
            "provider": self.provider,
            "model": self.model,
            "timestamp": self.timestamp,
            "content_sha256": self.content_sha256,
            "key_id": self.key_id,
            "sig": self.sig,
        }

    @classmethod
    def from_mapping(cls, data: Any) -> SignedOutput:
        """从 dict / 已是本类实例的输入归一化，缺字段抛 ``E_MALFORMED``。"""
        if isinstance(data, SignedOutput):
            return data
        if not isinstance(data, dict):
            raise GovernanceError(E_MALFORMED, f"信封不是 dict: {type(data).__name__}")
        missing = [f for f in (*SIGNED_FIELDS, "sig") if f not in data]
        if missing:
            raise GovernanceError(E_MALFORMED, "信封缺少字段", missing=missing)
        try:
            version = int(data["version"])
        except (TypeError, ValueError) as exc:
            raise GovernanceError(E_MALFORMED, f"信封 version 非法: {data.get('version')!r}") from exc
        return cls(
            agent_id=str(data["agent_id"]),
            provider=str(data["provider"]),
            model=str(data["model"]),
            timestamp=str(data["timestamp"]),
            content_sha256=str(data["content_sha256"]),
            key_id=str(data["key_id"]),
            sig=str(data["sig"]),
            version=version,
        )


def signing_payload(envelope: SignedOutput) -> str:
    """把信封去掉 ``sig`` 后做 canonical JSON —— 这就是被签的字节。"""
    data = envelope.to_dict()
    del data["sig"]
    return canonical_json(data)


def make_signature(key: bytes, envelope: SignedOutput) -> str:
    """对信封算 HMAC-SHA256（hex）。"""
    return hmac.new(key, signing_payload(envelope).encode("utf-8"), hashlib.sha256).hexdigest()


class IdentitySigner:
    """身份证明器：持一把密钥，产出签名信封 / 校验别人的信封。"""

    def __init__(self, key: str | bytes, key_id: str | None = None) -> None:
        self._key = normalize_key(key)
        self.key_id = key_id or key_fingerprint(self._key)

    @classmethod
    def from_env(cls, var: str = ENV_ID_KEY, environ: dict[str, str] | None = None) -> IdentitySigner:
        """从环境变量取密钥；缺失抛 ``E_MISSING_KEY``（fail-fast，不静默降级）。"""
        env = os.environ if environ is None else environ
        raw = env.get(var, "")
        if not raw:
            raise GovernanceError(E_MISSING_KEY, f"环境变量 {var} 未设置", env_var=var)
        return cls(raw)

    def sign(
        self,
        agent_id: str,
        provider: str,
        *,
        model: str = "",
        content: str | bytes = "",
        timestamp: str | None = None,
    ) -> SignedOutput:
        """产出一条签名信封。内容可以为空字符串（用于纯身份声明）。"""
        if not agent_id:
            raise GovernanceError(E_MALFORMED, "agent_id 不能为空")
        if not provider:
            raise GovernanceError(E_MALFORMED, "provider 不能为空")
        draft = SignedOutput(
            agent_id=agent_id,
            provider=provider,
            model=model,
            timestamp=timestamp or utc_now_iso(),
            content_sha256=content_digest(content),
            key_id=self.key_id,
            sig="",
        )
        return SignedOutput(**{**draft.to_dict(), "sig": make_signature(self._key, draft)})

    def verify(self, envelope: Any, content: str | bytes = "") -> SignedOutput:
        """校验信封并返回归一化后的 ``SignedOutput``；任一项不符抛 ``GovernanceError``。

        校验顺序（与错误码一一对应）：
        ① 结构合法 → ``E_MALFORMED``
        ② key_id 一致 → ``E_BAD_SIGNATURE``（拿别的密钥签的）
        ③ HMAC 一致 → ``E_BAD_SIGNATURE``
        ④ 内容摘要一致 → ``E_CONTENT_MISMATCH``
        """
        env = SignedOutput.from_mapping(envelope)
        if env.version != ENVELOPE_VERSION:
            raise GovernanceError(E_MALFORMED, f"不支持的信封版本: {env.version}", expected=ENVELOPE_VERSION)
        if env.key_id != self.key_id:
            raise GovernanceError(
                E_BAD_SIGNATURE,
                "key_id 不匹配（不是本密钥签出的信封）",
                expected_key_id=self.key_id,
                got_key_id=env.key_id,
            )
        expected = make_signature(self._key, env)
        if not hmac.compare_digest(expected, env.sig):
            raise GovernanceError(E_BAD_SIGNATURE, "HMAC 校验失败（内容或字段被篡改）", agent_id=env.agent_id)
        if content:
            actual = content_digest(content)
            if not hmac.compare_digest(actual, env.content_sha256):
                raise GovernanceError(
                    E_CONTENT_MISMATCH,
                    "内容摘要与签名不符（输出被替换或注入污染）",
                    agent_id=env.agent_id,
                    expected=env.content_sha256,
                    actual=actual,
                )
        return env


def sign_output(
    key: str | bytes,
    agent_id: str,
    provider: str,
    *,
    model: str = "",
    content: str | bytes = "",
) -> dict[str, Any]:
    """无状态便捷入口：直接产出信封 dict（密钥用后即弃）。"""
    return IdentitySigner(key).sign(agent_id, provider, model=model, content=content).to_dict()


def verify_output(key: str | bytes, envelope: Any, content: str | bytes = "") -> dict[str, Any]:
    """无状态便捷入口：验签成功返回信封 dict，失败抛 ``GovernanceError``。"""
    return IdentitySigner(key).verify(envelope, content).to_dict()
