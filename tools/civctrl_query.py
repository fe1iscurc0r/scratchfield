#!/usr/bin/env python
"""从 deep_disasm.json 提取关键分析信息分批打印"""
import json
import sys

JSON_PATH = r"d:\my git\scratchpad\tools\pe_analysis_output\CivCtrl_deep_disasm.json"

def load():
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)

def fmt_insn(ins):
    return f"  0x{ins['addr']:08x}: {ins['mnemonic']:8s} {ins['op_str']:40s} ; {ins['bytes']}"

def print_section(title):
    print(f"\n{'='*70}\n{title}\n{'='*70}")

def print_method(j, label_substr, limit=None):
    for m in j["internal_methods"]:
        if label_substr in m["label"]:
            print_section(f"INTERNAL: {m['label']} @ {m['va']}")
            insns = m["instructions"]
            if limit:
                insns = insns[:limit]
            for ins in insns:
                print(fmt_insn(ins))
            return
    print(f"[!] not found: {label_substr}")

def print_export(j, name_substr, limit=None):
    for e in j["exports_deep"]:
        if name_substr in e["name"]:
            print_section(f"EXPORT: {e['name']} ord={e['ordinal']} @ {e['va']}")
            insns = e["instructions"]
            if limit:
                insns = insns[:limit]
            for ins in insns:
                print(fmt_insn(ins))
            return
    print(f"[!] not found: {name_substr}")

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "summary"
    j = load()

    if mode == "summary":
        print_section("STRING XREF SUMMARY")
        for x in j["string_xrefs"]:
            if x.get("found"):
                print(f"  '{x['string'][:50]}' @ {x['string_va']} ({x['string_section']}) xrefs={x['xref_count']}")
                for xr in x["xrefs"][:3]:
                    print(f"      xref @ {xr['xref_va']}  func_start={xr['func_start']}")
        print_section("SERIAL CONFIG FUNC")
        sc = j["serial_config"]
        print(f"  baud_string_va = {sc.get('baud_string_va')}")
        print(f"  xref_va        = {sc.get('xref_va')}")
        print(f"  func_start     = {sc.get('func_start')}")
        print(f"  func_disasm    = {len(sc.get('func_disasm', []))} instructions")
    elif mode == "serial":
        sc = j["serial_config"]
        print_section(f"SERIAL CONFIG FUNC @ {sc['func_start']}")
        for ins in sc.get("func_disasm", []):
            print(fmt_insn(ins))
    elif mode == "handle":
        print_method(j, "HandleResolver")
        print_method(j, "HandleRelease")
    elif mode == "send":
        print_method(j, "0x402190_civSend", limit=120)
    elif mode == "recv":
        print_method(j, "0x402624_civRecv", limit=120)
    elif mode == "getrecv":
        print_method(j, "GetRecvSize")
    elif mode == "setters":
        # 打印所有 setter 实现 (短)
        for label in ["SetAddress", "SetAddPreamble", "SetCivTot", "SetRetryFA",
                      "SetWaitTime", "SetConType", "ResetOthAnsCount", "ResetRxByteCount",
                      "IsSendEnable", "GetOthAnsCount", "GetRxByteCount", "GetConType",
                      "civClose"]:
            print_method(j, label, limit=60)
    elif mode == "exports_all":
        for e in j["exports_deep"]:
            print_section(f"EXPORT {e['name']} ord={e['ordinal']} @ {e['va']}")
            for ins in e["instructions"]:
                print(fmt_insn(ins))
    elif mode == "civclose_impl":
        print_method(j, "0x401e28_civClose", limit=120)
    elif mode == "imm_fe_fd":
        print_section("IMM 0xFE / 0xFD USAGE (CI-V frame construction traces)")
        for u in j["imm_fe_fd_usage"]:
            print(f"  {u['va']:>12}  {u['mnemonic']:8s} {u['op_str']:40s}  imm={u['imm']}  func={u.get('func_start')}")
    elif mode == "iat":
        print_section("IAT THUNKS")
        for t in j["iat_thunks"]:
            print(f"--- {t['label']} @ {t['va']} ---")
            for ins in t["instructions"]:
                print(fmt_insn(ins))
            print()
    elif mode == "state":
        # 打印状态机函数, 通过子模式选择
        sub = sys.argv[2] if len(sys.argv) > 2 else "all"
        for m in j["state_machine_funcs"]:
            if sub == "all" or sub in m["label"]:
                print_section(f"STATE: {m['label']} @ {m['va']}")
                for ins in m["instructions"]:
                    print(fmt_insn(ins))
    elif mode == "internal":
        sub = sys.argv[2] if len(sys.argv) > 2 else "all"
        for m in j["internal_methods"]:
            if sub == "all" or sub in m["label"]:
                print_section(f"INTERNAL: {m['label']} @ {m['va']}")
                for ins in m["instructions"]:
                    print(fmt_insn(ins))

if __name__ == "__main__":
    main()
