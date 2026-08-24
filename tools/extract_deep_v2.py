#!/usr/bin/env python3
"""提取 deep_analysis_v2.json 关键反汇编结果打印"""
import json
from pathlib import Path

p = Path(r"d:\my git\scratchpad\tools\pe_analysis_output\deep_analysis_v2.json")
with open(p, encoding="utf-8") as f:
    data = json.load(f)

out = []
def emit(s=""):
    out.append(s)

# ── RemoteUty.exe WS2_32 调用点 ──────────────────────
ru = data["remote_uty_net"]
emit("=" * 80)
emit("RemoteUty.exe WS2_32.dll 调用点上下文反汇编")
emit("=" * 80)
for fn, callers in ru["ws2_calls"].items():
    emit(f"\n\n=== WS2_32!{fn}  ({len(callers)} call sites) ===")
    for c in callers:
        emit(f"\n  --- caller_rva={c['caller_rva']} ---")
        for ins in c["context"]:
            mark = "  >>>" if ins["rva"] == c["caller_rva"] else "     "
            emit(f"  {mark} {ins['rva']:>10s}: {ins['mnemonic']:8s} {ins['op_str']}")

# 字符串引用
emit("\n\n" + "=" * 80)
emit("RemoteUty.exe 关键字符串引用")
emit("=" * 80)
for str_val, info in ru["string_xrefs"].items():
    emit(f"\n\n=== String: \"{str_val[:80]}\"  (rva={info['str_rva']}) ===")
    for r in info["refs"][:3]:
        emit(f"\n  --- ref_rva={r['ref_rva']} ---")
        for ins in r["context"]:
            mark = "  >>>" if ins["rva"] == r["ref_rva"] else "     "
            emit(f"  {mark} {ins['rva']:>10s}: {ins['mnemonic']:8s} {ins['op_str']}")

# ── RadioSch.dll SETUPAPI 调用点 ──────────────────────
rs = data["radio_sch_setupapi"]
emit("\n\n" + "=" * 80)
emit("RadioSch.dll SETUPAPI 调用点上下文反汇编")
emit("=" * 80)
for fn, callers in rs["setupapi_calls"].items():
    emit(f"\n\n=== SETUPAPI!{fn}  ({len(callers)} call sites) ===")
    for c in callers:
        emit(f"\n  --- caller_rva={c['caller_rva']} ---")
        for ins in c["context"]:
            mark = "  >>>" if ins["rva"] == c["caller_rva"] else "     "
            emit(f"  {mark} {ins['rva']:>10s}: {ins['mnemonic']:8s} {ins['op_str']}")

# USB 字符串引用
emit("\n\n" + "=" * 80)
emit("RadioSch.dll USB 字符串引用")
emit("=" * 80)
for str_val, info in rs["string_xrefs"].items():
    emit(f"\n\n=== String: \"{str_val[:80]}\"  (rva={info['str_rva']}) ===")
    for r in info["refs"][:3]:
        emit(f"\n  --- ref_rva={r['ref_rva']} ---")
        for ins in r["context"]:
            mark = "  >>>" if ins["rva"] == r["ref_rva"] else "     "
            emit(f"  {mark} {ins['rva']:>10s}: {ins['mnemonic']:8s} {ins['op_str']}")

result = "\n".join(out)
out_path = Path(r"d:\my git\scratchpad\tools\pe_analysis_output\deep_analysis_v2_summary.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(result)
print(f"Wrote {out_path}")
print(f"Size: {len(result)} bytes")
