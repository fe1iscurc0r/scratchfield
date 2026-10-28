"""工单 228 任务一 · ``/admin/model_state`` 只读探针回归测试（全程 tmp_path，不碰真实配置）。

运行：``PYTHONPATH=<仓根> python -m pytest tests/test_admin_model_state.py -q``

导入方式说明：用 importlib **按文件路径**加载 ``apiserver/admin/router.py``，不走
``import apiserver.admin.router`` —— 避免拉起 ``apiserver`` 包的导入副作用
（与 ``tests/test_switch_llm_provider.py`` 同姿势）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "w228_admin_router", ROOT / "apiserver" / "admin" / "router.py")
M = importlib.util.module_from_spec(_spec)
sys.modules["w228_admin_router"] = M  # 供后续可能的自省使用
_spec.loader.exec_module(M)


def _write_config(tmp_path: Path, api: dict) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"api": api}, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def test_response_shape(tmp_path):
    """返回结构必须齐备（工单 §任务一 第 2 条）。"""
    cfg = _write_config(tmp_path, {
        "model": "deepseek-flash", "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
    })
    out = M.resolve_model_state(
        config_path=cfg, hermes_path=tmp_path / "none.yaml",
        log_path=tmp_path / "none.log",
        now=datetime(2026, 10, 13, 10, 0),  # 周二 10:00 → 峰段
    )
    assert {"peak", "current_model", "fallback_chain", "capabilities", "ts", "sources"} <= set(out)
    assert out["current_model"] == "deepseek-flash"
    assert out["current_provider"] == "deepseek"
    assert out["peak"] is True
    assert isinstance(out["fallback_chain"], list)
    assert isinstance(out["capabilities"], list)
    assert out["sources"]["peak"] == "clock"
    assert out["sources"]["config"].endswith("config.json")


def test_weekday_peak_window_boundaries():
    """峰段边界：09-12 / 14-18，左闭右开；周末一律谷段。"""
    assert M.is_weekday_peak(datetime(2026, 10, 13, 9, 0)) is True      # 周二 09:00
    assert M.is_weekday_peak(datetime(2026, 10, 13, 11, 59)) is True
    assert M.is_weekday_peak(datetime(2026, 10, 13, 12, 0)) is False    # 左闭右开
    assert M.is_weekday_peak(datetime(2026, 10, 13, 13, 0)) is False
    assert M.is_weekday_peak(datetime(2026, 10, 13, 14, 0)) is True
    assert M.is_weekday_peak(datetime(2026, 10, 13, 17, 59)) is True
    assert M.is_weekday_peak(datetime(2026, 10, 13, 18, 0)) is False
    assert M.is_weekday_peak(datetime(2026, 10, 17, 10, 0)) is False    # 周六
    assert M.is_weekday_peak(datetime(2026, 10, 18, 10, 0)) is False    # 周日


def test_peak_prefers_log_over_clock(tmp_path):
    """log 反应真实切换动作 → 优先级高于按时间的推断。"""
    cfg = _write_config(tmp_path, {"model": "MiniMax-M3", "provider": "openai"})
    log = tmp_path / "peak_switch.log"
    log.write_text(
        "2026-10-13T09:00 switch -> MiniMax-M3 (peak)\n"
        "2026-10-13T12:00 switch -> deepseek-flash (valley)\n",
        encoding="utf-8",
    )
    out = M.resolve_model_state(
        config_path=cfg, hermes_path=tmp_path / "none.yaml",
        log_path=log,
        now=datetime(2026, 10, 13, 10, 0),  # 时钟说"峰"
    )
    assert out["peak"] is False                 # log 末条 valley 说了算
    assert out["sources"]["peak"] == "log"


def test_missing_everything_degrades_not_raises(tmp_path):
    """三路都读不到 → 降级返回，绝不抛（探针不能变成新故障点）。"""
    out = M.resolve_model_state(
        config_path=tmp_path / "nope.json",
        hermes_path=tmp_path / "nope.yaml",
        log_path=tmp_path / "nope.log",
        now=datetime(2026, 10, 13, 3, 0),       # 周二凌晨 → 谷段
    )
    assert out["current_model"] is None
    assert out["current_provider"] is None
    assert out["fallback_chain"] == []
    assert out["peak"] is False
    assert out["sources"]["config"] == "missing"
    assert out["sources"]["peak"] == "clock"


def test_hermes_yaml_is_optional_fallback(tmp_path):
    """仓内 config 缺字段时，从 ~/.hermes 风格 YAML 补缺（存在才读）。"""
    pytest.importorskip("yaml", reason="PyYAML 可选；缺失时与 _load_yaml 的降级一致，跳过")
    cfg = _write_config(tmp_path, {"base_url": "https://api.deepseek.com/v1"})  # 无 model/provider
    yml = tmp_path / "hermes.yaml"
    yml.write_text(
        "model:\n"
        "  default: deepseek-flash\n"
        "  provider: deepseek\n"
        "  fallback_providers:\n"
        "    - MiniMax-M3\n",
        encoding="utf-8",
    )
    out = M.resolve_model_state(
        config_path=cfg, hermes_path=yml, log_path=tmp_path / "none.log",
        now=datetime(2026, 10, 13, 10, 0),
    )
    assert out["current_model"] == "deepseek-flash"
    assert out["current_provider"] == "deepseek"
    assert out["fallback_chain"] == ["MiniMax-M3"]
    assert "hermes" in out["sources"]


def test_repo_config_fallback_chain_wins(tmp_path):
    """仓内 config 若显式配了 fallback_providers，应以它为准（不被 YAML 覆盖）。"""
    cfg = _write_config(tmp_path, {
        "model": "deepseek-flash", "provider": "deepseek",
        "fallback_providers": ["MiniMax-M3", "glm-4.7-flash"],
    })
    out = M.resolve_model_state(
        config_path=cfg, hermes_path=tmp_path / "none.yaml",
        log_path=tmp_path / "none.log",
        now=datetime(2026, 10, 13, 10, 0),
    )
    assert out["fallback_chain"] == ["MiniMax-M3", "glm-4.7-flash"]


def test_capabilities_are_strings():
    """capability 探测返回模块名字符串列表（环境相关，只断言类型与无异常）。"""
    caps = M.detect_capabilities()
    assert isinstance(caps, list)
    assert all(isinstance(c, str) for c in caps)
    assert all(c in M.CAPABILITY_MODULES for c in caps)
