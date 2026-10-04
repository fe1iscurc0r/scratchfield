# -*- coding: utf-8 -*-
"""AC-01 · 固件无乘法指令验收：xtensa-esp32s3 反汇编按符号 grep。

原理：
  1. arduino-cli 编译 demo 后得到 .elf；
  2. xtensa-esp32s3-elf-objdump -dC 反汇编；
  3. 按符号切分指令流，对 mulfree::* 符号（热路径）grep 乘/除/取模族指令：
     mul*（mull/muluh/mulsh/mul.s/madd.s/msub.s）、quo*、rem*；
  4. mulfree::* 中出现任一即 FAIL；float_*（乘法对照组）应检出 >0，
     证明检查器本身有效（对照组必须"红"）。

用法（仓库根）：
  python tools/objdump_mulfree_check.py <path/to/demo.elf>
  # objdump 缺省自动探测 Arduino15 工具链，也可 --objdump 显式指定
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_OBJDUMP_DIR = (
    r"C:\Users\ASUS\AppData\Local\Arduino15\packages\esp32\tools\esp-x32")


def find_objdump(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    cands = sorted(Path(DEFAULT_OBJDUMP_DIR).glob(
        "*\\bin\\xtensa-esp32s3-elf-objdump.exe"))
    return cands[-1] if cands else Path()

SYM_RE = re.compile(r"^[0-9a-fA-F]+ <(.+)>:\s*$")
# 乘/除/取模族助记符（xtensa LX7: mull/muluh/mulsh + FPU mul.s/madd.s/msub.s；
# 除法在无硬件除核上走 __divsi3 软件例程，出现 quo*/rem* 同样算违规）
MUL_INSN_RE = re.compile(
    r"^\s*(mull|muluh|mulsh|mul\.s|madd\.s|msub\.s|mulu|quou|quos|remu|rems)\b")


def disassemble(objdump: Path, elf: Path) -> list[str]:
    out = subprocess.run([str(objdump), "-dC", str(elf)],
                         capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def split_symbols(lines: list[str]) -> dict[str, list[str]]:
    syms: dict[str, list[str]] = {}
    cur = None
    for line in lines:
        m = SYM_RE.match(line)
        if m:
            cur = m.group(1)
            syms.setdefault(cur, [])
        elif cur is not None:
            ins = line.split("\t")
            if len(ins) >= 3 and ins[2].strip():
                syms[cur].append(ins[2].strip())
    return syms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf", type=Path)
    ap.add_argument("--objdump", default=None)
    args = ap.parse_args()

    objdump = find_objdump(args.objdump)
    if not objdump.exists():
        print("FAIL: 未找到 xtensa-esp32s3-elf-objdump（--objdump 指定）")
        return 2
    if not args.elf.exists():
        print(f"FAIL: ELF 不存在: {args.elf}")
        return 2

    syms = split_symbols(disassemble(objdump, args.elf))
    mulfree = {k: v for k, v in syms.items()
               if k.startswith("mulfree::") or "::packet_features" in k}
    float_ref = {k: v for k, v in syms.items() if k.startswith("float_")}

    print(f"objdump: {objdump}")
    print(f"ELF: {args.elf}")
    print(f"mulfree::* 符号数: {len(mulfree)}, float_* 对照符号数: {len(float_ref)}")

    fail = False
    for name, insns in sorted(mulfree.items()):
        hits = [i for i in insns if MUL_INSN_RE.match(i)]
        status = "FAIL" if hits else "OK"
        if hits:
            fail = True
        print(f"  [{status}] {name}: {len(insns)} 指令, 乘/除/取模 {len(hits)}"
              + (f" -> {hits[:5]}" if hits else ""))
        for h in hits:
            print(f"        {h}")

    ref_hits = 0
    ref_total = 0
    for name, insns in sorted(float_ref.items()):
        n = sum(1 for i in insns if MUL_INSN_RE.match(i))
        ref_hits += n
        ref_total += len(insns)
        print(f"  [对照] {name}: {len(insns)} 指令, 乘/除/取模 {n}")
    if ref_hits == 0:
        print("  WARN: float 对照组未检出乘法指令——检查器有效性存疑（对照必须红）")
        fail = True

    print("结论:", "FAIL——热路径存在乘/除/取模指令" if fail
          else "PASS——mulfree::* 热路径无乘/除/取模指令，float 对照组有效")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
