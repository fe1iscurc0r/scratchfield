"""候选算法与执行评分（工单246 · 对应 SeisEvo 的 "scored by execution"）。

SeisEvo 的第三条机制：**候选靠真跑来打分，不靠 LLM 自评**。
本模块把这条落成：把候选参数喂给**本仓既有的** RFI 缓解实现
（`mcpserver/rf_brain/rfi_mitigation.py::mitigate_rfi`）在固定场景集上真跑，
用它对干净参考的 S/N 提升（dB）当适应度。

⚠️ 本模块**不实现任何滤波算法** —— 算法在 `rf_brain/rfi_mitigation.py`（冻结）。
本模块只负责「造场景 → 真跑 → 读数 → 聚合」。这条分工是本单与 `rf_brain` 的边界：
**rf_brain 提供被演化的算法，rf_evolve 提供搜索**。

评分口径（都是实测值，不是估计）
--------------------------------
- `mean_db`：各场景 S/N 提升（after − before）的均值（**主排序键**）
- `min_db`  ：最差场景的提升（**次排序键** —— 工程上"最坏情形"比均值更重要）
- `wall_s`  ：真实墙钟耗时（约束门说的"省算力"要能在这里被核对）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Scenario:
    """一个确定性可复现的评测场景（同 seed ⇒ 逐位可复现）。"""

    name: str
    sample_rate_hz: float = 1_000_000.0
    n_samples: int = 4096
    signal_band_hz: float = 100_000.0     # 有用信号占用的带宽（chirp 扫频范围）
    chirp_amp: float = 0.5
    noise_sigma: float = 0.08
    #: (频率Hz, 幅度, 初相) —— 窄带干扰
    interferers: tuple[tuple[float, float, float], ...] = ()
    seed: int = 20261016

    def build(self) -> tuple[np.ndarray, np.ndarray]:
        """返回 ``(reference, dirty)``：干净参考（信号+噪声）与受污染信号（+干扰）。"""
        rng = np.random.default_rng(self.seed)
        t = np.arange(self.n_samples) / self.sample_rate_hz
        # 有用信号 = 线性 chirp（LoRa 式）：能量摊在整段带宽上 ⇒ 谱峰不突出，
        # 因此**窄带峰检测器天然不该把它当干扰**（这正是本任务的前提）。
        sweep_rate = self.signal_band_hz / (self.n_samples / self.sample_rate_hz)
        wanted = self.chirp_amp * np.sin(2.0 * np.pi * (sweep_rate / 2.0) * t ** 2)
        noise = self.noise_sigma * rng.standard_normal(self.n_samples)
        reference = wanted + noise
        dirty = reference + sum(a * np.sin(2.0 * np.pi * f * t + p)
                               for f, a, p in self.interferers)
        return reference, dirty


#: 默认场景集：从"三个强单音"到"强弱悬殊"到"带内+带外"，刻意覆盖不同难点。
DEFAULT_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        name="three_strong_tones",
        interferers=((180_000.0, 0.60, 0.3), (260_000.0, 0.40, 1.1), (400_000.0, 0.30, 2.0)),
    ),
    Scenario(
        name="one_strong_two_weak",
        interferers=((180_000.0, 0.60, 0.3), (260_000.0, 0.05, 1.1), (400_000.0, 0.04, 2.0)),
    ),
    Scenario(
        name="interferer_inside_band",
        interferers=((60_000.0, 0.50, 0.3), (260_000.0, 0.40, 1.1), (400_000.0, 0.30, 2.0)),
    ),
)


@dataclass
class ScoreResult:
    """一次执行打分的读数。"""

    mean_db: float
    min_db: float
    per_scenario: dict[str, float] = field(default_factory=dict)
    wall_s: float = 0.0
    snr_before_db: dict[str, float] = field(default_factory=dict)

    @property
    def fitness(self) -> tuple[float, float]:
        """排序键：**主 = 均值，次 = 最差场景**（工程上最坏情形要能兜住）。"""
        return (self.mean_db, self.min_db)

    def as_dict(self) -> dict:
        return {"mean_db": round(self.mean_db, 4), "min_db": round(self.min_db, 4),
                "per_scenario": {k: round(v, 4) for k, v in self.per_scenario.items()},
                "wall_s": round(self.wall_s, 4),
                "snr_before_db": {k: round(v, 4) for k, v in self.snr_before_db.items()}}


def score(params: dict, scenarios: tuple[Scenario, ...] = DEFAULT_SCENARIOS,
          *, built: dict[str, tuple[np.ndarray, np.ndarray]] | None = None) -> ScoreResult:
    """把一组候选参数**真跑**在场景集上，返回 S/N 提升读数。

    :param built: 可注入已构造好的 `(reference, dirty)`（测试用，避免重复造信号）。
    """
    from mcpserver.rf_brain.rfi_mitigation import mitigate_rfi  # 惰性：只在真打分时导入

    per: dict[str, float] = {}
    before: dict[str, float] = {}
    t0 = time.perf_counter()
    for sc in scenarios:
        if built and sc.name in built:
            reference, dirty = built[sc.name]
        else:
            reference, dirty = sc.build()
        res = mitigate_rfi(dirty, sc.sample_rate_hz, reference=reference,
                           prominence_db=float(params["prominence_db"]),
                           notch_bw_hz=params.get("notch_bw_hz"),
                           adaptive=bool(params.get("adaptive", False)),
                           mu=float(params.get("mu", 0.01)))
        before[sc.name] = float(res.snr_before_db)
        per[sc.name] = float(res.snr_after_db - res.snr_before_db)
    wall = time.perf_counter() - t0
    vals = list(per.values())
    return ScoreResult(mean_db=float(np.mean(vals)), min_db=float(np.min(vals)),
                       per_scenario=per, wall_s=wall, snr_before_db=before)


def baseline_report(scenarios: tuple[Scenario, ...] = DEFAULT_SCENARIOS) -> dict:
    """把"仓库默认参数"的读数做成基线 —— 演化必须相对它说明收益。"""
    from mcpserver.rf_brain.rfi_mitigation import mitigate_rfi

    out: dict[str, dict] = {}
    for sc in scenarios:
        reference, dirty = sc.build()
        res = mitigate_rfi(dirty, sc.sample_rate_hz, reference=reference)   # 全默认
        out[sc.name] = {
            "snr_before_db": round(float(res.snr_before_db), 4),
            "snr_after_db": round(float(res.snr_after_db), 4),
            "improvement_db": round(float(res.snr_after_db - res.snr_before_db), 4),
            "detected_freq_count": len(res.detected_freqs_hz),
        }
    return out
