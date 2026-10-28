"""mcpserver.rf_evolve —— RF/信号处理**算法演化**框架（工单246）。

论文来源：**SeisEvo**（arXiv:2608.18272v1，Xu/Yu/Ma，2026-08-18）
《SeisEvo: Evolution of Seismic Data Reconstruction Algorithms by Agents》。
它的四条机制被逐条落到本仓可验证的形态：

| SeisEvo 的机制 | 本模块的落点 |
|---|---|
| 只在**用户打开的组件**上改动 | `editspace.py`：显式声明可编辑参数 + **冻结组件清单** |
| 违反**物理约束**的候选直接否决 | `constraints.py`：A 段参数级（O(1)）/ B 段检测级（1 次 FFT，**不跑陷波**） |
| 候选由**执行**打分 | `scorer.py`：真跑仓内既有 RFI 缓解实现，读数 = 对干净参考的 S/N 提升 dB |
| 输出**白盒算法**（推理期不需要 agent/NN） | `codegen.py`：生成只依赖 numpy 的自包含源码 |

**它不是什么**：本模块不实现任何滤波算法 —— 被演化的算法是
`mcpserver/rf_brain/rfi_mitigation.py`（**冻结**，本单只读不改）。
本模块提供的是**搜索**：提案 → 约束门 → 执行打分 → 选择 → 出产物。

与相邻模块的边界
----------------
- `mcpserver/rf_workflow`（工单242）：规格 → 生成 LoRa PHY **仿真脚本** → 跑 → 算 PHY 指标（**单次生成**）；
  本模块是**在受限编辑面上的多候选演化搜索**，用执行打分选优。两者不重叠。
- `mcpserver/rf_brain`：提供**被演化的算法**；本模块提供**搜索**。
"""

from __future__ import annotations

from .candidate import Candidate
from .editspace import RFI_MITIGATION_SPACE, EditSpace, Param, spaces
from .evolve import EvolveConfig, EvolveResult, evolve
from .scorer import DEFAULT_SCENARIOS, Scenario, ScoreResult, baseline_report

__all__ = [
    "DEFAULT_SCENARIOS",
    "RFI_MITIGATION_SPACE",
    "Candidate",
    "EditSpace",
    "EvolveConfig",
    "EvolveResult",
    "Param",
    "RfEvolveBridge",
    "Scenario",
    "ScoreResult",
    "baseline_report",
    "evolve",
    "spaces",
]


def __getattr__(name: str):
    """`RfEvolveBridge` 惰性暴露（`server` 只在真取用时导入）。"""
    if name == "RfEvolveBridge":
        from .server import RfEvolveBridge

        return RfEvolveBridge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
