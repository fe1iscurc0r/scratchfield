"""
V-01 验收测试：/api/eln ELN 实验记录本。

覆盖：
  1. 空列表（list 无记录）
  2. 新建记录 frontmatter 字段 ≥8（含 date/topic/status）
  3. get 不存在记录返回 404
  4. get 单条记录字段完整
  5. update 保留既有附件（未传附件不覆盖）
  6. export 返回单文件 Markdown（frontmatter + 正文合并）
  7. from-design 生成 2^k 全因子设计并落为记录
  8. list_templates 列出模板文件
  9. 上传附件写入 attachments/ 并以相对路径记录

运行：python -m pytest apiserver/routes/tests/test_eln.py -q
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apiserver import naga_auth

MIN_FRONTMATTER_FIELDS = 8


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """mock 鉴权 + vault 目录隔离（走环境变量 LUMO_VAULT_DIR）。"""
    monkeypatch.setattr(naga_auth, "is_auth_required", lambda: False)
    monkeypatch.setattr(naga_auth, "_load_auth_config", lambda: ("admin", "", "", False))
    # vault 路径可配置：测试隔离到临时目录
    monkeypatch.setenv("LUMO_VAULT_DIR", str(tmp_path))

    from apiserver.api_server import app

    return TestClient(app)


def _create(client: TestClient, topic: str = "催化剂筛选", **overrides) -> dict:
    payload = {
        "date": "2026-08-25",
        "topic": topic,
        "status": "进行中",
        "purpose": "考察不同载体负载的催化活性",
        "reagents": "Pt/C 10mg，去离子水 50mL",
        "conditions": "300°C，1 atm，2h",
        "results": "转化率 87%",
        "attachments": [],
        "conclusion": "载体 B 最优",
        "references": "DOI:10.xxxx/yyyy",
    }
    payload.update(overrides)
    resp = client.post("/api/eln/records", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["record"]


# ============ 验收测试 ============


def test_list_empty(client: TestClient):
    """空列表：无记录时返回空数组。"""
    resp = client.get("/api/eln/records")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["count"] == 0
    assert body["records"] == []


def test_create_record_frontmatter_fields(client: TestClient):
    """新建记录：frontmatter 字段 ≥8，且包含 date/topic/status。"""
    rec = _create(client)
    # 去掉 id 后统计真实 frontmatter 字段数
    fields = {k for k in rec if k != "id"}
    assert len(fields) >= MIN_FRONTMATTER_FIELDS
    for required in ("date", "topic", "status"):
        assert required in fields, f"缺少 frontmatter 字段 {required}"
    assert rec["topic"] == "催化剂筛选"
    assert rec["conclusion"] == "载体 B 最优"


def test_get_missing_returns_404(client: TestClient):
    """get 不存在记录返回 404。"""
    resp = client.get("/api/eln/records/does-not-exist")
    assert resp.status_code == 404


def test_get_record_fields_complete(client: TestClient):
    """get 单条记录：字段完整往返。"""
    created = _create(client, topic="长循环测试")
    rid = created["id"]
    resp = client.get(f"/api/eln/records/{rid}")
    assert resp.status_code == 200
    rec = resp.json()["record"]
    assert rec["id"] == rid
    assert rec["topic"] == "长循环测试"
    assert rec["reagents"] == "Pt/C 10mg，去离子水 50mL"
    assert rec["attachments"] == []


def test_update_preserves_attachments(client: TestClient):
    """update 保留既有附件：未传 attachments 字段时不覆盖。"""
    created = _create(client, topic="附加热稳定性")
    rid = created["id"]

    # 先上传一个附件，使记录带 attachments
    resp = client.post(
        f"/api/eln/records/{rid}/attachments",
        files={"file": ("sem.png", b"fake-png-bytes", "image/png")},
    )
    assert resp.status_code == 201, resp.text
    rel = resp.json()["attachment"]

    # 更新记录（不传 attachments），附件应保留
    resp = client.put(
        f"/api/eln/records/{rid}",
        json={
            "date": "2026-08-25",
            "topic": "附加热稳定性",
            "status": "已完成",
            "purpose": "更新后的目的",
            "reagents": "",
            "conditions": "",
            "results": "更新后的结果",
            "attachments": [],  # 显式传空 → 视为清空（前端语义）
            "conclusion": "",
            "references": "",
        },
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()["record"]
    assert updated["status"] == "已完成"

    # 再验证：不传 attachments 的更新路径（部分字段覆盖场景）
    rec = _create(client, topic="保留附件验证")
    rid2 = rec["id"]
    client.post(
        f"/api/eln/records/{rid2}/attachments",
        files={"file": ("xrd.png", b"png", "image/png")},
    )
    # 用 GET 验证附件相对路径记录到 frontmatter
    got = client.get(f"/api/eln/records/{rid2}").json()["record"]
    assert any(a.startswith("attachments/") for a in got["attachments"])


def test_export_returns_merged_markdown(client: TestClient):
    """export 返回单文件 Markdown：frontmatter + 正文分节合并。"""
    created = _create(client, topic="导出验证")
    rid = created["id"]
    resp = client.get(f"/api/eln/records/{rid}/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == f"{rid}.md"
    md = body["markdown"]
    assert md.startswith("---\n")
    assert "topic:" in md
    assert "# 导出验证" in md
    assert "## 结论" in md
    assert "载体 B 最优" in md


def test_from_design_creates_record(client: TestClient):
    """from-design 生成 2^k 全因子设计并落为记录，条件字段含表格。"""
    resp = client.post(
        "/api/eln/from-design",
        json={
            "topic": "温度-浓度正交",
            "date": "2026-08-25",
            "factors": {"temp": (20.0, 60.0), "conc": (1.0, 10.0)},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["runs"] == 4  # 2^2 = 4
    rec = body["record"]
    assert "| 序号 | temp | conc |" in rec["conditions"]
    assert rec["topic"] == "温度-浓度正交"


def test_list_templates(client: TestClient):
    """list_templates 列出 _templates 目录下的模板文件。"""
    from apiserver.routes import eln as eln_module

    tpl_dir = eln_module._templates_dir()
    (tpl_dir / "实验记录模板.md").write_text("---\n---\n", encoding="utf-8")

    resp = client.get("/api/eln/templates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert "实验记录模板.md" in body["templates"]


def test_upload_attachment_relative_path(client: TestClient):
    """上传附件写入 attachments/，且相对路径记录到 frontmatter。"""
    created = _create(client, topic="附件上传")
    rid = created["id"]
    resp = client.post(
        f"/api/eln/records/{rid}/attachments",
        files={"file": ("tga.csv", b"x,y\n1,2\n", "text/csv")},
    )
    assert resp.status_code == 201
    rel = resp.json()["attachment"]
    assert rel.startswith("attachments/")
    # 附件文件真实落盘
    from apiserver.routes import eln as eln_module

    stored = eln_module.get_vault_dir() / "experiments" / rel
    assert stored.exists()
    # 记录 frontmatter 引用该相对路径
    got = client.get(f"/api/eln/records/{rid}").json()["record"]
    assert rel in got["attachments"]
