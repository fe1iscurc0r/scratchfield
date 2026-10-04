"""授粉落地验收测试：LightRAG 图增强检索（lightrag_graph）。

覆盖：
  1. 实体抽取：英文词元 / 中文 n-gram / 停用词过滤 / 空输入
  2. 图构建：共现边正确、孤立节点统计、min_freq 噪声过滤
  3. 图检索：查询命中实体 → 多跳扩散返回关联（比单节点召回多）
  4. 确定性：同输入两次构建/检索一致
  5. 容错：空语料、无命中、非 ASCII 混合
"""
from __future__ import annotations

import numpy as np
import pytest

from mcpserver.rf_brain.lightrag_graph import (
    EntityGraph,
    build_graph,
    extract_entities,
    query_graph,
)

CHUNKS = [
    ("c1", "射频信号处理使用 FFT 计算频谱，SDR 接收机依赖频谱分析。"),
    ("c2", "SDR 接收机可解调 AM FM 信号，LoRa 调制用于远距离低功耗。"),
    ("c3", "LoRa 网络适合物联网传感器，ESP32 常作为 LoRa 节点主控。"),
    ("c4", "ESP32 开发板集成 WiFi 蓝牙，常用于嵌入式边缘设备。"),
    ("c5", "天线设计影响通信距离，匹配网络决定阻抗匹配质量。"),
]


class TestEntityExtraction:
    def test_english_tokens(self):
        ents = extract_entities("SDR and LoRa for ESP32")
        assert "SDR" in ents and "LoRa" in ents and "ESP32" in ents

    def test_stopwords_filtered(self):
        ents = extract_entities("the and for with this that")
        assert not ents

    def test_chinese_ngrams(self):
        ents = extract_entities("射频信号处理")
        assert any("射频" in e for e in ents)

    def test_empty_input(self):
        assert extract_entities("") == []
        assert extract_entities(None) == []

    def test_deterministic(self):
        a = extract_entities("SDR 解调 LoRa 频谱")
        b = extract_entities("SDR 解调 LoRa 频谱")
        assert a == b


class TestGraphBuild:
    def test_nodes_and_edges(self):
        g = build_graph(CHUNKS)
        assert "SDR" in g.nodes
        assert "LoRa" in g.nodes
        assert g.edge_count > 0

    def test_cooccurrence_edge(self):
        # c2 中 SDR 与 LoRa 共现 → 应有边
        g = build_graph(CHUNKS)
        assert "LoRa" in g.adj.get("SDR", {})

    def test_min_freq_filters_noise(self):
        # 低 min_freq 保留更多；高 min_freq 只留跨 chunk 稳定词
        g_low = build_graph(CHUNKS, min_freq=1)
        g_high = build_graph(CHUNKS, min_freq=3)
        assert len(g_high.nodes) <= len(g_low.nodes)

    def test_isolated_nodes(self):
        # 两个互不相干 chunk → 孤立节点出现
        g = build_graph([("a", "SDR 解调 频谱"), ("b", "天线 匹配 阻抗")])
        assert g.isolated_count > 0

    def test_deterministic_build(self):
        g1 = build_graph(CHUNKS)
        g2 = build_graph(CHUNKS)
        assert g1.nodes == g2.nodes


class TestGraphQuery:
    def test_query_hit_direct(self):
        g = build_graph(CHUNKS)
        ctx = query_graph(g, "SDR 解调")
        assert any(c["entity"] == "SDR" for c in ctx)

    def test_graph_diffusion_beyond_direct(self):
        # 查「FFT」应扩散到 SDR（同一分量），不止 FFT 自身
        g = build_graph(CHUNKS)
        ctx = query_graph(g, "FFT 频谱")
        entities = [c["entity"] for c in ctx]
        assert "FFT" in entities
        assert "SDR" in entities  # 图扩散拉取关联实体

    def test_diffusion_depth_effect(self):
        g = build_graph(CHUNKS)
        ctx_d1 = query_graph(g, "FFT", depth=1)
        ctx_d2 = query_graph(g, "FFT", depth=3)
        # 更深度数应召回更多关联（非严格，至少不回退）
        assert len(ctx_d2) >= len(ctx_d1)

    def test_no_hit_returns_empty(self):
        g = build_graph(CHUNKS)
        assert query_graph(g, "量子计算 不存在") == []

    def test_context_has_text(self):
        g = build_graph(CHUNKS)
        ctx = query_graph(g, "SDR")
        assert ctx and all(c["text"] for c in ctx)

    def test_empty_graph(self):
        g = EntityGraph()
        assert query_graph(g, "anything") == []


class TestIntegration:
    def test_connected_component_recall(self):
        """图增强检索应召回跨 chunk 的结构相关（LightRAG 核心价值）。"""
        g = build_graph(CHUNKS)
        ctx = query_graph(g, "LoRa 网络")
        entities = {c["entity"] for c in ctx}
        # LoRa 通过图扩散应连带 ESP32 / SDR（同分量）
        assert "LoRa" in entities
        assert len(entities) >= 3

    def test_scoring_priority(self):
        """直接命中实体应排在最前（命中权重 2.0 > 多跳 1/d）。"""
        g = build_graph(CHUNKS)
        ctx = query_graph(g, "SDR 解调")
        assert ctx[0]["entity"] == "SDR"
        assert ctx[0]["score"] >= ctx[-1]["score"]
