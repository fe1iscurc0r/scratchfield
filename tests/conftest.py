"""tests/ 全局收集配置 / Global collection config for the test suite.

按模块存在性做收集级跳过（skip collection when an optional dependency is
absent）。规则：被引用的模块在当前分支不存在时，测试文件整体不收集，
而不是在 import 阶段炸掉整个收集流程。
"""
from __future__ import annotations

import importlib.util
import os

# (测试文件名, 依赖模块) — 依赖缺失时跳过收集
# antenna_rotator: w130 云台服务引用的固件侧 Python 包，随 w129 硬件分支
# 交付；主线未合入（2026-09-22 登记，见 tests/test_ptz_lora.py 头注）。
_OPTIONAL_MODULE_TESTS: list[tuple[str, str]] = [
    ("test_ptz_lora.py", "mcpserver.antenna_rotator"),
    ("test_ptz_service.py", "mcpserver.antenna_rotator"),
    ("test_ptz_scheduler.py", "mcpserver.antenna_rotator"),
    ("test_ptz_safety.py", "mcpserver.antenna_rotator"),
    # 卷173 分层落地时补登记：scipy 为 try/except 降级依赖（pyproject 未声明，
    # 见 2026-09-29 依赖审计），干净 venv 下缺失属预期——跳过收集不拦全量。
    ("test_raman_utils.py", "scipy"),
    # ── 展示仓同步口径（2026-10-04 第五轮 CI 排障统一登记）─────────────
    # 展示仓不携带 vendor/ 与 research/ 等私有工作仓目录，也不强制安装
    # 全量可选 pip 依赖——对应测试在展示仓环境按模块存在性跳过收集；
    # 私有工作仓环境（vendor/ 在位、依赖齐全）不受影响。
    ("test_lorebook.py", "research"),
    ("test_planner.py", "research"),
    # NEKO vendored 子树的隐式顶层导入（utils.token_tracker）：CI 干净环境
    # （PYTHONPATH=workspace 根）下子树路径不在搜索序内。本地 hermes 环境
    # 因顶层 utils.py 遮蔽而"能过"，属假阴性，不以本地为准。
    ("test_spec03_phase1.py", "utils.token_tracker"),
    ("test_memory_maas.py", "utils.token_tracker"),
    # vendor/rsba1-core（独立仓，展示仓不含 vendor/）
    ("test_rsba1_adapter.py", "rsba1"),
    ("test_rsba1_adapter_fake_backends.py", "rsba1"),
    # 法学领域包的私有判例索引模块
    ("test_law_case_import.py", "casregnum"),
    ("test_law_tagging.py", "casregnum"),
    # 可选 pip 依赖（展示仓 CI 最小安装）
    ("test_duckdb_workbench.py", "duckdb"),
    ("test_writing_pipeline.py", "duckdb"),
    ("test_domain_pack.py", "matplotlib"),
    ("test_mcp_assembly_policy.py", "matplotlib"),
    ("test_mcp_adapters.py", "markitdown"),
    ("test_academic_bridge.py", "docx"),
    ("test_academic_interfaces.py", "docx"),
    # vendor checkout 的 matrix_registry.json（展示仓不含 vendor/）
    ("test_cli_anything_agent.py", "os.path.exists"),
    # torch 重型依赖（本地嵌入引擎；无 torch 环境跳过，CI 装 torch 时正常跑）
    ("test_local_embedder.py", "torch"),
    # academic 各接口包（ChemFormula 等 pip 包，展示仓 CI 不装）
    ("test_academic_interfaces.py", "chemformula"),
    ("test_academic_bridge.py", "chemformula"),
    # markitdown 真实转换路径（monkeypatch 只骗可用性检查，convert 需真包）
    ("test_pdf2md_adapter.py", "markitdown"),
    # doctor/onboard 依赖完整运行时组件（uvicorn 等），最小环境跳过
    ("test_onboard_doctor.py", "uvicorn"),
    ("test_verify_entrypoint.py", "uvicorn"),
]

def _spec_missing(module_name: str) -> bool:
    """模块缺失返回 True；父包不存在等异常同样视为缺失。

    特殊形态 "os.path.exists(<path>)"：按仓库文件存在性判断（vendor checkout
    等未同步目录），文件不在即视为缺失。
    """
    if module_name.startswith("os.path.exists("):
        rel = module_name[len("os.path.exists("):-1].strip("'\"")
        return not os.path.isfile(os.path.join(os.path.dirname(__file__), "..", rel))
    try:
        return importlib.util.find_spec(module_name) is None
    except (ImportError, AttributeError, ValueError):
        return True


collect_ignore = [
    test_file
    for test_file, module_name in _OPTIONAL_MODULE_TESTS
    if _spec_missing(module_name)
]
