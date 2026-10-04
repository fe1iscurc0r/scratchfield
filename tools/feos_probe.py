"""feos 状态方程轻量探针（诚实降级 · 不引重型依赖）。

授粉来源：feos-org/feos（Apache-2.0，Rust EoS 框架 + feos-py Python 绑定）。
本探针只做「绑定可用性探测 + API 面分析」：feos-py 不可用时输出 API 面/依赖/
接入路径，如实标注退化，不编造相平衡数值。
"""
from __future__ import annotations

import importlib.util
import json


def probe() -> dict:
    """探测 feos-py 可用性；不可用则诚实降级为 API 面分析。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "eos_supported",
    "api_surface", "conclusion"}``。
    """
    package = "feos"
    spec = importlib.util.find_spec(package)

    base = {
        "package": package,
        "license": "Apache-2.0",
        "eos_supported": ["PC-SAFT", "Peng-Robinson"],
        "api_surface": ["EquationOfState", "PhaseEquilibrium", "State（p/T/密度）"],
        "conclusion": "接入（主候选：状态方程/相平衡）",
    }

    if spec is not None:
        base["status"] = "success"
        base["summary"] = f"{package}（feos-py）已安装（import 可用）"
    else:
        base["status"] = "degraded"
        base["summary"] = (
            "feos-py 未安装（Rust 编译产物分发，平台相关，不在共享环境引入）；"
            "本次只输出 EoS 支持面与 API 分析（诚实降级，不编造相平衡数值）"
        )
    return base


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
