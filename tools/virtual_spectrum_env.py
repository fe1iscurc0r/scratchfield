"""R46 虚拟频谱环境生成器（AgentMercury 授粉 · 环境构建可学习 → 零成本 RF 仿真数据）

来源授粉点：AgentMercury（2608.x）——"环境构建可学习"（3.3%→83.3% 成功率）。
迁移到 rf_brain：用 RF 传播模型（自由空间 / 双线地面反射）+ 随机干扰事件生成
**带标注**的合成频谱，供 SDR 感知 Agent 训练，实现零成本数据采集。

生成现象三件套（验收要求）：
  - 干扰 interference  随机激活的窄带/宽带干扰源（突发）
  - 空洞 hole          无信号、无干扰的可用空白频段（白空间）
  - 跳变 hop           跳频信号源，中心频率随帧迁移

每个输出帧都带逐 bin 标注（noise / signal / interference / hole），标注完整。
纯 numpy 实现，无硬件依赖，可离线单元测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

_C = 3.0e8  # 光速 m/s
_LABELS = ("noise", "signal", "interference", "hole")


@dataclass
class Emitter:
    """一个射频发射源（信号源或干扰源）。"""

    kind: str                       # "signal" | "jammer"
    center_hz: float
    bandwidth_hz: float
    power_dbm: float                # EIRP (dBm)
    distance_m: float = 500.0       # 到接收机（原点）的距离
    hop_pattern: Sequence[float] | None = None  # 跳频中心序列，None = 固定频点
    id: int = 0

    def current_center(self, t: int) -> float:
        if self.hop_pattern:
            return float(self.hop_pattern[int(t) % len(self.hop_pattern)])
        return self.center_hz


@dataclass
class SpectrumFrame:
    """一帧带标注的合成频谱。"""

    t: int
    freqs_hz: np.ndarray
    psd_dbm: np.ndarray          # 逐 bin 功率 (dBm)
    labels: np.ndarray           # 逐 bin 标注（str）

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for lab in _LABELS:
            out[lab] = int(np.count_nonzero(self.labels == lab))
        return out


@dataclass
class VirtualSpectrumEnv:
    """虚拟频谱环境生成器。"""

    freqs_hz: np.ndarray
    noise_floor_dbm: float = -100.0
    rx_height_m: float = 1.5
    tx_height_m: float = 10.0
    seed: int | None = None
    jammer_active_prob: float = 0.7   # 干扰源每帧激活概率（随机突发）
    emitters: list[Emitter] = field(default_factory=list)
    hole_bands: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.freqs_hz = np.asarray(self.freqs_hz, dtype=float)
        if self.freqs_hz.ndim != 1 or self.freqs_hz.size == 0:
            raise ValueError("freqs_hz 必须是非空一维数组")
        if not 0.0 <= self.jammer_active_prob <= 1.0:
            raise ValueError(f"jammer_active_prob 需在 [0,1]，实际 {self.jammer_active_prob}")
        self._rng = np.random.default_rng(self.seed)
        self._emit_id = 0

    def reseed(self, seed: int | None) -> None:
        """重设随机种子（复现同一批数据集用）。"""
        self.seed = seed
        self._rng = np.random.default_rng(seed)

    # ---------- 传播模型 ----------

    def path_loss_db(self, distance_m: float, freq_hz: float, model: str = "free_space") -> float:
        """路径损耗 (dB)。free_space 或 two_ray（双线地面反射）。"""
        d = max(float(distance_m), 1.0)
        f = max(float(freq_hz), 1.0)
        if model == "free_space":
            # Friis: PL = 20log10(4π d f / c)
            return 20.0 * np.log10(4.0 * np.pi * d * f / _C)
        if model == "two_ray":
            # 双线地面反射近似：PL ≈ 40log10(d) - 20log10(ht) - 20log10(hr)
            return 40.0 * np.log10(d) - 20.0 * np.log10(self.tx_height_m) - 20.0 * np.log10(self.rx_height_m)
        raise ValueError(f"未知传播模型 {model!r}，可选: free_space / two_ray")

    def add_emitter(
        self,
        kind: str,
        center_hz: float,
        bandwidth_hz: float,
        power_dbm: float,
        *,
        distance_m: float = 500.0,
        hop_pattern: Sequence[float] | None = None,
    ) -> Emitter:
        if kind not in ("signal", "jammer"):
            raise ValueError(f"kind 必须为 signal/jammer，实际 {kind!r}")
        em = Emitter(
            id=self._emit_id,
            kind=kind,
            center_hz=float(center_hz),
            bandwidth_hz=float(bandwidth_hz),
            power_dbm=float(power_dbm),
            distance_m=float(distance_m),
            hop_pattern=tuple(float(h) for h in hop_pattern) if hop_pattern else None,
        )
        self._emit_id += 1
        self.emitters.append(em)
        return em

    def add_hole(self, f_low_hz: float, f_high_hz: float) -> None:
        self.hole_bands.append((float(f_low_hz), float(f_high_hz)))

    # ---------- 帧生成 ----------

    def _emitter_shape(self, em: Emitter, center: float, model: str) -> np.ndarray:
        """单个发射源的功率贡献 (dBm)，按 bin 计算（含路径损耗）。"""
        rx = em.power_dbm - self.path_loss_db(em.distance_m, center, model)
        df = float(np.diff(self.freqs_hz).mean())
        sigma_hz = max(em.bandwidth_hz / 4.0, df)
        # 高斯谱形（窄带信号/干扰）；宽带干扰用更大的 bandwidth 自然铺开
        shape = rx + 10.0 * np.log10(np.exp(-((self.freqs_hz - center) ** 2) / (2 * sigma_hz**2)) + 1e-12)
        return shape

    def generate_frame(self, t: int, model: str = "free_space") -> SpectrumFrame:
        """生成第 t 帧频谱。"""
        psd_lin = 10.0 ** (self.noise_floor_dbm / 10.0) * np.ones_like(self.freqs_hz, dtype=float)
        active: list[tuple[Emitter, float]] = []
        for em in self.emitters:
            center = em.current_center(t)
            if em.kind == "jammer":
                # 随机干扰事件：按 jammer_active_prob 激活（突发），激活时随机抬升功率
                if self._rng.random() > self.jammer_active_prob:
                    continue
                center += self._rng.normal(0.0, em.bandwidth_hz / 4.0)
            active.append((em, center))
            shape_db = self._emitter_shape(em, center, model)
            psd_lin += 10.0 ** (shape_db / 10.0)

        psd_dbm = 10.0 * np.log10(psd_lin)

        # 逐 bin 标注
        labels = np.full(self.freqs_hz.size, "noise", dtype=object)
        # 先标空洞（无源占用、无干扰的可用白空间）
        for lo, hi in self.hole_bands:
            labels[(self.freqs_hz >= lo) & (self.freqs_hz < hi)] = "hole"
        # 干扰源覆盖优先级最高
        for em, center in active:
            if em.kind != "jammer":
                continue
            covered = np.abs(self.freqs_hz - center) <= em.bandwidth_hz / 2.0
            labels[covered] = "interference"
        # 信号源覆盖
        for em, center in active:
            if em.kind != "signal":
                continue
            covered = np.abs(self.freqs_hz - center) <= em.bandwidth_hz / 2.0
            labels[covered] = "signal"

        return SpectrumFrame(t=int(t), freqs_hz=self.freqs_hz.copy(), psd_dbm=psd_dbm, labels=labels)

    def generate_dataset(self, n_frames: int, model: str = "free_space") -> list[SpectrumFrame]:
        return [self.generate_frame(t, model=model) for t in range(int(n_frames))]


def demo_env(seed: int = 0) -> VirtualSpectrumEnv:
    """构造一个包含 信号/跳频信号/干扰/空洞 的演示环境（测试与样例共用）。"""
    freqs = np.linspace(430.0e6, 440.0e6, 2048)
    env = VirtualSpectrumEnv(freqs, noise_floor_dbm=-100.0, seed=seed)
    # 两个固定信号
    env.add_emitter("signal", 432.0e6, 200e3, 30.0, distance_m=800.0)
    env.add_emitter("signal", 436.0e6, 200e3, 30.0, distance_m=1200.0)
    # 一个跳频信号（3 个频点循环）
    env.add_emitter(
        "signal", 438.0e6, 200e3, 30.0, distance_m=900.0,
        hop_pattern=(438.0e6, 434.0e6, 439.5e6),
    )
    # 一个窄带干扰源（突发）
    env.add_emitter("jammer", 433.0e6, 150e3, 20.0, distance_m=600.0)
    # 两个空洞（白空间）
    env.add_hole(430.5e6, 431.0e6)
    env.add_hole(437.0e6, 437.5e6)
    return env
