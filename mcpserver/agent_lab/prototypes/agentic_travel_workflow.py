"""A40 · Agentic Travel Behavior 三 Agent 工作流原型（来源 2608.20320）

论文核心：三 Agent 工作流整合「对话数据采集 + 结构化处理 + 行为预测」，
多模态 LLM 预测超越随机森林。

原型（简化替代，显式标注）：
  - 采集Agent：mock 旅行对话语料（模板词表生成，无真实数据）
  - 结构化Agent：规则抽取（模式词计数 → 特征向量）
  - 预测Agent：softmax 多项逻辑回归（numpy）替代随机森林 / 多模态 LLM
评估：预测准确率 ≥ 多数类基线 + 显著增益。

运行：python -m mcpserver.agent_lab.prototypes.agentic_travel_workflow
"""
from __future__ import annotations

import re

import numpy as np

MODES = ["飞机", "高铁", "自驾", "步行"]

# 各出行方式的模式词表（mock 语料生成与结构化抽取共用）
MODE_LEXICON = {
    "飞机": ["航班", "登机", "机场", "托运", "值机"],
    "高铁": ["车次", "站台", "二等座", "12306", "轨交"],
    "自驾": ["高速", "堵车", "加油", "停车", "导航"],
    "步行": ["散步", "步行", "人行道", "共享单车", "脚程"],
}
DIST_WORDS = ["公里", "km", "里"]
TIME_WORDS = ["小时", "分钟", "明早", "时刻"]
PRICE_WORDS = ["元", "票价", "费用"]


class CollectionAgent:
    """Agent 1 · 对话数据采集：生成 mock 多轮旅行对话（无真实数据，显式标注）"""

    def __init__(self, n_per_mode: int = 60, seed: int = 7):
        self.n_per_mode = n_per_mode
        self.seed = seed

    def collect(self) -> list[tuple[str, str]]:
        rng = np.random.default_rng(self.seed)
        dialogues: list[tuple[str, str]] = []
        aux = DIST_WORDS + TIME_WORDS + PRICE_WORDS
        for mode in MODES:
            lex = MODE_LEXICON[mode]
            for _ in range(self.n_per_mode):
                k = int(rng.integers(3, 6))  # 每段对话 3~5 个模式词
                words = [str(w) for w in rng.choice(lex, size=k, replace=True)]
                if rng.random() < 0.5:  # 混入距离/时间/价格噪声词
                    words.append(str(rng.choice(aux)))
                dialogues.append((" ".join(words), mode))
        rng.shuffle(dialogues)
        return dialogues


class StructuringAgent:
    """Agent 2 · 结构化处理：规则抽取，原始对话 → 数值特征向量"""

    def transform(self, text: str) -> np.ndarray:
        feats: list[float] = []
        for mode in MODES:
            for w in MODE_LEXICON[mode]:
                feats.append(float(len(re.findall(re.escape(w), text))))
        for lex in (DIST_WORDS, TIME_WORDS, PRICE_WORDS):
            feats.append(float(sum(len(re.findall(re.escape(w), text)) for w in lex)))
        return np.asarray(feats, dtype=float)

    @property
    def dim(self) -> int:
        return sum(len(v) for v in MODE_LEXICON.values()) + 3


class PredictorAgent:
    """Agent 3 · 行为预测：多项逻辑回归（numpy softmax 梯度下降）

    论文用随机森林/多模态 LLM，此处用线性模型替代（原型简化，足以验证工作流闭环）。
    """

    def __init__(self, dim: int, n_classes: int, lr: float = 0.5, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self.W = self.rng.standard_normal((dim, n_classes)) * 0.01
        self.lr = lr

    @staticmethod
    def _softmax(z: np.ndarray) -> np.ndarray:
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 300) -> "PredictorAgent":
        n = len(y)
        Y = np.zeros((n, len(MODES)))
        Y[np.arange(n), y] = 1.0
        for _ in range(epochs):
            p = self._softmax(X @ self.W)
            grad = X.T @ (p - Y) / n
            self.W -= self.lr * grad
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._softmax(X @ self.W).argmax(axis=1)


def evaluate(n_per_mode: int = 60, seed: int = 7) -> dict:
    """跑通三 Agent 闭环：采集 → 结构化 → 训练/评估，返回准确率与基线"""
    pairs = CollectionAgent(n_per_mode, seed).collect()
    struct = StructuringAgent()
    X = np.stack([struct.transform(t) for t, _ in pairs])
    y = np.array([MODES.index(m) for _, m in pairs])
    # 80/20 切分（固定种子可复现）
    rng = np.random.default_rng(seed + 1)
    idx = rng.permutation(len(y))
    cut = int(0.8 * len(idx))
    tr, te = idx[:cut], idx[cut:]
    model = PredictorAgent(X.shape[1], len(MODES), seed=seed).fit(X[tr], y[tr])
    acc = float((model.predict(X[te]) == y[te]).mean())
    majority = float((y[te] == np.bincount(y[tr]).argmax()).mean())
    return {"accuracy": acc, "majority_baseline": majority, "n_features": X.shape[1]}


if __name__ == "__main__":
    r = evaluate()
    print(f"三 Agent 旅行行为预测：准确率={r['accuracy']:.3f}"
          f"（多数类基线 {r['majority_baseline']:.3f}，特征维 {r['n_features']}）")
