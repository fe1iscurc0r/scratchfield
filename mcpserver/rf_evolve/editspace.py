"""受限编辑面（工单246 · 对应 SeisEvo 的 "components the user has opened for editing"）。

SeisEvo（arXiv:2608.18272v1）的第一条机制是：**不让人/LLM 随意改算法**，
而是显式声明「哪些组件在这个任务上**允许**被改、各自的取值域是什么」，
搜索只在**这个被打开的面上**进行。这既把搜索空间压到可枚举，也让每个候选都能被审计。

本模块把这条机制落成 `EditSpace` / `Param`：
每个参数都带**为什么它可编辑**（`why`）与**它影响什么**（`affects`），
不允许出现"能改但说不出理由"的参数 —— 那是把算法交给运气。

本单的编辑面 = `mcpserver/rf_brain/rfi_mitigation.py::mitigate_rfi` 的 4 个自由参数
（其余部分是**冻结的**：检测算法、陷波拓扑、滤波实现都不动 —— 与 SeisEvo 一致）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class Param:
    """一个**允许被演化**的参数。"""

    name: str
    kind: str                 # "float" | "int" | "bool" | "float_or_none"
    low: float | None = None
    high: float | None = None
    choices: tuple[Any, ...] = ()      # 离散取值（优先于 low/high）
    default: Any = None                # 经典实现的取值（= 演化起点）
    why: str = ""                      # 为什么允许改它
    affects: str = ""                  # 改它会动到算法的哪一环
    unit: str = ""

    def describe(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "unit": self.unit,
            "domain": list(self.choices) if self.choices else [self.low, self.high],
            "default": self.default, "why": self.why, "affects": self.affects,
        }


@dataclass
class EditSpace:
    """一次演化任务的**全部可编辑参数**（其余皆为冻结组件）。"""

    task: str
    target: str                        # 被演化的算法（模块::函数）
    frozen: list[str] = field(default_factory=list)   # 明确列出**不**动的组件
    params: list[Param] = field(default_factory=list)

    def names(self) -> list[str]:
        return [p.name for p in self.params]

    def get(self, name: str) -> Param:
        for p in self.params:
            if p.name == name:
                return p
        raise KeyError(f"未声明的参数 {name!r}（可编辑面只有 {self.names()}）")

    def defaults(self) -> dict:
        return {p.name: p.default for p in self.params}

    def canonical(self, params: dict) -> dict:
        """校验并规范化一组取值：**未声明的键直接拒绝**（不在编辑面上的一律不许改）。"""
        unknown = sorted(set(params) - set(self.names()))
        if unknown:
            raise KeyError(f"参数 {unknown} 不在可编辑面上（EditsSpace 只允许 {self.names()}）")
        missing = sorted(set(self.names()) - set(params))
        if missing:
            raise KeyError(f"缺参数 {missing}")
        out: dict = {}
        for p in self.params:
            v = params[p.name]
            if p.choices:
                if v not in p.choices:
                    raise ValueError(f"{p.name}={v!r} 不在取值域 {list(p.choices)}")
                out[p.name] = v
                continue
            if p.kind == "bool":
                out[p.name] = bool(v)
                continue
            if p.kind == "float_or_none":
                if v is None:
                    out[p.name] = None
                    continue
                v = float(v)
            elif p.kind == "float":
                v = float(v)
            elif p.kind == "int":
                v = int(v)
            if p.low is not None and v < p.low:
                raise ValueError(f"{p.name}={v} 低于下界 {p.low}")
            if p.high is not None and v > p.high:
                raise ValueError(f"{p.name}={v} 高于上界 {p.high}")
            out[p.name] = v
        return out

    def grid(self) -> Iterable[dict]:
        """按离散取值做笛卡尔积（`rules` 提案器的第一遍用；域已被压到可枚举）。"""
        keys = self.names()
        pools = [_pool_of(p) for p in self.params]
        import itertools
        for combo in itertools.product(*pools):
            yield dict(zip(keys, combo))

    def describe(self) -> dict:
        return {
            "task": self.task, "target": self.target,
            "editable": [p.describe() for p in self.params],
            "frozen": self.frozen,
        }


def _pool_of(p: Param) -> list:
    """一个参数在网格里的取值池。

    ⚠️ 布尔参数**没有 low/high**，若走通用分支会得到 ``[False, None, None]``
    —— 既有非法值又有重复（实测踩过：网格从 504 点涨到 756 点，且 `adaptive=None` 混进去）。
    因此 bool 单独走 ``[False, True]``；并对所有池去重（保序）。
    """
    if p.choices:
        pool = list(p.choices)
    elif p.kind == "bool":
        pool = [False, True]
    else:
        pool = [p.default, p.low, p.high]
    return list(dict.fromkeys(pool))


#: 本单的编辑面：`mcpserver/rf_brain/rfi_mitigation.py::mitigate_rfi` 的 4 个自由参数。
#:
#: ⚠️ 仅这 4 个可动；检测算法（`detect_rfi_narrowband`）、陷波拓扑（逐频点 biquad）、
#: 滤波实现（`notch_filter` / `adaptive_notch`）**全部冻结** —— 与 SeisEvo 的
#: "modifies only the components the user has opened for editing" 一致。
RFI_MITIGATION_SPACE = EditSpace(
    task="窄带干扰抑制（RFI mitigation）参数演化",
    target="mcpserver.rf_brain.rfi_mitigation::mitigate_rfi",
    frozen=[
        "detect_rfi_narrowband（检测算法：FFT 谱峰 + 显著度阈值）",
        "notch_filter / notch_biquad（固定陷波拓扑：2 阶 Butterworth 带阻）",
        "adaptive_notch（自适应拓扑：LMS 单频对消）",
        "滤波链顺序（逐个频点串行陷波）",
    ],
    params=[
        Param(
            name="prominence_db", kind="float", low=6.0, high=40.0, default=20.0, unit="dB",
            choices=(8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0),
            why="谱峰要多显著才判为干扰 —— 直接决定「漏检 vs 误检」的取舍",
            affects="检测级联的上游：定得太低会把噪声峰当干扰（灾难），太高会漏掉弱干扰",
        ),
        Param(
            name="notch_bw_hz", kind="float_or_none", low=100.0, high=20000.0, default=None,
            unit="Hz",
            choices=(None, 200.0, 500.0, 1000.0, 3000.0, 5000.0),
            why="陷波带宽 —— 决定「抑制干净度 vs 带内损伤」的取舍",
            affects="每个干扰频点的陷波器 Q；越宽越能容忍干扰频漂，但越会咬到邻近的有用谱",
        ),
        Param(
            name="adaptive", kind="bool", default=False,
            why="用自适应（LMS）替代固定陷波 —— 能跟踪干扰的幅度/相位慢漂移",
            affects="陷波环节的实现路径；代价是**逐样本循环**，算力/时延显著高于 biquad",
        ),
        Param(
            name="mu", kind="float", low=0.001, high=0.2, default=0.01,
            choices=(0.002, 0.005, 0.01, 0.02, 0.05, 0.08),
            why="LMS 步长 —— 收敛速度与稳态误差的取舍",
            affects="仅 adaptive=True 时生效；过大不收敛（**有硬性稳定上界**，见 constraints.py）",
        ),
    ],
)


def spaces() -> dict[str, EditSpace]:
    """已登记的编辑面（供 server 列目录）。"""
    return {"rfi_mitigation": RFI_MITIGATION_SPACE}
