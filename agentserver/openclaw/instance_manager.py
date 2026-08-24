#!/usr/bin/env python3
"""
OpenClaw 多实例管理器 — 通讯录模式

每个干员（Agent）有独立目录 ~/.naga/agents/{id}/，包含 workspace 文件。
进程生命周期与通讯录绑定：
  - 创建角色 → 写 manifest + 创建目录（不启动进程）
  - 发消息时 → ensure_running() 按需启动进程
  - 关闭 tab → 进程继续运行
  - 删除角色 → 杀进程 + 可选删数据
  - 关闭 Naga → 杀所有进程

端口映射：
  通讯录干员使用稀疏端口块分配独立 Gateway 进程
  20789 主 Gateway 保留给全局 OpenClaw（探索/旅行等链路）
"""

import asyncio
import json
import logging
import os
import shutil
import signal
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .embedded_runtime import EmbeddedRuntime
from .openclaw_client import OpenClawClient, OpenClawConfig
from .ws_client import OpenClawWSClient

logger = logging.getLogger("openclaw.instance_manager")

MAX_INSTANCES = 100
PRIMARY_GATEWAY_PORT = 20789
LEGACY_AGENT_PORT_RANGE_START = 20790
LEGACY_AGENT_PORT_RANGE_END = 20889  # exclusive
AGENT_BASE_PORT = 20920
AGENT_PORT_STRIDE = 128
PORT_RANGE_START = PRIMARY_GATEWAY_PORT
PORT_RANGE_END = AGENT_BASE_PORT + (AGENT_PORT_STRIDE * MAX_INSTANCES)  # exclusive

# ── 通讯录目录 ──

_AGENTS_DIR: Path | None = None


def _get_agents_dir() -> Path:
    global _AGENTS_DIR
    if _AGENTS_DIR is None:
        try:
            from system.config import get_data_dir
            _AGENTS_DIR = get_data_dir() / "agents"
        except Exception:
            _AGENTS_DIR = Path.home() / ".naga" / "agents"
    _AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    return _AGENTS_DIR


def _get_manifest_path() -> Path:
    return _get_agents_dir() / "agents.json"


def _load_manifest() -> dict:
    path = _get_manifest_path()
    if not path.exists():
        return {"agents": [], "next_agent_number": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"agents": [], "next_agent_number": 0}


def _save_manifest(data: dict):
    path = _get_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Workspace 文件初始化 ──

_OPENCLAW_WORKSPACE_FILES = {
    "HEARTBEAT.md": "",
    "IDENTITY.md": "",
    "SOUL.md": "",
    "TOOLS.md": (
        "# 干员工具补充\n\n"
        "## 跨干员协作\n\n"
        "- 查看干员通讯录：`GET http://127.0.0.1:8000/agents/directory`\n"
        "- 转发任务给另一名干员：`POST http://127.0.0.1:8000/agents/relay`\n"
        "- 推荐请求体字段：`target_agent_id` 或 `target_agent_name`、`message`、`purpose`、`context`\n"
        "- 若要调用本地 HTTP 接口，优先使用你现有的命令执行能力发起请求，不要伪造协作结果。\n"
    ),
    "USER.md": "",
}

_COMMON_AGENT_DIRS = ("memory", "skills", "notes")
_COMMON_AGENT_FILES = {
    "IDENTITY.md": "",
    "SOUL.md": "",
    "notes/CLAUDE.md": (
        "# 干员记事本\n\n"
        "这里用于存放该干员的长期约束、长期计划、固定注意事项和手工补充资料。\n"
    ),
}

SUPPORTED_AGENT_ENGINES = {"openclaw", "lumo-core", "naga-core"}


def normalize_agent_engine(engine: str | None) -> str:
    value = (engine or "openclaw").strip().lower()
    if value in {"nagacore", "naga_core", "naga-core"}:
        value = "lumo-core"
    if value not in SUPPORTED_AGENT_ENGINES:
        raise ValueError(f"不支持的干员引擎: {engine}")
    return value


def _load_character_identity_content(character_template: str | None) -> str:
    if not character_template:
        return ""

    try:
        from system.config import build_system_prompt

        return build_system_prompt(character_template)
    except Exception as e:
        logger.warning(f"加载角色模板 [{character_template}] 失败: {e}")
        return ""


def get_agent_dir(agent_id: str) -> Path:
    return _get_agents_dir() / agent_id


def _get_agent_openclaw_dir(agent_id: str) -> Path:
    return get_agent_dir(agent_id) / ".openclaw"


def _get_agent_runtime_dir(agent_id: str) -> Path:
    return _get_agent_openclaw_dir(agent_id) / "agent"


def _ensure_agent_runtime_dir(agent_id: str) -> Path:
    runtime_dir = _get_agent_runtime_dir(agent_id)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def _get_agent_session_file(agent_id: str) -> Path:
    return _get_agent_openclaw_dir(agent_id) / "openclaw_session.json"


def _get_agent_travel_report_sync_path(agent_id: str) -> Path:
    return _get_agent_openclaw_dir(agent_id) / "travel_report_sync.json"


def _get_agent_state_dir(agent_id: str) -> Path:
    return _get_agent_openclaw_dir(agent_id) / "state"


def _get_agent_config_path(agent_id: str) -> Path:
    return _get_agent_state_dir(agent_id) / "openclaw.json"


def _get_agent_auth_profiles_path(agent_id: str) -> Path:
    return _get_agent_config_path(agent_id).parent / "agents" / "main" / "agent" / "auth-profiles.json"


def _build_agent_env(agent_id: str) -> dict[str, str]:
    agent_runtime_dir = _get_agent_runtime_dir(agent_id)
    agent_state_dir = _get_agent_state_dir(agent_id)
    agent_config_path = _get_agent_config_path(agent_id)
    agent_state_dir.mkdir(parents=True, exist_ok=True)
    agent_config_path.parent.mkdir(parents=True, exist_ok=True)
    return {
        "OPENCLAW_AGENT_DIR": str(agent_runtime_dir),
        "PI_CODING_AGENT_DIR": str(agent_runtime_dir),
        "OPENCLAW_STATE_DIR": str(agent_state_dir),
        "OPENCLAW_CONFIG_PATH": str(agent_config_path),
    }


def _init_agent_dir(
    agent_id: str,
    agent_name: str = "",
    character_template: str | None = None,
    engine: str = "openclaw",
) -> Path:
    """创建干员目录（以 UUID 命名）并初始化 workspace 文件。返回目录路径。"""
    engine = normalize_agent_engine(engine)
    agent_dir = get_agent_dir(agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)

    for relative_dir in _COMMON_AGENT_DIRS:
        (agent_dir / relative_dir).mkdir(parents=True, exist_ok=True)

    if engine == "openclaw":
        _ensure_agent_runtime_dir(agent_id)
        # AGENTS.md 单独处理：包含干员名称
        agents_md = agent_dir / "AGENTS.md"
        if not agents_md.exists():
            display_name = agent_name or agent_id[:8]
            agents_md.write_text(
                f"# {display_name}\n\n"
                f"你是 NagaAgent 系统的干员「{display_name}」。\n"
                f"你可以独立完成用户分配的任务，使用可用的工具和技能。\n"
                f"将重要信息记录到 memory/ 目录中的日期文件，以便跨会话保持记忆。\n",
                encoding="utf-8",
            )

    identity_content = _load_character_identity_content(character_template)

    common_files = dict(_COMMON_AGENT_FILES)
    if engine == "openclaw":
        common_files.update(_OPENCLAW_WORKSPACE_FILES)

    for filename, default_content in common_files.items():
        fp = agent_dir / filename
        fp.parent.mkdir(parents=True, exist_ok=True)
        if not fp.exists():
            content = identity_content if filename == "IDENTITY.md" and identity_content else default_content
            fp.write_text(content, encoding="utf-8")
        elif filename == "IDENTITY.md" and identity_content and character_template:
            try:
                from system.character_bundle import is_legacy_character_identity

                current_text = fp.read_text(encoding="utf-8")
                if is_legacy_character_identity(current_text, character_template):
                    fp.write_text(identity_content, encoding="utf-8")
            except Exception:
                pass
        elif filename == "TOOLS.md" and default_content:
            try:
                if not fp.read_text(encoding="utf-8").strip():
                    fp.write_text(default_content, encoding="utf-8")
            except Exception:
                pass
    return agent_dir


def _delete_agent_dir(agent_id: str) -> bool:
    """删除干员目录（含所有 workspace 文件）。"""
    agent_dir = _get_agents_dir() / agent_id
    if agent_dir.exists():
        shutil.rmtree(agent_dir, ignore_errors=True)
        return True
    return False


def _read_agent_text_file(agent_id: str, relative_path: str) -> str:
    path = get_agent_dir(agent_id) / relative_path
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _write_agent_text_file(agent_id: str, relative_path: str, content: str) -> None:
    path = get_agent_dir(agent_id) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _render_identity_from_template(character_template: str | None) -> str:
    if not character_template:
        return ""
    try:
        from system.config import build_system_prompt

        return build_system_prompt(character_template) or ""
    except Exception as exc:
        logger.warning(f"渲染角色模板 [{character_template}] 失败: {exc}")
        return ""


@dataclass
class AgentInstance:
    """一个干员实例（通讯录条目 + 可选的运行时状态）"""

    id: str
    name: str
    port: int = 0  # 0 = 未分配（未启动）
    process: asyncio.subprocess.Process | None = None
    client: OpenClawClient | None = None
    primary: bool = False
    running: bool = False
    created_at: float = field(default_factory=time.time)
    character_template: str | None = None
    engine: str = "openclaw"


def cleanup_port_range(start: int = PORT_RANGE_START, end: int = PORT_RANGE_END) -> int:
    """启动时清理端口范围内的残留进程。返回清理的数量。"""
    def _default_cleanup_ports():
        yield PRIMARY_GATEWAY_PORT
        for port in range(LEGACY_AGENT_PORT_RANGE_START, LEGACY_AGENT_PORT_RANGE_END):
            yield port
        for port in range(AGENT_BASE_PORT, PORT_RANGE_END, AGENT_PORT_STRIDE):
            yield port

    killed = 0
    if start == PORT_RANGE_START and end == PORT_RANGE_END:
        ports = _default_cleanup_ports()
    else:
        ports = range(start, end)
    for port in ports:
        killed += _kill_stale_on_port(port)
    if killed:
        logger.info(f"端口清理完成，共清理 {killed} 个残留进程")
    return killed


def _kill_stale_on_port(port: int) -> int:
    """杀掉占用指定端口的 openclaw/gateway 残留进程（跨平台）。"""
    import subprocess as _sp

    killed = 0
    try:
        result = _sp.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = [int(p) for p in result.stdout.strip().split() if p.isdigit()]
    except Exception:
        return 0

    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info(f"清理残留进程 port={port} pid={pid}")
            killed += 1
        except (ProcessLookupError, PermissionError):
            pass
    return killed


class InstanceManager:
    """
    管理干员通讯录 + 进程生命周期。

    通讯录条目持久化在 manifest 中，进程按需启动。
    每个 openclaw 干员都使用独立 Gateway + 独立 agentDir。
    """

    def __init__(self, runtime: EmbeddedRuntime, primary_client: OpenClawClient | None = None) -> None:
        self._runtime = runtime
        self._primary_client = primary_client
        self._instances: dict[str, AgentInstance] = {}
        self._agent_locks: dict[str, asyncio.Lock] = {}
        self._port_pool: list[int] = []
        self._base_port: int = AGENT_BASE_PORT
        self._next_port: int = self._base_port
        self._agent_counter: int = 0

    def _allocate_port(self) -> int:
        candidates = sorted(self._port_pool)
        self._port_pool = []

        while True:
            if candidates:
                port = candidates.pop(0)
            else:
                if self._next_port >= PORT_RANGE_END:
                    raise RuntimeError("OpenClaw 端口池已耗尽")
                port = self._next_port
                self._next_port += AGENT_PORT_STRIDE

            if any(inst.running and inst.port == port for inst in self._instances.values()):
                continue

            if self._check_port(port):
                killed = _kill_stale_on_port(port)
                if killed:
                    time.sleep(0.2)
                if self._check_port(port):
                    logger.warning(f"端口 {port} 已被其他进程占用，跳过分配")
                    continue

            self._port_pool.extend(candidates)
            self._port_pool.sort()
            return port

    def _release_port(self, port: int) -> None:
        if port > 0 and port not in self._port_pool:
            self._port_pool.append(port)
            self._port_pool.sort()

    def _get_auth_snapshot(self):
        try:
            from .detector import detect_openclaw

            status = detect_openclaw(check_connection=False)
            hooks_path = getattr(status, "hooks_path", "/hooks")
            if not isinstance(hooks_path, str):
                hooks_path = "/hooks"
            hooks_path = hooks_path.strip() or "/hooks"
            if not hooks_path.startswith("/"):
                hooks_path = f"/{hooks_path}"
            hooks_path = hooks_path.rstrip("/") or "/hooks"
            return status.gateway_token, status.hooks_token, hooks_path
        except Exception:
            return None, None, "/hooks"

    def _get_instance_auth_snapshot(self, inst: AgentInstance):
        if inst.primary:
            return self._get_auth_snapshot()

        try:
            config_path = _get_agent_config_path(inst.id)
            data = json.loads(config_path.read_text(encoding="utf-8"))
            gateway = data.get("gateway") if isinstance(data.get("gateway"), dict) else {}
            hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}

            gateway_auth = gateway.get("auth") if isinstance(gateway.get("auth"), dict) else {}
            gateway_token = gateway_auth.get("token") if isinstance(gateway_auth.get("token"), str) else None
            hooks_token = hooks.get("token") if isinstance(hooks.get("token"), str) else None
            hooks_path = hooks.get("path") if isinstance(hooks.get("path"), str) else "/hooks"
            hooks_path = hooks_path.strip() or "/hooks"
            if not hooks_path.startswith("/"):
                hooks_path = f"/{hooks_path}"
            hooks_path = hooks_path.rstrip("/") or "/hooks"
            return gateway_token, hooks_token, hooks_path
        except Exception as exc:
            logger.warning(f"[{inst.name}] 读取实例认证快照失败，回退到全局快照: {exc}")
            return self._get_auth_snapshot()

    def _refresh_client_auth(self, inst: AgentInstance) -> None:
        if not inst.client:
            return
        gateway_token, hooks_token, hooks_path = self._get_instance_auth_snapshot(inst)
        inst.client.config.gateway_token = gateway_token
        inst.client.config.hooks_token = hooks_token
        if hooks_path:
            inst.client.config.hooks_path = hooks_path

    def _get_primary_port(self) -> int:
        try:
            from system.config import config as _cfg
            return _cfg.openclaw.gateway_port
        except Exception:
            return PRIMARY_GATEWAY_PORT

    def _sync_agent_gateway_config(self, inst: AgentInstance, port: int) -> None:
        try:
            from .llm_config_bridge import (
                ensure_gateway_local_mode,
                ensure_gateway_port,
                ensure_hooks_allow_request_session_key,
                ensure_hooks_path,
                ensure_openclaw_config,
                inject_naga_llm_config,
            )
            from .state_paths import get_openclaw_config_path

            ensure_openclaw_config()
            ensure_gateway_local_mode(auto_create=False)
            ensure_hooks_path(auto_create=False)
            ensure_hooks_allow_request_session_key(auto_create=False)
            ensure_gateway_port(auto_create=False)
            inject_naga_llm_config()

            source_config_path = get_openclaw_config_path()
            if not source_config_path.exists():
                raise RuntimeError("主 OpenClaw 配置不存在")

            config_data = json.loads(source_config_path.read_text(encoding="utf-8"))
            gateway = config_data.setdefault("gateway", {})
            gateway["mode"] = "local"
            gateway["port"] = port
            gateway["bind"] = "loopback"

            hooks = config_data.setdefault("hooks", {})
            hooks["enabled"] = True
            hooks["path"] = "/hooks"
            hooks["allowRequestSessionKey"] = True

            browser = config_data.setdefault("browser", {})
            browser.pop("profiles", None)
            browser.pop("cdpUrl", None)
            browser["cdpPortRangeStart"] = port + 11

            agents = config_data.setdefault("agents", {})
            defaults = agents.setdefault("defaults", {})
            defaults["workspace"] = str(get_agent_dir(inst.id))

            target_config_path = _get_agent_config_path(inst.id)
            target_config_path.parent.mkdir(parents=True, exist_ok=True)
            target_config_path.write_text(
                json.dumps(config_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            source_auth_profiles = source_config_path.parent / "agents" / "main" / "agent" / "auth-profiles.json"
            target_auth_profiles = _get_agent_auth_profiles_path(inst.id)
            if source_auth_profiles.exists():
                target_auth_profiles.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_auth_profiles, target_auth_profiles)
        except Exception as exc:
            raise RuntimeError(f"同步干员 OpenClaw 配置失败: {exc}") from exc

    def _get_agent_lock(self, agent_id: str) -> asyncio.Lock:
        lock = self._agent_locks.get(agent_id)
        if lock is None:
            lock = asyncio.Lock()
            self._agent_locks[agent_id] = lock
        return lock

    def _set_agent_browser_visibility(self, agent_id: str, visible: bool) -> bool:
        agent_id = str(agent_id)
        inst = self._instances.get(agent_id)
        if inst is None:
            raise RuntimeError(f"干员 {agent_id} 不存在")
        target_config_path = _get_agent_config_path(agent_id)
        if not target_config_path.exists():
            self._ensure_gateway_config()
            self._sync_agent_gateway_config(inst, inst.port if inst.port > 0 else self._base_port)
        config_data = json.loads(target_config_path.read_text(encoding="utf-8"))
        browser = config_data.setdefault("browser", {})
        next_headless = not visible
        changed = browser.get("headless") != next_headless
        browser["headless"] = next_headless
        target_config_path.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return changed

    async def update_browser_preferences(
        self,
        agent_id: str,
        *,
        visible: bool | None = None,
        stop_browser_if_changed: bool = True,
    ) -> dict:
        lock = self._get_agent_lock(agent_id)
        async with lock:
            inst = self._instances.get(agent_id)
            if inst is None:
                raise RuntimeError(f"干员 {agent_id} 不存在")

            visibility_changed = False
            if visible is not None:
                visibility_changed = self._set_agent_browser_visibility(agent_id, bool(visible))

            browser_stopped = False
            if visibility_changed and stop_browser_if_changed and inst.client is not None:
                try:
                    await inst.client.invoke_tool(
                        tool="browser",
                        args={"action": "stop"},
                    )
                    browser_stopped = True
                except Exception as exc:
                    logger.warning(f"[{inst.name}] 变更浏览器可见性后停止旧浏览器失败: {exc}")

            return {
                "id": inst.id,
                "name": inst.name,
                "browser_visible": None if visible is None else bool(visible),
                "visibility_changed": visibility_changed,
                "browser_stopped": browser_stopped,
            }

    async def _prepare_instance_for_request(self, inst: AgentInstance) -> AgentInstance:
        if not inst.client:
            raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
        self._refresh_client_auth(inst)

        if not inst.primary and inst.process is not None and inst.process.returncode is not None:
            raise RuntimeError(f"干员 [{inst.name}] 进程已退出")

        if not self._check_port(inst.port):
            logger.info(f"[{inst.name}] 端口 {inst.port} 不可达，重新启动...")
            started = await self._try_start_gateway(inst)
            if not started:
                raise RuntimeError(f"Gateway 端口 {inst.port} 正在启动中")
        return inst

    async def run_serialized(
        self,
        instance_id: str,
        worker: Callable[[AgentInstance], Awaitable[Any]],
    ):
        lock = self._get_agent_lock(instance_id)
        async with lock:
            inst = await self.ensure_running(instance_id)
            inst = await self._prepare_instance_for_request(inst)
            return await worker(inst)

    # ── 通讯录操作（不启动进程） ──

    def create_agent(
        self,
        name: str | None = None,
        agent_id: str | None = None,
        character_template: str | None = None,
        engine: str = "openclaw",
    ) -> AgentInstance:
        """创建干员（写 manifest + 创建目录），不启动进程。"""
        if len(self._instances) >= MAX_INSTANCES:
            raise RuntimeError("干员数量最多100个，如有特殊需求请联系开发组")

        engine = normalize_agent_engine(engine)

        self._agent_counter += 1
        if not name:
            name = f"干员{self._agent_counter}"

        if agent_id is None:
            agent_id = uuid.uuid4().hex[:12]

        # 创建目录 + workspace 文件（用 UUID 命名，含干员名称）
        _init_agent_dir(agent_id, name, character_template, engine=engine)

        inst = AgentInstance(
            id=agent_id,
            name=name,
            created_at=time.time(),
            character_template=character_template,
            engine=engine,
        )
        self._instances[agent_id] = inst
        self._save_to_manifest()

        logger.info(f"创建干员 [{name}] id={agent_id} engine={engine}（通讯录条目，未启动进程）")
        return inst

    def delete_agent(self, agent_id: str, delete_data: bool = True) -> None:
        """从通讯录删除干员 + 停止进程 + 可选删数据。"""
        inst = self._instances.pop(agent_id, None)
        if inst is None:
            logger.warning(f"干员 {agent_id} 不存在")
            return

        logger.info(f"删除干员 [{inst.name}] id={agent_id} delete_data={delete_data}")

        # 同步方式标记需要清理，实际清理在 async 方法中执行
        # 这里只做 manifest 和目录清理
        if delete_data:
            _delete_agent_dir(inst.id)

        self._save_to_manifest()

    async def destroy_agent_async(self, agent_id: str, delete_data: bool = True) -> None:
        """异步销毁干员：停止进程 + 从通讯录删除 + 可选删数据。"""
        inst = self._instances.get(agent_id)
        if inst is None:
            logger.warning(f"干员 {agent_id} 不存在")
            return

        # 先停止进程
        if inst.running:
            await self._stop_instance(inst)

        # 再从通讯录删除
        self._instances.pop(agent_id, None)

        if delete_data:
            _delete_agent_dir(inst.id)
            try:
                for sf in (
                    _get_agent_session_file(inst.id),
                ):
                    if sf.exists():
                        sf.unlink()
            except Exception:
                pass

        self._save_to_manifest()
        logger.info(f"干员 [{inst.name}] 已销毁 delete_data={delete_data}")
        self._agent_locks.pop(agent_id, None)

    def rename_agent(self, agent_id: str, new_name: str) -> bool:
        """重命名干员（只改 manifest，目录用 UUID 不变）。"""
        inst = self._instances.get(agent_id)
        if inst is None:
            return False

        old_name = inst.name
        if old_name == new_name:
            return True

        inst.name = new_name
        self._save_to_manifest()

        logger.info(f"干员 [{old_name}] → [{new_name}]")
        return True

    def get_agent_settings(self, agent_id: str) -> dict | None:
        inst = self._instances.get(agent_id)
        if inst is None:
            return None

        return {
            "id": inst.id,
            "name": inst.name,
            "engine": inst.engine,
            "character_template": inst.character_template,
            "soul_content": _read_agent_text_file(agent_id, "SOUL.md"),
        }

    async def update_agent_settings(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        character_template: str | None = None,
        update_character_template: bool = False,
        engine: str | None = None,
        soul_content: str | None = None,
        update_soul_content: bool = False,
    ) -> dict | None:
        inst = self._instances.get(agent_id)
        if inst is None:
            return None

        next_name = (name or inst.name).strip() if name is not None else inst.name
        next_engine = normalize_agent_engine(engine or inst.engine)
        next_character_template = inst.character_template
        if update_character_template:
            next_character_template = character_template

        engine_changed = next_engine != inst.engine
        if engine_changed and inst.running:
            await self._stop_instance(inst)

        inst.name = next_name or inst.name
        inst.engine = next_engine
        inst.character_template = next_character_template

        _init_agent_dir(inst.id, inst.name, inst.character_template, engine=inst.engine)

        if update_character_template:
            _write_agent_text_file(
                inst.id,
                "IDENTITY.md",
                _render_identity_from_template(inst.character_template),
            )

        if update_soul_content:
            _write_agent_text_file(inst.id, "SOUL.md", soul_content or "")

        self._save_to_manifest()
        return self.get_agent_settings(agent_id)

    def list_agents(self) -> list[dict]:
        """返回通讯录中的所有干员（不管进程是否在跑）。"""
        return [
            {
                "id": inst.id,
                "name": inst.name,
                "running": inst.running,
                "created_at": inst.created_at,
                "character_template": inst.character_template,
                "engine": inst.engine,
            }
            for inst in self._instances.values()
        ]

    def get_instance(self, agent_id: str) -> AgentInstance | None:
        return self._instances.get(agent_id)

    async def resolve_runtime(self, agent_id: str, wake: bool = False) -> dict:
        """解析干员当前运行时信息；可选按需唤醒 openclaw 干员。"""
        inst = self._instances.get(agent_id)
        if inst is None:
            raise RuntimeError(f"干员 {agent_id} 不存在")

        was_running = bool(
            inst.engine == "openclaw"
            and inst.running
            and inst.port > 0
            and self._check_port(inst.port)
        )

        if inst.engine == "openclaw" and wake:
            inst = await self.ensure_running(agent_id)

        is_running = bool(
            inst.engine == "openclaw"
            and inst.running
            and inst.port > 0
            and self._check_port(inst.port)
        )
        port = inst.port if is_running else None

        return {
            "id": inst.id,
            "name": inst.name,
            "engine": inst.engine,
            "running": is_running,
            "woken": bool(wake and not was_running and is_running),
            "port": port,
            "gateway_url": f"http://127.0.0.1:{port}" if port else None,
            "primary": bool(inst.primary) if inst.engine == "openclaw" else False,
        }

    # ── 进程管理（按需启动） ──

    async def ensure_running(self, agent_id: str) -> AgentInstance:
        """确保干员进程在运行。若未启动则按需启动。"""
        inst = self._instances.get(agent_id)
        if inst is None:
            raise RuntimeError(f"干员 {agent_id} 不存在")
        if inst.engine != "openclaw":
            raise RuntimeError(f"干员 [{inst.name}] 使用的是 {inst.engine}，暂未接入独立 OpenClaw 运行时")

        if inst.running and inst.client is not None:
            # 检查端口是否仍可达
            if inst.port > 0 and self._check_port(inst.port):
                return inst
            # 端口不通了，标记为未运行，重新启动
            logger.info(f"[{inst.name}] 端口 {inst.port} 不可达，重新启动")
            inst.running = False

        # 启动进程
        await self._start_instance(inst)
        return inst

    async def _start_instance(self, inst: AgentInstance) -> None:
        """启动干员 Gateway 进程。"""
        port = self._allocate_port()
        logger.info(f"启动干员 [{inst.name}] 独立 Gateway 端口={port}")
        try:
            _ensure_agent_runtime_dir(inst.id)

            if self._check_port(port):
                logger.warning(f"[{inst.name}] 端口 {port} 在启动前已被占用，尝试清理残留进程")
                _kill_stale_on_port(port)
                await asyncio.sleep(0.5)
                if self._check_port(port):
                    raise RuntimeError(f"端口 {port} 已被其他进程持续占用")

            self._ensure_gateway_config()
            self._sync_agent_gateway_config(inst, port)
            process = await self._runtime.start_gateway_on_port(
                port,
                extra_env=_build_agent_env(inst.id),
            )
            if process is None:
                raise RuntimeError(f"无法在端口 {port} 启动 Gateway 进程")

            gateway_token, hooks_token, hooks_path = self._get_instance_auth_snapshot(inst)
            gw_url = f"http://127.0.0.1:{port}"
            client = OpenClawClient(OpenClawConfig(
                gateway_url=gw_url,
                gateway_token=gateway_token,
                hooks_token=hooks_token,
                hooks_path=hooks_path,
                timeout=120,
            ))
            client._default_session_key = f"agent:main:{inst.id}"
            client._SESSION_FILE = _get_agent_session_file(inst.id)
        except Exception:
            # 端口已分配但启动流程失败：必须归还端口，避免反复崩溃后端口池耗尽
            self._release_port(port)
            raise

        inst.port = port
        inst.client = client
        inst.primary = False
        inst.process = process

        inst.running = True
        logger.info(f"干员 [{inst.name}] 进程已启动 port={inst.port} primary={inst.primary}")

    async def _stop_instance(self, inst: AgentInstance) -> None:
        """停止干员进程（不删除通讯录条目）。"""
        if not inst.running:
            return

        logger.info(f"停止干员 [{inst.name}] port={inst.port} primary={inst.primary}")

        if inst.client:
            try:
                await inst.client.close()
            except Exception as e:
                logger.warning(f"关闭客户端失败: {e}")
            inst.client = None

        if inst.process is not None:
            try:
                if inst.process.returncode is None:
                    inst.process.terminate()
                    try:
                        await asyncio.wait_for(inst.process.wait(), timeout=10)
                    except TimeoutError:
                        inst.process.kill()
                        await inst.process.wait()
            except Exception as e:
                logger.error(f"停止进程失败: {e}")
            inst.process = None

        self._release_port(inst.port)
        inst.port = 0
        inst.running = False
        inst.primary = False

    async def destroy_all(self) -> None:
        """停止所有运行中的进程（关闭应用时调用）。"""
        for inst in list(self._instances.values()):
            if inst.running:
                await self._stop_instance(inst)

    # ── 兼容旧 API ──

    async def create_instance(self, name: str | None = None, instance_id: str | None = None, _restoring: bool = False) -> AgentInstance:
        """兼容旧接口：创建干员并立即启动。"""
        inst = self.create_agent(name, instance_id)
        await self.ensure_running(inst.id)
        return inst

    async def destroy_instance(self, instance_id: str) -> None:
        """兼容旧接口。"""
        await self.destroy_agent_async(instance_id, delete_data=True)

    def list_instances(self) -> list[dict]:
        """兼容旧接口。"""
        return self.list_agents()

    def rename_instance(self, instance_id: str, new_name: str) -> bool:
        """兼容旧接口。"""
        return self.rename_agent(instance_id, new_name)

    # ── Manifest 持久化 ──

    def _save_to_manifest(self):
        data = {
            "agents": [
                {
                    "id": inst.id,
                    "name": inst.name,
                    "created_at": inst.created_at,
                    "character_template": inst.character_template,
                    "engine": inst.engine,
                }
                for inst in self._instances.values()
            ],
            "next_agent_number": self._agent_counter,
        }
        try:
            _save_manifest(data)
        except Exception as e:
            logger.warning(f"保存 manifest 失败: {e}")

    def restore_from_manifest(self):
        """从 manifest 恢复通讯录（不启动进程）。返回角色列表。"""
        manifest = _load_manifest()
        agents = manifest.get("agents", [])

        saved_counter = manifest.get("next_agent_number", 0)
        if saved_counter > self._agent_counter:
            self._agent_counter = saved_counter

        restored = 0
        for saved in agents:
            agent_id = saved.get("id")
            if not agent_id or agent_id in self._instances:
                continue

            name = saved.get("name", f"干员{self._agent_counter + 1}")
            character_template = saved.get("character_template")
            engine = normalize_agent_engine(saved.get("engine"))
            # 确保目录存在（用 UUID）
            _init_agent_dir(agent_id, name, character_template, engine=engine)

            inst = AgentInstance(
                id=agent_id,
                name=name,
                created_at=saved.get("created_at", time.time()),
                character_template=character_template,
                engine=engine,
            )
            self._instances[agent_id] = inst
            restored += 1

        if restored:
            logger.info(f"从 manifest 恢复了 {restored} 个干员（通讯录条目，未启动进程）")

        return self.list_agents()

    # ── 消息发送 ──

    async def send_message(
        self,
        instance_id: str,
        message: str,
        timeout: int = 120,
        session_key: str | None = None,
        name: str | None = None,
    ) -> dict:
        """通过指定实例发送消息。自动 ensure_running。"""
        try:
            async def _worker(inst: AgentInstance):
                if not inst.client:
                    raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")

                logger.info(
                    f"发送消息到 [{inst.name}] port={inst.port} primary={inst.primary} "
                    f"gateway_url={inst.client.config.gateway_url} msg={message[:50]}..."
                )
                agent_workspace = str(_get_agents_dir() / instance_id)
                task = await inst.client.send_message(
                    message=message,
                    session_key=session_key,
                    workspace=agent_workspace,
                    name=name,
                    wake_mode="now",
                    deliver=False,
                    timeout_seconds=timeout,
                )
                return {
                    "success": task.status.value != "failed",
                    "reply": task.result.get("reply") if task.result else None,
                    "replies": task.result.get("replies") if task.result else None,
                    "error": task.error,
                }

            return await self.run_serialized(instance_id, _worker)
        except RuntimeError as e:
            return {"success": False, "retry": "正在启动中" in str(e), "error": str(e)}
        except Exception as e:
            logger.error(f"发送消息到干员 [{instance_id}] 失败: {e}")
            return {"success": False, "error": str(e)}

    async def _try_start_gateway(self, inst: AgentInstance) -> bool:
        self._ensure_gateway_config()
        _ensure_agent_runtime_dir(inst.id)
        self._sync_agent_gateway_config(inst, inst.port)
        try:
            _kill_stale_on_port(inst.port)
            await asyncio.sleep(0.5)
        except Exception:
            pass
        if self._check_port(inst.port):
            logger.warning(f"[{inst.name}] 端口 {inst.port} 清理后仍被占用，放弃重启")
            return False

        process = await self._runtime.start_gateway_on_port(
            inst.port,
            extra_env=_build_agent_env(inst.id),
        )
        if process is not None and self._check_port(inst.port):
            inst.process = process
            return True
        return False

    # ── 流式发送 ──

    # Skill/Tool 调用检测（LLM 输出文本格式而非原生 ToolCall）
    import json as _json_lib
    import re as _re

    _SKILL_XML_RE = _re.compile(
        r"<skill\b[^>]*>\s*<name>\s*(\S+?)\s*</name>"
        r"(?:\s*<location>[^<]*</location>)?"
        r"[\s\S]*?</skill>",
        _re.IGNORECASE,
    )
    _SKILL_CALL_XML_RE = _re.compile(
        r"<skill_call>\s*<skill_name>\s*(\S+?)\s*</skill_name>"
        r"[\s\S]*?</skill_call>",
        _re.IGNORECASE,
    )
    _JSON_TOOL_RE = _re.compile(
        r'\{\s*"action"\s*:\s*"([^"]+)"\s*,\s*"args"\s*:\s*(\{[^}]*\})\s*\}',
        _re.IGNORECASE,
    )
    # 检测伪代码工具调用: await read(...), await search(...) 等
    _PSEUDO_CODE_RE = _re.compile(
        r'(?:await\s+)?(\w+)\s*\(\s*["\']([^"\']+)["\']\s*\)',
        _re.IGNORECASE,
    )
    # 检测特殊分隔符工具调用格式（Qwen/GLM 等）
    _SPECIAL_TOOL_RE = _re.compile(
        r'<\|tool_call_begin\|>functions\.(\w+):\d+<\|tool_call_argument_begin\|>(\{[^}]+\})',
        _re.IGNORECASE,
    )
    _SPECIAL_TOOL_MARKERS = (
        "<|tool_calls_section_begin|>",
        "<|tool_calls_section_end|>",
        "<|tool_call_begin|>",
        "<|tool_call_argument_begin|>",
        "<|tool_call_end|>",
    )

    def _detect_tool_invocation(self, text: str) -> dict | None:
        """检测 skill XML、JSON、伪代码或特殊分隔符工具调用。返回 {"type": "...", "name": "...", "args": {...}} 或 None。"""
        # 优先检测 skill XML
        m = self._SKILL_XML_RE.search(text)
        if m:
            return {"type": "skill", "name": m.group(1)}
        m = self._SKILL_CALL_XML_RE.search(text)
        if m:
            return {"type": "skill", "name": m.group(1)}

        # 检测特殊分隔符格式（Qwen/GLM）
        m = self._SPECIAL_TOOL_RE.search(text)
        if m:
            try:
                tool_name = m.group(1)
                args = self._json_lib.loads(m.group(2))
                return {"type": "special", "name": tool_name, "args": args}
            except Exception:
                pass

        # 检测 JSON 工具调用
        m = self._JSON_TOOL_RE.search(text)
        if m:
            try:
                args = self._json_lib.loads(m.group(2))
                return {"type": "json", "name": m.group(1), "args": args}
            except Exception:
                pass

        # 检测伪代码工具调用
        m = self._PSEUDO_CODE_RE.search(text)
        if m:
            func_name = m.group(1).lower()
            arg = m.group(2)
            skill_map = {
                "read": "read",
                "search": "web-search",
                "websearch": "web-search",
                "web_search": "web-search",
            }
            if func_name in skill_map:
                return {"type": "pseudo", "name": skill_map[func_name], "original": func_name, "arg": arg}

        return None

    def _strip_tool_invocation(self, text: str) -> str:
        """移除文本中所有 skill XML 和 JSON 工具调用。"""
        text = self._SKILL_XML_RE.sub("", text)
        text = self._SKILL_CALL_XML_RE.sub("", text)
        text = self._JSON_TOOL_RE.sub("", text)
        return text.strip()

    def _sanitize_stream_content(self, text: str) -> str:
        """移除流式内容里残留的工具分隔符前缀。"""
        if not text:
            return text
        sanitized = text
        for marker in self._SPECIAL_TOOL_MARKERS:
            sanitized = sanitized.replace(marker, "")
        return sanitized

    @staticmethod
    def _read_skill_file(skill_name: str) -> str | None:
        """读取 skills/{name}/SKILL.md。"""
        # 审计 LOW L4: 校验 skill_name 为单段安全名，防路径穿越/绝对路径
        import re as _re
        if not skill_name or not _re.fullmatch(r"[A-Za-z0-9_-]+", skill_name):
            logger.warning(f"[skill] 非法 skill_name 拒绝读取: {skill_name!r}")
            return None
        project_root = Path(__file__).resolve().parent.parent.parent
        skill_md = project_root / "skills" / skill_name / "SKILL.md"
        if skill_md.is_file():
            return skill_md.read_text(encoding="utf-8")
        return None

    async def _do_single_stream(self, http, stream_url, headers, payload, timeout, inst_name=""):
        """单轮 SSE 流。yield 中间事件，最终 yield {"type": "done"/"error", ...}。"""
        import json as _json

        async with http.stream(
            "POST", stream_url, json=payload, headers=headers, timeout=timeout + 30,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                logger.error(f"[stream] [{inst_name}] SSE 失败: {resp.status_code} {body[:200]}")
                yield {"type": "error", "text": f"Gateway 拒绝: {resp.status_code}", "statusCode": resp.status_code}
                return

            full_text = ""
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = _json.loads(data_str)
                except _json.JSONDecodeError:
                    continue

                chunk_type = chunk.get("type", "")
                chunk_text = chunk.get("text", "")
                logger.info(f"[stream] [{inst_name}] 收到事件: type={chunk_type}, chunk={chunk}")

                if chunk_type == "content":
                    chunk_text = self._sanitize_stream_content(chunk_text)
                    full_text += chunk_text
                    yield {"type": "content", "text": chunk_text}
                elif chunk_type == "done":
                    final = self._sanitize_stream_content(full_text or chunk_text).strip()
                    yield {"type": "done", "text": final}
                    return
                elif chunk_type == "error":
                    yield {"type": "error", "text": chunk_text}
                    return
                elif chunk_type == "status":
                    yield {"type": "status", "text": chunk_text}
                elif chunk_type == "tool_call":
                    yield {
                        "type": "tool_call",
                        "name": chunk.get("name", ""),
                        "text": chunk_text,
                        "toolCallId": chunk.get("toolCallId", ""),
                        "args": chunk.get("args"),
                    }
                elif chunk_type == "tool_result":
                    yield {
                        "type": "tool_result",
                        "name": chunk.get("name", ""),
                        "text": chunk_text,
                        "toolCallId": chunk.get("toolCallId", ""),
                        "isError": bool(chunk.get("isError", False)),
                        "result": chunk.get("result"),
                    }

            # 流结束但没有 done event
            if full_text:
                final = self._sanitize_stream_content(full_text).strip()
                yield {"type": "done", "text": final}
            else:
                yield {"type": "error", "text": "流结束但无回复"}

    async def send_message_stream(self, instance_id: str, message: str, timeout: int = 120):
        """流式发送消息。使用 Gateway chat.send 正常聊天通道，不走 hooks/agent。"""

        def _extract_chat_text(msg: Any) -> str:
            if isinstance(msg, dict):
                content = msg.get("content")
            else:
                content = None
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "text" and isinstance(item.get("text"), str):
                        text = item["text"].strip()
                        if text:
                            parts.append(text)
                return "\n".join(parts).strip()
            return ""

        async def _sync_latest_travel_report_if_needed(
            *,
            inst: AgentInstance,
            ws_client: OpenClawWSClient,
            session_key: str,
        ) -> None:
            from apiserver.travel_service import TravelStatus, list_sessions

            completed_sessions = list_sessions(
                agent_id=inst.id,
                statuses={TravelStatus.COMPLETED},
            )
            latest_report = next(
                (
                    session for session in completed_sessions
                    if (session.summary_report_path or "").strip() or (session.summary or "").strip()
                ),
                None,
            )
            if latest_report is None:
                return

            report_title = (latest_report.summary_report_title or "").strip() or "最近一次探索报告"
            report_path = (latest_report.summary_report_path or "").strip()
            report_body = ""
            if report_path:
                try:
                    report_body = Path(report_path).read_text(encoding="utf-8")
                except Exception as exc:
                    logger.warning(f"[{inst.name}] 读取探索报告文件失败: {exc}")
            if not report_body:
                report_body = (latest_report.summary or "").strip()
            report_body = report_body.strip()
            if not report_body:
                return

            transcript_path = None
            if inst.client:
                try:
                    transcript_path = inst.client._resolve_local_session_file(session_key)
                except Exception:
                    transcript_path = None

            sync_path = _get_agent_travel_report_sync_path(inst.id)
            sync_state: dict[str, Any] = {}
            try:
                if sync_path.exists():
                    sync_state = json.loads(sync_path.read_text(encoding="utf-8"))
            except Exception:
                sync_state = {}

            current_sync_key = {
                "travel_session_id": latest_report.session_id,
                "report_path": report_path or None,
                "session_key": session_key,
                "transcript_path": str(transcript_path) if transcript_path else None,
            }
            if all(sync_state.get(k) == v for k, v in current_sync_key.items()):
                return

            if len(report_body) > 12000:
                report_body = f"{report_body[:12000]}\n\n...后续内容已截断。"

            report_path_line = f"报告文件：{report_path}\n" if report_path else ""
            injected_message = (
                f"以下是你最近一次已完成探索的成果报告，请在后续对话中视为可用上下文。\n\n"
                f"报告标题：{report_title}\n"
                f"探索会话：{latest_report.session_id}\n"
                f"{report_path_line}"
                f"\n{report_body}"
            )
            await ws_client.chat_inject(
                session_key=session_key,
                message=injected_message,
                label="travel-report-sync",
            )
            sync_path.parent.mkdir(parents=True, exist_ok=True)
            sync_path.write_text(
                json.dumps(current_sync_key, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        inst = self._instances.get(instance_id)
        if inst is None:
            yield {"type": "error", "text": f"干员 {instance_id} 不存在"}
            return

        lock = self._get_agent_lock(instance_id)
        await lock.acquire()
        try:
            if not inst.running or not inst.client:
                yield {"type": "status", "text": "干员苏醒中"}
            try:
                inst = await self.ensure_running(instance_id)
                inst = await self._prepare_instance_for_request(inst)
            except Exception as e:
                yield {"type": "error", "text": f"启动失败: {e}"}
                return

            logger.info(f"[stream] [{inst.name}] 开始: {message[:50]}...")
            yield {"type": "status", "text": "思考中"}

            client = inst.client
            if not client:
                yield {"type": "error", "text": f"干员 [{inst.name}] 客户端未就绪"}
                return
            session_key = client._default_session_key
            if not session_key:
                session_key = f"agent:main:{instance_id}"
                client._default_session_key = session_key

            logger.info(f"[stream] [{inst.name}] chat.send → {client.config.gateway_url} session={session_key}")
            try:
                event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

                async def _on_event(frame: dict[str, Any]) -> None:
                    await event_queue.put(frame)

                ws_client = OpenClawWSClient(
                    gateway_url=client.config.gateway_url,
                    token=client.config.gateway_token,
                    on_event=_on_event,
                )
                if not await ws_client.connect():
                    yield {"type": "error", "text": "连接干员聊天通道失败"}
                    return

                try:
                    await _sync_latest_travel_report_if_needed(
                        inst=inst,
                        ws_client=ws_client,
                        session_key=session_key,
                    )
                    ack = await ws_client.chat_send(
                        message=message,
                        session_key=session_key,
                        timeout_ms=timeout * 1000,
                    )
                    run_id = str(ack.get("runId") or "").strip()
                    if not run_id:
                        yield {"type": "error", "text": "聊天通道未返回 runId"}
                        return

                    last_content = ""
                    while True:
                        frame = await asyncio.wait_for(event_queue.get(), timeout=timeout + 30)
                        if frame.get("type") != "event":
                            continue

                        event_name = str(frame.get("event") or "").strip()
                        payload = frame.get("payload") if isinstance(frame.get("payload"), dict) else {}

                        if event_name == "chat":
                            if str(payload.get("runId") or "").strip() != run_id:
                                continue
                            if str(payload.get("sessionKey") or "").strip() != session_key:
                                continue

                            state = str(payload.get("state") or "").strip()
                            if state == "delta":
                                merged = _extract_chat_text(payload.get("message"))
                                if merged:
                                    delta = merged[len(last_content):] if merged.startswith(last_content) else merged
                                    last_content = merged
                                    if delta:
                                        yield {"type": "content", "text": delta}
                                continue

                            if state == "final":
                                final_text = _extract_chat_text(payload.get("message")) or last_content
                                yield {"type": "done", "text": final_text}
                                return

                            if state == "error":
                                yield {"type": "error", "text": str(payload.get("errorMessage") or "聊天失败")}
                                return

                            if state == "aborted":
                                yield {"type": "error", "text": "对话已中止"}
                                return

                        if event_name == "agent":
                            if str(payload.get("runId") or "").strip() != run_id:
                                continue
                            stream = str(payload.get("stream") or "").strip()
                            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

                            if stream == "tool":
                                phase = str(data.get("phase") or "").strip()
                                tool_name = str(data.get("name") or "工具").strip() or "工具"
                                if phase == "start":
                                    yield {"type": "status", "text": f"调用工具: {tool_name}"}
                                    yield {
                                        "type": "tool_call",
                                        "name": tool_name,
                                        "toolCallId": str(data.get("toolCallId") or ""),
                                        "args": data.get("args"),
                                    }
                                elif phase in {"end", "result"}:
                                    yield {
                                        "type": "tool_result",
                                        "name": tool_name,
                                        "toolCallId": str(data.get("toolCallId") or ""),
                                        "isError": bool(data.get("isError", False)),
                                        "result": data.get("result"),
                                    }
                                continue

                            if stream == "lifecycle":
                                phase = str(data.get("phase") or "").strip()
                                if phase == "start":
                                    yield {"type": "status", "text": "思考中"}
                                elif phase == "error":
                                    yield {"type": "error", "text": str(data.get("error") or "聊天失败")}
                                    return
                finally:
                    await ws_client.close()

            except TimeoutError:
                logger.warning(f"[stream] [{inst.name}] SSE 超时 {timeout}s")
                yield {"type": "error", "text": "等待回复超时"}
            except Exception as e:
                logger.error(f"[stream] [{inst.name}] chat.send 异常: {e}")
                yield {"type": "error", "text": f"连接失败: {e}"}
        finally:
            lock.release()

    @staticmethod
    def _check_port(port: int, host: str = "127.0.0.1") -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                return s.connect_ex((host, port)) == 0
        except Exception:
            return False

    @staticmethod
    def _ensure_gateway_config():
        try:
            from .llm_config_bridge import (
                ensure_gateway_local_mode,
                ensure_gateway_port,
                ensure_hooks_allow_request_session_key,
                ensure_hooks_path,
                ensure_openclaw_config,
                inject_naga_llm_config,
            )

            ensure_openclaw_config()
            ensure_gateway_local_mode(auto_create=False)
            ensure_hooks_path(auto_create=False)
            ensure_hooks_allow_request_session_key(auto_create=False)
            ensure_gateway_port(auto_create=False)
            inject_naga_llm_config()
        except Exception:
            pass
