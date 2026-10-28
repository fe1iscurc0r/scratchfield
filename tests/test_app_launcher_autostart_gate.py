"""工单269 T2（P0-7）· 应用启动器的开机自启确认门。

被测对象：``NEKO/N.E.K.O/plugin/plugins/app_launcher/__init__.py``。
开机自启会往 ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` 落一条
"开机即执行"的命令——跨重启的持久化写入。改动前，一次 ``set_autostart(app_id,
enabled=true)`` 就写进去了；``add_app(autostart=true)`` 和 ``update_app``（改完路径
"顺手刷新"）同样能。

测试口径（对应工单验收项）：
    1. 「调用 set_autostart 不产生注册表写入」——断言 SetValueEx **未被调用**、
       返回体含确认要求；
    2. 令牌两跳才落盘；一次性、绑定命令原文、到期作废、绑会话；
    3. 登记/改路径校验：不存在 / UNC / ``..`` / 相对路径 / 非白名单类型全部被拒；
    4. launch_app 只认已登记的 app_id，不接调用方临时给的路径；
    5. 落盘前完整 command 进日志（顺序断言：日志先于 SetValueEx）。

本机/CI 约束（诚实登记，别当成覆盖够了）：
    * NEKO 自带 venv 里没有 pytest，且 ``plugin.sdk.plugin`` 依赖 msgpack，本仓
      venv 装不了（工单边界：不新增外部依赖、NEKO 环境禁动）。所以在 import 插件
      之前把 ``plugin.sdk.plugin`` 换成 **sys.modules 门面桩**，桩里的符号全部取自
      NEKO 真实 SDK 中不依赖 msgpack 的模块（decorators / models / base）——被测
      代码走的还是真装饰器、真 EventMeta，不是手搓假元数据。
    * ``winreg`` 一律换成假模块、``_is_windows`` 打桩：这样测试在 Linux 上跑绿也
      算数，而且绝不碰真注册表。
    * ``NEKO/**`` 是 ``tools/sync_neko_upstream.py`` 每次同步都会整片覆盖的子树，
      测试放进去等于随时可能被上游抹掉。这道守卫因此放在**仓根 tests/**（同步碰不到
      这里）：门一旦被覆盖掉，这里立刻红。
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[1]
NEKO_ROOT = ROOT / "NEKO" / "N.E.K.O"


def _install_sdk_shim() -> None:
    """把 ``plugin.sdk.plugin`` 换成 msgpack-free 的真符号门面（必须在导入插件前）。"""
    if "plugin.plugins.app_launcher" in sys.modules:
        return
    # 必须是 insert(0)：append 会让先前的 sys.path 条目抢先命中，NEKO SDK 里的
    # ``import utils`` 会捡到 agentserver/utils.py（同名不同物），既导不动插件，
    # 又把这份假 utils 缓存进 sys.modules，毒到后面所有需要 NEKO utils 的测试。
    if str(NEKO_ROOT) not in sys.path:
        sys.path.insert(0, str(NEKO_ROOT))
    from plugin.sdk.shared.core.base import NekoPluginBase
    from plugin.sdk.shared.core.decorators import lifecycle, neko_plugin, plugin_entry
    from plugin.sdk.shared.models import Err, Ok, SdkError

    shim = types.ModuleType("plugin.sdk.plugin")
    for name, value in {
        "NekoPluginBase": NekoPluginBase,
        "neko_plugin": neko_plugin,
        "plugin_entry": plugin_entry,
        "lifecycle": lifecycle,
        "Ok": Ok,
        "Err": Err,
        "SdkError": SdkError,
    }.items():
        setattr(shim, name, value)
    sys.modules["plugin.sdk.plugin"] = shim


_install_sdk_shim()

import plugin.plugins.app_launcher as mod  # noqa: E402

EVENT_META_ATTR = "__neko_event_meta__"


def meta_of(method) -> Any:
    meta = getattr(method, EVENT_META_ATTR, None)
    assert meta is not None, f"{method.__name__} 没被 @plugin_entry 装饰（EventMeta 丢失）"
    return meta


class _RecorderLogger:
    """按 logger.info("... {} ...", arg) 的形状把调用顺序记进同一条流水。"""

    def __init__(self, sink: List[str]) -> None:
        self._sink = sink

    def _emit(self, level: str, message: Any, *args: Any) -> None:
        rendered = str(message)
        if args:
            try:
                rendered = rendered.format(*args)
            except (IndexError, KeyError):
                rendered = f"{rendered} {args!r}"
        self._sink.append(f"{level}:{rendered}")

    def info(self, message: Any, *args: Any) -> None:
        self._emit("INFO", message, *args)

    def warning(self, message: Any, *args: Any) -> None:
        self._emit("WARN", message, *args)

    def error(self, message: Any, *args: Any) -> None:
        self._emit("ERROR", message, *args)


class _KeyCtx:
    def __init__(self) -> None:
        pass

    def __enter__(self) -> str:
        return "fake-key"

    def __exit__(self, *_exc: Any) -> bool:
        return False


def _fake_winreg_module(events: List[str]) -> types.ModuleType:
    """替身 winreg：只往 ``events`` 记流水，永不落盘。"""

    def open_key(*_a: Any, **_k: Any) -> _KeyCtx:
        return _KeyCtx()

    def set_value_ex(_key: Any, name: str, _reserved: int, _typ: int, value: str) -> None:
        events.append(f"SetValueEx:{name}={value!r}")

    def delete_value(_key: Any, name: str) -> None:
        events.append(f"DeleteValue:{name}")

    def query_value_ex(_key: Any, _name: str) -> tuple:
        raise FileNotFoundError("no such value")

    def enum_value(_key: Any, _index: int):
        raise OSError("no values")

    module = types.ModuleType("winreg")
    module.HKEY_CURRENT_USER = "HKCU"
    module.KEY_SET_VALUE = 2
    module.KEY_READ = 1
    module.REG_SZ = 1
    module.OpenKey = open_key
    module.SetValueEx = set_value_ex
    module.DeleteValue = delete_value
    module.QueryValueEx = query_value_ex
    module.EnumValue = enum_value
    return module


class _FakeStore:
    """list_apps 之类走存储的路径；本测试直接喂内存清单，所以这里恒空。"""

    enabled = False

    def _read_value(self, _key: str, default: Any) -> Any:
        return default

    def _write_value(self, _key: str, _value: Any) -> None:
        pass


class FakeLauncher(mod.AppLauncherPlugin):
    """真插件类 + 内存清单。只替换存储与日志，入口逻辑一律走真代码。"""

    def __init__(self, events: List[str], apps: Optional[List[Dict[str, Any]]] = None) -> None:
        self.logger = _RecorderLogger(events)
        self.store = _FakeStore()
        self._apps: List[Dict[str, Any]] = list(apps or [])
        self._apps_lock = threading.Lock()
        self._recent_lock = threading.Lock()
        self._autostart_confirmations = mod._AutostartConfirmationGate()

    def _load_apps_unlocked(self) -> List[Dict[str, Any]]:
        return [dict(app) for app in self._apps]

    def _save_apps_unlocked(self, apps: List[Dict[str, Any]]) -> None:
        self._apps = [dict(app) for app in apps]


def make_launcher(events: List[str], monkeypatch) -> FakeLauncher:
    plugin = FakeLauncher(events)
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg_module(events))
    monkeypatch.setattr(mod, "_is_windows", lambda: True)
    return plugin


@pytest.fixture
def events() -> List[str]:
    return []


@pytest.fixture
def launcher(events, monkeypatch) -> FakeLauncher:
    return make_launcher(events, monkeypatch)


def registered_app(tmp_path: Path, *, name: str = "Demo", app_id: str = "a1",
                   autostart: bool = False, filename: str = "Demo.exe") -> Dict[str, Any]:
    """造一个真在磁盘上的 ``.exe``（校验链里有 exists 这一关，必须真给文件）。"""
    exe = tmp_path / filename
    if not exe.exists():
        exe.write_bytes(b"MZ\x90\x00")
    path = str(exe)
    return {
        "id": app_id,
        "name": name,
        "path": path,
        "resolved_path": mod._resolve_path(path),
        "type": mod._get_file_type(path),
        "aliases": [],
        "description": "",
        "autostart": autostart,
    }


def registry_writes(events: List[str]) -> List[str]:
    """从同一条流水里只挑注册表动作（日志和写动作共用 events，顺序断言要用）。"""
    return [item for item in events if item.startswith(("SetValueEx:", "DeleteValue:"))]


def run(coro) -> Any:
    return asyncio.run(coro)


def data_of(result: Any) -> Dict[str, Any]:
    assert result.is_ok(), f"期望 Ok，实际 Err: {result.error}"
    return result.value


# ---------------------------------------------------------------- 1. 模型可见面


def test_set_autostart_is_off_the_agent_surface() -> None:
    """第一层闸：入口退出 Agent 自动路由（brain/task_executor 读的就是这个标记）。"""
    assert meta_of(mod.AppLauncherPlugin.set_autostart).metadata.get("agent_auto") is False


def test_confirmation_token_is_not_llm_projected() -> None:
    """令牌只交给界面，不进模型可见字段——模型读不到令牌，也就无法自我确认。"""
    for method in (
        mod.AppLauncherPlugin.set_autostart,
        mod.AppLauncherPlugin.add_app,
        mod.AppLauncherPlugin.update_app,
    ):
        fields = list(meta_of(method).llm_result_fields or [])
        assert "confirmation_token" not in fields, f"{method.__name__} 把令牌投影给了模型"
        assert "command" not in fields, f"{method.__name__} 把待写命令投影给了模型"


def test_other_entries_stay_agent_visible() -> None:
    """边界登记：只收自启面。启动/列表仍归猫娘，否则这个插件就没意义了。"""
    for method in (mod.AppLauncherPlugin.launch_app, mod.AppLauncherPlugin.list_apps):
        assert meta_of(method).metadata.get("agent_auto") is not False


def test_packaged_manifest_matches_the_gate() -> None:
    """``plugin.meta.json`` 是主机读取的入口契约（刷新已不再导入插件）。

    它要是没跟着改，界面就发不出 ``confirmed``，这道门形同虚设——所以生成物必须
    和代码同批交付，这里把它钉住。
    """
    raw = json.loads(
        (NEKO_ROOT / "plugin/plugins/app_launcher/plugin.meta.json").read_text(encoding="utf-8")
    )
    entries = {e["id"]: e for e in raw["entries"]}
    autostart_entry = entries["set_autostart"]
    assert autostart_entry["metadata"].get("agent_auto") is False
    assert {"confirmed", "confirmation_token"} <= set(autostart_entry["input_schema"]["properties"])
    assert "confirmation_token" not in (autostart_entry["llm_result_fields"] or [])


# ---------------------------------------------------------------- 2. 单次调用不写注册表


def test_single_call_writes_no_registry(launcher: FakeLauncher, events: List[str], tmp_path: Path) -> None:
    """工单验收原文：调用 set_autostart 不产生注册表写入，且返回体含确认要求。"""
    app = registered_app(tmp_path)
    launcher._apps = [app]

    result = data_of(run(launcher.set_autostart(app_id=app["id"], enabled=True)))

    assert result["needs_confirmation"] is True
    assert result["success"] is False
    assert "确认" in result["message"]
    assert result["command"] == f'"{app["resolved_path"]}"'
    assert registry_writes(events) == [], f"未确认就动了注册表: {events}"


def test_confirm_two_step_writes_the_exact_command(launcher: FakeLauncher, events: List[str], tmp_path: Path) -> None:
    """人确认后（界面那一跳）才落盘，落的正是给人看过的那条命令。"""
    app = registered_app(tmp_path)
    launcher._apps = [app]

    first = data_of(run(launcher.set_autostart(app_id=app["id"], enabled=True)))
    token = first["confirmation_token"]
    events.clear()

    second = data_of(run(launcher.set_autostart(
        app_id=app["id"], enabled=True, confirmed=True, confirmation_token=token
    )))

    assert second["success"] is True, second
    # 落盘的字节必须等于刚才给人看过的那条命令
    assert registry_writes(events) == [f"SetValueEx:NekoAppLauncher_{app['id']}={first['command']!r}"]
    assert launcher._apps[0]["autostart"] is True


def test_token_is_one_shot(launcher: FakeLauncher, events: List[str], tmp_path: Path) -> None:
    """同一枚令牌用第二次必须被拒——回放不能再来一次写入。"""
    app = registered_app(tmp_path)
    launcher._apps = [app]
    first = data_of(run(launcher.set_autostart(app_id=app["id"], enabled=True)))

    run(launcher.set_autostart(app_id=app["id"], enabled=True, confirmed=True,
                               confirmation_token=first["confirmation_token"]))
    events.clear()

    replay = data_of(run(launcher.set_autostart(
        app_id=app["id"], enabled=True, confirmed=True,
        confirmation_token=first["confirmation_token"]
    )))

    assert replay["needs_confirmation"] is True
    assert registry_writes(events) == [], "用过的令牌被复用，又写了一次注册表"


def test_token_is_bound_to_the_command(launcher: FakeLauncher, events: List[str], tmp_path: Path) -> None:
    """确认之后换路径 ⇒ 旧令牌作废。不给"确认一次、之后随便换命令"留口子。"""
    app = registered_app(tmp_path)
    launcher._apps = [app]
    first = data_of(run(launcher.set_autostart(app_id=app["id"], enabled=True)))

    moved = registered_app(tmp_path, filename="Moved.exe")
    launcher._apps = [dict(app, path=moved["path"], resolved_path=moved["resolved_path"])]
    events.clear()

    result = data_of(run(launcher.set_autostart(
        app_id=app["id"], enabled=True, confirmed=True,
        confirmation_token=first["confirmation_token"]
    )))

    assert result["needs_confirmation"] is True
    assert registry_writes(events) == [], "命令原文变了还照写"


def test_expired_token_is_refused(launcher: FakeLauncher, events: List[str], tmp_path: Path, monkeypatch) -> None:
    app = registered_app(tmp_path)
    launcher._apps = [app]
    # TTL 在建门时定格（默认取模块常量），所以这里直接换一把已过期的门，而不是改常量
    launcher._autostart_confirmations = mod._AutostartConfirmationGate(ttl_seconds=-1.0)

    first = data_of(run(launcher.set_autostart(app_id=app["id"], enabled=True)))
    events.clear()
    result = data_of(run(launcher.set_autostart(
        app_id=app["id"], enabled=True, confirmed=True,
        confirmation_token=first["confirmation_token"]
    )))

    assert result["needs_confirmation"] is True
    assert registry_writes(events) == [], "过期令牌仍可用"


def test_scope_binds_the_token_to_the_calling_conversation(events: List[str], tmp_path: Path, monkeypatch) -> None:
    """A 会话签发的令牌不能在 B 会话消费（UI 直连时两边 scope 都是空串，不受影响）。

    必须用**同一个插件实例**：门是实例级的，换实例等于换个门，令牌本来就不在里面，
    那种"拒绝"证明不了 scope 起作用（变异对照 M7 就是这么把假绿抓出来的）。
    """
    app = registered_app(tmp_path)
    plugin = make_launcher(events, monkeypatch)
    plugin._apps = [app]

    issued = data_of(run(plugin.set_autostart(
        app_id=app["id"], enabled=True, _ctx={"conversation_id": "chat-A"}
    )))
    events.clear()

    refused = data_of(run(plugin.set_autostart(
        app_id=app["id"], enabled=True, confirmed=True,
        confirmation_token=issued["confirmation_token"], _ctx={"conversation_id": "chat-B"},
    )))

    assert refused["needs_confirmation"] is True
    assert registry_writes(events) == [], "跨会话重放了确认令牌"

    # 正对照：同一会话里换一张新令牌就该放行，否则上面那条红是"永远不放行"造成的
    again = data_of(run(plugin.set_autostart(
        app_id=app["id"], enabled=True, _ctx={"conversation_id": "chat-A"}
    )))
    events.clear()
    accepted = data_of(run(plugin.set_autostart(
        app_id=app["id"], enabled=True, confirmed=True,
        confirmation_token=again["confirmation_token"], _ctx={"conversation_id": "chat-A"},
    )))

    assert accepted["success"] is True, accepted
    assert len(registry_writes(events)) == 1, registry_writes(events)



def test_confirmation_ttl_and_pending_caps_are_a_table_not_scattered_literals() -> None:
    """令牌参数是配置表：5 分钟 / 一次性 / 有上限，改这里必须显式过一遍测试。"""
    assert mod._AUTOSTART_CONFIRM_TTL_SECONDS == 300.0
    assert mod._AUTOSTART_CONFIRM_MAX_PENDING == 64
    assert mod._AUTOSTART_CONFIRM_ACTION == "app_launcher.autostart"
    assert mod._EXECUTABLE_TYPES == ("exe", "lnk", "url", "script")


def test_pending_gate_does_not_grow_without_bound(tmp_path: Path, monkeypatch) -> None:
    """签发上限：界面反复点、模型反复试探都不能把内存堆满。"""
    gate = mod._AutostartConfirmationGate(max_pending=2)
    for idx in range(5):
        gate.issue({"app_id": f"a{idx}", "path": f"p{idx}", "command": f"c{idx}"})
    assert len(gate._pending) == 2


# ---------------------------------------------------------------- 3. 关是安全方向


def test_disable_needs_no_confirmation(launcher: FakeLauncher, events: List[str], tmp_path: Path) -> None:
    """取消自启不设闸：往"更少持久化"的方向走，拦住只会拖累用户自救。"""
    app = registered_app(tmp_path, autostart=True)
    launcher._apps = [app]

    result = data_of(run(launcher.set_autostart(app_id=app["id"], enabled=False)))

    assert result["success"] is True
    assert registry_writes(events) == [f"DeleteValue:NekoAppLauncher_{app['id']}"]
    assert launcher._apps[0]["autostart"] is False


# ---------------------------------------------------------------- 4. 落盘前打命令


def test_full_command_is_logged_before_the_write(launcher: FakeLauncher, events: List[str], tmp_path: Path) -> None:
    app = registered_app(tmp_path)
    launcher._apps = [app]
    first = data_of(run(launcher.set_autostart(app_id=app["id"], enabled=True)))

    events.clear()
    run(launcher.set_autostart(app_id=app["id"], enabled=True, confirmed=True,
                               confirmation_token=first["confirmation_token"]))

    write_at = next((i for i, item in enumerate(events) if item.startswith("SetValueEx")), None)
    assert write_at is not None, f"没写注册表: {events}"
    logged_before = [item for item in events[:write_at] if "Autostart WRITE" in item]
    assert logged_before, f"写之前没有把完整 command 打进日志: {events}"
    assert app["resolved_path"] in logged_before[0]


# ---------------------------------------------------------------- 5. add_app


def test_add_app_with_autostart_registers_but_writes_no_registry(
    launcher: FakeLauncher, events: List[str], tmp_path: Path
) -> None:
    exe = tmp_path / "Fresh.exe"
    exe.write_bytes(b"MZ\x90\x00")

    result = data_of(run(launcher.add_app(name="Fresh", path=str(exe), autostart=True)))

    assert len(launcher._apps) == 1, "软件应已登记进清单"
    assert launcher._apps[0]["autostart"] is False
    assert result["needs_confirmation"] is True
    assert registry_writes(events) == [], "add_app 绕过了确认门直接写注册表"


def test_token_issued_by_add_app_can_finish_the_job(
    launcher: FakeLauncher, events: List[str], tmp_path: Path
) -> None:
    """界面拿 add_app 返回的令牌，一跳 set_autostart 就能完成确认（不额外加摩擦）。"""
    exe = tmp_path / "Fresh.exe"
    exe.write_bytes(b"MZ\x90\x00")
    issued = data_of(run(launcher.add_app(name="Fresh", path=str(exe), autostart=True)))

    result = data_of(run(launcher.set_autostart(
        app_id=issued["app_id"], enabled=True, confirmed=True,
        confirmation_token=issued["confirmation_token"],
    )))

    assert result["success"] is True, result
    assert len(registry_writes(events)) == 1 and registry_writes(events)[0].startswith("SetValueEx")


@pytest.mark.parametrize("make_path", [
    pytest.param(lambda tmp_path: str(tmp_path / "Ghost.exe"), id="不存在的 exe"),
    pytest.param(lambda tmp_path: "\\\\evil\\share\\x.exe", id="UNC 路径"),
    pytest.param(lambda tmp_path: "C:\\apps\\..\\Windows\\system32\\cmd.exe", id="含 .. 越界"),
    pytest.param(lambda tmp_path: "relative/demo.exe", id="相对路径"),
    pytest.param(lambda tmp_path: str(tmp_path / "notes.txt"), id="非白名单类型"),
])
def test_add_app_refuses_bad_path(launcher: FakeLauncher, events: List[str], tmp_path: Path, make_path) -> None:
    rejected = run(launcher.add_app(name="Bad", path=make_path(tmp_path)))

    assert rejected.is_err(), f"恶意路径被放行: {data_of(rejected)}"
    assert launcher._apps == [], "被拒的路径不该进清单"
    assert registry_writes(events) == [], "被拒的路径不该动注册表"


# ---------------------------------------------------------------- 6. update_app


def test_update_app_refuses_bad_new_path(launcher: FakeLauncher, events: List[str], tmp_path: Path) -> None:
    app = registered_app(tmp_path)
    launcher._apps = [app]

    rejected = run(launcher.update_app(app_id=app["id"], path=str(tmp_path / "nope.exe")))

    assert rejected.is_err()
    assert launcher._apps[0]["path"] == app["path"], "拒绝后原路径必须保持"
    assert registry_writes(events) == []


def test_path_change_drops_autostart_instead_of_repointing_it(
    launcher: FakeLauncher, events: List[str], tmp_path: Path
) -> None:
    """改路径 ⇒ 之前确认过的命令失效：先摘掉旧自启项，新路径重新等确认。"""
    app = registered_app(tmp_path, autostart=True)
    launcher._apps = [app]
    moved = tmp_path / "Moved.exe"
    moved.write_bytes(b"MZ\x90\x00")

    result = data_of(run(launcher.update_app(app_id=app["id"], path=str(moved))))

    assert registry_writes(events) == [f"DeleteValue:NekoAppLauncher_{app['id']}"], f"不该写新命令: {events}"
    assert launcher._apps[0]["autostart"] is False
    assert result["needs_confirmation"] is True
    assert str(moved) in result["command"]


def test_update_app_without_path_change_keeps_autostart_untouched(
    launcher: FakeLauncher, events: List[str], tmp_path: Path
) -> None:
    """只改别名不该惊动注册表（确认门不是"任何更新都要点一下"的橡皮图章）。"""
    app = registered_app(tmp_path, autostart=True)
    launcher._apps = [app]

    result = data_of(run(launcher.update_app(app_id=app["id"], aliases=["dd"])))

    assert registry_writes(events) == [], f"没改路径却动了注册表: {events}"
    assert "needs_confirmation" not in result
    assert launcher._apps[0]["aliases"] == ["dd"]


# ---------------------------------------------------------------- 7. launch_app


@pytest.fixture
def spawn_recorder(monkeypatch) -> List[Any]:
    """拦住真起进程的三张嘴：Popen / os.startfile / xdg-open。"""
    calls: List[Any] = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_kw: calls.append(argv))
    monkeypatch.setattr(os, "startfile", lambda path: calls.append(path), raising=False)
    return calls


def test_launch_app_only_accepts_registered_ids(launcher: FakeLauncher, spawn_recorder: List[Any], tmp_path: Path) -> None:
    """工单第 3 条：只允许启动已在清单里登记的 app_id（钉住现状，别改回去）。"""
    app = registered_app(tmp_path)
    launcher._apps = [app]

    outside = str(tmp_path / "unregistered.exe")
    Path(outside).write_bytes(b"MZ\x90\x00")
    rejected = run(launcher.launch_app(app_id=outside))

    assert rejected.is_err(), "launch_app 接了清单外的路径"
    assert spawn_recorder == [], f"清单外路径被启动: {spawn_recorder}"

    ok = data_of(run(launcher.launch_app(app_id=app["id"])))
    assert ok["success"] is True, ok
    assert spawn_recorder == [[app["path"]]], spawn_recorder


def test_launch_refuses_legacy_unlisted_type(launcher: FakeLauncher, spawn_recorder: List[Any], tmp_path: Path) -> None:
    """老清单里 type=="other" 的条目：以前会落到 os.startfile()，现在兜闸拦住。"""
    legacy = dict(registered_app(tmp_path, filename="payload.bin"), type="other")
    launcher._apps = [legacy]

    rejected = run(launcher.launch_app(app_id=legacy["id"]))

    assert rejected.is_err()
    assert spawn_recorder == [], "os.startfile 被调用 = 由外壳关联决定执行什么"


def test_launch_refuses_missing_file(launcher: FakeLauncher, spawn_recorder: List[Any], tmp_path: Path) -> None:
    app = registered_app(tmp_path)
    launcher._apps = [app]
    Path(app["path"]).unlink()

    rejected = run(launcher.launch_app(app_id=app["id"]))

    assert rejected.is_err()
    assert spawn_recorder == []

# ---------------------------------------------------------------- 8. 界面的第二跳
#
# 门放在服务端，但"一次点击就开成"的体验靠界面补第二跳。这一节把两条腿都钉住：
# 界面必须问人、必须把令牌带回来；8 个语言包都得有这句确认文案（缺一个就有人看到
# 键名而不是命令）。


def _plugin_file(*parts: str) -> Path:
    return NEKO_ROOT / "plugin/plugins/app_launcher" / Path(*parts)


def test_ui_asks_the_human_and_completes_the_second_hop() -> None:
    html = _plugin_file("static/index.html").read_text(encoding="utf-8")

    assert "needs_confirmation" in html, "界面不看确认标志 = 第一跳的拒绝被当成成功"
    assert "first.command" in html, "确认框没把人要看的那条命令显示出来"
    assert "confirmation_token: first.confirmation_token" in html
    assert "confirmed: true" in html
    assert "await setAutostartConfirmed({ app_id: appId, enabled: enabled })" in html
    # 开关的旧写法（单跳直接开启）必须已经从界面里消失
    assert "callPlugin('set_autostart', { app_id: appId, enabled: enabled })" not in html


def test_ui_locales_all_carry_the_confirmation_copy() -> None:
    locales = ["zh-CN", "zh-TW", "en", "ja", "ko", "es", "pt", "ru"]
    shapes = {}
    for locale in locales:
        data = json.loads(_plugin_file("i18n", f"{locale}.json").read_text(encoding="utf-8"))
        assert {"ui.confirm.autostart", "ui.info.autostart_cancelled"} <= set(data), locale
        assert "{command}" in data["ui.confirm.autostart"], locale
        shapes[locale] = tuple(sorted(data))
    assert len(set(shapes.values())) == 1, f"语言包键集漂移: {sorted(shapes)}"


def test_ui_fallback_copy_matches_zh_cn() -> None:
    """t(key, fallback) 的兜底串和 zh-CN 必须逐字一致，否则换语言才暴露差异。"""
    html = _plugin_file("static/index.html").read_text(encoding="utf-8")
    data = json.loads(_plugin_file("i18n/zh-CN.json").read_text(encoding="utf-8"))

    literal = data["ui.confirm.autostart"].replace(chr(10), chr(92) + "n")
    assert literal in html, "界面里的兜底文案和 zh-CN 不是同一句"
