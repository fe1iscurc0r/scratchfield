# -*- coding: utf-8 -*-
"""memory_eval_set 测试（W62-03 验收：评测集可运行且输出 recall/mrr）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from memory_eval_set import _build_cases, _build_entries, compute_metrics, keyword_retrieve, run_eval


def test_builds_30_entries_and_cases():
    assert len(_build_entries(30)) == 30
    assert len(_build_cases(30)) == 30


def test_keyword_retrieve_hits_expected():
    entries = _build_entries(30)
    # 查询 keyword-00 应命中 mem-00
    retrieved = keyword_retrieve("keyword-00", entries, top_k=5)
    assert "mem-00" in retrieved


def test_metrics_outputs_recall_and_mrr():
    m = run_eval()
    assert "recall_at_k" in m and "mrr" in m
    assert m["recall_at_k"] > 0.0
    assert 0.0 <= m["mrr"] <= 1.0


def test_keyword_retrieve_covers_type_project_dimension():
    # type/project 维度词也能召回（content 含 project/type）
    entries = _build_entries(30)
    retrieved = keyword_retrieve("rf decision 频谱感知", entries, top_k=10)
    assert len(retrieved) > 0
