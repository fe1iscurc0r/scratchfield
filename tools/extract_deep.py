#!/usr/bin/env python3
"""提取 deep_analysis.json 中关键信息打印输出"""
import json
from pathlib import Path

p = Path(r"d:\my git\scratchpad\tools\pe_analysis_output\deep_analysis.json")
with open(p, encoding="utf-8") as f:
    data = json.load(f)

# ── RadioSch.dll 部分 ────────────────────────────────
rs = data["radio_sch"]
print("=" * 80)
print("RadioSch.dll 深度反汇编")
print("=" * 80)
print(f"ImageBase: {rs['image_base']}")
print()

# 导出函数反汇编 - 全部打印
for exp in rs["exports_disasm"]:
    print(f"\n### Export: {exp['name']}  (RVA: {exp['rva']})")
    print("-" * 70)
    for i, ins in enumerate(exp["instructions"], 1):
        line = f"  [{i:2d}] {ins['addr']}: {ins['mnemonic']:8s} {ins['op_str']}"
        if "call_target" in ins:
            line += f"  ; → {ins['call_target']}"
        elif "call_target_rva" in ins:
            line += f"  ; → call rva={ins['call_target_rva']}"
        if "operands_resolved" in ins:
            for op_info in ins["operands_resolved"]:
                if "iat_call" in op_info:
                    line += f"  ; IAT={op_info['iat_call']}"
                if "string_ref" in op_info:
                    line += f"  ; STR=\"{op_info['string_ref'][:60]}\""
                if "imm_rva" in op_info:
                    line += f"  ; rva={op_info['imm_rva']}"
        print(line)

# SETUPAPI 调用点
print("\n" + "=" * 80)
print("RadioSch.dll SETUPAPI 调用点")
print("=" * 80)
for fn, callers in rs["setupapi_callers"].items():
    print(f"\nSetupAPI!{fn}  ({len(callers)} call sites):")
    for c in callers:
        print(f"  {c['caller_rva']}  {c['insn']}")

# USB 字符串
print("\n" + "=" * 80)
print("RadioSch.dll USB/VID/PID 字符串")
print("=" * 80)
for s in rs["usb_vid_pid_strings"]:
    print(f"  {s['rva']}: {s['str'][:100]}")

print("\n" + "=" * 80)
print("RadioSch.dll SETUPAPI/设备字符串")
print("=" * 80)
for s in rs["setupapi_strings"]:
    print(f"  {s['rva']}: {s['str'][:120]}")

# ── RemoteUty.exe 部分 ───────────────────────────────
ru = data["remote_uty"]
print("\n\n" + "=" * 80)
print("RemoteUty.exe 网络层分析")
print("=" * 80)
print(f"ImageBase: {ru['image_base']}")

# WS2_32 IAT
print("\n--- WS2_32.dll 导入 (18 个) ---")
for w in ru["ws2_32_iat"]:
    cnt = len(ru["ws2_32_callers"].get(w["function"], []))
    print(f"  {w['function']:20s}  IAT_RVA={w['iat_rva']}  callers={cnt}")

# 端口常量
print("\n--- htons 调用点（端口常量）---")
for pc in ru["port_constants"]:
    print(f"\n  caller_rva={pc['caller_rva']}  port_imm={pc.get('port_imm')}  port_dec={pc.get('port_dec')}")
    for ins in pc["pre_insns"]:
        print(f"    {ins['addr']}: {ins['mnemonic']:8s} {ins['op_str']}")

# WS2_32 调用点（仅前 3 个 + 总数）
print("\n--- WS2_32 调用点位置 ---")
for fn, callers in ru["ws2_32_callers"].items():
    if not callers:
        continue
    addrs = ", ".join(c["caller_rva"] for c in callers[:8])
    if len(callers) > 8:
        addrs += f" ... ({len(callers)} total)"
    print(f"  {fn:20s} ({len(callers):2d}): {addrs}")

# SETUPAPI 调用点
print("\n--- SETUPAPI 调用点 ---")
for fn, callers in ru["setupapi_callers"].items():
    print(f"\n  SetupAPI!{fn}  ({len(callers)} call sites):")
    for c in callers:
        print(f"    {c['caller_rva']}  {c['insn']}")

# 虚拟驱动字符串
print("\n--- 虚拟驱动字符串 ---")
for s in ru["virtual_driver_strings"][:30]:
    print(f"  {s['rva']}: {s['str'][:120]}")

# 网络协议字符串
print("\n--- 网络协议字符串 (前 40 条) ---")
for s in ru["network_protocol_strings"][:40]:
    print(f"  {s['rva']}: {s['str'][:120]}")

# UDP 协议字符串
print("\n--- UDP 协议字符串 (前 30 条) ---")
for s in ru["udp_protocol_strings"][:30]:
    print(f"  {s['rva']}: {s['str'][:120]}")
