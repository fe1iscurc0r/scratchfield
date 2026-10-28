# -*- coding: utf-8 -*-
"""本机服务边界统一策略：绑定地址 / 远程开关 / 访问令牌。

对应审查报告 P0-1（`main.py` 把 MCP 与 Agent 绑在 ``0.0.0.0`` 且写路由无鉴权）
与其同源问题（sitaware、前端静态壳的 ``0.0.0.0`` / ``""`` 绑定）。口径来自
``docs/workorders/batch/P0-派单表-2026-10-22.md`` 的「主线 A」拍板：

    默认回环 + 环境变量逃生；打开必须同时给 token，缺 token 直接 fail-fast。

三个环境变量（全仓所有本地服务共用同一套命名）：

* ``NEKO_BIND_HOST``   默认 ``127.0.0.1``
* ``NEKO_ALLOW_REMOTE`` 只有字面量 ``1`` 才允许非回环绑定
* ``NEKO_AUTH_TOKEN``   非空且长度 ≥ 32 才算有效令牌

为什么非回环绑定时令牌对**所有**来源都要（包括来自 127.0.0.1 的请求）：
绑了通配地址之后，同一台机器上的进程和局域网里的进程用的是同一个监听套接字，
「来源是不是回环」不再是可信的区分依据——攻击者要的只是能连上端口，而回环来源
的检查在 DNS 重绑定 / 本机恶意软件面前也一起失效。要么只绑回环（本机自用，
不需要令牌），要么开远程（所有人都得带令牌），不允许第三种「开远程但谁都能连」。

NEKO 侧另有一套独立进程，无法 import 本模块，其镜像实现位于
``NEKO/N.E.K.O/utils/net_boundary.py``。两份实现的判据由各自
``tests/unit/test_net_boundary_policy.py`` 钉在同一张决策表上：改一边不改另一边
会在那一侧红。
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import sys
from dataclasses import dataclass, field

BIND_HOST_ENV = "NEKO_BIND_HOST"
ALLOW_REMOTE_ENV = "NEKO_ALLOW_REMOTE"
AUTH_TOKEN_ENV = "NEKO_AUTH_TOKEN"

DEFAULT_BIND_HOST = "127.0.0.1"
MIN_TOKEN_LENGTH = 32
EX_CONFIG = 78  # sysexits.h: 配置错误，与服务自身的运行期故障区分开

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
TOKEN_HEADERS = ("authorization", "x-neko-token")

_WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", "::0", "*"})
_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})

# 进程内实际使用的绑定地址。启动器在 uvicorn.run 之前写入，路由侧的守卫读它，
# 这样「策略判定」与「真实监听」不会因为绕过启动器的裸 uvicorn 调用而脱钩。
_effective_bind_host: str | None = None


def normalize_bind_host(value: object) -> str:
    """把任意写法的绑定地址收成可比较的小写形式（去掉 IPv6 方括号）。"""

    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    return text.strip("[]").lower().rstrip(".")


def is_loopback_host(value: object) -> bool:
    """回环判定：名字 + 整段 127/8 + ::1 + IPv4 映射的 IPv6 回环。"""

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


def is_wildcard_host(value: object) -> bool:
    """通配（= 全部网卡）绑定：``0.0.0.0`` / ``::`` / ``*`` / 空串。"""

    return normalize_bind_host(value) in _WILDCARD_HOSTS or normalize_bind_host(value) == ""


def bind_pair(host: str) -> tuple[int, str]:
    """返回 ``(地址族, 可 bind 的地址)``。

    端口探测必须用即将监听的同一地址族：拿 AF_INET 去探 ``::1`` 会成功（因为
    IPv6 端口根本没被占），反过来把 IPv6 字面量喂给 AF_INET 则直接报错，被
    误判成「端口已被占用」而跳过整个服务。
    """

    import socket

    text = normalize_bind_host(host)
    if text in ("::", "::0"):
        return socket.AF_INET6, "::"
    if text in ("0.0.0.0", "*", ""):
        return socket.AF_INET, "0.0.0.0"
    if ":" in text:
        return socket.AF_INET6, text
    return socket.AF_INET, text or DEFAULT_BIND_HOST


def read_bind_host(default: str = DEFAULT_BIND_HOST) -> str:
    raw = os.environ.get(BIND_HOST_ENV)
    host = normalize_bind_host(raw)
    return host or normalize_bind_host(default) or DEFAULT_BIND_HOST


def explicit_opt_in(env_name: str) -> bool:
    """危险动作的显式开关：只有字面量 ``1`` 算打开。

    不接受 ``true``/``yes``/``on``。这类开关控制的是「装完就一直在本机」「改
    LLM 上游」这种事后难以回收的动作，拼错的值必须落在关闭那一侧。
    """

    return str(os.environ.get(env_name) or "").strip() == "1"


def read_allow_remote() -> bool:
    """只有字面量 ``1`` 算打开。

    故意不接受 ``true``/``yes``：这是个安全闸门，拼错的值必须落在关闭那一侧，
    而不是「用户以为打开了、其实没打开」——反过来（以为关了其实开了）更危险。
    """

    return explicit_opt_in(ALLOW_REMOTE_ENV)


def read_auth_token() -> tuple[str, str]:
    """返回 ``(令牌, 状态)``，状态 ∈ {``unset``, ``too_short``, ``ok``}``。

    ``too_short`` 单独成态：它不能退化成「没有令牌」继续裸奔，也不能被当成
    「已经配了」而放行——必须让启动器明确拒绝并告诉用户短了多少。
    """

    token = str(os.environ.get(AUTH_TOKEN_ENV) or "").strip()
    if not token:
        return "", "unset"
    if len(token) < MIN_TOKEN_LENGTH:
        return token, "too_short"
    return token, "ok"


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
    """纯函数判定：给定绑定地址 + 远程开关 + 令牌，能不能启动。"""

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
        f"[net_boundary]   修法：删掉 {BIND_HOST_ENV} 让它只绑 127.0.0.1；确需跨机才同时给 "
        f"{BIND_HOST_ENV}=<网卡地址> {ALLOW_REMOTE_ENV}=1 {AUTH_TOKEN_ENV}=<≥{MIN_TOKEN_LENGTH} 字符令牌>"
    )
    return "\n".join(lines)


def enforce_startup_policy(component: str, *, bind_host: str | None = None) -> str:
    """启动期先校验后监听：不满足即 ``SystemExit(78)``，不进入服务循环。

    返回真正该传给 uvicorn 的绑定地址（校验通过时才返回）。
    """

    decision = evaluate_startup_policy(bind_host=bind_host)
    if not decision.accepted:
        text = policy_failure_text(component, decision)
        print(text, file=sys.stderr, flush=True)
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
    """``Authorization: Bearer x`` 优先，其次 ``X-Neko-Token``。"""

    get = getattr(headers, "get", None)
    if get is None:
        return ""
    authorization = str(get("authorization", "") or "").strip()
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return str(get("x-neko-token", "") or "").strip()


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
    """单个请求的放行判定（纯函数，便于脱离 HTTP 服务器做表驱动测试）。

    只读方法在非回环暴露时同样需要令牌——一旦开到局域网，``GET /services``
    这类「看起来无害」的清单本身就是在往外漏能力面。
    """

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
            f"非回环来源 {client_host!r} 访问写路由被拒：本机服务只接受回环请求，"
            f"跨机请设 {AUTH_TOKEN_ENV}（≥{MIN_TOKEN_LENGTH} 字符）"
        )
    return True, ""


def is_trusted_local_origin(origin: str) -> bool:
    """浏览器发的 ``Origin``/``Referer`` 是否落在本机壳来源白名单里。

    判定直接用 CORS 那一条正则（``system/cors_config.LOCAL_ORIGIN_REGEX``），
    两处共用一个口径：能被 CORS 放行的源，才允许在本机不带令牌发起变更请求。
    ``evil.example`` 这类外部网页既过不了 CORS，也过不了这里。
    """

    from system.cors_config import LOCAL_ORIGIN_REGEX

    text = str(origin or "").strip()
    if not text:
        return True
    import re

    return re.match(LOCAL_ORIGIN_REGEX, text) is not None


def _origin_of_request(scope) -> str:
    """取浏览器来源：``Origin`` 优先，其次 ``Referer`` 的 scheme://authority。"""

    headers = _Headers(scope)
    origin = headers.get("origin").strip()
    if origin:
        return origin
    referer = headers.get("referer").strip()
    if not referer:
        return ""
    from urllib.parse import urlsplit

    parts = urlsplit(referer)
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}"


class LocalBoundaryMiddleware:
    """默认拒绝的 ASGI 闸门：非回环暴露时全部请求要令牌，回环绑定时只拦非回环写。

    用中间件而不是逐路由挂依赖，是为了让「以后新加的写路由」自动落到保护面里；
    P0-1 之所以能挂了两年，一部分原因就是把鉴权当作每条路由的自觉。
    """

    def __init__(self, app, *, component: str, public_paths: tuple[str, ...] = ()):
        self.app = app
        self.component = component
        self.public_paths = tuple(public_paths)

    def _is_public(self, path: str) -> bool:
        return any(path == prefix or path.startswith(prefix) for prefix in self.public_paths)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or self._is_public(
            str(scope.get("path", ""))
        ):
            await self.app(scope, receive, send)
            return

        client = scope.get("client") or ("", None)
        headers = _Headers(scope)
        candidate = headers.extract()
        method = str(
            scope.get("method", "GET") if scope["type"] == "http" else "POST"
        ).upper()
        allowed, detail = authorize_request(
            client_host=str(client[0] or ""),
            method=method,
            candidate_token=candidate,
        )
        # CORS 只管读响应，拦不住跨源写：外部网页 POST 本机端口在旧实现里是通的。
        # 带对令牌的客户端已经是运维显式授权的（局域网 UI 属于这一类），不再叠加
        # 来源判定；无令牌的跨源浏览器写请求在这里被拒。
        if (
            allowed
            and method in UNSAFE_METHODS
            and not token_matches(candidate)
            and not is_trusted_local_origin(_origin_of_request(scope))
        ):
            allowed, status, detail = (
                False,
                403,
                "跨源变更请求被拒：Origin 不属于本机壳来源白名单",
            )
        else:
            status = 401
        if allowed:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            from starlette.websockets import WebSocket

            await WebSocket(scope, receive, send).close(code=1008)
            return
        from starlette.responses import JSONResponse

        response = JSONResponse(
            {"detail": detail, "component": self.component},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)


class _Headers:
    """在 ASGI scope 上按名字取值（headers 是 latin-1 编码的 (name, value) 对）。"""

    def __init__(self, scope):
        self._pairs = [
            (bytes(k).lower().decode("latin-1"), bytes(v).decode("latin-1"))
            for k, v in (scope.get("headers") or [])
        ]

    def get(self, name: str, default: str = "") -> str:
        needle = name.lower()
        for key, value in self._pairs:
            if key == needle:
                return value
        return default

    def extract(self) -> str:
        return extract_token(self)


def boundary_snapshot() -> dict:
    """给健康检查用：当前生效的边界，不回显令牌本身。"""

    _secret, state = read_auth_token()
    return {
        "bind_host": effective_bind_host(),
        "loopback_only": not remote_exposure_in_effect(),
        "allow_remote": read_allow_remote(),
        "auth_token_state": state,
        "min_token_length": MIN_TOKEN_LENGTH,
    }
