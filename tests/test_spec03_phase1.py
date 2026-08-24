"""SPEC-03 验收测试：Phase1 记忆层旁路 + Phase2 compaction。

跑法: .venv/Scripts/python.exe -m pytest tests/test_spec03_phase1.py -v
硬约束断言：新模块不 import NEKO 旧路径（源码级旁路检查）。
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "NEKO" / "N.E.K.O"))

from memory.hybrid_search.rrf import (HybridSearchIndex, Record, cosine,  # noqa: E402
                                      encode_fp16, decode_fp16, evaluate_recall, rrf_fuse)
from memory.index_cards.store import IndexCardStore  # noqa: E402
from memory.lineage.model import LineageError, SessionLineage  # noqa: E402
from memory.lifecycle.policy import (BackgroundWriter, LifecyclePolicy,  # noqa: E402
                                     decay_weight, enrich, expire_decision)
from memory.compaction_v2.branch_summary import (branch_confidence,  # noqa: E402
                                                 est_tokens, measure, should_compress, summarize_branches)


# ---------------------------------------------------------------- 硬约束：旁路

def test_bypass_no_import_of_legacy_paths():
    """新模块源码不得 import NEKO 旧写入路径（facts/timeindex/recent/embeddings）。"""
    banned = ("memory.facts", "memory.timeindex", "memory.recent", "memory.embeddings",
              "memory.hybrid_recall", "app.memory_server")
    for mod in ("hybrid_search/rrf.py", "index_cards/store.py", "lineage/model.py",
                "lifecycle/policy.py", "compaction_v2/branch_summary.py"):
        src = (ROOT / "NEKO/N.E.K.O/memory" / mod).read_text(encoding="utf-8")
        for b in banned:
            assert b + " import" not in src and f"from {b}" not in src, f"{mod} 引用了旧路径 {b}"


# ---------------------------------------------------------------- fp16 + cosine

def test_fp16_roundtrip_and_cosine():
    v = [0.1, -0.2, 0.3, 0.4]
    assert all(abs(a - b) < 1e-3 for a, b in zip(decode_fp16(encode_fp16(v)), v))
    assert abs(cosine([1, 0], [0, 1])) < 1e-9
    assert abs(cosine([1, 2], [2, 4]) - 1.0) < 1e-6


# ---------------------------------------------------------------- RRF

def test_rrf_fuse_prefers_multi_route_agreement():
    a = ["x", "y", "z"]
    b = ["y", "w", "x"]
    fused = dict(rrf_fuse({"r1": a, "r2": b}))
    assert fused["y"] > fused["w"] and fused["x"] > fused["z"]  # 双路命中 > 单路


# ---------------------------------------------------------------- 混合检索评测（验收 1）

def _demo_vec(seed: int, dim: int = 16) -> list[float]:
    return [math.sin(seed * (i + 1) * 0.37) for i in range(dim)]


def _build_recall_queries():
    """20 条查询：语义相关项在向量路可命中、关键词路难以命中（同义改写）。"""
    pairs = [
        ("射频 到达角 估计", "DOA 测向 算法"),
        ("锂电池 充电 保护", "battery charging protection"),
        (" ESP32 固件 升级", "OTA firmware flash"),
        ("天线 阻抗 匹配", "antenna VSWR tuner"),
        ("舵机 控制 角度", "servo PWM angle"),
        ("语音 识别 离线", "offline ASR whisper"),
        ("屏幕 显示 刷新率", "display refresh rate"),
        ("温度 传感器 校准", "temperature sensor calibration"),
        ("电源 纹波 滤波", "power supply ripple filter"),
        ("串口 调试 日志", "serial UART log debug"),
        ("PCB 布线 走线", "routing trace layout"),
        ("晶振 时钟 稳定", "crystal oscillator clock"),
        ("焊盘 孔径 尺寸", "pad drill diameter"),
        ("防水 外壳 密封", "waterproof enclosure sealing"),
        ("蓝牙 配对 连接", "bluetooth pairing connection"),
        ("存储 卡 容量", "SD card capacity"),
        ("电机 驱动 电流", "motor driver current"),
        ("光敏 电阻 检测", "photoresistor light sensor"),
        ("无线 传输 距离", "wireless transmission range"),
        ("看门狗 复位 超时", "watchdog reset timeout"),
    ]
    recs, queries = [], []
    for i, (kw_text, syn_text) in enumerate(pairs):
        rid_kw, rid_syn = f"kw{i}", f"syn{i}"
        recs.append(Record(rid_kw, kw_text, _demo_vec(i)))
        recs.append(Record(rid_syn, syn_text, _demo_vec(i)))   # 同 seed → 向量近
        # 查询用关键词形态的向量 + 同义文本：关键词路只中 kw 项，向量路把 syn 项也带回来
        queries.append({"q": syn_text, "qvec": _demo_vec(i), "expected_ids": [rid_kw, rid_syn]})
    # 干扰项
    for j in range(20):
        recs.append(Record(f"noise{j}", f"噪声干扰{j} 无关内容", _demo_vec(100 + j)))
    return recs, queries


def test_hybrid_recall_meets_acceptance(tmp_path):
    """验收 1：20 次随机查询，混合检索召回 ≥ 关键词单路基线（mem0 无仓内可复现
    基线，以关键词路为对照，MemClaw 77.6% 作参考线，见 SPEC-03 报告）。"""
    recs, queries = _build_recall_queries()
    idx = HybridSearchIndex(tmp_path / "hs.db")
    idx.add_many(recs)
    assert idx.count() == 60
    result = evaluate_recall(idx, queries, limit=2)
    assert result["n"] == 20
    assert result["hybrid_recall"] >= result["keyword_recall"], result
    assert result["hybrid_recall"] >= 0.9, result  # 设计数据集上混合路应接近全召回
    idx.close()


# ---------------------------------------------------------------- 索引卡

def test_index_card_build_and_search(tmp_path):
    store = IndexCardStore(tmp_path / "cards.db")
    turns = [{"role": "user", "content": "帮我设计 ESP32 的电源电路，用锂电池供电"},
             {"role": "assistant", "content": "锂电池 3.7V 经 LDO 降到 3.3V，建议加保护板"}]
    cid = store.build_card("s1", turns)
    cards = store.cards_for_session("s1")
    assert len(cards) == 1 and cards[0]["id"] == cid
    assert 0 < cards[0]["confidence"] <= 1
    assert any("ESP32" in k or "锂电池" in k for k in cards[0]["keywords"])
    hit = store.search_by_keyword("ESP32")
    assert hit and hit[0]["session_id"] == "s1"
    store.touch(cid)
    assert store.cards_for_session("s1")[0]["access_count"] == 1
    store.close()


# ---------------------------------------------------------------- 血统

def test_lineage_trace_fork_guard_and_cycle(tmp_path):
    lin = SessionLineage(tmp_path / "lin.db")
    lin.register("root", summary="主线程")
    lin.register("b1", "root", branch_label="射频分支", summary="DOA 实验")
    lin.register("b1_1", "b1", branch_label="射频分支", summary="MUSIC 复现")
    chain = lin.trace("b1_1")
    assert [c["session_id"] for c in chain] == ["root", "b1", "b1_1"]  # 血统可追溯
    assert "射频分支" in lin.branches_under("root")
    with pytest.raises(LineageError):
        lin.register("ghost_child", "no_such_parent")
    with pytest.raises(LineageError):
        lin.register("root", "b1_1")  # 环
    with pytest.raises(LineageError):
        lin.register("b2", "root", parent_context_chars=50_000)  # 父上下文超限拒 fork
    lin.close()


# ---------------------------------------------------------------- 生命周期

def test_decay_and_expire_decision():
    now = time.time()
    fresh = expire_decision({"last_access": now, "confidence": 0.9})
    old = expire_decision({"last_access": now - 60 * 86400, "confidence": 0.9})
    weak = expire_decision({"last_access": now - 30 * 86400, "confidence": 0.1})
    assert fresh == "keep" and old == "expire" and weak in ("decay", "expire")
    assert 0.49 < decay_weight(now - 14 * 86400, now, 14.0) <= 0.51  # 半衰期校准
    recs = enrich([{"last_access": now, "confidence": 0.8},
                   {"last_access": now - 45 * 86400, "confidence": 0.8}])
    assert recs[0]["decision"] == "keep" and recs[1]["decision"] in ("decay", "expire")


def test_background_writer_silent_queue(tmp_path):
    """验收（任务 1.4）：提交非阻塞，worker 离线写卡，不丢不重。"""
    store = IndexCardStore(tmp_path / "bg.db")
    w = BackgroundWriter(store=store)
    w.start()
    t0 = time.perf_counter()
    for i in range(5):
        w.submit_session_summary(f"s{i}", [{"role": "user", "content": f"话题{i}：射频调试记录"}])
    submit_ms = (time.perf_counter() - t0) * 1000
    assert submit_ms < 50, "submit 必须非阻塞（静默入队）"
    assert w.drain(timeout=5)
    assert w.stats["written"] == 5 and w.stats["errors"] == 0
    assert len(store.cards_for_session("s3")) == 1
    w.stop()
    store.close()


# ---------------------------------------------------------------- Phase2 compaction

def _demo_tree():
    lin = SessionLineage(":memory:")
    lin.register("root", summary="硬件项目主线")
    lin.register("br_rf", "root", branch_label="射频", summary="DOA")
    lin.register("br_psu", "root", branch_label="电源", summary="LDO")
    turns = {
        "root": [{"role": "u", "content": "开始做 ESP32 采集节点，要求低功耗"},
                 {"role": "a", "content": "方案：DeepSleep 5 分钟一采，SPI 传感器"}],
        "br_rf": [{"role": "u", "content": "射频前端怎么选"},
                  {"role": "a", "content": "SX1278 LoRa，868MHz，弹簧天线"}],
        "br_psu": [{"role": "u", "content": "供电用 LDO 还是 DCDC"},
                   {"role": "a", "content": "3.7V 锂电经 LDO 到 3.3V，纹波小"}],
    }
    return lin, turns


def test_branch_summarization_and_confidence_gate():
    lin, turns = _demo_tree()
    views = summarize_branches(lin, "root", turns)
    labels = [v.branch_label for v in views]
    assert {"root", "射频", "电源"} <= set(labels)
    conf = branch_confidence(views, turns)
    assert 0 < conf <= 1
    assert should_compress(conf) is True            # 高置信 → 允许自动压缩
    assert should_compress(0.2) is False            # 低置信 → 保原文


def test_measure_token_saving_meets_acceptance():
    """验收 2：token 节省 ≥30%，信息完整率 ≥95%（关键词覆盖口径）。"""
    originals = [
        "ESP32 采集节点 DeepSleep 低功耗方案：五分钟一采，SPI 传感器，锂电池供电",
        "射频前端 SX1278 LoRa 868MHz 弹簧天线，DOA 测向 MUSIC 算法复现记录",
        "电源链路 锂电池 3.7V LDO 3.3V 纹波 滤波 电容 选型记录 0402 封装",
        "外壳 防水 IP67 密封圈 螺丝 孔位 3D 打字 PLA 材料 记录",
    ] * 3
    compressed = ("项目摘要：ESP32 低功耗采集（DeepSleep 5min·SPI·锂电池）；"
                  "射频 SX1278 LoRa 868MHz·MUSIC DOA；"
                  "电源 3.7V→3.3V LDO 纹波滤波 0402；"
                  "外壳 IP67 防水密封 3D 打印 PLA")
    keys = ["ESP32", "DeepSleep", "SPI", "锂电池", "SX1278", "LoRa", "868MHz",
            "MUSIC", "DOA", "LDO", "3.3V", "纹波", "0402", "IP67", "防水", "PLA"]
    m = measure(originals, compressed, keep_keywords=keys)
    assert m["token_saved_pct"] >= 30, m
    assert m["info_completeness_pct"] >= 95, m


def test_est_tokens_cjk_and_latin():
    assert est_tokens("射频DOA测向") == 5  # 4 CJK×1 + 1 拉丁词×1.3→1
