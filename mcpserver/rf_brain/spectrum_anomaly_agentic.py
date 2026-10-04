"""射频大脑 · Agentic 主动学习频谱异常筛选（R49）

授粉自 digest-g6-2b-2026-08-30.md 授粉点 1（来源 2608.23688）：把「隔离森林
排序 → 多模态 LLM agent 迭代评审 → 共识过滤」的 Agentic 主动学习 pipeline 迁移
到 SDR/射电频谱异常检测，解决「射电干扰 / 智能干扰 / 未知信号类型需人工判读、
无法规模化」的痛点。

管线（纯 numpy，无 sklearn / 无 LLM 硬依赖，可离线单元测试）：

  1. embed_spectrum    频谱（dB 或线性功率）→ 归一化 + 降采样嵌入向量，
                       形状与强度联合表征，作为隔离森林的输入特征。
  2. IsolationForest    纯 numpy 隔离森林：随机切分树 → 平均路径长度 →
                       异常分（分数越高越异常）。与 sklearn 语义一致，但零依赖。
  3. RuleReviewer       确定性规则评审（噪声/平坦度/能量/多峰），给每个候选
                       标注 + 共识过滤，过滤「确定正常」的窗口。
  4. screen_candidates  隔离森林排序 → 规则评审 → 共识过滤 → 输出候选列表，
                       供下游 Agent（LLM 深度分析）只处理 top-K，而非全量。

对比口径：全量扫描 = 对每个窗口都做一次深度分析（开销 O(N)）；本管线把昂贵的
Agent 深度分析收敛到 top-K（K = ceil(N / target_reduction)），确定性阶段（嵌入 +
隔离森林）本身廉价，筛选量降 ≥10×。LLM 评审是可选挂钩：传 ``reviewer`` 可换成
多模态 Agent 共识，缺省降级为 RuleReviewer（不崩、不依赖外部服务）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# 平均路径长度校正里的欧拉常数（隔离森林 c(n) 公式用）
_EULER = 0.5772156649015329

# 规则评审标签（共识过滤/标注用）
RULE_NOISE = "noise_floor"      # 平坦/近底噪 → 判定正常，过滤
RULE_EMPTY = "empty"            # 全零/常数 → 无信息，过滤
RULE_MULTIPEAK = "multipeak"    # 多显著峰 → 可疑，标注保留
RULE_WIDEBAND = "wideband"      # 带宽异常宽 → 可疑，标注保留


# ---------------------------------------------------------------------------
# 嵌入
# ---------------------------------------------------------------------------
def _downsample(values: np.ndarray, target: int) -> np.ndarray:
    """分块均值降采样（与 spectrum.downsample 同语义，此处内联避免循环依赖）。"""
    values = np.asarray(values, dtype=float)
    n = values.size
    if n == 0:
        return np.zeros(0, dtype=float)
    if n <= target:
        return values.copy()
    edges = np.linspace(0, n, target + 1)
    out = np.empty(target, dtype=float)
    for i in range(target):
        lo, hi = int(edges[i]), int(edges[i + 1])
        out[i] = values[lo:hi].mean() if hi > lo else values[min(lo, n - 1)]
    return out


def embed_spectrum(spectrum: np.ndarray, n_bins: int = 48) -> np.ndarray:
    """单帧频谱 → 归一化嵌入向量（形状 + 强度联合表征，长度 = n_bins）。

    归一化到 [0,1]：异常检测关心「形状异常」而非绝对强度，去量纲后同强度下
    不同形状可比较；平坦/常数谱（max==min）返回全零，交由规则评审兜底过滤。
    """
    x = np.asarray(spectrum, dtype=float)
    if x.ndim != 1 or x.size == 0:
        raise ValueError("spectrum 必须为非空一维数组")
    x = _downsample(x, n_bins)
    span = float(x.max() - x.min())
    if span <= 1e-12:
        return np.zeros(n_bins, dtype=float)
    return (x - float(x.min())) / span


def embed_spectra(spectra: list[np.ndarray] | np.ndarray, n_bins: int = 48) -> np.ndarray:
    """批量嵌入：N 帧 → (N, n_bins) 特征矩阵。"""
    if isinstance(spectra, np.ndarray) and spectra.ndim == 2:
        return np.stack([embed_spectrum(row, n_bins) for row in spectra])
    return np.stack([embed_spectrum(s, n_bins) for s in spectra])


# ---------------------------------------------------------------------------
# 纯 numpy 隔离森林
# ---------------------------------------------------------------------------
def _c_factor(n: int) -> float:
    """隔离森林平均路径长度校正 c(n) = 2H(n-1) - 2(n-1)/n（H 为调和数）。"""
    if n <= 1:
        return 0.0
    h = math.log(n - 1) + _EULER
    return 2.0 * h - 2.0 * (n - 1) / n


class IsolationForest:
    """纯 numpy 隔离森林（随机切分树 → 平均路径长度 → 异常分）。

    与 sklearn.ensemble.IsolationForest 语义一致：异常点路径短 → 分数 → 1，
    正常点路径长 → 分数 → 0。零第三方依赖，便于离线单元测试与边缘侧移植。
    """

    def __init__(self, n_estimators: int = 100, max_samples: int = 256,
                 seed: int | None = None) -> None:
        if n_estimators < 1:
            raise ValueError("n_estimators 必须 >= 1")
        if max_samples < 2:
            raise ValueError("max_samples 必须 >= 2")
        self.n_estimators = int(n_estimators)
        self.max_samples = int(max_samples)
        self.seed = seed
        self._trees: list[tuple] = []
        self._sample_size = 0
        self._depth_limit = 0

    def fit(self, X: np.ndarray) -> "IsolationForest":
        """训练：为每棵树从 X 采样 build 随机切分树（纯列表结构，无对象开销）。"""
        X = np.asarray(X, dtype=float)
        if X.ndim != 2 or X.shape[0] == 0:
            raise ValueError("X 必须为 (n_samples, n_features) 非空矩阵")
        n = X.shape[0]
        self._sample_size = min(self.max_samples, n)
        self._depth_limit = int(math.ceil(math.log2(max(2, self._sample_size))))
        rng = np.random.default_rng(self.seed)
        self._trees = [
            self._build_tree(X, rng, depth=0)
            for _ in range(self.n_estimators)
        ]
        return self

    def _build_tree(self, X: np.ndarray, rng: np.random.Generator, depth: int) -> tuple:
        """递归切分：节点 = (feature, split, left, right, size)；叶子 (None,None,None,None,size)。"""
        n = X.shape[0]
        if depth >= self._depth_limit or n <= 1:
            return (None, None, None, None, n)

        # 选一个有变异的特征（避免在常数特征上切出空孩子）
        ranges = X.max(axis=0) - X.min(axis=0)
        cand = np.where(ranges > 1e-12)[0]
        if cand.size == 0:
            return (None, None, None, None, n)
        q = int(cand[rng.integers(0, cand.size)])
        col = X[:, q]
        p = float(rng.uniform(col.min(), col.max()))
        left_mask = col < p
        if bool(left_mask.all()) or bool((~left_mask).all()):
            return (None, None, None, None, n)
        left = self._build_tree(X[left_mask], rng, depth + 1)
        right = self._build_tree(X[~left_mask], rng, depth + 1)
        return (int(q), p, left, right, n)

    def anomaly_scores(self, X: np.ndarray) -> np.ndarray:
        """异常分：2^(-E[h(x)] / c(n))，越接近 1 越异常。

        路径长度按树批量向量化：每棵树一次性算完所有样本的路径（`_path_lengths`），
        替代逐样本 Python 内层循环——N 样本 × T 树规模下显著更快，契合「高效筛选」。
        """
        X = np.asarray(X, dtype=float)
        if not self._trees:
            raise RuntimeError("IsolationForest 尚未 fit")
        c = _c_factor(self._sample_size)
        if c <= 0.0:
            return np.zeros(X.shape[0], dtype=float)
        depth_sum = np.zeros(X.shape[0], dtype=float)
        for tree in self._trees:
            depth_sum += self._path_lengths(X, tree)
        avg = depth_sum / len(self._trees)
        return np.power(2.0, -(avg / c))

    @staticmethod
    def _path_lengths(X: np.ndarray, tree: tuple) -> np.ndarray:
        """批量路径长度：返回 X 每行在该树上的路径长度（与逐样本遍历逐位等价）。

        递归按节点把样本集按切分方向二分，用 numpy 布尔索引同时推进所有样本，
        每层一次向量化比较——O(depth) 层，替代 O(样本数) 次 Python 调用。
        """
        n = X.shape[0]
        lengths = np.zeros(n, dtype=float)

        def visit(node: tuple, rows: np.ndarray, edges: int) -> None:
            q, p, left, right, size = node
            if q is None:  # 叶子：补 c(size) 校正（size>1）
                lengths[rows] = edges + (_c_factor(size) if size > 1 else 0.0)
                return
            col = X[rows, q]
            left_rows = rows[col < p]
            right_rows = rows[col >= p]
            if left_rows.size:
                visit(left, left_rows, edges + 1)
            if right_rows.size:
                visit(right, right_rows, edges + 1)

        visit(tree, np.arange(n), 0)
        return lengths


# ---------------------------------------------------------------------------
# 规则评审（LLM 评审的可降级替身）
# ---------------------------------------------------------------------------
@dataclass
class ReviewVerdict:
    """规则评审结论：accepted=False 表示共识过滤掉（确定正常/无信息）。"""
    accepted: bool
    labels: list[str]


class RuleReviewer:
    """确定性规则评审：给候选窗口打标签并共识过滤「确定正常」的窗口。

    判据（保守，只过滤明显无信息/纯噪声，绝不误杀可疑形状）：
      - empty：全零或常数（无信息）→ 过滤
      - noise_floor：峰值过低（< -6dB 归一化）或频谱过平（flatness > 0.85）→ 过滤
      - multipeak：显著峰 >= 3 → 保留并标注（多载波/谐波类可疑）
      - wideband：主峰 -3dB 带宽占比 > 0.5 → 保留并标注（宽带/扫频类可疑）

    LLM 评审挂钩：继承本类并覆写 ``review`` 即可注入多模态 Agent 共识（如
    频谱图 + 时频图联合评审），共识过滤逻辑不变——「任一确定正常」即过滤，
    与 2608.23688 的共识过滤语义对齐。
    """

    def __init__(self, flatness_threshold: float = 0.85) -> None:
        self.flatness_threshold = flatness_threshold

    def review(self, spectrum: np.ndarray) -> ReviewVerdict:
        x = np.asarray(spectrum, dtype=float)
        if x.ndim != 1 or x.size == 0:
            return ReviewVerdict(False, [RULE_EMPTY])
        span = float(x.max() - x.min())
        if span <= 1e-12:
            return ReviewVerdict(False, [RULE_EMPTY])

        # 频谱平坦度（Wiener 熵）：几何均值 / 算术均值，在非负功率谱上计算——
        # 平坦噪声底 → 1，集中信号 → →0。对负值（dB 谱）先平移为正，不改变相对起伏。
        pos = x if float(x.min()) >= 0.0 else (x - float(x.min()) + 1.0)
        flatness = float(np.exp(np.mean(np.log(pos + 1e-12))) / (np.mean(pos) + 1e-12))
        if flatness > self.flatness_threshold:
            return ReviewVerdict(False, [RULE_NOISE])

        labels: list[str] = []
        # 峰/带宽标注在归一化 [0,1] 谱上（相对主峰，与绝对强度无关）
        xn = (x - float(x.min())) / span
        above = xn > 0.5  # 主峰 -6dB 以内
        peaks = 0
        for i in range(1, len(xn) - 1):
            if above[i] and xn[i] >= xn[i - 1] and xn[i] >= xn[i + 1]:
                peaks += 1
        if peaks >= 3:
            labels.append(RULE_MULTIPEAK)
        if float((xn > 0.5).sum()) / len(xn) > 0.5:
            labels.append(RULE_WIDEBAND)
        return ReviewVerdict(True, labels)


# ---------------------------------------------------------------------------
# 管线：隔离森林排序 → 规则评审 → 共识过滤
# ---------------------------------------------------------------------------
@dataclass
class AnomalyCandidate:
    """候选异常窗口（供 Agent 深度分析）。"""
    index: int                 # 在原输入批中的下标
    score: float               # 隔离森林异常分（高=更异常）
    labels: list[str]          # 规则评审标签
    accepted: bool             # 共识过滤后是否保留


@dataclass
class ScreeningResult:
    """筛选结果 + 全量扫描对比口径。"""
    candidates: list[AnomalyCandidate]   # 按异常分降序，已共识过滤
    n_total: int                         # 全量窗口数（= 全量扫描要处理的量）
    n_candidates: int                    # 输出候选数（Agent 只需深度分析这些）
    reduction: float                     # 全量 / 候选（降幅倍率，≥ target）
    scores: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=float))


def screen_candidates(
    spectra: list[np.ndarray] | np.ndarray,
    *,
    n_bins: int = 48,
    target_reduction: float = 10.0,
    iforest: IsolationForest | None = None,
    reviewer: RuleReviewer | None = None,
    seed: int | None = None,
) -> ScreeningResult:
    """Agentic 主动学习候选筛选：隔离森林排序 → 规则评审 → 共识过滤 → top-K。

    参数:
        spectra:          N 帧频谱（每帧 1D 数组）或 (N, n_bins) 矩阵。
        n_bins:           嵌入维度。
        target_reduction: 目标降幅（全量 / 候选 ≥ 该值）。K = ceil(N / target)。
        iforest:          预训练隔离森林；缺省按 seed 现训。
        reviewer:         规则评审器（可换 LLM 多模态 Agent 共识）；缺省 RuleReviewer。
        seed:             隔离森林随机种子（可复现）。

    返回:
        ScreeningResult：candidates 按异常分降序、共识过滤后至多 K 个；reduction ≥ target。
    """
    if isinstance(spectra, np.ndarray) and spectra.ndim == 2:
        n_total = spectra.shape[0]
    else:
        n_total = len(spectra)
    if n_total == 0:
        raise ValueError("spectra 不能为空")
    if target_reduction <= 0:
        raise ValueError("target_reduction 必须 > 0")

    X = embed_spectra(spectra, n_bins)
    forest = iforest if iforest is not None else IsolationForest(seed=seed)
    if not getattr(forest, "_trees", None):
        forest.fit(X)
    scores = np.asarray(forest.anomaly_scores(X), dtype=float)

    rev = reviewer if reviewer is not None else RuleReviewer()
    # 向下取整：K = ⌊N / target⌋，保证 reduction = N / K ≥ target（≥10× 硬验收）。
    K = max(1, int(n_total / float(target_reduction)))

    order = np.argsort(-scores)  # 异常分降序
    candidates: list[AnomalyCandidate] = []
    for idx in order:
        raw = spectra[idx]  # list 与 2D ndarray 均支持整数下标取行
        verdict = rev.review(raw)
        if not verdict.accepted:
            continue  # 共识过滤：确定正常/无信息，不进候选
        candidates.append(AnomalyCandidate(
            index=int(idx),
            score=float(scores[idx]),
            labels=verdict.labels,
            accepted=True,
        ))
        if len(candidates) >= K:
            break
    return ScreeningResult(
        candidates=candidates,
        n_total=n_total,
        n_candidates=len(candidates),
        reduction=(n_total / max(1, len(candidates))),
        scores=scores,
    )


__all__ = [
    "embed_spectrum",
    "embed_spectra",
    "IsolationForest",
    "RuleReviewer",
    "ReviewVerdict",
    "AnomalyCandidate",
    "ScreeningResult",
    "screen_candidates",
    "RULE_NOISE",
    "RULE_EMPTY",
    "RULE_MULTIPEAK",
    "RULE_WIDEBAND",
]
