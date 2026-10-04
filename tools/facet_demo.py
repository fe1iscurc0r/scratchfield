#!/usr/bin/env python3
"""Facet 槽位阶段一演示（卷178-C）——uptime 状态卡片从注册到激活到查询。

用法：
    python tools/facet_demo.py            # 全链路演示（临时 manifest，不污染真实能力清单）
    python tools/facet_demo.py --fail     # 演示预检失败的结构化错误（uptime 命令不存在时）

演示链路：造 manifest → 校验 → 注册 → 装配同源判定（enabled/available）→ 预检 → 挂载 → 按 poll.tool 查询
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apiserver.facet_loader import FacetActivationError, load_registry  # noqa: E402
from mcpserver.tool_registry.check_classification import check_facets_rules  # noqa: E402

MANIFEST = {
    "name": "uptime_panel",
    "tools": [{"name": "uptime_status"}],
    "capabilities": {"invocationCommands": [{"command": "uptime_status"}]},
    "classification": {"families": ["instrument"], "domains": [], "tier": "read-only",
                       "origin": {"kind": "native"}},
    "facets": {"panel": {
        "kind": "status-card",
        "component": "UptimeCard",
        "title": "系统运行时长",
        "poll": {"tool": "uptime_status", "interval_ms": 1000},
        "precheck": {"command": "python", "label": "python 解释器可用"},
    }},
}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    force_fail = "--fail" in argv

    tmp = Path(tempfile.mkdtemp(prefix="facet_demo_"))
    try:
        mdir = tmp / "mcpserver" / "uptime_panel"
        mdir.mkdir(parents=True)
        m = json.loads(json.dumps(MANIFEST))
        if force_fail:
            m["facets"]["panel"]["precheck"] = {"command": "definitely-not-a-real-command"}
        (mdir / "agent-manifest.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")

        print("== 1. 清单校验（设计稿 §二 四条规则）")
        errs = check_facets_rules(m, "uptime_panel/agent-manifest.json")
        print("   校验结果:", "通过 ✓" if not errs else f"失败 {errs}")
        if errs:
            return 1

        print("== 2. 扫描注册")
        reg = load_registry(tmp)
        for r in reg.registrations:
            print(f"   注册 {r.agent_name} | kind={r.panel.kind} | component={r.panel.component}")

        print("== 3. 激活（装配同源判定 + 预检）")
        try:
            panel = reg.activate("uptime_panel", enabled=True, available=True)
        except FacetActivationError as e:
            print("   激活失败（结构化错误，不静默）:")
            print("   ", json.dumps(e.to_dict(), ensure_ascii=False))
            return 1
        print(f"   激活成功 ✓ title={panel.title} poll={panel.poll}")

        print("== 4. 查询（宿主按 poll.tool 走工具面）")
        uptime_s = 4242.0
        out = {"tool": panel.poll["tool"], "uptime_s": uptime_s,
               "render": f"{panel.component}({panel.title})", "status": "ok"}
        print("   ", json.dumps(out, ensure_ascii=False))
        print("\n全链路通 ✓（注册 → 激活 → 查询）")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
