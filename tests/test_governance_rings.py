import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.smoke, pytest.mark.core]
# -*- coding: utf-8 -*-
"""治理线回归测试（智能体 07 · apiserver 依赖环拆解）。

锁定 07-01 的结论：system_governance 旧扫描器把「函数内延迟导入」误判为依赖边，
凑出 5 个假环；修正后应报 0 个真实模块级环，且 rag→system 是延迟导入、非硬依赖。
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import system_governance as gov  # noqa: E402

# apiserver 病灶带 7 模块（07-01 环清单涉及的节点）
RING_MODULES = {'apiserver', 'rag', 'system', 'mcpserver', 'summer_memory', 'agentserver', 'guide_engine'}


def _analyze():
    """跑一次结构扫描 + 分析，返回 (mods, result)。"""
    mods = gov.scan_modules()
    result = gov.analyze(mods)
    return mods, result


def test_no_real_module_level_cycle():
    """治理口径的「环」应为空：模块级硬依赖图无 ≥3 节点循环（假环不算）。"""
    _, result = _analyze()
    # 真实环（模块级硬依赖，≥3 节点）必须为 0
    assert result['cycles'] == [], f"仍存在真实模块级依赖环: {result['cycles']}"


def test_ring_edges_are_lazy_not_hard():
    """7 个病灶模块之间的闭合边必须是延迟导入（假边），而非模块级硬依赖。

    具体锁定最小假环 apiserver→rag→system→apiserver 的关键边：
    - rag→system 应为 lazy（硬依赖里不含 system）
    - system→apiserver 应为 lazy（硬依赖里不含 apiserver）
    """
    mods, _ = _analyze()
    # rag 对 system 只有延迟导入
    assert 'system' not in mods['rag']['deps'], "rag 不应有对 system 的模块级硬依赖"
    assert 'system' in mods['rag']['lazy_deps'], "rag 对 system 应是函数内延迟导入"
    # system 对 apiserver 只有延迟导入
    assert 'apiserver' not in mods['system']['deps'], "system 不应有对 apiserver 的模块级硬依赖"
    assert 'apiserver' in mods['system']['lazy_deps'], "system 对 apiserver 应是函数内延迟导入"


def test_import_rag_does_not_trigger_system():
    """实证：单独 import rag 不应触发加载 system（证明 rag→system 是延迟导入）。"""
    code = "import sys; import rag; print('LOADED' if 'system' in sys.modules else 'NOT_LOADED')"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
    )
    assert proc.returncode == 0, f"import rag 失败: {proc.stderr}"
    assert proc.stdout.strip() == "NOT_LOADED", "import rag 不应触发加载 system"


def test_all_ring_modules_import_cleanly():
    """实证：7 个病灶模块顺序导入无循环导入报错（真环=0 的运行期证据）。"""
    code = (
        "import importlib\n"
        "mods = ['apiserver','rag','system','mcpserver','summer_memory','agentserver','guide_engine']\n"
        "for m in mods:\n"
        "    importlib.import_module(m)\n"
        "print('ALL_SEVEN_IMPORTED_OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
    )
    assert proc.returncode == 0, f"7 模块导入失败(存在循环导入风险): {proc.stderr}"
    assert "ALL_SEVEN_IMPORTED_OK" in proc.stdout, "7 模块应全部导入成功"
