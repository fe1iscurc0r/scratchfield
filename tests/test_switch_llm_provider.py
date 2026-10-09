"""工单210 任务二 · switch_llm_provider 回归测试（全部在 tmp_path 上跑，不碰真实配置）。

运行：CODEBUDDY_SAFE_DELETE_ENABLED=0 .venv/Scripts/python.exe -m pytest tests/test_switch_llm_provider.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 工单225 病二修复：原实现 sys.path.insert(0, ROOT/"tools") 会让 pytest 全量跑时
# tools/tests/（台账验证子包，有自己的 __init__.py）抢走顶层 "tests" 命名空间——
# 之后所有 `from tests.test_agentic_loop_flow import ...`（7 个测试文件的既有模式）
# 解析到 tools/tests 而炸 ModuleNotFoundError。
# 修法：不再污染 sys.path，改 importlib 按文件路径加载 tools 脚本（同 tools/tests 自己的姿势）。
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "switch_llm_provider", ROOT / "tools" / "switch_llm_provider.py")
S = importlib.util.module_from_spec(_spec)
sys.modules["switch_llm_provider"] = S  # dataclass 装饰器需要模块已在 sys.modules
_spec.loader.exec_module(S)


@pytest.fixture()
def cfg(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "schema_version": 2,
        "api": {"base_url": "https://tokenrhythm.studio/v1",
                "model": "deepseek-v4-pro-0813", "provider": "openai",
                "api_key": "sk-test-0123456789", "use_gateway": True},
        "system": {"ai_name": "陆墨"},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def run(argv: list[str]) -> int:
    old = sys.argv
    sys.argv = ["switch_llm_provider.py"] + argv
    try:
        return S.main()
    finally:
        sys.argv = old


def api_of(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))["api"]


def test_switch_changes_only_three_fields_and_backs_up(cfg, capsys):
    before = api_of(cfg)
    assert run(["--config", str(cfg), "deepseek"]) == 0
    after = api_of(cfg)
    assert after["base_url"] == S.PRESETS["deepseek"]["base_url"]
    assert after["model"] == S.PRESETS["deepseek"]["model"]
    assert after["provider"] == "openai"
    # 未声明的字段必须原样保留（含 api_key / use_gateway / 其它顶层段）
    assert after["api_key"] == before["api_key"], "默认不得改 api_key"
    assert after["use_gateway"] == before["use_gateway"], "默认不得改 use_gateway"
    assert json.loads(cfg.read_text(encoding="utf-8"))["system"]["ai_name"] == "陆墨"
    baks = list(cfg.parent.glob("config.json.bak.*"))
    assert len(baks) >= 1, "必须留备份"


def test_dry_run_does_not_write(cfg):
    snap = cfg.read_bytes()
    assert run(["--config", str(cfg), "minimax", "--dry-run"]) == 0
    assert cfg.read_bytes() == snap, "dry-run 不得落盘"
    assert api_of(cfg)["base_url"].startswith("https://tokenrhythm")


def test_idempotent_when_already_target(cfg, capsys):
    assert run(["--config", str(cfg), "tokenrhythm"]) == 0
    out = capsys.readouterr().out
    assert "无改动" in out, f"同 provider 应报无改动，实际: {out[-200:]}"
    assert not list(cfg.parent.glob("config.json.bak.*")), "无改动时不应产备份"


def test_round_trip_and_restore(cfg):
    orig = cfg.read_bytes()
    assert run(["--config", str(cfg), "deepseek"]) == 0
    assert run(["--config", str(cfg), "zhipu", "--model", "glm-4.7-flash"]) == 0
    assert api_of(cfg)["model"] == "glm-4.7-flash"
    baks = sorted(p.name for p in cfg.parent.glob("config.json.bak.*"))
    # 最早那份 = 原始 tokenrhythm
    assert run(["--config", str(cfg), "--restore", baks[0]]) == 0
    assert cfg.read_bytes() == orig, "恢复后应与最初的原始内容一致"


def test_set_key_from_env(cfg, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env-abcdef")
    assert run(["--config", str(cfg), "deepseek", "--set-key-from-env"]) == 0
    assert api_of(cfg)["api_key"] == "sk-from-env-abcdef"


def test_probe_failure_exits_1(cfg):
    """探测不可达端点 → 失败路径必须返回 1（这是 playbook 的降级依据）。"""
    if run(["--config", str(cfg), "tokenrhythm", "--probe"]) == 1:
        pass  # 真实网关可能仍可达 → 也可能 OK，见下
    # 指向必然不可达的端口，确保 FAIL 路径
    S.PRESETS["__unreachable__"] = {"base_url": "http://127.0.0.1:1/v1", "model": "x",
                                    "provider": "openai", "key_env": "X", "note": "test"}
    try:
        rc = run(["--config", str(cfg), "__unreachable__", "--probe"])
    finally:
        S.PRESETS.pop("__unreachable__", None)
    assert rc == 1, "不可达端点必须 exit 1"


def test_missing_config_exit_3(tmp_path):
    assert run(["--config", str(tmp_path / "nope.json"), "deepseek"]) == 3


def test_list_and_show_do_not_write(cfg):
    snap = cfg.read_bytes()
    assert run(["--list"]) == 0
    assert run(["--config", str(cfg), "--show"]) == 0
    assert cfg.read_bytes() == snap
