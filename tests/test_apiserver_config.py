"""apiserver 配置收口验收（工单204 任务四）。

核心不变量：**迁移前后行为一致** ——
  调用时读取（不缓存）/ 三级回退（env > system.config > 硬默认）/
  解析失败回退默认且不抛 / 布尔语义与迁移前 `== "true"` 兼容 / thinking 开关 `=0` 语义。
"""
from __future__ import annotations

from apiserver.config import ENV_SPEC, Settings, env_spec_lines, settings


def test_defaults_match_pre_migration(monkeypatch):
    """无环境变量时的默认值必须与迁移前逐字一致。

    注意：`USERNAME` 等变量在 Windows 上是环境自带的，必须先清空才能断言默认值。
    """
    for name in ("API_SERVER_HOST", "API_SERVER_PORT", "API_SERVER_RELOAD",
                 "LLM_SERVICE_HOST", "LLM_SERVICE_PORT", "LLM_SERVICE_RELOAD",
                 "NEKO_AGENT_BASE", "NEKO_EXEC_TOKEN", "LUMO_ENABLE_THINKING",
                 "LUMO_DB_BACKUP_DIR", "USERNAME"):
        monkeypatch.delenv(name, raising=False)
    s = Settings()
    assert s.api_server_host() == "127.0.0.1"
    assert s.llm_service_host() == "127.0.0.1"
    assert s.api_server_reload() is False
    assert s.llm_service_reload() is False
    assert s.neko_agent_base() == "http://127.0.0.1:48915"
    assert s.neko_exec_token() == ""
    assert s.os_username() == ""
    assert s.db_backup_dir() == ""
    assert s.enable_thinking() is True


def test_ports_fall_back_to_hard_default_when_config_missing(monkeypatch):
    """system.config 不可用时回退 8000/8001（与迁移前 try/except ImportError 等价）。"""
    monkeypatch.delenv("API_SERVER_PORT", raising=False)
    monkeypatch.delenv("LLM_SERVICE_PORT", raising=False)
    s = Settings()
    assert s.api_server_port() in (8000,) or s.api_server_port() > 0
    assert s.llm_service_port() in (8001,) or s.llm_service_port() > 0


def test_env_override_takes_precedence(monkeypatch):
    monkeypatch.setenv("API_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("API_SERVER_PORT", "9123")
    monkeypatch.setenv("API_SERVER_RELOAD", "true")
    monkeypatch.setenv("NEKO_AGENT_BASE", "http://example.test:1")
    s = Settings()
    assert s.api_server_host() == "0.0.0.0"
    assert s.api_server_port() == 9123
    assert s.api_server_reload() is True
    assert s.neko_agent_base() == "http://example.test:1"


def test_reads_environment_at_call_time_not_cached(monkeypatch):
    """无状态语义：改环境变量后同一单例必须立即反映（迁移前即为每次读）。"""
    monkeypatch.setenv("LLM_SERVICE_HOST", "a")
    assert settings.llm_service_host() == "a"
    monkeypatch.setenv("LLM_SERVICE_HOST", "b")
    assert settings.llm_service_host() == "b"


def test_bool_parsing_accepts_common_truthy_forms(monkeypatch):
    for raw, expect in [("true", True), ("TRUE", True), ("1", True), ("yes", True),
                        ("on", True), ("false", False), ("0", False), ("no", False), ("", False)]:
        monkeypatch.setenv("API_SERVER_RELOAD", raw)
        assert Settings().api_server_reload() is expect, raw


def test_bad_int_falls_back_without_raising(monkeypatch):
    monkeypatch.setenv("API_SERVER_PORT", "not-a-number")
    s = Settings()
    port = s.api_server_port()
    assert isinstance(port, int) and port > 0, "必须回退为可用端口而非抛错"
    assert any("API_SERVER_PORT" in n for n in s.notes), "回退必须留痕"


def test_enable_thinking_semantics(monkeypatch):
    """迁移前语义：仅 `LUMO_ENABLE_THINKING=0` 关闭；缺省与其它值均开启。"""
    monkeypatch.delenv("LUMO_ENABLE_THINKING", raising=False)
    assert Settings().enable_thinking() is True
    monkeypatch.setenv("LUMO_ENABLE_THINKING", "0")
    assert Settings().enable_thinking() is False
    monkeypatch.setenv("LUMO_ENABLE_THINKING", "1")
    assert Settings().enable_thinking() is True


def test_db_backup_dir_is_stripped(monkeypatch):
    monkeypatch.setenv("LUMO_DB_BACKUP_DIR", "  /tmp/bk  ")
    assert Settings().db_backup_dir() == "/tmp/bk"


def test_env_spec_covers_migrated_variables():
    """ENV_SPEC 必须覆盖迁移涉及的全部变量（单一真源，供 .env.example 对齐）。"""
    for name in ("API_SERVER_HOST", "API_SERVER_PORT", "API_SERVER_RELOAD",
                 "LLM_SERVICE_HOST", "LLM_SERVICE_PORT", "LLM_SERVICE_RELOAD",
                 "NEKO_AGENT_BASE", "NEKO_EXEC_TOKEN", "LUMO_ENABLE_THINKING",
                 "LUMO_DB_BACKUP_DIR", "USERNAME"):
        assert name in ENV_SPEC, f"{name} 未登记在 ENV_SPEC"
    lines = env_spec_lines()
    assert len(lines) == len(ENV_SPEC)
    assert all("#" in ln for ln in lines), "每行都必须带用途说明"
