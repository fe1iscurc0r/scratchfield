"""工单217 任务一 · /api/eda/ingest 端到端测试（TestClient，不起真端口）。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    """独立 app（只挂 eda 路由），落盘目录指到 tmp。"""
    monkeypatch.setenv("EDA_INGEST_TOKEN", "test-token-123")
    import apiserver.routes.eda_ingest as EI

    monkeypatch.setattr(EI, "get_data_dir", lambda: str(tmp_path))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(EI.router)
    # 抓事件：挂在总线上
    events: list[dict] = []
    EI.get_bus().on(EI.EVENT_TOPIC, lambda e: events.append(dict(e)))
    return TestClient(app), tmp_path, events


def _payload(project="RA01-底板", doc_type="esch", source=None):
    src = source or json.dumps({"doc": {"name": project}, "shapes": [1, 2, 3]})
    return {"meta": {"project": project, "page": "Page1", "doc_type": doc_type}, "source": src}


def test_rejects_without_token(app_client):
    client, _, _ = app_client
    r = client.post("/api/eda/ingest", json=_payload())
    assert r.status_code == 401


def test_rejects_wrong_token(app_client):
    client, _, _ = app_client
    r = client.post("/api/eda/ingest", json=_payload(), headers={"X-EDA-Token": "wrong"})
    assert r.status_code == 401


def test_ingest_stores_file_and_emits_event(app_client):
    client, root, events = app_client
    r = client.post("/api/eda/ingest", json=_payload(), headers={"X-EDA-Token": "test-token-123"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["stored"] is True and body["duplicate"] is False
    p = Path(body["path"])
    assert p.exists() and p.parent == root / "eda_ingest"
    assert p.name.endswith(".esch.json")
    # 事件已发布
    assert any(e["project"] == "RA01-底板" and e["doc_type"] == "esch" for e in events)
    assert events[-1]["content_hash"] == body["content_hash"]
    assert events[-1]["size"] > 0


def test_idempotent_same_content(app_client):
    client, _, events = app_client
    r1 = client.post("/api/eda/ingest", json=_payload(), headers={"X-EDA-Token": "test-token-123"})
    r2 = client.post("/api/eda/ingest", json=_payload(), headers={"X-EDA-Token": "test-token-123"})
    assert r1.json()["stored"] is True
    assert r2.json()["stored"] is False and r2.json()["duplicate"] is True
    assert r1.json()["content_hash"] == r2.json()["content_hash"]
    assert r1.json()["path"] == r2.json()["path"]
    # 两次都发事件（消费方按 hash 去重）
    dup_events = [e for e in events if e["duplicate"]]
    assert len(dup_events) == 1


def test_different_content_stores_new_file(app_client):
    client, _, _ = app_client
    r1 = client.post("/api/eda/ingest", json=_payload(source='{"v":1}'),
                     headers={"X-EDA-Token": "test-token-123"})
    r2 = client.post("/api/eda/ingest", json=_payload(source='{"v":2}'),
                     headers={"X-EDA-Token": "test-token-123"})
    assert r1.json()["stored"] and r2.json()["stored"]
    assert r1.json()["path"] != r2.json()["path"]


def test_project_name_sanitized(app_client):
    client, _, _ = app_client
    r = client.post("/api/eda/ingest", json=_payload(project="..\\evil/name"),
                    headers={"X-EDA-Token": "test-token-123"})
    assert r.status_code == 200
    assert ".." not in Path(r.json()["path"]).name
    assert "\\" not in Path(r.json()["path"]).name


def test_no_token_configured_503(app_client, monkeypatch):
    client, _, _ = app_client
    monkeypatch.delenv("EDA_INGEST_TOKEN", raising=False)
    monkeypatch.delenv("LUMO_PROXY_TOKEN", raising=False)
    r = client.post("/api/eda/ingest", json=_payload(), headers={"X-EDA-Token": "anything"})
    assert r.status_code == 503
