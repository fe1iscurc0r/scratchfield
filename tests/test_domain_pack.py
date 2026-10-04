"""卷162 · 领域包（Domain Pack）加载器测试。

覆盖：
- default 包行为与改造前逐字段一致（回归红线）
- law 包可加载，字段为法学字段
- 坏包降级为警告（不抛异常、不炸启动）
- `GET /api/domains` 响应结构
- papers 主键按包解析
- eln.py 的 frontmatter 顺序在 default 下与改造前一致
"""

from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_domain_pack():
    """直接按路径加载 apiserver/domain_pack.py。

    不能 `import apiserver.domain_pack` —— `apiserver/__init__.py` 会拉起整个
    应用（含 matplotlib 等重依赖），测试环境未必具备。
    """
    path = REPO_ROOT / "apiserver" / "domain_pack.py"
    spec = importlib.util.spec_from_file_location("domain_pack_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


dp = _load_domain_pack()

# 改造前 eln.py 的 frontmatter 字段快照（顺序敏感）。
LEGACY_FRONTMATTER_FIELDS = [
    "date",
    "topic",
    "status",
    "purpose",
    "reagents",
    "conditions",
    "results",
    "attachments",
    "conclusion",
    "references",
]


@pytest.fixture(autouse=True)
def _reset_cache():
    dp.reload_packs()
    yield
    dp.reload_packs()


def test_default_pack_exists_and_matches_legacy_field_set():
    """回归红线：default 包 ELN 字段名集合 == 改造前快照。"""
    pack = dp.get_default_pack()
    assert pack is not None, "domains/default 必须存在"
    assert pack.name == "default"
    # 字段名集合（顺序按 pack 声明，前端表单用；集合须与快照一致）
    assert set(pack.eln_field_keys) == set(LEGACY_FRONTMATTER_FIELDS)


def test_default_pack_form_fields_match_legacy_elnview():
    """回归红线：default 包表单字段顺序/label/type == 改造前 ElnView 手写表单。

    改造前 ElnView.vue 的表单（顺序即页面自上而下）：
    topic / date / status / purpose / reagents / conditions / results /
    conclusion / references —— 注意不含 attachments。
    """
    pack = dp.get_default_pack()
    assert pack is not None
    form = pack.form_eln_fields
    got = [(f.key, f.type, f.label) for f in form]
    expected = [
        ("topic", "text", "课题 *"),
        ("date", "date", "日期"),
        ("status", "text", "状态"),
        ("purpose", "textarea", "目的"),
        ("reagents", "textarea", "药品与用量"),
        ("conditions", "textarea", "条件"),
        ("results", "textarea", "结果"),
        ("conclusion", "textarea", "结论"),
        ("references", "textarea", "关联文献"),
    ]
    assert got == expected


def test_default_pack_attachments_hidden_from_form():
    """attachments 不进前端表单（改造前表单不渲染它），但仍在 all fields 里。"""
    pack = dp.get_default_pack()
    assert pack is not None
    assert "attachments" in pack.eln_field_keys
    assert "attachments" not in [f.key for f in pack.form_eln_fields]


def test_default_id_fields_are_legacy():
    assert dp.get_id_fields("default") == ["doi", "arxiv_id"]


def test_law_pack_loads_with_law_fields():
    pack = dp.get_pack("law")
    assert pack is not None, "domains/law 必须可加载"
    keys = pack.eln_field_keys
    for k in (
        "topic",
        "parties",
        "cause_of_action",
        "dispute_focus",
        "holding",
        "legal_basis",
        "related_cases",
    ):
        assert k in keys, f"law 包缺字段 {k}"
    assert dp.get_id_fields("law") == ["flk_id", "case_no"]


def test_law_pack_topic_first_for_backend_contract():
    """后端 ElnRecordIn.topic 必填，故各包表单首字段须为 topic。"""
    pack = dp.get_pack("law")
    assert pack is not None
    assert pack.eln_field_keys[0] == "topic"
    assert pack.eln_fields[0].required is True


def test_unknown_pack_falls_back_to_default():
    assert dp.get_pack("no-such-pack") is None
    assert dp.get_eln_fields("no-such-pack") == LEGACY_FRONTMATTER_FIELDS
    assert dp.get_id_fields("no-such-pack") == ["doi", "arxiv_id"]


def test_get_eln_fields_default_returns_all_legacy():
    assert dp.get_eln_fields("default") == LEGACY_FRONTMATTER_FIELDS
    assert dp.get_eln_fields(None) == LEGACY_FRONTMATTER_FIELDS


def test_list_packs_contains_default_and_law():
    names = {p.name for p in dp.list_packs()}
    assert "default" in names
    assert "law" in names


def test_to_dict_shape():
    """GET /api/domains 元素结构。"""
    pack = dp.get_default_pack()
    assert pack is not None
    d = pack.to_dict()
    assert set(d) >= {
        "name",
        "label",
        "description",
        "eln",
        "papers",
        "source_presets",
        "tagging",
    }
    assert "fields" in d["eln"] and "form_fields" in d["eln"]
    assert isinstance(d["papers"]["id_fields"], list)
    for f in d["eln"]["fields"]:
        assert set(f) >= {"key", "type", "label", "required", "show_in_form"}


def test_bad_pack_degrades_to_warning(tmp_path, monkeypatch, caplog):
    """坏包（缺 label）只记 warning，不抛异常，且被跳过。"""
    bad_dir = tmp_path / "domains" / "broken"
    bad_dir.mkdir(parents=True)
    (bad_dir / "pack.yaml").write_text("name: broken\n", encoding="utf-8")

    monkeypatch.setattr(dp, "DOMAINS_DIR", tmp_path / "domains")
    dp.reload_packs()

    with caplog.at_level("WARNING"):
        packs = dp.reload_packs()
    assert "broken" not in packs
    assert any("broken" in r.message or "broken" in str(r.args) for r in caplog.records)


def test_missing_domains_dir_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "DOMAINS_DIR", tmp_path / "nope")
    dp.reload_packs()
    assert dp.list_packs() == []
    # 仍回退到硬编码快照，保证不回归
    assert dp.get_eln_fields(None) == LEGACY_FRONTMATTER_FIELDS


def test_yaml_syntax_error_degrades(tmp_path, monkeypatch):
    bad_dir = tmp_path / "domains" / "bad_yaml"
    bad_dir.mkdir(parents=True)
    (bad_dir / "pack.yaml").write_text("name: [unclosed\n", encoding="utf-8")
    monkeypatch.setattr(dp, "DOMAINS_DIR", tmp_path / "domains")
    dp.reload_packs()
    assert dp.get_pack("bad_yaml") is None


# ── eln.py frontmatter 顺序回归 ──────────────────────────────────────


def _load_eln_frontmatter_fn():
    """加载 eln.py 里的 `_frontmatter_fields`（避免拉起整个 apiserver 包）。

    采用 AST 摘取：只取出 `_frontmatter_fields` 函数源码，在受控命名空间里
    注入 domain_pack 的 get_eln_fields 后执行。
    """
    import ast

    src = (REPO_ROOT / "apiserver" / "routes" / "eln.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    chunks = [
        ast.get_source_segment(src, node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_frontmatter_fields"
    ]
    ns: dict = {"get_eln_fields": dp.get_eln_fields}
    exec("\n\n".join(chunks), ns)  # noqa: S102
    return ns["_frontmatter_fields"]


def test_eln_frontmatter_order_default_is_legacy():
    """回归红线：default 包 frontmatter 顺序 == 改造前快照（date 在前、含 attachments）。"""
    fn = _load_eln_frontmatter_fn()
    assert fn("default") == LEGACY_FRONTMATTER_FIELDS
    assert fn(None) == LEGACY_FRONTMATTER_FIELDS
    assert fn("no-such") == LEGACY_FRONTMATTER_FIELDS


def test_eln_frontmatter_order_law_uses_pack_order():
    """law 包 frontmatter 顺序按其 pack.yaml 声明（新领域，无回归约束）。"""
    fn = _load_eln_frontmatter_fn()
    assert fn("law") == dp.get_eln_fields("law")
