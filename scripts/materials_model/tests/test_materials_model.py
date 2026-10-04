"""W-01 验收测试：特征构建 / 缺失处理 / 训练管线 / 预测结构 / 回写 / 坏数据降级。

运行：python -m pytest scripts/materials_model/tests/ -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.materials_model import data, sample_data, suggest, train, writeback
from scripts.materials_model import predict as predict_mod

# ============ 特征构建 ============


def test_feature_build_shape_and_names():
    records = sample_data.load_sample_records()
    mat = data.build_feature_matrix(records)
    assert mat["n_samples"] == len(records)
    assert mat["X"].shape == (len(records), len(mat["feature_names"]))
    assert set(mat["target_names"]) == set(data.TARGETS)
    assert set(mat["y"].keys()) == set(data.TARGETS)
    # 数值特征 + 前驱体 one-hot 均在特征名中
    assert "temperature" in mat["feature_names"]
    assert any(name.startswith("precursor=") for name in mat["feature_names"])


def test_encode_input_matches_feature_width():
    records = sample_data.load_sample_records()
    mat = data.build_feature_matrix(records)
    x = data.encode_input(
        {"temperature": 600, "time": 120, "heating_rate": 5, "precursor": "秸秆", "koh_ratio": 2},
        mat,
    )
    assert x.shape == (1, mat["X"].shape[1])


# ============ 缺失处理 ============


def test_missing_handling_impute_and_nan_target():
    records = [
        {"precursor": "木质素", "temperature": 600, "time": 120, "heating_rate": 5,
         "koh_ratio": 2, "yield_rate": 40, "surface_area": 800, "calorific_value": 22},
        {"precursor": "秸秆", "temperature": 700, "time": 90, "heating_rate": 10,
         "koh_ratio": None, "yield_rate": 35, "surface_area": 900, "calorific_value": 21},
        {"precursor": None, "temperature": None, "time": 100, "heating_rate": 8,
         "koh_ratio": 1, "yield_rate": None, "surface_area": 700, "calorific_value": 20},
    ]
    mat = data.build_feature_matrix(records)
    assert mat["imputed"]["koh_ratio"] == 1
    assert mat["imputed"]["temperature"] == 1
    # 缺失标签保留 NaN，训练时丢弃
    assert np.isnan(mat["y"]["yield_rate"][2])
    # 缺失前驱体归入 unknown
    assert "unknown" in mat["precursor_categories"]


# ============ 坏数据降级 ============


def test_bad_data_strict_raises_clear_error():
    bad = [{"precursor": "x", "temperature": "high", "time": 120, "heating_rate": 5,
            "yield_rate": 40, "surface_area": 800, "calorific_value": 22}]
    with pytest.raises(data.DataError) as exc:
        data.build_feature_matrix(bad, strict=True)
    assert "temperature" in str(exc.value)


def test_bad_data_lenient_degrades_to_impute():
    bad = [{"precursor": "x", "temperature": "high", "time": 120, "heating_rate": 5,
            "yield_rate": 40, "surface_area": 800, "calorific_value": 22}]
    mat = data.build_feature_matrix(bad, strict=False)
    assert mat["imputed"]["temperature"] == 1
    assert np.isfinite(mat["X"][0, 0])


def test_bad_json_raises_data_error():
    with pytest.raises(data.DataError):
        data.load_eln_records("{not-json")


# ============ 训练管线 ============


def test_train_pipeline_reports_metrics():
    records = sample_data.load_sample_records()
    mat = data.build_feature_matrix(records)
    r = train.train_and_report(mat["X"], mat["y"], "yield_rate", model_type="rf", sample_data=True)
    for key in ("r2", "mae", "rmse", "n_train", "n_test", "n_samples", "honest_label", "degraded"):
        assert key in r
    assert r["n_train"] + r["n_test"] == r["n_samples"]
    assert np.isfinite(r["r2"])
    assert "样例数据" in r["honest_label"]
    # sklearn 缺失时按设计降级为均值基线（degraded=True），否则为 False
    assert r["degraded"] is (not train._SKLEARN)


def test_train_bp_baseline_runs():
    records = sample_data.load_sample_records()
    mat = data.build_feature_matrix(records)
    r = train.train_and_report(mat["X"], mat["y"], "surface_area", model_type="bp", sample_data=True)
    assert np.isfinite(r["r2"])
    assert r["model_type"] == "bp"


# ============ 预测输出结构 ============


def test_predict_output_structure():
    res = predict_mod.predict(
        {"temperature": 600, "time": 120, "heating_rate": 5, "precursor": "秸秆", "koh_ratio": 2}
    )
    assert res["ok"] is True
    assert {p["target"] for p in res["predictions"]} == set(data.TARGETS)
    for p in res["predictions"]:
        assert p["kind"] == "预测值"
        assert "value" in p and "unit" in p
        assert isinstance(p["value"], float)
    assert "样例数据" in res["honest_label"]
    # 随机森林提供不确定区间；sklearn 缺失时降级为均值基线（无区间）
    for p in res["predictions"]:
        if train._SKLEARN:
            assert p["interval"] is not None
        else:
            assert p["interval"] is None


# ============ 回写 ELN 格式 ============


def test_writeback_format_marks_prediction(tmp_path):
    res = predict_mod.predict({"temperature": 600, "time": 120, "heating_rate": 5, "precursor": "秸秆"})
    record = writeback.build_eln_record(res)
    md = writeback.render_eln_markdown(record)
    assert md.startswith("---")
    assert "模型预测待验证" in md
    assert "预测值" in md
    assert "## 输入条件" in md and "## 预测结果" in md

    path = writeback.write_eln_record(res, tmp_path)
    assert Path(path).exists()
    assert "模型预测待验证" in Path(path).read_text(encoding="utf-8")


# ============ 样例数据诚实标注 ============


def test_sample_data_honest_label():
    payload = sample_data.sample_payload(30)
    assert payload["_meta"]["sample"] is True
    assert "样例数据" in payload["_meta"]["note"]
    assert 20 <= len(payload["records"]) <= 50


# ============ Ollama 辅助降级 ============


def test_suggest_degrades_when_ollama_unavailable(monkeypatch):
    monkeypatch.setattr(suggest, "DEFAULT_BASE_URL", "http://127.0.0.1:1")
    out = suggest.suggest_experiment(
        {"input": {}, "predictions": [], "honest_label": "样例数据（合成，非真实实验）"},
        timeout=2,
    )
    assert out["ok"] is False
    assert out["available"] is False
    assert "note" in out
