# -*- coding: utf-8 -*-
# Copyright 2025-2026 Project N.E.K.O. Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""N.E.K.O 侧的本机服务边界策略（与仓库根 ``system/net_boundary.py`` 同判据）。

N.E.K.O 是与根启动器分进程运行的独立应用，无法 import 根侧模块，所以这里是一份
镜像实现。两份实现的判据由各自的 ``tests/unit/test_net_boundary_policy.py`` 钉在
同一张决策表上——改一边不改另一边会在那一侧红。

环境变量口径（与根侧完全同名）：

* ``NEKO_BIND_HOST``    默认 ``127.0.0.1``
* ``NEKO_ALLOW_REMOTE`` 只有字面量 ``1`` 才允许非回环绑定
* ``NEKO_AUTH_TOKEN``   非空且长度 ≥ 32 才算有效令牌

历史名 ``NEKO_MONITOR_HOST`` / ``MONITOR_HOST`` / ``NEKO_MONITOR_TOKEN`` /
``MONITOR_TOKEN`` 继续可用（新名优先），因为 launcher wrapper 与既有部署都在写
这两个；但**默认值改了**：不再默认 ``0.0.0.0``（P0-4 的「刻意保留历史 LAN 绑定」
注释到此为止）。
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import sys
from dataclasses import dataclass, field

BIND_HOST_ENV = "NEKO_BIND_HOST"
LEGACY_BIND_HOST_ENVS = ("NEKO_MONITOR_HOST", "MONITOR_HOST")
ALLOW_REMOTE_ENV = "NEKO_ALLOW_REMOTE"
AUTH_TOKEN_ENV = "NEKO_AUTH_TOKEN"
LEGACY_AUTH_TOKEN_ENVS = ("NEKO_MONITOR_TOKEN", "MONITOR_TOKEN")

DEFAULT_BIND_HOST = "127.0.0.1"
MIN_TOKEN_LENGTH = 32
EX_CONFIG = 78

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})

_effective_bind_host: str | None = None


def normalize_bind_host(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    return text.strip("[]").lower().rstrip(".")


def is_loopback_host(value: object) -> bool:
    host = normalize_bind_host(value)
    if not host:
        return False
    if host in _LOOPBACK_NAMES:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return bool(address.is_loopback or (mapped is not None and mapped.is_loopback))


def explicit_opt_in(env_name: str) -> bool:
    """危险动作 / 边界放行的显式开关：只认字面量 ``1``，拼错一律算关闭。"""

    return str(os.environ.get(env_name) or "").strip() == "1"


def _first_env(names: tuple[str, ...]) -> str:
    for name in names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return ""


def read_bind_host(default: str = DEFAULT_BIND_HOST) -> str:
    host = normalize_bind_host(_first_env((BIND_HOST_ENV, *LEGACY_BIND_HOST_ENVS)))
    return host or normalize_bind_host(default) or DEFAULT_BIND_HOST


def read_allow_remote() -> bool:
    return explicit_opt_in(ALLOW_REMOTE_ENV)


def read_auth_token() -> tuple[str, str]:
    """``(令牌, 状态)``，状态 ∈ {``unset``, ``too_short``, ``ok``}。

    过短不退回「未配置」继续裸奔，也不当作已配置放行：它是独立的第三态，
    必须让启动器明确拒绝并说明短了多少。
    """

    token = _first_env((AUTH_TOKEN_ENV, *LEGACY_AUTH_TOKEN_ENVS))
    if not token:
        return "", "unset"
    if len(token) < MIN_TOKEN_LENGTH:
        return token, "too_short"
    return token, "ok"


def auth_token_source() -> str:
    """哪个环境变量提供了令牌（给日志/健康检查用，不回显值本身）。"""

    for name in (AUTH_TOKEN_ENV, *LEGACY_AUTH_TOKEN_ENVS):
        if str(os.environ.get(name) or "").strip():
            return name
    return ""


@dataclass
class PolicyDecision:
    accepted: bool
    bind_host: str
    allow_remote: bool
    token_state: str
    reasons: list[str] = field(default_factory=list)

    @property
    def remote_exposed(self) -> bool:
        return not is_loopback_host(self.bind_host)


def evaluate_startup_policy(
    *,
    bind_host: str | None = None,
    allow_remote: bool | None = None,
    token: str | None = None,
    token_state: str | None = None,
) -> PolicyDecision:
    host = (
        normalize_bind_host(bind_host)
        if bind_host not in (None, "")
        else read_bind_host()
    )
    host = host or DEFAULT_BIND_HOST
    allowed = read_allow_remote() if allow_remote is None else bool(allow_remote)
    if token_state is None or token is None:
        secret, state = read_auth_token()
        token_state = state if token_state is None else token_state
        token = secret if token is None else token
    state = token_state or "unset"

    reasons: list[str] = []
    if is_loopback_host(host):
        return PolicyDecision(True, host or DEFAULT_BIND_HOST, allowed, state)

    if not allowed:
        reasons.append(
            f"{ALLOW_REMOTE_ENV}=1 未设置：非回环绑定 {host!r} 需要显式打开远程访问"
        )
    if state == "unset":
        reasons.append(
            f"{AUTH_TOKEN_ENV} 未设置：非回环绑定必须同时提供长度 ≥{MIN_TOKEN_LENGTH} 的访问令牌"
        )
    elif state == "too_short":
        reasons.append(
            f"{AUTH_TOKEN_ENV} 长度 {len(token or '')} < {MIN_TOKEN_LENGTH}：过短令牌不视为已鉴权"
        )
    return PolicyDecision(not reasons, host, allowed, state, reasons)


def policy_failure_text(component: str, decision: PolicyDecision) -> str:
    lines = [
        f"[net_boundary] {component} 拒绝启动：绑定地址 {decision.bind_host!r} 不在回环范围内。",
    ]
    lines += [f"[net_boundary]   - {reason}" for reason in decision.reasons]
    lines.append(
        f"[net_boundary]   修法：删掉 {BIND_HOST_ENV} 让它只绑 127.0.0.1；"
        f"确需跨机才同时给 {BIND_HOST_ENV}=<网卡地址> {ALLOW_REMOTE_ENV}=1 "
        f"{AUTH_TOKEN_ENV}=<≥{MIN_TOKEN_LENGTH} 字符令牌>"
    )
    return "\n".join(lines)


def enforce_startup_policy(component: str, *, bind_host: str | None = None) -> str:
    """先校验后监听：不满足即 ``SystemExit(78)``。"""

    decision = evaluate_startup_policy(bind_host=bind_host)
    if not decision.accepted:
        print(policy_failure_text(component, decision), file=sys.stderr, flush=True)
        raise SystemExit(EX_CONFIG)
    record_bind_host(decision.bind_host)
    return decision.bind_host


def record_bind_host(host: str) -> None:
    global _effective_bind_host
    _effective_bind_host = normalize_bind_host(host) or DEFAULT_BIND_HOST


def effective_bind_host() -> str:
    return _effective_bind_host or read_bind_host()


def remote_exposure_in_effect() -> bool:
    return not is_loopback_host(effective_bind_host())


def extract_token(headers) -> str:
    """``Authorization: Bearer x`` 优先，其次 ``X-Neko-Token``，再 ``X-Monitor-Token``。"""

    get = getattr(headers, "get", None)
    if get is None:
        return ""
    authorization = str(get("authorization", "") or "").strip()
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    for name in ("x-neko-token", "x-monitor-token"):
        candidate = str(get(name, "") or "").strip()
        if candidate:
            return candidate
    return ""


def token_matches(candidate: str) -> bool:
    secret, state = read_auth_token()
    if state != "ok":
        return False
    return hmac.compare_digest(str(candidate or ""), secret)


def authorize_request(
    *,
    client_host: str | None,
    method: str,
    candidate_token: str = "",
    remote_exposed: bool | None = None,
    token_state: str | None = None,
) -> tuple[bool, str]:
    """单请求放行判定（纯函数，可脱离 HTTP 服务器做表驱动测试）。"""

    exposed = remote_exposure_in_effect() if remote_exposed is None else bool(remote_exposed)
    state = token_state or read_auth_token()[1]
    if exposed:
        if state != "ok":
            return False, (
                f"{AUTH_TOKEN_ENV} 未配置或过短：服务已绑定非回环地址，禁止匿名访问"
            )
        if not token_matches(candidate_token):
            return False, "缺少或错误的访问令牌（Authorization: Bearer / X-Neko-Token）"
        return True, ""
    if str(method or "").upper() in UNSAFE_METHODS and not is_loopback_host(client_host):
        if state == "ok" and token_matches(candidate_token):
            # 只在「反向代理把真实来源写进 client」时可达：绑定本身已经决定了
            # 内核会不会投递进来，带对令牌的跨机写请求按运维的显式配置放行。
            return True, ""
        if state == "ok":
            return False, "缺少或错误的访问令牌（Authorization: Bearer / X-Neko-Token）"
        return False, (
            f"非回环来源 {client_host!r} 访问变更路由被拒：本机服务只接受回环请求，"
            f"跨机请设 {AUTH_TOKEN_ENV}（≥{MIN_TOKEN_LENGTH} 字符）"
        )
    return True, ""


def boundary_snapshot() -> dict:
    _secret, state = read_auth_token()
    return {
        "bind_host": effective_bind_host(),
        "loopback_only": not remote_exposure_in_effect(),
        "allow_remote": read_allow_remote(),
        "auth_token_state": state,
        "auth_token_source": auth_token_source(),
        "min_token_length": MIN_TOKEN_LENGTH,
    }
