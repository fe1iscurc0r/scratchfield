"""卷180 验收测试：manifest 分类标签的加载侧消费 + 过滤查询。

覆盖（工单 C）：
- 补标前后注册表 tool 数一致（只加标签不加能力）
- 三个典型查询：by_tier（offensive 闸门候选）/ by_family / by_domain(±generic)
- filter_apps 组合语义（AND）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # tests/ -> tool_registry/ -> mcpserver/ -> 仓库根
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcpserver.tool_registry.registry import (  # noqa: E402
    by_domain,
    by_family,
    by_tier,
    convert_manifest_to_meta,
    filter_apps,
    scan_manifest_dir,
    summarize_labels,
)


@pytest.fixture(scope="module")
def apps():
    return scan_manifest_dir(PROJECT_ROOT)


def test_all_manifests_carry_classification(apps):
    """53 个 manifest 全部带分类（工单验收：40/40 有分类字段——实际覆盖 53 个）。"""
    assert len(apps) >= 40
    untagged = [a.name for a in apps if not a.families and not a.tier]
    assert untagged == [], f"以下能力缺分类标签: {untagged}"


def test_tool_count_unchanged_by_labeling(apps):
    """只加标签不加能力：function 总数与 manifest 声明一致（补标不改变能力面）。"""
    total_functions = sum(len(a.functions) for a in apps)
    assert total_functions >= len(apps)  # 每个能力至少 1 个入口
    # 逐个 manifest 的 function 数与源文件 commands 数一致
    for f in (PROJECT_ROOT / "mcpserver").rglob("agent-manifest.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        meta = convert_manifest_to_meta(data)
        caps = data.get("capabilities")
        # dict 型取 invocationCommands；list 型（字符串能力名）无调用契约 → functions=0
        if isinstance(caps, dict):
            declared = [c for c in (caps.get("invocationCommands") or [])
                        if isinstance(c, dict) and c.get("command")]
        else:
            declared = []
        assert len(meta.functions) == len(declared), f"{f.name} 能力数不一致"


class TestTypicalQueries:
    """三个典型查询（工单验收）。"""

    def test_query_by_tier_offensive(self, apps):
        """查询 1：offensive tier（默认闸门关闭的攻防能力集）。"""
        hit = by_tier(apps, "offensive")
        assert hit, "offensive 查询不应为空"
        assert all(a.tier == "offensive" for a in hit)
        assert len(hit) < len(apps)  # 真过滤而非全量

    def test_query_by_family(self, apps):
        """查询 2：按族（如 instrument——硬件/仪器类）。"""
        hit = by_family(apps, "instrument")
        assert hit
        assert all("instrument" in a.families for a in hit)

    def test_query_by_domain_excludes_generic_by_default(self, apps):
        """查询 3：按域（materials），默认不含跨领域通用件。"""
        hit = by_domain(apps, "materials")
        assert hit
        assert all("materials" in a.domains for a in hit)
        with_generic = by_domain(apps, "materials", include_generic=True)
        assert len(with_generic) >= len(hit)
        assert all(not a.domains for a in with_generic if a not in hit)


class TestFilterSemantics:
    def test_combined_and_semantics(self, apps):
        """组合过滤 = AND。"""
        both = filter_apps(apps, families=["compute"], tier="read-only")
        assert all("compute" in a.families and a.tier == "read-only" for a in both)

    def test_empty_filter_returns_all(self, apps):
        assert len(filter_apps(apps)) == len(apps)

    def test_origin_kind_native(self, apps):
        native = filter_apps(apps, origin_kind="native")
        assert native
        assert all(str((a.origin or {}).get("kind")) == "native" for a in native)

    def test_summarize_labels_covers_value_domains(self, apps):
        s = summarize_labels(apps)
        assert "offensive" in s["tiers"]
        assert "native" in s["origins"]
        assert s["families"] and s["domains"]
