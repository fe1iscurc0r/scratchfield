"""W-02 验收测试：文献管理器 /api/papers。

覆盖：CRUD / 搜索 / DOI 导入（mock crossref + 网络失败降级）/ JSON 批量导入 /
坏 JSON 降级 / 文献↔ELN 关联 / 404。

运行：python -m pytest apiserver/routes/tests/test_papers.py -q
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apiserver import naga_auth
from apiserver.routes import papers as papers_module


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """mock 鉴权 + 数据目录隔离 + 使用真实 app（跳过 lifespan 后台任务）。"""
    monkeypatch.setattr(naga_auth, "is_auth_required", lambda: False)
    monkeypatch.setattr(naga_auth, "_load_auth_config", lambda: ("admin", "", "", False))
    monkeypatch.setattr(papers_module, "get_data_dir", lambda: tmp_path)

    from apiserver.api_server import app

    return TestClient(app)


def _create(client: TestClient, title: str = "Test Paper", **kwargs) -> dict:
    resp = client.post("/api/papers", json={"title": title, **kwargs})
    assert resp.status_code == 200, resp.text
    return resp.json()["paper"]


# ============ CRUD ============


def test_crud(client):
    paper = _create(client, "碳化实验综述", doi="10.1234/abc", tags=["碳化", "综述"], year=2024)
    pid = paper["id"]
    assert paper["title"] == "碳化实验综述"
    assert paper["tags"] == ["碳化", "综述"]

    # get
    got = client.get(f"/api/papers/{pid}").json()["paper"]
    assert got["doi"] == "10.1234/abc"

    # update（部分更新）
    upd = client.put(f"/api/papers/{pid}", json={"notes": "重点读 Section 4"}).json()["paper"]
    assert upd["notes"] == "重点读 Section 4"
    assert upd["title"] == "碳化实验综述"  # 未传字段保留

    # delete
    assert client.delete(f"/api/papers/{pid}").json()["success"] is True
    assert client.get(f"/api/papers/{pid}").status_code == 404


def test_get_missing_404(client):
    assert client.get("/api/papers/99999").status_code == 404


# ============ 搜索 ============


def test_search_by_title_and_tag(client):
    _create(client, "木质素水凝胶", authors=["张三", "李四"], tags=["水凝胶"])
    _create(client, "生物质碳化", authors=["王五"], tags=["碳化"])
    _create(client, "KOH 活化", authors=["赵六"], tags=["碳化"])

    # 按标题/作者关键词搜索
    res = client.get("/api/papers", params={"q": "木质素"}).json()
    assert res["total"] == 1
    assert res["papers"][0]["title"] == "木质素水凝胶"

    # 按作者搜索
    res = client.get("/api/papers", params={"q": "王五"}).json()
    assert res["total"] == 1
    assert res["papers"][0]["title"] == "生物质碳化"

    # 按标签过滤
    res = client.get("/api/papers", params={"tag": "碳化"}).json()
    assert res["total"] == 2


# ============ DOI 导入 ============


def test_doi_import_mock(client, monkeypatch):
    def fake_fetch(doi, timeout=10.0):
        return {
            "title": "Mock Crossref Title",
            "journal": "Nature",
            "authors": ["Given Family"],
            "year": 2020,
            "abstract": "mock abstract",
            "doi": doi,
        }

    monkeypatch.setattr(papers_module, "fetch_crossref", fake_fetch)
    resp = client.post("/api/papers/import-doi", json={"doi": "10.1038/xyz", "tags": ["碳化"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["paper"]["title"] == "Mock Crossref Title"
    assert body["paper"]["journal"] == "Nature"
    assert body["paper"]["tags"] == ["碳化"]


def test_doi_import_network_failure_degrades(client, monkeypatch):
    def boom(doi, timeout=10.0):
        raise papers_module.CrossrefError("网络不可达")

    monkeypatch.setattr(papers_module, "fetch_crossref", boom)
    resp = client.post("/api/papers/import-doi", json={"doi": "10.1038/xyz"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["fallback"] == "manual"
    assert "网络不可达" in body["error"]


# ============ JSON 批量导入 ============


def test_json_import_with_md_content(client, tmp_path):
    items = [
        {
            "title": "Imported Paper A",
            "doi": "10.1/a",
            "abstract": "abstract A",
            "md": "# Paper A\n\ncontent",
            "authors": ["A One", "B Two"],
        },
        {"title": "Imported Paper B", "doi": "10.1/b"},
    ]
    resp = client.post("/api/papers/import", json=items)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 2
    assert len(body["ids"]) == 2
    assert body["skipped"] == []

    got = client.get("/api/papers").json()
    assert got["total"] == 2

    # md 内容已落盘为 md_path
    paper_a = next(p for p in got["papers"] if p["title"] == "Imported Paper A")
    assert paper_a["md_path"] and Path(paper_a["md_path"]).exists()
    assert "# Paper A" in Path(paper_a["md_path"]).read_text(encoding="utf-8")


def test_json_import_bad_data_degrades(client):
    items = [
        {"title": "Good Paper"},
        {"doi": "10.1/bad"},  # 缺 title → 跳过
        "not-an-object",  # 非对象 → 跳过
        {"title": "Another Good"},
    ]
    resp = client.post("/api/papers/import", json=items)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 2
    assert [s["index"] for s in body["skipped"]] == [1, 2]


# ============ 文献 ↔ ELN 关联 ============


def test_link_experiments(client):
    paper = _create(client, "关联测试文献")
    pid = paper["id"]
    resp = client.put(f"/api/papers/{pid}/experiments", json={"experiment_ids": ["exp-1", "exp-2"]})
    assert resp.status_code == 200, resp.text
    linked = resp.json()["paper"]["linked_experiments"]
    assert linked == ["exp-1", "exp-2"]

    # 持久化到 SQLite 表可查
    db_path = papers_module._db_path()
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT linked_experiments FROM papers WHERE id = ?", (pid,)).fetchone()
    conn.close()
    assert "exp-1" in row[0]


def test_papers_table_exists(client):
    """grep 验收之外，确认 papers 表真实落盘。"""
    _create(client, "table check")
    db_path = papers_module._db_path()
    conn = sqlite3.connect(db_path)
    table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers'").fetchone()
    conn.close()
    assert table is not None
