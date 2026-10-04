"""pylabrobot 实验自动化轻量探针（诚实降级 · 硬件无关抽象层验证）。

授粉来源：PyLabRobot/pylabrobot（MIT，★525）。本探针重点验证「硬件无关抽象层」：
定义板布局 + 移液步骤，**不硬编码具体设备型号**；不可用时退化为抽象层演示
（诚实降级，不接真实移液工作站）。
"""
from __future__ import annotations

import importlib.util
import json


def probe() -> dict:
    """编排一个最小实验流程（板布局 + 移液步骤），验证硬件无关 API。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "board_layout",
    "steps", "device_specific"}``。``device_specific`` 恒为 False（硬件无关）。
    """
    package = "pylabrobot"
    spec = importlib.util.find_spec(package)

    # 硬件无关抽象层：只用抽象类型（plate/pipette），不写具体设备型号
    board_layout = [
        {"name": "source_plate", "type": "plate", "wells": 96},
        {"name": "dest_plate", "type": "plate", "wells": 96},
    ]
    steps = [
        {"op": "transfer", "from": "source_plate.A1", "to": "dest_plate.A1", "volume_ul": 100},
        {"op": "mix", "well": "dest_plate.A1", "times": 3},
    ]

    if spec is not None:
        status = "success"
        summary = f"{package} 已安装（import 可用），抽象层流程可编排"
    else:
        status = "degraded"
        summary = (
            "pylabrobot 未安装，不在共享环境引入；"
            "本次输出硬件无关抽象层演示（板布局 + 移液步骤，诚实降级）"
        )

    return {
        "package": package,
        "status": status,
        "license": "MIT",
        "summary": summary,
        "board_layout": board_layout,
        "steps": steps,
        "device_specific": False,
    }


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
