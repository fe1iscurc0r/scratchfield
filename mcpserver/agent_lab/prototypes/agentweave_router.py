"""A52 · AgentWeave Routing-Before-Reasoning 工具路由原型（来源 2608.23078）

论文核心：LLM 面对海量工具/函数/API 集合时，先路由（筛出小子集）再推理，
兼顾召回与成本。

原型（mock，显式标注）：
  - mock 工具集：8 域 × 25 个工具（模板词表生成描述，无真实数据）
  - 两级路由：TF-IDF 余弦 → 域质心粗筛 → 域内 top-k 细筛
评估：top-5 召回率 ≫ 随机基线；路由成本（候选数/总数）≪ 1。

运行：python -m mcpserver.agent_lab.prototypes.agentweave_router
"""
from __future__ import annotations

import re

import numpy as np

DOMAINS = ["日历", "邮件", "财务", "数据库", "文件", "网络", "图像", "翻译"]
DOMAIN_WORDS = {
    "日历": ["会议", "日程", "提醒", "日历"],
    "邮件": ["邮件", "发送", "收件箱", "附件"],
    "财务": ["发票", "报销", "预算", "账目"],
    "数据库": ["查询", "表", "索引", "事务"],
    "文件": ["文件", "目录", "复制", "压缩"],
    "网络": ["请求", "接口", "网关", "协议"],
    "图像": ["图像", "裁剪", "滤镜", "水印"],
    "翻译": ["翻译", "语言", "术语", "语料"],
}
NOISE_WORDS = ["天气", "日志", "缓存", "配置"]  # 查询噪声词


def tokenize(text: str) -> list[str]:
    """中英文混合分词（原型简化）：英文按词，中文按单字"""
    toks = re.findall(r"[a-z0-9]+", text.lower())
    toks += [c for c in text if "\u4e00" <= c <= "\u9fff"]
    return toks


class TfIdf:
    """最小 TF-IDF 向量化器（numpy 实现，无外部依赖）"""

    def __init__(self, docs: list[str]):
        self.vocab: dict[str, int] = {}
        for doc in docs:
            for w in tokenize(doc):
                self.vocab.setdefault(w, len(self.vocab))
        n, v = len(docs), len(self.vocab)
        m = np.zeros((n, v))
        for i, doc in enumerate(docs):
            for w in tokenize(doc):
                m[i, self.vocab[w]] += 1.0
        df = (m > 0).sum(axis=0)
        self.idf = np.log((1.0 + n) / (1.0 + df)) + 1.0
        self.docs = self._norm(m * self.idf)

    @staticmethod
    def _norm(m: np.ndarray) -> np.ndarray:
        return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)

    def encode(self, text: str) -> np.ndarray:
        v = np.zeros(len(self.vocab))
        for w in tokenize(text):
            if w in self.vocab:
                v[self.vocab[w]] += 1.0
        v = v * self.idf
        return v / (np.linalg.norm(v) + 1e-9)


def make_toolset(per_domain: int = 25, seed: int = 2) -> list[dict]:
    """mock 工具集：每域 per_domain 个，描述为域词表随机组合"""
    rng = np.random.default_rng(seed)
    tools = []
    for d in DOMAINS:
        for i in range(per_domain):
            words = [str(w) for w in rng.choice(DOMAIN_WORDS[d], size=3, replace=True)]
            tools.append(dict(name=f"{d}_{i}", domain=d, desc=" ".join(words)))
    return tools


class AgentWeaveRouter:
    """两级路由：查询 → 域质心粗筛 → 域内 top-k"""

    def __init__(self, tools: list[dict]):
        self.tools = tools
        self.vec = TfIdf([t["desc"] for t in tools])
        self.centroids: dict[str, np.ndarray] = {}
        for d in DOMAINS:
            idx = [i for i, t in enumerate(tools) if t["domain"] == d]
            c = self.vec.docs[idx].mean(axis=0)
            self.centroids[d] = c / (np.linalg.norm(c) + 1e-9)

    def route(self, query: str, k: int = 5) -> tuple[list[str], str]:
        qv = self.vec.encode(query)
        dom = max(self.centroids, key=lambda d: float(qv @ self.centroids[d]))
        idx = [i for i, t in enumerate(self.tools) if t["domain"] == dom]
        sims = self.vec.docs[idx] @ qv
        top = np.argsort(sims)[::-1][:k]
        return [self.tools[idx[int(j)]]["name"] for j in top], dom


def evaluate(seed: int = 2, per_domain: int = 25, n_queries: int = 80, k: int = 5) -> dict:
    """评测：查询 = 目标工具描述 + 噪声词；统计 top-k 召回与路由成本"""
    tools = make_toolset(per_domain, seed)
    router = AgentWeaveRouter(tools)
    rng = np.random.default_rng(seed + 1)
    by_name = {t["name"]: t for t in tools}
    hit, dom_hit = 0, 0
    for _ in range(n_queries):
        d = DOMAINS[int(rng.integers(len(DOMAINS)))]
        target = f"{d}_{int(rng.integers(per_domain))}"
        noise = [str(w) for w in rng.choice(NOISE_WORDS, size=2)]
        query = by_name[target]["desc"] + " " + " ".join(noise)
        names, dom = router.route(query, k)
        hit += target in names
        dom_hit += dom == d
    recall = hit / n_queries
    return dict(
        recall_at_k=recall,
        domain_accuracy=dom_hit / n_queries,
        random_baseline=min(1.0, k / len(tools)),
        cost_ratio=k / len(tools),
    )


if __name__ == "__main__":
    r = evaluate()
    print(f"AgentWeave 路由：recall@5={r['recall_at_k']:.3f}"
          f"（随机基线 {r['random_baseline']:.3f}），"
          f"域路由准确率={r['domain_accuracy']:.3f}，候选成本比={r['cost_ratio']:.3f}")
