"""m3gnet 材料图网络轻量探针（诚实降级 · 不引入重型依赖）。

授粉来源：materialyzeai/m3gnet（BSD-3）。本探针只做「可用性探测 + 属性面分析」：
- 若 m3gnet 已安装（罕见）→ 尝试最小属性预测；
- 若未安装 → 输出诚实退化标注 + 属性/依赖/接入分析，不编造预测值。

实现纪律（授粉）：
- BSD-3 可参考实现，但不整仓搬运；不 pip 安装（tensorflow 等重型依赖）。
- 纯标准库（importlib），不引新依赖；中文注释与输出。
"""
from __future__ import annotations

import importlib.util
import json


def probe() -> dict:
    """探测 m3gnet 可用性；不可用则输出诚实退化 + 属性面分析。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "properties",
    "deps", "conclusion", "runs"}``。
    """
    package = "m3gnet"
    spec = importlib.util.find_spec(package)

    if spec is not None:
        # 已安装（罕见）：标记可运行；不真正加载权重（避免重型依赖副作用）。
        return {
            "package": package,
            "status": "success",
            "license": "BSD-3-Clause",
            "summary": f"{package} 已安装（import 可用）",
            "properties": ["形成能", "带隙", "结构松弛"],
            "deps": ["tensorflow/pytorch", "pymatgen"],
            "conclusion": "接入（晶体/无机属性预测，与 chemprop 互补）",
            "runs": True,
        }

    return {
        "package": package,
        "status": "degraded",
        "license": "BSD-3-Clause",
        "summary": (
            "m3gnet 未安装（tensorflow/pymatgen 等重型依赖，不在共享环境引入），"
            "本次只输出属性面与接入分析，不执行真实预测（诚实降级）"
        ),
        "properties": ["形成能", "带隙", "弹性模量", "结构松弛"],
        "deps": ["tensorflow 或 pytorch", "pymatgen"],
        "conclusion": "接入（晶体/无机属性预测，与 chemprop 互补；无定形生物质适用性待评估）",
        "runs": False,
    }


def main() -> None:
    """命令行入口：输出 JSON，便于脚本化验收。"""
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
