"""
V-02 验收测试：/api/data-tools 实验数据工具台（TGA/DSC/XRD 导入+绘图）。

覆盖：
  1. samples 返回三类样例数据（标注「样例」）
  2. parse 逗号分隔 CSV 分隔符探测
  3. parse Tab 分隔 TXT 分隔符探测
  4. parse 少于两列返回 400
  5. TGA 预处理基线扣除（首值=100）
  6. DSC 归一化（质量归一 / min-max 到 [0,1]）
  7. XRD 平滑（窗口>1 曲线变平滑）
  8. plot 未知数据类型返回 400
  9. plot 列缺失 / 非数值列返回 400
 10. plot 生成 PNG 存 attachments/ 并创建 ELN 记录
 11. plot 追加附件到已有 ELN 记录

运行：python -m pytest apiserver/routes/tests/test_data_tools.py -q
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from apiserver import naga_auth

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """mock 鉴权 + vault 目录隔离（走环境变量 LUMO_VAULT_DIR）。"""
    monkeypatch.setattr(naga_auth, "is_auth_required", lambda: False)
    monkeypatch.setattr(naga_auth, "_load_auth_config", lambda: ("admin", "", "", False))
    monkeypatch.setenv("LUMO_VAULT_DIR", str(tmp_path))

    from apiserver.api_server import app

    return TestClient(app)


def _sample_text(data_type: str) -> str:
    """取样例数据文本（自造样例，标注「样例」）。"""
    from apiserver.routes import data_tools as dt

    return dt._SAMPLES[data_type]()


# ============ 验收测试 ============


def test_samples_return_four_types(client: TestClient):
    """samples：返回四类样例（tga/dsc/xrd/raman），且标注「样例」。"""
    from apiserver.routes import data_tools as dt

    resp = client.get("/api/data-tools/samples")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert set(body["samples"]) == {"tga", "dsc", "xrd", "raman"}
    for data_type, item in body["samples"].items():
        assert "样例" in item["label"]
        assert "样例" in item["content"]
        # 内容可被解析且至少两列
        df, delim = dt.parse_dataframe(item["content"])
        assert df.shape[1] >= 2
        assert delim in (",", "\t", ";", r"\s+")


def test_parse_comma_csv(client: TestClient):
    """parse：逗号分隔 CSV 探测为逗号，返回列/行数/预览。"""
    text = "Temperature_C,Weight_pct\n30,99.5\n40,99.1\n50,98.7\n"
    resp = client.post(
        "/api/data-tools/parse",
        files={"file": ("tga.csv", text.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delimiter"] == ","
    assert body["columns"] == ["Temperature_C", "Weight_pct"]
    assert body["row_count"] == 3
    assert len(body["preview"]) == 3


def test_parse_tab_txt(client: TestClient):
    """parse：Tab 分隔 TXT 探测为 \\t。"""
    text = "2Theta\tIntensity\n10.0\t120\n20.0\t300\n"
    resp = client.post(
        "/api/data-tools/parse",
        files={"file": ("xrd.txt", text.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delimiter"] == "\t"
    assert body["row_count"] == 2


def test_parse_single_column_400(client: TestClient):
    """parse：少于两列返回 400。"""
    resp = client.post(
        "/api/data-tools/parse",
        files={"file": ("bad.csv", b"only_one\n1\n2\n", "text/csv")},
    )
    assert resp.status_code == 400
    assert "两列" in resp.json()["detail"]


def test_preprocess_tga_baseline(client: TestClient):
    """TGA 预处理：基线扣除后首值=100。"""
    from apiserver.routes import data_tools as dt

    df = pd.DataFrame({"T": [100.0, 200.0, 300.0], "W": [98.0, 95.0, 90.0]})
    out = dt.preprocess_tga(df, "T", "W")
    assert out["W"].iloc[0] == pytest.approx(100.0)
    # 相对首值的偏移保持不变
    assert out["W"].iloc[1] == pytest.approx(97.0)


def test_preprocess_dsc_normalize(client: TestClient):
    """DSC 预处理：质量归一（有质量）与 min-max（无质量）。"""
    from apiserver.routes import data_tools as dt

    df = pd.DataFrame({"T": [0.0, 100.0, 200.0], "Q": [1.0, 3.0, 2.0]})

    with_mass = dt.preprocess_dsc(df, "T", "Q", mass_mg=10.0)
    assert with_mass["Q"].iloc[0] == pytest.approx(0.1)

    no_mass = dt.preprocess_dsc(df, "T", "Q")
    assert no_mass["Q"].min() == pytest.approx(0.0)
    assert no_mass["Q"].max() == pytest.approx(1.0)


def test_preprocess_xrd_smooth(client: TestClient):
    """XRD 预处理：奇数窗口移动平均使曲线变平滑（std 下降）。"""
    from apiserver.routes import data_tools as dt

    y = np.array([1.0, 50.0, 100.0, 50.0, 1.0, 40.0, 90.0, 40.0])
    df = pd.DataFrame({"2T": np.arange(len(y), dtype=float), "I": y})
    out = dt.preprocess_xrd(df, "2T", "I", smooth_window=3)
    # 长度不变，且移动平均使曲线变平滑（std 下降）
    assert len(out["I"]) == len(df["I"])
    assert out["I"].std() < df["I"].std()
    # 偶数窗口自动 +1 为奇数后同样生效
    out2 = dt.preprocess_xrd(df, "2T", "I", smooth_window=4)
    assert len(out2["I"]) == len(df["I"])
    assert out2["I"].std() < df["I"].std()


def test_plot_unknown_type_400(client: TestClient):
    """plot：未知数据类型返回 400。"""
    resp = client.post(
        "/api/data-tools/plot",
        data={"data_type": "not_a_type", "x_col": "T", "y_col": "W"},
        files={"file": ("t.csv", b"T,W\n1,2\n", "text/csv")},
    )
    assert resp.status_code == 400
    assert "未知数据类型" in resp.json()["detail"]


def test_plot_bad_columns_400(client: TestClient):
    """plot：列缺失或非数值列返回 400。"""
    text = "T,W\n1,2\n2,3\n"
    # 列缺失
    resp = client.post(
        "/api/data-tools/plot",
        data={"data_type": "tga", "x_col": "Nope", "y_col": "W"},
        files={"file": ("t.csv", text.encode(), "text/csv")},
    )
    assert resp.status_code == 400
    assert "列不存在" in resp.json()["detail"]
    # 非数值列
    resp = client.post(
        "/api/data-tools/plot",
        data={"data_type": "tga", "x_col": "W", "y_col": "T", "title": "x"},
        files={"file": ("t.csv", b"W,T\nfoo,2\nbar,3\n", "text/csv")},
    )
    assert resp.status_code == 400
    assert "不是数值列" in resp.json()["detail"]


def test_plot_creates_record_with_attachment(client: TestClient):
    """plot：生成 PNG 存 attachments/，并创建 ELN 记录引用该相对路径。"""
    from apiserver.routes import data_tools as dt
    from apiserver.routes import eln as eln_module

    resp = client.post(
        "/api/data-tools/plot",
        data={
            "data_type": "tga",
            "x_col": "Temperature_C",
            "y_col": "Weight_pct",
            "title": "TGA 验收",
            "topic": "TGA 数据工具台验收",
        },
        files={"file": ("tga.csv", _sample_text("tga").encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["attachment"].startswith("attachments/")
    assert body["data_type"] == "tga"

    # PNG 真实落盘且为合法 PNG
    stored = eln_module.get_vault_dir() / "experiments" / body["attachment"]
    assert stored.exists()
    assert stored.read_bytes()[:8] == PNG_MAGIC

    # ELN 记录已创建且引用该附件
    rid = body["record_id"]
    assert rid
    rec = client.get(f"/api/eln/records/{rid}").json()["record"]
    assert body["attachment"] in rec["attachments"]


def test_plot_xrd_with_smoothing(client: TestClient):
    """plot：XRD 样例 + 平滑窗口，生成 PNG 并入库（三类样例各出图）。"""
    from apiserver.routes import eln as eln_module

    resp = client.post(
        "/api/data-tools/plot",
        data={
            "data_type": "xrd",
            "x_col": "TwoTheta_deg",
            "y_col": "Intensity",
            "smooth_window": "5",
            "title": "XRD 平滑验收",
            "topic": "XRD 数据工具台验收",
        },
        files={"file": ("xrd.csv", _sample_text("xrd").encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data_type"] == "xrd"

    stored = eln_module.get_vault_dir() / "experiments" / body["attachment"]
    assert stored.exists()
    assert stored.read_bytes()[:8] == PNG_MAGIC

    rec = client.get(f"/api/eln/records/{body['record_id']}").json()["record"]
    assert body["attachment"] in rec["attachments"]


def test_plot_appends_attachment_to_existing(client: TestClient):
    """plot：传 record_id 时把图追加为已有 ELN 记录附件。"""
    from apiserver.routes import eln as eln_module

    # 先创建一条 ELN 记录
    resp = client.post(
        "/api/eln/records",
        json={
            "date": "2026-08-25",
            "topic": "DSC 联测",
            "status": "进行中",
            "purpose": "",
            "reagents": "",
            "conditions": "",
            "results": "",
            "attachments": [],
            "conclusion": "",
            "references": "",
        },
    )
    assert resp.status_code == 201, resp.text
    rid = resp.json()["record"]["id"]

    resp = client.post(
        "/api/data-tools/plot",
        data={
            "data_type": "dsc",
            "x_col": "Temperature_C",
            "y_col": "HeatFlow_mW",
            "record_id": rid,
        },
        files={"file": ("dsc.csv", _sample_text("dsc").encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["record_id"] == rid

    rec = client.get(f"/api/eln/records/{rid}").json()["record"]
    assert body["attachment"] in rec["attachments"]

    # 再追加一次：每次绘图生成新 PNG 文件，应追加为新附件（路径互不相同）
    resp = client.post(
        "/api/data-tools/plot",
        data={
            "data_type": "dsc",
            "x_col": "Temperature_C",
            "y_col": "HeatFlow_mW",
            "record_id": rid,
        },
        files={"file": ("dsc.csv", _sample_text("dsc").encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    rec2 = client.get(f"/api/eln/records/{rid}").json()["record"]
    assert len(rec2["attachments"]) == 2  # 每次绘图追加一个新附件
