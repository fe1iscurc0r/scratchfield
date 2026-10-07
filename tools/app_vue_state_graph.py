"""分析 App.vue 的 `<script setup>` 状态依赖 → 生成依赖表（工单204 任务三 · App.vue 第一步）。

为什么用脚本：script 有 615 行、六类职责交织，人工读易漏；脚本能给出**可复核**的
「符号 → 它引用了哪些符号」表。

⚠️ 实现说明：`<script setup lang="ts">` 是 **TypeScript**，Python 的 `ast` 无法解析
（`//` 注释即报 `invalid character`）→ 本工具用**正则 + 声明区间**做粗粒度分析：
    1. 按行匹配顶层声明（const/let/function/async function/class/interface/type）；
    2. 每个声明的区间 = 本声明起点 → 下一个声明起点；
    3. 在区间内用词边界匹配其它顶层名 → 即依赖。
精度足以支撑 composable 边界划分（不追求类型级精确）。

用法：python tools/app_vue_state_graph.py [--json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.vue"

DECL_RE = re.compile(
    r"^(?:export\s+)?(?:(?:async\s+)?function|const|let|var|class|interface|type)\s+"
    r"([A-Za-z_$][\w$]*)"
)


def extract_script_setup(text: str) -> str:
    m = re.search(r"<script setup[^>]*>(.*?)</script>", text, re.S)
    if not m:
        raise SystemExit("未找到 <script setup>")
    return m.group(1)


def main() -> int:
    src = extract_script_setup(APP.read_text(encoding="utf-8"))
    lines = src.splitlines()

    decls: list[tuple[str, int]] = []          # (name, 0-based line)
    for i, ln in enumerate(lines):
        m = DECL_RE.match(ln)
        if m:
            decls.append((m.group(1), i))

    names = [n for n, _ in decls]
    spans: dict[str, tuple[int, int]] = {}
    for idx, (name, start) in enumerate(decls):
        end = decls[idx + 1][1] if idx + 1 < len(decls) else len(lines)
        spans[name] = (start, end)

    pat = {n: re.compile(r"(?<![\w$])" + re.escape(n) + r"(?![\w$])") for n in names}
    deps: dict[str, list[str]] = {}
    for name, (a, b) in spans.items():
        block = "\n".join(lines[a:b])
        block = block.replace(name, "", 1)      # 去掉自身声明行，避免自引用
        used = sorted(n for n in names if n != name and pat[n].search(block))
        deps[name] = used

    rev: dict[str, list[str]] = {n: [] for n in names}
    for n, ds in deps.items():
        for d in ds:
            rev[d].append(n)

    if "--json" in sys.argv:
        print(json.dumps({"decls": dict(decls), "deps": deps, "reverse": rev},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"顶层符号 {len(names)} 个 | script setup {len(lines)} 行\n")
    print(f"{'符号':<28}{'行':>5} {'依赖数':>6}  依赖")
    for n in sorted(deps, key=lambda x: (-len(deps[x]), x)):
        d = deps[n]
        print(f"{n:<28}{spans[n][0] + 1:>5} {len(d):>6}  " + ", ".join(d[:6]) + ("…" if len(d) > 6 else ""))
    print("\n=== 被依赖最多（抽 composable 时的关键边界）===")
    for n, users in sorted(rev.items(), key=lambda kv: -len(kv[1]))[:14]:
        if users:
            print(f"  {n:<28} 被 {len(users):>2} 处引用: " + ", ".join(users[:5]) + ("…" if len(users) > 5 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
