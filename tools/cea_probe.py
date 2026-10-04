"""NASA CEA 平衡组成轻量探针（诚实降级 · Fortran 只做架构分析）。

授粉来源：nasa/cea（Apache-2.0，Fortran 平衡组成计算）。本探针只做「Python 包装
可用性探测 + 接口面分析」：包装不可用时输出 Fortran 接口面分析，如实标注退化，
不编造平衡组成数值。
"""
from __future__ import annotations

import importlib.util
import json


def probe() -> dict:
    """探测 CEA Python 包装（cea2 等）可用性；不可用则诚实降级为接口面分析。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "inputs",
    "outputs", "integration", "conclusion"}``。
    """
    wrapper_found = any(
        importlib.util.find_spec(m) is not None for m in ("cea2", "cea_wrapper")
    )

    base = {
        "package": "cea",
        "license": "Apache-2.0",
        "inputs": ["温度", "压力", "当量比", "组分"],
        "outputs": ["平衡组成", "热力学性质"],
        "integration": ["Python 包装(cea2)", "子进程调用", "核心逻辑独立实现"],
        "conclusion": "接入（热化学补充：平衡组成计算）",
    }

    if wrapper_found:
        base["status"] = "success"
        base["summary"] = "CEA Python 包装已安装（import 可用）"
    else:
        base["status"] = "degraded"
        base["summary"] = (
            "CEA Python 包装未安装（Fortran 源码需编译，不在共享环境引入）；"
            "本次只输出输入/输出接口面与集成路径分析（诚实降级，不编造平衡组成数值）"
        )
    return base


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
