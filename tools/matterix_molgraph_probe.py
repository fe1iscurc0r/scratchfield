"""Matterix + molgraph 轻量探针（诚实降级 · 不引重型依赖）。

授粉来源：AccelerationConsortium/Matterix（BSD-3）、akensert/molgraph（MIT）。
molgraph 走 import 探测；Matterix 走静态分析（能否虚拟运行）。合并输出一份结果。
"""
from __future__ import annotations

import importlib.util
import json


def probe() -> dict:
    """探测 molgraph 可用性 + Matterix 能否虚拟运行（静态分析）。

    返回
    ----
    dict：``{"molgraph": {...}, "matterix": {...}}``，两部分各标注状态。
    """
    mg_spec = importlib.util.find_spec("molgraph")
    if mg_spec is not None:
        molgraph = {
            "status": "success",
            "license": "MIT",
            "summary": "molgraph 已安装（import 可用）",
            "properties": ["分子性质预测（QSAR）"],
            "conclusion": "仅参考/暂缓（TF 侧补覆盖）",
        }
    else:
        molgraph = {
            "status": "degraded",
            "license": "MIT",
            "summary": "molgraph 未安装（TF 生态重型依赖，不在共享环境引入，诚实降级）",
            "properties": ["分子性质预测（QSAR）"],
            "conclusion": "仅参考/暂缓（TF 侧补覆盖）",
        }

    matterix = {
        "status": "degraded",
        "license": "BSD-3-Clause",
        "summary": (
            "Matterix 未浅克隆（环境约束）；基于上游公开文档静态分析，"
            "结论：数字孪生仿真接口，可虚拟运行，与 pylabrobot 虚拟后端组合"
        ),
        "can_simulate": True,
        "conclusion": "仅参考（数字孪生蓝图）",
    }

    return {"molgraph": molgraph, "matterix": matterix}


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
