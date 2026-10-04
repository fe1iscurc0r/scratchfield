# -*- coding: utf-8 -*-
"""cozo 记忆 sidecar 试路径（W65-07 · standalone 二进制路径试点，mock）。

评估结论：standalone 二进制路径试点（下载/启动/建库/读写最小流程）。网络不可达
时写步骤文档 + mock。对比路径 A（standalone）/ C（真机再验）可行性。结论标注：
不阻塞其他工单，试点结果待用户真机确认。纯标准库。
"""
from __future__ import annotations


# mock 的 cozo 试运行：不依赖真实 cozo 二进制，仅模拟建库/读写流程
class MockCozo:
    """mock cozo 引擎：建库 + 读写（诚实降级，网络/二进制不可达时用）。"""
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def create_table(self, name: str) -> None:
        self.data.setdefault(name, "")

    def put(self, table: str, key: str, value: str) -> None:
        self.data[f"{table}:{key}"] = value

    def get(self, table: str, key: str) -> str | None:
        return self.data.get(f"{table}:{key}")


def trial_plan() -> dict:
    """试点计划：路径 A/C 决策树 + 下载/启动命令（mock）。"""
    return {
        "path_a": {
            "desc": "standalone 二进制路径（下载/启动/建库/读写最小流程）",
            "download": "curl -L <cozo-release-url> -o cozo && chmod +x cozo",
            "start": "./cozo server --path ./cozo_data",
            "note": "网络不可达时走 mock（MockCozo）",
        },
        "path_c": {
            "desc": "真机再验（试点通过后再上真机）",
            "note": "结果待用户真机确认，不阻塞其他工单",
        },
        "decision": "先 A 后 C；A 失败或网络不可达则标记阻塞并回报",
    }


if __name__ == "__main__":
    c = MockCozo()
    c.create_table("mem")
    c.put("mem", "k1", "v1")
    print("读回:", c.get("mem", "k1"))
    print("试点计划:", trial_plan()["decision"])
