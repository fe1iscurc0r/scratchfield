# -*- coding: utf-8 -*-
"""WO-267 / P0-4、P0-5、P0-6：N.E.K.O 侧边界策略的决策表。

根侧 ``tests/test_net_boundary_policy.py`` 钉的是**同一张表**：两侧实现分进程
运行、无法互相 import（N.E.K.O 不 import 仓库根的 ``system/``），漂移只能靠表来钉。
改 ``utils/net_boundary.py`` 而不改根侧，根侧红；反之亦然。

控制实验（「改坏 ⇒ FAIL / 注入失败 ⇒ 行为正确」）见文件末尾两条。
"""

from __future__ import annotations

import asyncio
import ipaddress

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import monitor_auth
from utils import net_boundary as nb
from utils.host_origin_guard import is_http_browser_origin_allowed
from utils.net_boundary import (
    AUTH_TOKEN_ENV,
    ALLOW_REMOTE_ENV,
    BIND_HOST_ENV,
    LEGACY_AUTH_TOKEN_ENVS,
    LEGACY_BIND_HOST_ENVS,
    MIN_TOKEN_LENGTH,
)

BOUNDARY_ENVS = (
    BIND_HOST_ENV,
    ALLOW_REMOTE_ENV,
    AUTH_TOKEN_ENV,
    *LEGACY_BIND_HOST_ENVS,
    *LEGACY_AUTH_TOKEN_ENVS,
)

GOOD_TOKEN = "t" * MIN_TOKEN_LENGTH


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """每条用例从「未配置」开始，并复位进程内的生效绑定地址。"""

    for name in BOUNDARY_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(nb, "_effective_bind_host", None)
    yield
    monkeypatch.setattr(nb, "_effective_bind_host", None)


def _set(monkeypatch, *, host=None, allow=None, token=...):
    if host is not None:
        monkeypatch.setenv(BIND_HOST_ENV, host)
    if allow is not None:
        monkeypatch.setenv(ALLOW_REMOTE_ENV, allow)
    if token is not ...:
        if token is None:
            monkeypatch.delenv(AUTH_TOKEN_ENV, raising=False)
        else:
            monkeypatch.setenv(AUTH_TOKEN_ENV, token)


# --------------------------------------------------------------------------- #
# 绑定地址判定
# --------------------------------------------------------------------------- #

LOOPBACK_HOSTS = [
    "127.0.0.1",
    "localhost",
    "::1",
    "[::1]",
    "127.0.0.53",
    "LOCALHOST.",
    "::ffff:127.0.0.1",
]
NON_LOOPBACK_HOSTS = [
    "0.0.0.0",
    "::",
    "*",
    "192.168.1.10",
    "10.0.0.1",
    "172.16.0.5",
    "[fd00::1]",
]


@pytest.mark.parametrize("host", LOOPBACK_HOSTS)
def test_loopback_recognised(host):
    assert nb.is_loopback_host(host), host


@pytest.mark.parametrize("host", NON_LOOPBACK_HOSTS)
def test_non_loopback_not_mistaken_for_loopback(host):
    assert not nb.is_loopback_host(host), host


def test_empty_is_not_loopback():
    """空串 = 通配。``host=""`` 会绑到所有网卡，绝不能被判成回环。"""

    assert not nb.is_loopback_host("")


# --------------------------------------------------------------------------- #
# 环境变量：新名优先，历史名继续可用
# --------------------------------------------------------------------------- #

def test_default_bind_host_is_loopback():
    """P0-4 的落点：Monitor 不再默认 ``0.0.0.0``。"""

    assert nb.read_bind_host() == "127.0.0.1"


@pytest.mark.parametrize("legacy", LEGACY_BIND_HOST_ENVS)
def test_legacy_bind_host_still_honoured(legacy, monkeypatch):
    monkeypatch.setenv(legacy, "0.0.0.0")
    assert nb.read_bind_host() == "0.0.0.0"


def test_new_bind_host_name_wins_over_legacy(monkeypatch):
    monkeypatch.setenv(LEGACY_BIND_HOST_ENVS[0], "0.0.0.0")
    monkeypatch.setenv(BIND_HOST_ENV, "127.0.0.1")
    assert nb.read_bind_host() == "127.0.0.1"


@pytest.mark.parametrize("legacy", LEGACY_AUTH_TOKEN_ENVS)
def test_legacy_token_still_honoured(legacy, monkeypatch):
    monkeypatch.setenv(legacy, GOOD_TOKEN)
    value, state = nb.read_auth_token()
    assert (value, state) == (GOOD_TOKEN, "ok")
    assert nb.auth_token_source() == legacy


def test_new_token_name_wins_over_legacy(monkeypatch):
    monkeypatch.setenv(LEGACY_AUTH_TOKEN_ENVS[0], "s" * MIN_TOKEN_LENGTH)
    monkeypatch.setenv(AUTH_TOKEN_ENV, GOOD_TOKEN)
    assert nb.read_auth_token()[0] == GOOD_TOKEN
    assert nb.auth_token_source() == AUTH_TOKEN_ENV


@pytest.mark.parametrize("raw,expected", [
    ("1", True),
    (" 1 ", True),
    ("0", False),
    ("true", False),   # 只认字面量 1：拼错的值必须落在关闭那一侧
    ("yes", False),
    ("", False),
])
def test_allow_remote_only_literal_one(monkeypatch, raw, expected):
    monkeypatch.setenv(ALLOW_REMOTE_ENV, raw)
    assert nb.read_allow_remote() is expected, raw


@pytest.mark.parametrize("token,expected_state", [
    (None, "unset"),
    ("", "unset"),
    ("x" * (MIN_TOKEN_LENGTH - 1), "too_short"),
    ("x" * MIN_TOKEN_LENGTH, "ok"),
])
def test_token_is_tri_valued(monkeypatch, token, expected_state):
    _set(monkeypatch, token=token)
    assert nb.read_auth_token()[1] == expected_state


def test_snapshot_never_echoes_the_token(monkeypatch):
    _set(monkeypatch, token="short-token")
    assert "short-token" not in str(nb.boundary_snapshot())
    assert nb.boundary_snapshot()["auth_token_state"] == "too_short"


# --------------------------------------------------------------------------- #
# 启动期决策表（与根侧逐行一致）
# --------------------------------------------------------------------------- #

STARTUP_TABLE = [
    ("127.0.0.1",  False, "unset",     True,  ""),
    ("localhost",  False, "unset",     True,  ""),
    ("::1",        False, "unset",     True,  ""),
    ("127.0.0.1",  True,  "unset",     True,  ""),
    ("127.0.0.1",  True,  "ok",        True,  ""),
    ("0.0.0.0",    False, "unset",     False, "NEKO_ALLOW_REMOTE"),
    ("0.0.0.0",    True,  "unset",     False, "NEKO_AUTH_TOKEN"),
    ("0.0.0.0",    False, "too_short", False, "NEKO_ALLOW_REMOTE"),
    ("0.0.0.0",    True,  "too_short", False, "NEKO_AUTH_TOKEN"),
    ("0.0.0.0",    True,  "ok",        True,  ""),
    ("::",         True,  "ok",        True,  ""),
    ("192.168.1.10", True, "ok",       True,  ""),
    ("192.168.1.10", False, "ok",      False, "NEKO_ALLOW_REMOTE"),
]


@pytest.mark.parametrize(
    "host,allow_remote,token_state,accepted,first_reason",
    STARTUP_TABLE,
    ids=[f"{r[0]}|allow={int(r[1])}|{r[2]}" for r in STARTUP_TABLE],
)
def test_startup_decision_table(monkeypatch, host, allow_remote, token_state, accepted, first_reason):
    _set(monkeypatch, host=host, allow="1" if allow_remote else "0",
         token=GOOD_TOKEN if token_state == "ok" else ("x" * 8 if token_state == "too_short" else None))
    decision = nb.evaluate_startup_policy()
    assert decision.accepted is accepted, decision.reasons
    assert decision.token_state == token_state
    assert decision.remote_exposed is (not nb.is_loopback_host(host))
    if accepted:
        assert decision.reasons == []
    else:
        assert first_reason in decision.reasons[0]


def test_wildcard_without_token_lists_both_blockers(monkeypatch):
    _set(monkeypatch, host="0.0.0.0")
    assert len(nb.evaluate_startup_policy().reasons) == 2


def test_enforce_raises_ex_config_before_listening(monkeypatch, capsys):
    _set(monkeypatch, host="0.0.0.0", allow="1")
    with pytest.raises(SystemExit) as excinfo:
        nb.enforce_startup_policy("Monitor 服务")
    assert excinfo.value.code == nb.EX_CONFIG == 78
    err = capsys.readouterr().err
    assert AUTH_TOKEN_ENV in err and "Monitor 服务" in err


def test_enforce_accepts_the_fully_opened_case(monkeypatch):
    _set(monkeypatch, host="0.0.0.0", allow="1", token=GOOD_TOKEN)
    assert nb.enforce_startup_policy("Monitor 服务") == "0.0.0.0"
    assert nb.remote_exposure_in_effect() is True


def test_empty_bind_host_falls_back_to_loopback(monkeypatch):
    _set(monkeypatch, host="")
    assert nb.enforce_startup_policy("Monitor 服务") == "127.0.0.1"


# --------------------------------------------------------------------------- #
# 单请求放行（与根侧逐行一致）
# --------------------------------------------------------------------------- #

REQUEST_TABLE = [
    (False, "unset",     "",          "127.0.0.1",   "GET",    True),
    (False, "unset",     "",          "127.0.0.1",   "POST",   True),
    (False, "unset",     "",          "::1",         "DELETE", True),
    (False, "unset",     "",          "192.168.1.5", "GET",    True),
    (False, "unset",     "",          "192.168.1.5", "POST",   False),
    (False, "ok",        "",          "10.0.0.9",    "PUT",    False),
    (False, "ok",        GOOD_TOKEN,  "10.0.0.9",    "PUT",    True),
    (True,  "unset",     "",          "127.0.0.1",   "GET",    False),
    (True,  "too_short", "x" * 8,     "127.0.0.1",   "GET",    False),
    (True,  "ok",        "",          "127.0.0.1",   "POST",   False),
    (True,  "ok",        "wrong",     "127.0.0.1",   "GET",    False),
    (True,  "ok",        GOOD_TOKEN,  "127.0.0.1",   "POST",   True),
    (True,  "ok",        GOOD_TOKEN,  "192.168.1.5", "GET",    True),
]


@pytest.mark.parametrize(
    "exposed,token_state,candidate,client,method,allowed",
    REQUEST_TABLE,
    ids=[f"{r[0]}|{r[1]}|{r[3]}|{r[4]}|want={int(r[5])}" for r in REQUEST_TABLE],
)
def test_request_decision_table(monkeypatch, exposed, token_state, candidate, client, method, allowed):
    _set(monkeypatch, token=GOOD_TOKEN if token_state == "ok" else ("x" * 8 if token_state == "too_short" else None))
    ok, detail = nb.authorize_request(
        client_host=client, method=method, candidate_token=candidate,
        remote_exposed=exposed,
    )
    assert ok is allowed, (client, method, detail)
    if not allowed:
        assert detail, "拒绝必须给原因，不能静默 401"


def test_extract_token_accepts_monitor_header():
    assert nb.extract_token({"x-monitor-token": "abc"}) == "abc"
    assert nb.extract_token({"authorization": "Bearer abc", "x-monitor-token": "zzz"}) == "abc"
    assert nb.extract_token({"authorization": "Basic Zm9vOmJhcg=="}) == ""
    assert nb.extract_token({}) == ""


# --------------------------------------------------------------------------- #
# P0-5：Monitor 的公开面只剩 /static/
# --------------------------------------------------------------------------- #

def test_monitor_public_prefixes_no_longer_cover_user_assets():
    """付费 Live2D 模型与 Steam 创意工坊目录从前免鉴权整目录可下载。"""

    assert monitor_auth._PUBLIC_PATH_PREFIXES == ("/static/",)
    for hidden in ("/user_live2d/", "/user_live2d_local/", "/workshop/"):
        assert not hidden.startswith(monitor_auth._PUBLIC_PATH_PREFIXES), hidden


def _monitor_scope(path, *, headers=(), query=b"", typ="http", client="127.0.0.1"):
    return {
        "type": typ,
        "path": path,
        "raw_path": path.encode(),
        "method": "GET",
        "query_string": query,
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers],
        "client": (client, 51234),
        "cookies": {},
    }


def _run_monitor_middleware(scope):
    """返回 (是否透传, 状态码/关闭码)。"""

    passed = []
    outcome = []

    async def downstream(scope_, receive, send):
        passed.append(scope_["path"])

    async def send(message):
        if message["type"] == "http.response.start":
            outcome.append(message["status"])
        elif message["type"] == "websocket.close":
            outcome.append(("ws-close", message.get("code")))

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = monitor_auth.MonitorAuthMiddleware(downstream)
    asyncio.run(middleware(scope, receive, send))
    return bool(passed), outcome


def test_monitor_asset_routes_require_token_once_auth_enabled(monkeypatch):
    monkeypatch.setattr(monitor_auth, "MONITOR_TOKEN", GOOD_TOKEN)
    for path in ("/user_live2d/model/model3.json", "/workshop/1234/file.vpk",
                 "/sync/state", "/api/monitor/x"):
        passed, outcome = _run_monitor_middleware(_monitor_scope(path))
        assert passed is False and outcome == [401], path


def test_monitor_static_assets_stay_open(monkeypatch):
    monkeypatch.setattr(monitor_auth, "MONITOR_TOKEN", GOOD_TOKEN)
    passed, outcome = _run_monitor_middleware(
        _monitor_scope("/static/yui-origin/yui.model3.json"))
    assert passed is True and outcome == []


def test_monitor_viewer_token_cannot_write_sync(monkeypatch):
    """共用一条 viewer 链接的人拿不到生产者写面。"""

    monkeypatch.setattr(monitor_auth, "MONITOR_TOKEN", GOOD_TOKEN)
    viewer = "v" * MIN_TOKEN_LENGTH
    monkeypatch.setattr(monitor_auth, "MONITOR_VIEWER_TOKEN", viewer)
    assert _run_monitor_middleware(
        _monitor_scope("/sync/state", headers=[("x-monitor-token", viewer)]))[0] is False
    assert _run_monitor_middleware(
        _monitor_scope("/characters", headers=[("x-monitor-token", viewer)]))[0] is True


def test_monitor_websocket_handshake_is_policy_closed(monkeypatch):
    monkeypatch.setattr(monitor_auth, "MONITOR_TOKEN", GOOD_TOKEN)
    passed, outcome = _run_monitor_middleware(_monitor_scope("/ws", typ="websocket"))
    assert passed is False and outcome == [("ws-close", 1008)]


# --------------------------------------------------------------------------- #
# P0-6：/api/agent/* 的变更面
# --------------------------------------------------------------------------- #

def _agent_scope(method, *, client="127.0.0.1", origin=None, host="127.0.0.1:48911", headers=()):
    pairs = [("host", host)] + list(headers)
    if origin is not None:
        pairs.append(("origin", origin))
    return {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": "/api/agent/computer-use",
        "raw_path": b"/api/agent/computer-use",
        "query_string": b"",
        "scheme": "http",
        "client": (client, 51234),
        "server": ("127.0.0.1", 48911),
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in pairs],
    }


def _call_boundary(scope):
    from main_routers.agent_router import agent_mutation_boundary

    return asyncio.run(agent_mutation_boundary(Request(scope)))


def test_agent_dependency_is_registered_on_the_router():
    """前缀级依赖：新挂到 ``/api/agent`` 的路由自动进保护面。"""

    from main_routers.agent_router import router

    assert router.prefix == "/api/agent"
    assert len(router.dependencies) == 1


def test_agent_read_requests_pass(monkeypatch):
    _set(monkeypatch, host="127.0.0.1")
    assert _call_boundary(_agent_scope("GET", origin="http://evil.example")) is None


def test_agent_loopback_write_without_origin_passes(monkeypatch):
    """Electron / 本机原生客户端不发 Origin，必须照常可用（否则会全线瘫痪）。"""

    _set(monkeypatch, host="127.0.0.1")
    assert _call_boundary(_agent_scope("POST")) is None


def test_agent_same_origin_browser_write_passes(monkeypatch):
    _set(monkeypatch, host="127.0.0.1")
    assert _call_boundary(_agent_scope("POST", origin="http://localhost:48911")) is None


def test_agent_cross_origin_write_is_rejected_with_403(monkeypatch):
    """外部网页跨源 POST 打开 computer_use 并投递 agent 命令：CORS 拦不住写，这里拦。"""

    _set(monkeypatch, host="127.0.0.1", token=GOOD_TOKEN)
    with pytest.raises(HTTPException) as excinfo:
        _call_boundary(_agent_scope("POST", origin="https://evil.example"))
    assert excinfo.value.status_code == 403


def test_agent_cross_origin_write_with_valid_token_passes(monkeypatch):
    """局域网 UI 是运维显式配了令牌的客户端：来源判定不该再拦它。"""

    _set(monkeypatch, host="0.0.0.0", allow="1", token=GOOD_TOKEN)
    nb.record_bind_host("0.0.0.0")
    assert _call_boundary(_agent_scope(
        "POST", client="192.168.1.5", origin="http://192.168.1.9:5173",
        headers=[("authorization", f"Bearer {GOOD_TOKEN}")])) is None
    with pytest.raises(HTTPException):
        _call_boundary(_agent_scope(
            "POST", client="192.168.1.5", origin="http://192.168.1.9:5173"))


def test_agent_non_loopback_write_needs_a_token(monkeypatch):
    _set(monkeypatch, host="127.0.0.1")
    with pytest.raises(HTTPException) as excinfo:
        _call_boundary(_agent_scope("DELETE", client="192.168.1.5"))
    assert excinfo.value.status_code == 401

    _set(monkeypatch, host="127.0.0.1", token=GOOD_TOKEN)
    assert _call_boundary(_agent_scope(
        "DELETE", client="192.168.1.5",
        headers=[("x-neko-token", GOOD_TOKEN)])) is None


def test_agent_write_needs_token_when_bound_wildcard(monkeypatch):
    """逃生阀打开后的口径：通配绑定 ⇒ 本机匿名写也拒。"""

    _set(monkeypatch, host="0.0.0.0", allow="1", token=GOOD_TOKEN)
    nb.record_bind_host("0.0.0.0")
    with pytest.raises(HTTPException) as excinfo:
        _call_boundary(_agent_scope("POST"))
    assert excinfo.value.status_code == 401
    assert _call_boundary(_agent_scope(
        "POST", headers=[("authorization", f"Bearer {GOOD_TOKEN}")])) is None


def test_agent_boundary_never_reaches_for_the_real_listener(monkeypatch):
    """判定读的是生效绑定地址，不是环境变量：绕过启动器也不能脱钩。"""

    _set(monkeypatch, host="127.0.0.1", allow="1", token=GOOD_TOKEN)
    nb.record_bind_host("0.0.0.0")
    with pytest.raises(HTTPException):
        _call_boundary(_agent_scope("GET"))


# --------------------------------------------------------------------------- #
# 与 issue #1023 的远程部署契约共存：边界不许抢答那四个 501 短路端点
# --------------------------------------------------------------------------- #

_REMOTE_BLOCKED_CASES = [
    ("/api/agent/flags", {"flags": {}}),
    ("/api/agent/command", {"command": "set_agent_enabled", "enabled": True}),
    ("/api/agent/admin/control", {}),
    ("/api/agent/tasks/abc-123/cancel", None),
]


def _agent_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from main_routers import agent_router as agent_router_module

    app = FastAPI()
    app.include_router(agent_router_module.router)
    return TestClient(app)


@pytest.mark.parametrize("path,body", _REMOTE_BLOCKED_CASES)
def test_agent_remote_mode_envelope_survives_the_boundary(monkeypatch, path, body):
    """``TestClient`` 的 client 是 ``("testclient", …)``，不是回环。

    边界若照字面把「非回环来源的写请求」一律 401，就会盖掉
    ``test_agent_router_remote_block.py`` 钉住的那条运维契约（远程部署下必须 501、
    错误里必须点名 ``NEKO_ACTIVITY_TRACKER_REMOTE``，前端按它统一显示「agent
    unavailable on remote backend」）。这条用例是两边不许各退一步的对齐点：
    删掉端点里的任何一处 ``_remote_backend_block()`` 短路，它就会变回 401 而变红。
    """

    _set(monkeypatch, host="127.0.0.1")
    monkeypatch.delenv("ACTIVITY_TRACKER_REMOTE", raising=False)
    monkeypatch.setenv("NEKO_ACTIVITY_TRACKER_REMOTE", "1")
    client = _agent_client()
    resp = client.post(path, json=body) if body is not None else client.post(path)
    assert resp.status_code == 501, resp.text
    payload = resp.json()
    assert payload.get("success") is False
    assert "NEKO_ACTIVITY_TRACKER_REMOTE" in payload.get("error", "")


def test_agent_internal_bridge_is_not_exempt_from_the_boundary(monkeypatch):
    """让路名单只覆盖「端点自己已经拒绝」的路径。

    ``/internal/analyze_request`` 没有远程短路，若把它一起放掉，远程部署下就是一个
    免鉴权的事件投递口 —— 所以这里必须仍是 401。
    """

    _set(monkeypatch, host="127.0.0.1")
    monkeypatch.delenv("ACTIVITY_TRACKER_REMOTE", raising=False)
    monkeypatch.setenv("NEKO_ACTIVITY_TRACKER_REMOTE", "1")
    resp = _agent_client().post("/api/agent/internal/analyze_request", json={})
    assert resp.status_code == 401, resp.text


# --------------------------------------------------------------------------- #
# 装配点：默认值确实改了
# --------------------------------------------------------------------------- #

def test_config_wires_monitor_defaults_through_the_policy():
    """``config/network.py`` 必须经边界策略取值，别再留一份 ``0.0.0.0`` 默认。"""

    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "config" / "network.py"
    ).read_text(encoding="utf-8")
    assert "_read_str_env(\"MONITOR_HOST\", \"0.0.0.0\")" not in source
    assert "read_bind_host()" in source and "read_auth_token()" in source
    assert "ALLOW_REMOTE" in source and "AUTH_TOKEN_STATE" in source


def test_monitor_entrypoint_enforces_before_serving():
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[2] / "app" / "monitor.py"
    ).read_text(encoding="utf-8")
    assert "enforce_startup_policy" in source
    assert 'uvicorn.run(app, host=bind_host' in source


def test_loopback_detection_is_not_a_hardcoded_string_compare():
    """判据必须是地址判定：``127.0.0.53`` 这类整段 127/8 也是回环。"""

    assert ipaddress.ip_address("127.0.0.53").is_loopback
    assert nb.is_loopback_host("127.0.0.53")


# --------------------------------------------------------------------------- #
# 控制实验
# --------------------------------------------------------------------------- #

def test_control_experiment_origin_guard_is_consulted(monkeypatch):
    """同源判定若被摘掉，跨源写必须在这里红——而不是靠 ``allow_origins`` 兜。"""

    _set(monkeypatch, host="127.0.0.1", token=GOOD_TOKEN)
    scope = _agent_scope("POST", origin="https://evil.example")
    assert is_http_browser_origin_allowed(scope) is False
    assert is_http_browser_origin_allowed(_agent_scope("POST")) is True
    assert is_http_browser_origin_allowed(
        _agent_scope("POST", origin="http://127.0.0.1:48911")) is True


def test_control_experiment_policy_is_not_softcoded(monkeypatch):
    _set(monkeypatch, host="0.0.0.0")
    assert nb.evaluate_startup_policy().accepted is False
    assert nb.authorize_request(
        client_host="192.168.1.5", method="POST", remote_exposed=False)[0] is False
    _set(monkeypatch, host="127.0.0.1")
    assert nb.authorize_request(
        client_host="127.0.0.1", method="POST", remote_exposed=False)[0] is True
