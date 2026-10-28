# -*- coding: utf-8 -*-
"""WO-267 / P0-1、P0-3：本机服务边界策略的决策表。

NEKO 侧 ``NEKO/N.E.K.O/tests/unit/test_net_boundary_policy.py`` 钉的是**同一张表**。
两份实现（根 ``system/net_boundary.py`` 与 NEKO ``utils/net_boundary.py``）分进程
运行、无法互相 import，所以漂移只能靠表来钉：改一边不改另一边，另一侧红。

控制实验（工单验收要求「注入失败 ⇒ 行为正确」）见文件末尾：把 ``0.0.0.0`` 当成
回环、把过短令牌当成有效，都会在这里被拒。
"""

from __future__ import annotations

import re
import socket

import pytest

from system import net_boundary as nb

BOUNDARY_ENVS = (
    nb.BIND_HOST_ENV,
    nb.ALLOW_REMOTE_ENV,
    nb.AUTH_TOKEN_ENV,
    "API_SERVER_HOST",
    "LLM_SERVICE_HOST",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """每个用例从「未配置」开始，并把进程内的生效绑定地址复位。"""

    for name in BOUNDARY_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(nb, "_effective_bind_host", None)
    yield
    monkeypatch.setattr(nb, "_effective_bind_host", None)


GOOD_TOKEN = "t" * nb.MIN_TOKEN_LENGTH


def _set(monkeypatch, *, host=None, allow=None, token=...):
    if host is not None:
        monkeypatch.setenv(nb.BIND_HOST_ENV, host)
    if allow is not None:
        monkeypatch.setenv(nb.ALLOW_REMOTE_ENV, allow)
    if token is not ...:
        if token is None:
            monkeypatch.delenv(nb.AUTH_TOKEN_ENV, raising=False)
        else:
            monkeypatch.setenv(nb.AUTH_TOKEN_ENV, token)


# --------------------------------------------------------------------------- #
# 绑定地址判定
# --------------------------------------------------------------------------- #

LOOPBACK_HOSTS = [
    "127.0.0.1",
    "localhost",
    "::1",
    "[::1]",
    "127.0.0.53",          # 整段 127/8 都是回环，不只是 .1
    "LOCALHOST.",          # FQDN 尾点
    "::ffff:127.0.0.1",    # IPv4 映射的 IPv6 回环
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
    """空串 = 通配，不是回环。旧代码 ``host=""`` 会绑到所有网卡。"""

    assert not nb.is_loopback_host("")
    assert nb.is_wildcard_host("")


@pytest.mark.parametrize(
    "host,expected",
    [
        ("0.0.0.0", (socket.AF_INET, "0.0.0.0")),
        ("", (socket.AF_INET, "0.0.0.0")),
        ("::", (socket.AF_INET6, "::")),
        ("[::1]", (socket.AF_INET6, "::1")),
        ("fe80::1", (socket.AF_INET6, "fe80::1")),
        ("127.0.0.1", (socket.AF_INET, "127.0.0.1")),
    ],
)
def test_bind_pair_family_matches_listen_address(host, expected):
    """端口探测必须用即将监听的地址族：AF_INET 探 ``::1`` 恒成功 ⇒ 误报端口空闲。"""

    assert nb.bind_pair(host) == expected


# --------------------------------------------------------------------------- #
# 环境变量语义
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    ("1", True),
    (" 1 ", True),
    ("0", False),
    ("true", False),   # 只认字面量 1：拼错的值必须落在关闭那一侧
    ("yes", False),
    ("on", False),
    ("2", False),
    ("", False),
    ("ture", False),
])
def test_allow_remote_only_literal_one(monkeypatch, raw, expected):
    monkeypatch.setenv(nb.ALLOW_REMOTE_ENV, raw)
    assert nb.read_allow_remote() is expected, raw


def test_allow_remote_unset_is_false(monkeypatch):
    monkeypatch.delenv(nb.ALLOW_REMOTE_ENV, raising=False)
    assert nb.read_allow_remote() is False


def test_default_bind_host_is_loopback(monkeypatch):
    monkeypatch.delenv(nb.BIND_HOST_ENV, raising=False)
    assert nb.read_bind_host() == "127.0.0.1"


@pytest.mark.parametrize("token,expected_state", [
    (None, "unset"),
    ("", "unset"),
    ("   ", "unset"),
    ("x" * (nb.MIN_TOKEN_LENGTH - 1), "too_short"),
    ("x" * nb.MIN_TOKEN_LENGTH, "ok"),
    ("x" * 64, "ok"),
])
def test_token_is_tri_valued(monkeypatch, token, expected_state):
    """``too_short`` 既不退化成「没有令牌」，也不被当成「已经配了」。"""

    _set(monkeypatch, token=token)
    value, state = nb.read_auth_token()
    assert state == expected_state
    if expected_state == "unset":
        assert value == ""


def test_token_value_never_leaks_into_snapshot(monkeypatch):
    """健康检查只报状态，不报值——包括「过短」那种半截令牌。"""

    _set(monkeypatch, token="short-token")
    assert GOOD_TOKEN not in str(nb.boundary_snapshot())
    assert "short-token" not in str(nb.boundary_snapshot())
    assert nb.boundary_snapshot()["auth_token_state"] == "too_short"


# --------------------------------------------------------------------------- #
# 启动期决策表（与 NEKO 侧逐行一致）
# --------------------------------------------------------------------------- #

STARTUP_TABLE = [
    # host,        allow_remote, token_state, accepted, 首条拒绝理由的关键词
    ("127.0.0.1",  False,        "unset",     True,     ""),
    ("localhost",  False,        "unset",     True,     ""),
    ("::1",        False,        "unset",     True,     ""),
    ("127.0.0.1",  True,         "unset",     True,     ""),   # 回环绑定不需要令牌
    ("127.0.0.1",  True,         "ok",        True,     ""),
    ("0.0.0.0",    False,        "unset",     False,    "NEKO_ALLOW_REMOTE"),
    ("0.0.0.0",    True,         "unset",     False,    "NEKO_AUTH_TOKEN"),
    ("0.0.0.0",    False,        "too_short", False,    "NEKO_ALLOW_REMOTE"),
    ("0.0.0.0",    True,         "too_short", False,    "NEKO_AUTH_TOKEN"),
    ("0.0.0.0",    True,         "ok",        True,     ""),
    ("::",         True,         "ok",        True,     ""),
    ("192.168.1.10", True,       "ok",        True,     ""),
    ("192.168.1.10", False,      "ok",        False,    "NEKO_ALLOW_REMOTE"),
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


def test_too_short_reason_states_the_length(monkeypatch):
    _set(monkeypatch, host="0.0.0.0", allow="1", token="x" * 8)
    decision = nb.evaluate_startup_policy()
    assert not decision.accepted
    assert "8 < 32" in " ".join(decision.reasons)


def test_wildcard_without_token_lists_both_blockers(monkeypatch):
    """两个闸门都没开 ⇒ 两条都报，别让用户修一个再撞第二个。"""

    _set(monkeypatch, host="0.0.0.0")
    decision = nb.evaluate_startup_policy()
    assert len(decision.reasons) == 2


def test_enforce_raises_ex_config_before_listening(monkeypatch, capsys):
    _set(monkeypatch, host="0.0.0.0", allow="1")  # 有开关、没令牌
    with pytest.raises(SystemExit) as excinfo:
        nb.enforce_startup_policy("测试组件")
    assert excinfo.value.code == nb.EX_CONFIG == 78
    err = capsys.readouterr().err
    assert nb.AUTH_TOKEN_ENV in err
    assert "测试组件" in err


def test_enforce_records_and_returns_loopback(monkeypatch):
    _set(monkeypatch, host="127.0.0.1")
    assert nb.effective_bind_host() == "127.0.0.1"
    assert nb.enforce_startup_policy("测试组件") == "127.0.0.1"
    assert nb.remote_exposure_in_effect() is False


def test_enforce_accepts_the_fully_opened_case(monkeypatch):
    _set(monkeypatch, host="0.0.0.0", allow="1", token=GOOD_TOKEN)
    assert nb.enforce_startup_policy("测试组件") == "0.0.0.0"
    assert nb.remote_exposure_in_effect() is True


def test_empty_bind_host_falls_back_to_loopback(monkeypatch):
    """``config.api_server.host=""`` 这类空值不能被判成非回环而拒绝启动。"""

    _set(monkeypatch, host="")
    assert nb.enforce_startup_policy("测试组件") == "127.0.0.1"


# --------------------------------------------------------------------------- #
# 单请求放行
# --------------------------------------------------------------------------- #

REQUEST_TABLE = [
    # exposed, token_state, candidate,        client,     method,   allowed
    (False, "unset",     "",             "127.0.0.1", "GET",    True),
    (False, "unset",     "",             "127.0.0.1", "POST",   True),
    (False, "unset",     "",             "::1",       "DELETE", True),
    (False, "unset",     "",             "192.168.1.5", "GET",  True),   # 读：回环绑定下不拦（历史自用场景）
    (False, "unset",     "",             "192.168.1.5", "POST", False),  # 写：非回环来源一律拒
    (False, "ok",        "",             "10.0.0.9",    "PUT",  False),
    (False, "ok",        GOOD_TOKEN,     "10.0.0.9",    "PUT",  True),   # 反代转发的跨机写：带对令牌才放
    (True,  "unset",     "",             "127.0.0.1",   "GET",  False),  # 开了远程 ⇒ 本机匿名也不放行
    (True,  "too_short", "x" * 8,        "127.0.0.1",   "GET",  False),  # 过短令牌不等于已鉴权
    (True,  "ok",        "",             "127.0.0.1",   "POST", False),
    (True,  "ok",        "wrong-token",  "127.0.0.1",   "GET",  False),
    (True,  "ok",        GOOD_TOKEN,     "127.0.0.1",   "POST", True),
    (True,  "ok",        GOOD_TOKEN,     "192.168.1.5", "GET",  True),
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


def test_remote_exposure_is_read_from_the_effective_bind_host(monkeypatch):
    """策略判定与真实监听同源：绕过启动器的裸 uvicorn 调用不能让它脱钩。"""

    _set(monkeypatch, host="127.0.0.1", allow="1", token=GOOD_TOKEN)
    nb.record_bind_host("0.0.0.0")
    ok, _detail = nb.authorize_request(client_host="127.0.0.1", method="GET")
    assert ok is False


def test_extract_token_precedence():
    headers = {
        "authorization": "Bearer from-header",
        "x-neko-token": "from-alt",
    }
    assert nb.extract_token(headers) == "from-header"
    assert nb.extract_token({"x-neko-token": "from-alt"}) == "from-alt"
    assert nb.extract_token({"authorization": "Basic Zm9vOmJhcg=="}) == ""
    assert nb.extract_token({}) == ""


def test_extract_token_survives_missing_get():
    class NoGet:
        pass

    assert nb.extract_token(NoGet()) == ""


# --------------------------------------------------------------------------- #
# ASGI 闸门
# --------------------------------------------------------------------------- #

def _scope(path="/call", method="POST", client="192.168.1.5", headers=(), typ="http"):
    return {
        "type": typ,
        "path": path,
        "method": method,
        "client": (client, 51234),
        "headers": list(headers),
    }


PASSED: list[str] = []


async def _echo_app(scope, receive, send):
    """下游替身：只有真正被透传才会记一笔。"""

    PASSED.append(scope["path"])


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _run(middleware, scope):
    """跑一遍中间件，返回 (透传给下游的路径列表, ASGI 消息摘录)。"""

    import asyncio

    PASSED.clear()
    result: list = []

    async def send(message):
        if message["type"] == "http.response.start":
            result.append(message["status"])
            result.append({
                k.decode("latin-1"): v.decode("latin-1")
                for k, v in message.get("headers", [])
            })
        elif message["type"] == "websocket.close":
            result.append(("ws-close", message.get("code")))

    asyncio.run(middleware(scope, _receive, send))
    return list(PASSED), result


def test_asgi_gate_blocks_remote_write_and_admits_loopback(monkeypatch):
    _set(monkeypatch, host="127.0.0.1")
    gate = nb.LocalBoundaryMiddleware(_echo_app, component="测试组件")

    passed, out = _run(gate, _scope(method="POST", client="192.168.1.5"))
    assert passed == [] and out[0] == 401, out

    passed, out = _run(gate, _scope(method="POST", client="127.0.0.1"))
    assert passed == ["/call"] and out == []


def test_asgi_gate_requires_token_on_every_source_once_exposed(monkeypatch):
    _set(monkeypatch, host="0.0.0.0", allow="1", token=GOOD_TOKEN)
    nb.record_bind_host("0.0.0.0")
    gate = nb.LocalBoundaryMiddleware(_echo_app, component="测试组件")

    passed, out = _run(gate, _scope(method="GET", client="127.0.0.1"))
    assert passed == [] and out[0] == 401

    passed, out = _run(gate, _scope(
        method="GET", client="127.0.0.1",
        headers=[(b"authorization", b"Bearer " + GOOD_TOKEN.encode())],
    ))
    assert passed == ["/call"] and out == []


def test_asgi_gate_public_paths_stay_open(monkeypatch):
    _set(monkeypatch, host="0.0.0.0", allow="1", token=GOOD_TOKEN)
    nb.record_bind_host("0.0.0.0")
    gate = nb.LocalBoundaryMiddleware(_echo_app, component="测试组件", public_paths=("/health",))
    passed, _out = _run(gate, _scope(path="/health", method="GET", client="192.168.1.5"))
    assert passed == ["/health"]


def test_asgi_gate_rejects_websocket_handshake_with_policy_violation(monkeypatch):
    _set(monkeypatch, host="0.0.0.0", allow="1", token=GOOD_TOKEN)
    nb.record_bind_host("0.0.0.0")
    gate = nb.LocalBoundaryMiddleware(_echo_app, component="测试组件")
    passed, out = _run(gate, _scope(path="/ws", typ="websocket", method=None, client="192.168.1.5"))
    assert passed == []
    assert out and out[0] == ("ws-close", 1008)


def test_asgi_gate_never_caches_denied_response(monkeypatch):
    _set(monkeypatch, host="0.0.0.0", allow="1", token=GOOD_TOKEN)
    nb.record_bind_host("0.0.0.0")
    gate = nb.LocalBoundaryMiddleware(_echo_app, component="测试组件")
    _passed, out = _run(gate, _scope(method="GET", client="127.0.0.1"))
    assert out[1].get("cache-control") == "no-store"


# --------------------------------------------------------------------------- #
# 跨源写（P0-6 同源判定在根侧的等价物）
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("origin", [
    "https://evil.example",
    "http://localhost.evil.com:8080",   # 子串绕过：CORS 那条 $ 锚定挡住，这里同样挡住
    "http://192.168.1.99:5173",         # 非本机壳来源（局域网页面）无令牌不放行
    "null",
])
def test_foreign_browser_origin_write_is_rejected(origin, monkeypatch):
    """外部网页 POST 本机端口：CORS 只管读响应，拦不住这类写请求。"""

    _set(monkeypatch, host="127.0.0.1")
    gate = nb.LocalBoundaryMiddleware(_echo_app, component="测试组件")
    passed, out = _run(gate, _scope(
        method="POST", client="127.0.0.1", headers=[(b"origin", origin.encode())]))
    assert passed == [] and out[0] == 403, (origin, out)


@pytest.mark.parametrize("origin", [
    "http://127.0.0.1:5173",
    "https://localhost:8000",
    "lumo-app://dist",
    "file://",
])
def test_local_shell_origin_write_passes(origin, monkeypatch):
    """Electron 构建版 / dev 页面 / file 壳：与 CORS 白名单同一口径，别把人锁在门外。"""

    _set(monkeypatch, host="127.0.0.1")
    gate = nb.LocalBoundaryMiddleware(_echo_app, component="测试组件")
    passed, _out = _run(gate, _scope(
        method="POST", client="127.0.0.1", headers=[(b"origin", origin.encode())]))
    assert passed == ["/call"], (origin, _out)


def test_valid_token_bypasses_origin_check(monkeypatch):
    """局域网 UI 是运维显式配了令牌的客户端：来源判定不该再拦它。"""

    _set(monkeypatch, host="0.0.0.0", allow="1", token=GOOD_TOKEN)
    nb.record_bind_host("0.0.0.0")
    gate = nb.LocalBoundaryMiddleware(_echo_app, component="测试组件")
    passed, _out = _run(gate, _scope(
        method="POST", client="192.168.1.5",
        headers=[(b"origin", b"http://192.168.1.9:5173"),
                 (b"authorization", b"Bearer " + GOOD_TOKEN.encode())]))
    assert passed == ["/call"]


def test_origin_whitelist_shares_the_cors_regex():
    """口径只有一份：能过 CORS 的源才允许无令牌发起变更，两处不能各写一套。"""

    from system.cors_config import LOCAL_ORIGIN_REGEX

    assert nb.is_trusted_local_origin("http://localhost.evil.com:8080") is False
    assert nb.is_trusted_local_origin("http://127.0.0.1:5173") is True
    assert nb.is_trusted_local_origin("lumo-app://dist") is True
    assert nb.is_trusted_local_origin("") is True
    for probe in ("http://127.0.0.1:5173", "lumo-app://dist", "file://"):
        assert bool(re.match(LOCAL_ORIGIN_REGEX, probe)) is nb.is_trusted_local_origin(probe)


# --------------------------------------------------------------------------- #
# 装配点：新路由默认落在保护面里
# --------------------------------------------------------------------------- #

def test_mcp_app_registers_the_boundary_middleware():
    from mcpserver.mcp_server import app

    names = [item.cls.__name__ for item in app.user_middleware]
    assert "LocalBoundaryMiddleware" in names, names
    # CORS 必须比边界更外层，否则 401 不带 CORS 头，浏览器侧只显示 "Failed to fetch"
    assert names.index("CORSMiddleware") < names.index("LocalBoundaryMiddleware"), names


def test_agent_app_registers_the_boundary_middleware():
    from agentserver.agent_server import app

    names = [item.cls.__name__ for item in app.user_middleware]
    assert "LocalBoundaryMiddleware" in names, names
    assert names.index("CORSMiddleware") < names.index("LocalBoundaryMiddleware"), names


def test_openclaw_install_is_default_closed(monkeypatch):
    """安装接口不能靠边界令牌顺带放行：那是另一件事，要另一个开关。"""

    from agentserver.agent_server_parts.openclaw import INSTALL_ENV

    monkeypatch.delenv(INSTALL_ENV, raising=False)
    assert nb.explicit_opt_in(INSTALL_ENV) is False
    monkeypatch.setenv(INSTALL_ENV, "true")
    assert nb.explicit_opt_in(INSTALL_ENV) is False
    monkeypatch.setenv(INSTALL_ENV, "1")
    assert nb.explicit_opt_in(INSTALL_ENV) is True


# --------------------------------------------------------------------------- #
# 控制实验：故意改坏判据 ⇒ 上面必须有测试红
# --------------------------------------------------------------------------- #

def test_control_experiment_policy_is_not_softcoded(monkeypatch):
    """把「0.0.0.0 视为回环」注进实现 ⇒ 通配 + 无令牌必须仍然被拒。

    这条不是走形式：P0-1 存活两年，正是因为「绑 0.0.0.0」在旧代码里被写成
    默认且无任何判定。这里显式钉住判据来自 ``is_loopback_host``，而不是
    某个 ``if host != "0.0.0.0"`` 的旁路。
    """

    _set(monkeypatch, host="0.0.0.0")
    assert nb.evaluate_startup_policy().accepted is False
    assert nb.authorize_request(
        client_host="192.168.1.5", method="POST", remote_exposed=False
    )[0] is False
    # 反向：判据若被放宽成「回环也算远程」，本机自用会立刻坏
    _set(monkeypatch, host="127.0.0.1")
    assert nb.authorize_request(
        client_host="127.0.0.1", method="POST", remote_exposed=False
    )[0] is True
