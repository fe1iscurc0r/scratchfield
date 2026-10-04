"""卷125 W125-03 验收：端侧嵌入（本地可用 / 云端回退 / 缓存 / 检索一致性 / 节省估算）。

本地模型是真实 bge-small-zh-v1.5（仓库自带），所以「本地可用」这一条是真跑；
云端回退路径用桩（不真打外部 API）。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import pytest

from apiserver import local_embedder as le


class _EmbedderCfg:
    def __init__(self, **kw):
        self.mode = kw.get("mode", "auto")
        self.cache_size = kw.get("cache_size", 8)
        self.cloud_api_base = kw.get("cloud_api_base", "")
        self.cloud_api_key = kw.get("cloud_api_key", "")
        self.cloud_model = kw.get("cloud_model", "")


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    le.reset_for_tests()  # capacity 跟随 cfg（否则固定容量会压过测试里的 cache_size）
    yield
    le.reset_for_tests()


@pytest.fixture()
def cfg(monkeypatch):
    def _set(**kw):
        c = _EmbedderCfg(**kw)
        monkeypatch.setattr(le, "_cfg", lambda: c)
        return c

    return _set


# ---------------------------------------------------------------------------
# 本地路径
# ---------------------------------------------------------------------------


def test_local_embed_works_and_is_normalized(cfg):
    cfg(mode="local")
    vectors = le.embed(["材料的带隙计算", "band gap calculation", "今天天气不错"])
    assert vectors is not None and len(vectors) == 3
    assert all(len(v) > 0 for v in vectors)
    assert len({len(v) for v in vectors}) == 1, "同一批向量维度一致"
    norm = sum(float(x) * float(x) for x in vectors[0]) ** 0.5
    assert abs(norm - 1.0) < 1e-3, "bge 向量已归一化"

    stats = le.stats()
    assert stats["local_calls"] == 3 and stats["cloud_calls"] == 0
    assert stats["mode"] == "local" and stats["local_available"] is True


def test_similarity_consistency_chinese(cfg):
    """中文语义相似度抽样：相关句 > 无关句（本地向量质量 sanity check）。"""
    cfg(mode="local")
    base = le.embed_one("材料的带隙可以通过第一性原理计算")
    related = le.embed_one("用 DFT 算半导体带隙")
    unrelated = le.embed_one("今天午饭吃什么")
    assert base and related and unrelated
    sim_related = le.cosine(base, related)
    sim_unrelated = le.cosine(base, unrelated)
    assert sim_related > sim_unrelated, (sim_related, sim_unrelated)
    assert sim_related > 0.3, f"相关句相似度偏低：{sim_related}"


def test_embed_empty_and_single(cfg):
    cfg(mode="local")
    assert le.embed([]) == []
    assert le.embed_one("") is not None  # 空串也能编码（不炸）
    assert le.cosine(le.embed_one("a") or [], []) == 0.0

# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------


def test_cache_hit_avoids_recompute(cfg):
    cfg(mode="local", cache_size=4)
    first = le.embed(["重复的文本"])
    before = le.stats()["local_calls"]
    second = le.embed(["重复的文本"])
    after = le.stats()
    assert first == second, "缓存命中应返回同一向量"
    assert after["local_calls"] == before, "命中缓存不再调用本地编码"
    assert after["cache"]["hits"] >= 1

    le.embed(["重复的文本"], use_cache=False)
    assert le.stats()["local_calls"] == before + 1, "use_cache=False 走真实编码"


def test_cache_lru_eviction(cfg):
    cfg(mode="local", cache_size=2)
    for text in ("一", "二", "三"):
        le.embed([text])
    assert le.stats()["cache"]["size"] == 2, "超出容量淘汰最旧"
    assert le._cache.capacity == 2, "容量跟随配置"


def test_stats_and_saved_tokens_estimate(cfg):
    cfg(mode="local")
    le.embed(["一段中文文本用于估算"])
    stats = le.stats()
    assert stats["model"] == "BAAI/bge-small-zh-v1.5" and stats["dim"] > 0
    estimate = le.estimate_saved_tokens(["a" * 400, "b" * 600], cloud_price_per_1k=0.02)
    assert estimate["chars"] == 1000 and estimate["tokens_estimate"] == 250.0
    assert estimate["cloud_cost_estimate"] == 0.005
    assert "公式" in estimate["formula"] or "tokens" in estimate["formula"]


# ---------------------------------------------------------------------------
# 云端回退
# ---------------------------------------------------------------------------


def test_cloud_fallback_when_local_unavailable(cfg, monkeypatch):
    """本地不可用 → 自动回退云端（mode=auto）。"""
    cfg(mode="auto")
    monkeypatch.setattr(le, "_local_engine", lambda: None)  # 模拟本地模型缺失
    called: list[list[str]] = []

    def _fake_cloud(texts):
        called.append(list(texts))
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(le, "_cloud_embed", _fake_cloud)
    vectors = le.embed(["走云端"])
    assert vectors == [[0.1, 0.2, 0.3]]
    assert called == [["走云端"]]
    stats = le.stats()
    assert stats["fallbacks"] == 1 and stats["cloud_calls"] == 1


def test_mode_local_returns_none_when_unavailable(cfg, monkeypatch):
    cfg(mode="local")
    monkeypatch.setattr(le, "_local_engine", lambda: None)
    assert le.embed(["只有本地"]) is None, "mode=local 不静默走云端"


def test_both_unavailable_returns_none(cfg, monkeypatch):
    cfg(mode="auto")
    monkeypatch.setattr(le, "_local_engine", lambda: None)
    monkeypatch.setattr(le, "_cloud_embed", lambda texts: None)
    assert le.embed(["都不行"]) is None


def test_cloud_only_mode(cfg, monkeypatch):
    cfg(mode="cloud")
    monkeypatch.setattr(le, "_local_engine", lambda: (_ for _ in ()).throw(AssertionError("不该加载本地")))
    monkeypatch.setattr(le, "_cloud_embed", lambda texts: [[1.0] for _ in texts])
    assert le.embed(["x"]) == [[1.0]]


def test_cloud_config_resolution(monkeypatch):
    """云端配置解析：embedder 段优先，其次 embedding 段，再回退 api.*"""
    from system.config import get_config

    conf = le._cloud_config()
    assert set(conf) == {"api_base", "api_key", "model"}
    assert conf["model"], "至少有一个默认模型名"
    assert hasattr(get_config(), "embedder")
