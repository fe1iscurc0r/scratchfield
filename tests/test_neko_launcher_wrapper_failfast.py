"""issue #19: neko_launcher_wrapper monkey-patch fail-fast 守护。

原实现多处静默吞错：overlay 缺失只打 WARN 就继续、lifecycle 校验
失败只打 WARN、patch 后无生效断言。修复后：
- overlay 缺失抛 RuntimeError（融合功能整体失效不许无声）
- lifecycle import/校验失败 sys.exit(1)
- 每个 patch 后断言属性确实被替换

wrapper 模块级要求 LUMO_PROXY_TOKEN（铁律7），导入前先设置。
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import types
from pathlib import Path

import pytest

_WRAPPER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "neko_launcher_wrapper.py"


def _load_wrapper(monkeypatch) -> types.ModuleType:
    monkeypatch.setenv("LUMO_PROXY_TOKEN", "test-token")
    spec = importlib.util.spec_from_file_location("neko_launcher_wrapper", _WRAPPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def wrapper(monkeypatch):
    return _load_wrapper(monkeypatch)


def test_missing_overlay_raises_instead_of_silent_continue(wrapper, monkeypatch, tmp_path):
    """overlay 缺失必须抛错，不许 WARN 后静默继续（融合功能会无声失效）。"""
    fake_os = types.SimpleNamespace(
        path=types.SimpleNamespace(
            join=os.path.join,
            dirname=os.path.dirname,
            exists=lambda p: False,
        ),
        environ=os.environ,
    )
    monkeypatch.setattr(wrapper, "os", fake_os)

    with pytest.raises(RuntimeError, match="overlay file not found"):
        wrapper._patch_api_providers()


def test_servers_patch_effective_and_memory_server_removed(wrapper, monkeypatch):
    """_patch_servers_list：正常替换 + memory_server 被移除。"""
    runtime_stub = types.ModuleType("launcher_core.runtime")
    runtime_stub.SERVERS = [
        {"module": "main_server"},
        {"module": "memory_server"},
        {"module": "subtitle_server"},
    ]
    launcher_stub = types.ModuleType("launcher_core")
    launcher_stub.runtime = runtime_stub
    monkeypatch.setitem(sys.modules, "launcher_core", launcher_stub)
    monkeypatch.setitem(sys.modules, "launcher_core.runtime", runtime_stub)

    wrapper._patch_servers_list()

    assert all(s["module"] != "memory_server" for s in runtime_stub.SERVERS)
    assert len(runtime_stub.SERVERS) == 2


def test_uvicorn_run_patch_effective_and_intercepts_monitor(wrapper, monkeypatch):
    """_patch_monitor_host：uvicorn.run 被替换，且 monitor 端口 0.0.0.0 被改写。"""
    calls = []

    uvicorn_stub = types.ModuleType("uvicorn")
    uvicorn_stub.run = lambda app, host=None, port=None, **kw: calls.append((host, port))
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn_stub)

    network_stub = types.ModuleType("config.network")
    network_stub.MONITOR_SERVER_PORT = 48912
    config_stub = types.ModuleType("config")
    config_stub.network = network_stub
    monkeypatch.setitem(sys.modules, "config", config_stub)
    monkeypatch.setitem(sys.modules, "config.network", network_stub)

    wrapper._patch_monitor_host()
    assert uvicorn_stub.run is not None

    uvicorn_stub.run("app", host="0.0.0.0", port=48912)
    uvicorn_stub.run("app", host="0.0.0.0", port=48911)  # 非 monitor 端口不动

    assert calls[0] == ("127.0.0.1", 48912)
    assert calls[1] == ("0.0.0.0", 48911)


def test_lifecycle_verify_exits_on_import_failure(wrapper, monkeypatch, tmp_path):
    """lifecycle 不可 import 时 sys.exit(1)，不许 WARN 后继续。"""
    pkg_stub = types.ModuleType("main_logic")
    pkg_stub.__path__ = [str(tmp_path)]  # 空目录 → 子模块 import 必失败
    monkeypatch.setitem(sys.modules, "main_logic", pkg_stub)
    sys.modules.pop("main_logic.core", None)
    sys.modules.pop("main_logic.core.lifecycle", None)

    with pytest.raises(SystemExit) as exc_info:
        wrapper._verify_lifecycle_patch()
    assert exc_info.value.code == 1


def test_lifecycle_verify_exits_when_markers_missing(wrapper, monkeypatch):
    """源码 patch 标注不足 4 处时 sys.exit(1)。"""
    lifecycle_stub = types.ModuleType("main_logic.core.lifecycle")
    core_stub = types.ModuleType("main_logic.core")
    core_stub.lifecycle = lifecycle_stub
    pkg_stub = types.ModuleType("main_logic")
    pkg_stub.core = core_stub
    monkeypatch.setitem(sys.modules, "main_logic", pkg_stub)
    monkeypatch.setitem(sys.modules, "main_logic.core", core_stub)
    monkeypatch.setitem(sys.modules, "main_logic.core.lifecycle", lifecycle_stub)
    monkeypatch.setattr(
        inspect, "getsource", lambda m: "仅一处 [local-patch] 陆墨融合 标注"
    )

    with pytest.raises(SystemExit) as exc_info:
        wrapper._verify_lifecycle_patch()
    assert exc_info.value.code == 1


def test_lifecycle_verify_passes_with_enough_markers(wrapper, monkeypatch, capsys):
    lifecycle_stub = types.ModuleType("main_logic.core.lifecycle")
    core_stub = types.ModuleType("main_logic.core")
    core_stub.lifecycle = lifecycle_stub
    pkg_stub = types.ModuleType("main_logic")
    pkg_stub.core = core_stub
    monkeypatch.setitem(sys.modules, "main_logic", pkg_stub)
    monkeypatch.setitem(sys.modules, "main_logic.core", core_stub)
    monkeypatch.setitem(sys.modules, "main_logic.core.lifecycle", lifecycle_stub)
    monkeypatch.setattr(
        inspect, "getsource", lambda m: "[local-patch] 陆墨融合 " * 4
    )

    wrapper._verify_lifecycle_patch()  # 不应退出
    assert "verified (4/4)" in capsys.readouterr().out


def test_wrapper_import_requires_token(monkeypatch):
    """铁律7 回归：无 LUMO_PROXY_TOKEN 时模块导入直接退出。"""
    monkeypatch.delenv("LUMO_PROXY_TOKEN", raising=False)
    spec = importlib.util.spec_from_file_location(
        "neko_launcher_wrapper_no_token", _WRAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    with pytest.raises(SystemExit) as exc_info:
        spec.loader.exec_module(module)
    assert exc_info.value.code == 1
