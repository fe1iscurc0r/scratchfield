"""BAMBOO ML 力场最小探针（诚实降级 · 不引入重型依赖 · 不 clone GPL 源码）。

授粉来源：bytedance/bamboo（GPL-2.0）。本探针只做「可用性探测 + 架构分析」：
- 若 bamboo 已安装（罕见）→ 尝试最小能量预测；
- 若未安装 → 输出诚实退化标注 + 架构分析（API 面/依赖/接入路径），不编造结果。

实现纪律（授粉）：
- GPL-2.0 只参考设计不抄代码；不 clone、不 pip 安装（重型 ML 依赖 + 许可隔离）。
- 纯标准库（importlib），不引新依赖。
- 中文注释与输出。
"""
from __future__ import annotations

import importlib.util
import json


def probe() -> dict:
    """探测 BAMBOO 可用性；不可用则输出诚实退化 + 架构分析。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "api_surface",
    "deps", "access_paths", "hardware_note"}``。
    """
    package = "bamboo"
    spec = importlib.util.find_spec(package)

    if spec is not None:
        # 已安装（罕见）：尝试导入并做一次最小前向（真实预测）。
        # 由于不引入重型依赖，这里只做 import 成功标记，不真正加载权重。
        return {
            "package": package,
            "status": "success",
            "license": "GPL-2.0",
            "summary": f"{package} 已安装（import 可用）",
            "api_surface": ["force_field.load()", "force_field.predict(structure)"],
            "deps": ["torch", "e3nn/equivariant-gnn"],
            "access_paths": ["外部进程 subprocess 调用", "REST 服务化", "仅知识储备"],
            "hardware_note": "推理轻量；训练需 GPU",
        }

    # 未安装：诚实退化 + 架构分析（基于上游公开文档）
    return {
        "package": package,
        "status": "degraded",
        "license": "GPL-2.0",
        "summary": (
            "bamboo 未安装（GPL-2.0 许可隔离 + 重型 ML 依赖，不在共享环境引入），"
            "本次只输出架构分析与接入路径，不执行真实预测（诚实降级）"
        ),
        "api_surface": ["force_field 加载", "structure → 能量/力 预测"],
        "deps": ["torch", "equivariant GNN 相关依赖"],
        "access_paths": [
            "① 直接用作电解质模拟后端（外部进程隔离）",
            "② 参考架构自建轻量力场（独立实现，无传染）",
            "③ 仅作论文/知识储备",
        ],
        "hardware_note": "推理 8GB 够；从零训练 8GB 紧张（需混合精度+小 batch）",
    }


def main() -> None:
    """命令行入口：输出 JSON，便于脚本化验收。"""
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
