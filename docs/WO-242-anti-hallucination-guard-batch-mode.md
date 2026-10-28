# 工单 242 · 跨工单验收守卫脚本（anti_hallucination_guard 统一封装）

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-242 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_242.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-242-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_242.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-15
> **触发**：师傅 13:35 下令"全部出下去"，本单配套 WO-238/239/240 同批验收防线
> **素材来源**：
> - WO-238 §5、WO-239 §5、WO-240 §7 三份工单都引 `python3 ~/scratchpad/scripts/anti_hallucination_guard.py --check-report <path> --detect-upstream`
> - 实际脚本在 `~/scratchpad/scripts/anti_hallucination_guard.py`，但**还没有"批量跨工单"模式**
> **关联 cron**：`a37ffecbd730` GitHub 扫货日报、`ad17cd9d341f` 论文流水线、`bda7241fa9c3` 授粉流水线-超限战轮

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 校验 `anti_hallucination_guard.py` 存在 | ✅ | 路径：`/home/ubuntu/scratchpad/scripts/anti_hallucination_guard.py` |
| 2 | 校对当前 CLI 参数 | ✅ | 已知支持 `--check-report <path>` + `--detect-upstream` 两条 |
| 3 | 校验 WO-238/239/240 三份的 §5/§7 是否真的引用同一条命令 | ✅ | 引用一致 |
| 4 | 看下脚本是否已经支持"批量"<sup>trailing scope</sup> | ❌ | 当前单文件模式——3 份 WO 跑 3 次 |

**核心痛点**：3 份 WO 的守卫调用分散、参数手填易错、合并守卫 vs 单工单守卫没区分；以后 WO 越多越乱。

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | 给 `anti_hallucination_guard.py` 加「跨工单批量模式」+ 写一份 `scripts/acceptance_helpers/wo_batch_check.sh` 包装 |
| **M** Measurable | ① 单 CLI 调用 `--check-workorders WO-238 WO-239 WO-240` 一次过 3 个；② 输出每 WO 的 FAIL/WARN 表 + 总计时；③ pytest 全过 |
| **A** Achievable | 现有脚本已是 Python，纯参数扩展（180 行内） |
| **R** Relevant | 师傅铁律 #②（vision 验真前不空喊）+日报 SKILL 950-957 行"防幻觉守卫·强制"已是事实标准 |
| **T** Time-bound | 1-2 天（W1 收尾即可，本任务不接 Trae 大任务）|

## §2 · 任务清单

### 任务 A · 改 anti_hallucination_guard.py

新增两个 CLI 接口（保留旧 `--check-report` 兼容性）：

```python
# 新增 CLI（argparse 适配）
parser.add_argument("--check-workorders", nargs="+",
                    help="批量检查指定工单（接受 WO-238 WO-239 等短名，自动拼 docs/WO-*.md 路径）")
parser.add_argument("--json", action="store_true",
                    help="JSON 输出（CI 友好）")
parser.add_argument("--fail-on-warn", action="store_true",
                    help="默认仅 WARN 不阻塞；本开关让 WARN=失败")
```

**核心算法**：
```python
def batch_check(wo_list: list[str]) -> dict:
    """对每个 WO 跑单文件 check，再合一份总表
    路径生成规则：scratchpad/docs/WO-<num>-*.md（按 glob）
    """
    results = {}
    for wo in wo_list:
        path = resolve_wo_path(wo)  # 例：WO-238 → docs/WO-238-pollination-r41-ammunition-intake.md
        results[wo] = check_single(path, detect_upstream=True)
    return results

if __name__ == "__main__":
    args = parser.parse_args()
    if args.check_workorders:
        out = batch_check(args.check_workorders)
        print(json.dumps(out, indent=2, ensure_ascii=False) if args.json
              else format_table(out))
```

**验收 grep/assert**：
```bash
# 1. 新 CLI 已注册
python3 ~/scratchpad/scripts/anti_hallucination_guard.py --help | grep -E -- "--check-workorders|--json|--fail-on-warn" | wc -l
# 期望：3

# 2. 批量调用一次过 3 份
python3 ~/scratchpad/scripts/anti_hallucination_guard.py --check-workorders WO-238 WO-239 WO-240
# 期望输出表格：每 WO 一行（FAIL/WARN 计数 + 总评）

# 3. JSON 模式可用
python3 ~/scratchpad/scripts/anti_hallucination_guard.py --check-workorders WO-238 WO-239 WO-240 --json | jq '.WO_238.fail, .WO_239.fail, .WO_240.fail'
# 期望：3 个 0
```

### 任务 B · 写 acceptance_helpers 包装

新文件 `scripts/acceptance_helpers/wo_batch_check.sh`（POSIX bash，无 Python 依赖）：

```bash
#!/usr/bin/env bash
# 用法：./wo_batch_check.sh [WO-238 WO-239 WO-240 ...]
# 默认扫 docs/WO-*.md 所有工单
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKORDER_DIR="${WORKORDER_DIR:-$HOME/scratchpad/docs}"
GUARD="${GUARD:-$HOME/scratchpad/scripts/anti_hallucination_guard.py}"

wo_list=("$@")
[ "${#wo_list[@]}" -eq 0 ] && wo_list=($(ls "$WORKORDER_DIR"/WO-*.md 2>/dev/null | xargs -n1 basename))

echo "=== 跨工单守卫 ($(date -Iseconds)) ==="
"$GUARD" --check-workorders "${wo_list[@]}"
```

**验收 grep/assert**：
```bash
# 1. 包装脚本存在且可执行
test -x scripts/acceptance_helpers/wo_batch_check.sh
# 2. 默认扫全部 WO
./scripts/acceptance_helpers/wo_batch_check.sh 2>&1 | tail -10
# 期望：3 份 WO 的最终守卫表
```

### 任务 C · pytest + CI 集成（轻量）

新文件 `tests/test_acceptance_helpers.py`：

```python
import subprocess, json, sys, pathlib

def test_check_workorders_runs():
    r = subprocess.run(
        ["python3", str(pathlib.Path("~/scratchpad/scripts/anti_hallucination_guard.py").expanduser()),
         "--check-workorders", "WO-238", "--json"],
        capture_output=True, text=True, timeout=30
    )
    assert r.returncode in (0, 1), f"guard crashed: {r.stderr}"
    data = json.loads(r.stdout)
    assert "WO_238" in data

def test_legacy_check_report_still_works():
    """回归测试：旧 --check-report 接口不能被破坏"""
    r = subprocess.run(
        ["python3", str(pathlib.Path("~/scratchpad/scripts/anti_hallucination_guard.py").expanduser()),
         "--check-report", "/tmp/wo238_final.md", "--detect-upstream"],
        capture_output=True, text=True, timeout=30
    )
    assert r.returncode in (0, 1)
```

**验收 grep/assert**：
```bash
python3 -m pytest tests/test_acceptance_helpers.py -q  # ≥ 2 passed
```

## §3 · 仓库与文件落点

- **工单 doc**：`scratchpad/docs/WO-242-anti-hallucination-guard-batch-mode.md`（本文件）
- **改文件**：`scratchpad/scripts/anti_hallucination_guard.py`
- **新文件**：`scratchpad/scripts/acceptance_helpers/wo_batch_check.sh`
- **测试**：`scratchpad/tests/test_acceptance_helpers.py`

## §4 · 风险与边界

| 风险 | 缓解 |
|------|------|
| 改 `anti_hallucination_guard.py` 破坏其他调用方 | 保留 `--check-report` 旧接口（任务 A 已明示兼容性）|
| `~/scratchpad/scripts/` 不在 git 仓库内 | 写入前 `git ls-files scripts/` 二次确认 |
| bash 包装在 macOS/BSD 不兼容 | 走 POSIX 子集（`set -euo pipefail` 通用）|
| pytest 装在 scratchpad 仓库？ | 仓库 `pyproject.toml` 有 pytest 配置（按已读 §0 摸排）|

**不在本工单范围**：
- 改 anti_hallucination_guard.py 的核心算法（仅扩 CLI）
- 加 CI 工作流（`.github/workflows/`）—— 留给 CI-Lint-Record 工单
- 写 v2 守卫（语义层 AI 验真）—— 留未来工单

## §5 · 验收不变量

```bash
# 1. 新 CLI 注册
python3 ~/scratchpad/scripts/anti_hallucination_guard.py --help | grep -c -- '--check-workorders\|--json\|--fail-on-warn'  # = 3

# 2. 批量一次过 3 份
python3 ~/scratchpad/scripts/anti_hallucination_guard.py --check-workorders WO-238 WO-239 WO-240 2>&1 | tail -3
# 期望：3 行均显示 FAIL=0

# 3. 包装脚本可执行
test -x scratchpad/scripts/acceptance_helpers/wo_batch_check.sh && echo OK

# 4. pytest
python3 -m pytest scratchpad/tests/test_acceptance_helpers.py -q | tail -1
# 期望：2 passed

# 5. 不动主流程
git diff --stat -- NEKO apiserver | wc -l   # = 0
```

## §6 · 与已有工单的关系

| 现有 | 关系 |
|------|------|
| WO-238/239/240 §5/§7 引用 `anti_hallucination_guard.py` | **硬化执行层**——本工单把"手动跑 3 次"变为"一次过" |
| `scripts/anti_hallucination_guard.py` | **改对象**（任务 A）|
| 日报 SKILL 950-957 行防幻觉守卫铁律 | **触发源**——8-23 立的铁律要求每次交付前跑守卫 |

---

> 沈遥出单 · 师傅如不调整，本单与 WO-238/239/240 同批 review
