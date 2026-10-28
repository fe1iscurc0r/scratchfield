# ci.yml「lint 记录」时效性刷新（2026-10-16）—— 承接 244c，补上 244d 漏掉的那次刷新

> 执行：Trae（GitHub 线）｜ 日期：**2026-10-16** ｜ 基线：main `184066678969`（工单247 落地点）
> 性质：**纯注释维护**（`.github/workflows/ci.yml` 一个文件；不含任何流水线行为变更）
> 依据：该文件自己写下的规矩 —— *「⚠️ 引用本注释前必须自己实测。只要动了 frontend/src/** 或后端 .py，
> 就重跑下面两步，并把日期更新到"最近一次实测"。」*

## §0 · 为什么要刷：注释腐烂了一天

| 时间 | main | `ruff check .` 实测 | 谁记的 |
|---|---|---|---|
| 2026-10-15 | `2a458623cd`（244b） | **314 errors** | 244c（PR #337）写进注释 |
| 2026-10-15（同日稍后） | `26bde1d18c`（244d） | **0**（清完了） | **没人刷新注释** |
| 2026-10-16（本次） | `184066678969` | **All checks passed** | 本单 |

⇒ 244d 的提交里 **`changed_files` 不含 `.github/workflows/ci.yml`**（已核：59 个文件里没有它），
而它恰恰**改了 57 个后端 `.py`** —— 按注释自己的规矩，那次就该刷新。没刷 ⇒「314」原样躺了一天。

**这正是注释开头警告的那种腐烂，第二次发生**（第一次是 2026-09-22 → 2026-10-12 那次「未复核」）。

## §1 · 本次实测（2026-10-16）

### 1.1 Python

```
ruff 0.16.4
cd <full tree> && ruff check .
→ All checks passed!          （0 error / 0 warning）
```

**期间变了什么**（`GET /compare/2a458623cd...main` 实测）：

| 项 | 实测 |
|---|---|
| commit 数 | **15**（244c 自身 + 其后 14 个） |
| changed_files | **178** |
| `frontend/**` 变更 | **0 个** |
| `*.py` 变更 | **94 个**（其中 **新增 36 个** —— 245~249 的 `kicad_mcp`/`rf_evolve`/`zhi_mcp`/`agentic_inventory` 等新模块） |
| 那 36 个新 `.py` 的违规数 | **0** |

### 1.2 frontend（CI 同款两步）

```
cd frontend && npm ci --no-audit --no-fund      # 965 packages / 39 s
node scripts/run-eslint.mjs
→ exit code 0 ；stdout + stderr 合计 0 字节
```

⚠️ **诚实标注**：这期间 `frontend/**` **一个文件都没变**（见 1.1 表）⇒ 这次是**复现确认**，不是新信号。
真要拿它当"前端没坏"的凭据，得等 frontend 真有改动时再跑一遍。

⚠️ 该脚本**没加 `--max-warnings`** ⇒ 只有 error 挂 CI；且 targets 不含 `tests/tools/scripts/docs`。

## §2 · 结论：闸门该不该打开？——**仍然保持关闭**，但理由换了

| | 244c 时的理由 | **现在（本单）** |
|---|---|---|
| 后端 | 314 errors（代码有欠账） | **0 —— 代码面已全绿** |
| 前端 | 0 error | 0 error |
| ⇒ 能否开 `ENABLE_LINT` | ❌ 会因为代码错而红 | ⚠️ **仍然不能开，但换成了另一个更硬的拦截** |

> **`ENABLE_LINT` 默认关闭的决定仍然是对的**，理由从「代码有 314 错」换成「**hosted runner 计费未解封**」——
> 就算代码全绿，runner 也不会被调度，job 会以"**未启动**"红着退出（那才是把红灯变成"狼来了"的真凶）。

保留意见（已写进注释）：CI 的 `pip install ruff` **未钉版本**、Node/依赖版本也与本机不同，
"本机 0"**不证明** CI 绿；但 0 与 314 不同量级，留给版本漂移的余量小得多。

## §3 · 改了什么（`.github/workflows/ci.yml`，28 行 → 34 行）

只替换「★ 最近一次实测」整块（原第 45~72 行），**流水线行为一行未动**：

- 记录日期/基线更新为 `2026-10-16` / `184066678969`；
- 后端从「❌ 314 errors」改为「✅ All checks passed」，并**解释为什么不与上一条矛盾**（同日先后 + 244d 漏刷）；
- 补上「94 个 `.py` 变更 / 36 个新增，零违规」的可核对数字；
- 前端保留 0 error / 0 字节，并**如实标注"期间 frontend 零变更 ⇒ 只是复现确认"**；
- 把「打开就会红」改写成「代码面绿、但计费未解封 ⇒ 仍保持关闭」，避免后人误据旧结论决策；
- **历史记录两条全部保留**（2026-10-15 的 314、2026-10-12 的未复核）—— 腐烂史本身是资产。

## §4 · 证据链：改的是不是"只有注释"

本文件是 **CRLF**（实测 169/169、零裸 LF）⇒ 改完做**三重证明**：

| # | 证明 | 结果 |
|---|---|---|
| ① | **去掉注释行与空行后逐行 `old == new`** | **63 行 → 63 行，逐行相同** ✅ |
| ② | `yaml.safe_load(old) == yaml.safe_load(new)`（对象级相等） | **相等** ✅（`jobs = [lint, smoke]`、`on` 触发条件不变） |
| ③ | 行尾仍**全 CRLF**、零裸 LF | **169/169、裸 LF = 0** ✅ |

> 落盘用 `open(..., newline="")` 直写字节（**不是** `write_text` —— 它在 Windows 会把 `\n` 翻成 `\r\n`）。
> 中途有一次用编辑器直接改一行，改完**立刻按字节复核**：CRLF 未被破坏（169/169、裸 LF 0）。

## §5 · 复现

```bash
# ① 后端（无需全仓 clone；本机实测用此法）
git archive <sha> -- '*.py' $(git ls-tree -r --name-only <sha> | \
    grep -E '(^|/)(pyproject\.toml|ruff\.toml|\.ruff\.toml|setup\.cfg|tox\.ini)$') | tar -x
ruff check .                    # → All checks passed；跑完清掉 ruff_cache/
#     ⚠️ 必须一并解出**嵌套**配置文件，否则 ruff 的逐文件配置发现会不全（2026-10-15 实测踩到）

# ② 前端（CI 同款两步）
cd frontend && npm ci && node scripts/run-eslint.mjs      # → exit 0、输出 0 字节

# ③ 期间变了什么
GET /repos/fe1iscurc0r/scratchpad/compare/2a458623cd...main   # frontend/** = 0、*.py = 94（新增 36）
```

> ⚠️ 作业纪律（本单实测）：行尾判据**只信逐字节统计**（`read_bytes()` + `count(b"\r\n")`）——
> `grep -c $'\r'` 在本机出现过对纯 LF 文件报满行数的假阳性。
