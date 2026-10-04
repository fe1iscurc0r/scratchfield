"""asset_manifest 验收硬线（handcrafted 蒸馏批 W100-03）。"""
import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lumo import asset_manifest  # noqa: E402


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_manifest_all_ok(tmp_path):
    """假 manifest 自检：全部在场且哈希一致 → ok。"""
    (tmp_path / "a.bin").write_bytes(b"hello")
    (tmp_path / "b.bin").write_bytes(b"world")
    mf = {
        "assets": [
            {"id": "a", "path": "a.bin", "sha256": hashlib.sha256(b"hello").hexdigest()},
            {"id": "b", "path": "b.bin", "sha256": hashlib.sha256(b"world").hexdigest(), "size_bytes": 5},
        ],
    }
    report = asset_manifest.check_manifest(mf, tmp_path)
    assert report["ok"] is True
    assert all(i["status"] == "ok" for i in report["items"])


def test_manifest_missing_detected(tmp_path):
    """缺失资产被检出。"""
    mf = {"assets": [{"id": "ghost", "path": "nope.bin", "sha256": "x" * 64}]}
    report = asset_manifest.check_manifest(mf, tmp_path)
    assert report["ok"] is False
    assert report["items"][0]["status"] == "missing"
    assert asset_manifest.missing_assets(mf, tmp_path) == ["ghost"]


def test_manifest_hash_mismatch_detected(tmp_path):
    """sha256 不匹配被检出。"""
    (tmp_path / "c.bin").write_bytes(b"tampered")
    mf = {"assets": [{"id": "c", "path": "c.bin", "sha256": "0" * 64}]}
    report = asset_manifest.check_manifest(mf, tmp_path)
    assert report["items"][0]["status"] == "hash_mismatch"


def test_manifest_size_mismatch_detected(tmp_path):
    """大小不符被检出。"""
    (tmp_path / "d.bin").write_bytes(b"1234")
    mf = {"assets": [{"id": "d", "path": "d.bin", "size_bytes": 999}]}
    report = asset_manifest.check_manifest(mf, tmp_path)
    assert report["items"][0]["status"] == "size_mismatch"


def test_load_manifest_missing_file():
    """manifest 不存在明确报错。"""
    import pytest
    with pytest.raises(FileNotFoundError):
        asset_manifest.load_manifest(Path("no_such_manifest.json"))


def test_load_manifest_bad_structure(tmp_path):
    """manifest 结构非法明确报错。"""
    import pytest
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"nope": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="结构非法"):
        asset_manifest.load_manifest(bad)
