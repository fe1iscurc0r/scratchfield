"""apiserver 配置收口（工单204 任务四）。

**单一真源**：集中声明本包读取的全部环境变量（名称 / 默认值 / 类型 / 用途）。
纯 stdlib（`os` + `dataclass`）——工单口径明确「不引入 pydantic-settings 等新重依赖」。

设计要点（迁移前后**行为必须一致**）：
1. **调用时读取**，不缓存 —— 迁移前各文件也是每次调用读 `os.environ`，
   缓存会让运行时改环境变量失效（语义变化，禁止）；
2. 三级回退：环境变量 > `system.config`（可用时）> 本模块硬默认；
3. 解析失败**不抛**：回退默认值并留痕（`notes`），避免启动期因一个坏 env 崩掉服务。

用法：
    from apiserver.config import settings
    host, port = settings.api_server_host(), settings.api_server_port()
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

#: 布尔真值（大小写不敏感）；其余一律 False（与迁移前 `.lower() == "true"` 兼容并放宽）
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _get(name: str, default: str = "") -> str:
    val = os.environ.get(name)
    return default if val is None else val


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


@dataclass
class Settings:
    """环境变量访问器（**每次调用都重新读取**，见模块 docstring 第 1 条）。

    `notes` 记录本次解析中的回退/异常，供诊断（不抛异常）。
    """

    notes: list[str] = field(default_factory=list)

    # ---- 通用读取 ----
    def get(self, name: str, default: str = "") -> str:
        return _get(name, default)

    def get_bool(self, name: str, default: bool = False) -> bool:
        return _get_bool(name, default)

    def get_int(self, name: str, default: int) -> int:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            self.notes.append(f"{name}={raw!r} 不是整数，回退默认 {default}")
            return default

    # ---- API 服务（迁移自 apiserver/start_server.py）----
    def api_server_host(self) -> str:
        return self.get("API_SERVER_HOST", "127.0.0.1")

    def api_server_port(self) -> int:
        """默认端口：system.config 可用时取 api_server 配置，否则 8000（与原逻辑一致）。"""
        return self.get_int("API_SERVER_PORT", _config_port("api_server", 8000, self))

    def api_server_reload(self) -> bool:
        return self.get_bool("API_SERVER_RELOAD", False)

    # ---- LLM 服务（迁移自 apiserver/start_server.py）----
    def llm_service_host(self) -> str:
        return self.get("LLM_SERVICE_HOST", "127.0.0.1")

    def llm_service_port(self) -> int:
        return self.get_int("LLM_SERVICE_PORT", _config_port("agent_server", 8001, self))

    def llm_service_reload(self) -> bool:
        return self.get_bool("LLM_SERVICE_RELOAD", False)

    # ---- NEKO 桌宠壳对接（迁移自 apiserver/neko_cua.py）----
    def neko_agent_base(self) -> str:
        return self.get("NEKO_AGENT_BASE", "http://127.0.0.1:48915")

    def neko_exec_token(self) -> str:
        return self.get("NEKO_EXEC_TOKEN", "")

    # ---- 本机用户（迁移自 apiserver/naga_auth.py）----
    def os_username(self) -> str:
        return self.get("USERNAME", "")

    # ---- 行为开关（迁移自 apiserver/llm_service.py）----
    def enable_thinking(self) -> bool:
        """思考链开关：默认开；显式 `LUMO_ENABLE_THINKING=0` 关闭（原语义为 `== '0'`）。"""
        return self.get("LUMO_ENABLE_THINKING", "1").strip() != "0"

    # ---- 备份（迁移自 apiserver/db_backup.py）----
    def db_backup_dir(self) -> str:
        return self.get("LUMO_DB_BACKUP_DIR", "").strip()


def _config_port(service: str, fallback: int, settings: Settings) -> int:
    """从 system.config 取端口；不可用时回退硬默认（失败留痕，不抛）。"""
    try:
        from system.config import get_server_port

        return int(get_server_port(service))
    except Exception as exc:  # noqa: BLE001
        settings.notes.append(f"system.config 端口({service}) 不可用({type(exc).__name__})，用 {fallback}")
        return fallback


#: 模块级单例（无状态：字段每次调用重新读环境变量）
settings = Settings()


#: 环境变量清单（**单一真源**，供 .env.example 与文档对齐）
#: 名称 → (默认值, 类型, 用途)
ENV_SPEC: dict[str, tuple[object, str, str]] = {
    "API_SERVER_HOST": ("127.0.0.1", "str", "API 服务监听地址"),
    "API_SERVER_PORT": ("(system.config → 8000)", "int", "API 服务端口"),
    "API_SERVER_RELOAD": ("False", "bool", "API 服务热重载"),
    "LLM_SERVICE_HOST": ("127.0.0.1", "str", "LLM 服务监听地址"),
    "LLM_SERVICE_PORT": ("(system.config → 8001)", "int", "LLM 服务端口"),
    "LLM_SERVICE_RELOAD": ("False", "bool", "LLM 服务热重载"),
    "NEKO_AGENT_BASE": ("http://127.0.0.1:48915", "str", "NEKO 桌宠壳 agent 端点"),
    "NEKO_EXEC_TOKEN": ("", "str", "NEKO 桌宠壳执行令牌"),
    "LUMO_ENABLE_THINKING": ("1", "bool-ish", "思考链开关（=0 关闭）"),
    "LUMO_DB_BACKUP_DIR": ("(空=data_dir/db_backups)", "str", "数据库备份根目录"),
    "USERNAME": ("", "str", "本机用户名（naga_auth）"),
    "LUMO_PROXY_TOKEN": ("", "str", "NEKO 注入鉴权令牌（铁律7）"),
    "LUMO_VAULT_DIR": ("", "str", "凭据库目录"),
    "LUMO_VISION_API_KEY": ("", "str", "视觉模型 API key"),
    "LUMO_VISION_MODEL": ("", "str", "视觉模型名"),
    "SPECTRUM_SOURCE": ("", "str", "频谱数据源"),
    "ASR_API_URL": ("", "str", "ASR 服务地址"),
    "ASR_MODEL": ("", "str", "ASR 模型名"),
}


def env_spec_lines() -> list[str]:
    """生成 .env.example 用的说明行（名称=默认值  # 用途）。"""
    return [f"{name}={'' if str(d).startswith('(') else d}   # {use}（类型 {typ}）"
            for name, (d, typ, use) in ENV_SPEC.items()]
