"""W71-09 · ADIF 解析/生成（吞入自 x-qsl 思路，ADIF 为开放标准格式）。

ADIF（Amateur Data Interchange Format）业余无线电日志交换格式：
  记录由若干字段组成，字段形如 <FIELD:LENGTH>value，记录以 <EOR> 结束，头字段以 <EOH> 结束。

本模块自研实现 ADIF 的解析与生成（开放标准，无版权风险），供 IC-705 电台线
（呼号 BG5GXO）做日志导入导出（对接 LoTW/eQSL）。纯标准库。
"""
from __future__ import annotations

EOR = "<EOR>"
EOH = "<EOH>"


def parse_adif(text: str) -> list[dict]:
    """解析 ADIF 文本 → 记录列表（每条为 {字段名: 值}）。"""
    records = []
    current = {}
    i = 0
    n = len(text)
    while i < n:
        if text.startswith(EOR, i):
            if current:
                records.append(current)
                current = {}
            i += len(EOR)
        elif text.startswith(EOH, i):
            i += len(EOH)
        elif text[i] == "<":
            j = text.find(">", i)
            if j == -1:
                break
            tag = text[i + 1:j]
            name, _, size_s = tag.partition(":")
            size = int(size_s) if size_s else 0
            value = text[j + 1:j + 1 + size]
            current[name.strip().upper()] = value
            i = j + 1 + size
        else:
            i += 1
    if current:
        records.append(current)
    return records


def generate_adif(records: list[dict]) -> str:
    """记录列表 → ADIF 文本。"""
    parts = []
    for rec in records:
        for name, value in rec.items():
            v = str(value)
            parts.append(f"<{name.upper()}:{len(v)}>{v}")
        parts.append(EOR)
    return "".join(parts) + "\n"


def run_demo() -> None:
    rec = {"CALL": "BG5GXO", "BAND": "20m", "MODE": "SSB", "QSO_DATE": "20260902"}
    text = generate_adif([rec])
    print("[W71-09] ADIF 生成：", text.strip())
    print("[W71-09] ADIF 解析：", parse_adif(text))


if __name__ == "__main__":
    run_demo()
