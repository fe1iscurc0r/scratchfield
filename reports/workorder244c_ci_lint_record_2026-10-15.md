# 工单 244c 报告 · ci.yml「lint 记录」时效性刷新（附 314 errors 实测发现）

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）
> 日期：**2026-10-15** · 基线：main `2a458623cd`（工单244b 的 squash 合并点）
> 性质：**维护性补丁** —— 履行 `memory/MEMORY.md` §B6 / `REFERENCE.md` §R3 记下的义务：
> 「该注释是**时效性断言、会腐烂** ⇒ 动了 `frontend/src/**` 或后端 `.py` 就重跑并更新」。
> 变更文件：**1 个**（`.github/workflows/ci.yml`，仅注释块）

---

## §0 · 为什么现在要动它

工单 243 / 244 / 244b 连续改了后端 `.py`（`mcpserver/esp32/**`、`mcpserver/toolknit_mcp/**`、
`tools/**`、`tests/**`），触发了 B6 的刷新义务。而 ci.yml 里 `lint` job 的
「★ 最近一次实测」仍停在 **2026-10-12 / `875fef7676`**。

用 GitHub `compare` 实测 `875fef7676...main`：**26 个 commit / 187 个文件**变更，其中

| 类别 | 数量 |
|---|---|
| `*.py` | **74** |
| `frontend/src/**` | **5**（App.vue / api/index.ts / api/domains/travel.ts / travel/components/TravelResultPanel.vue / travel/types.ts） |
| `*.md` | 61 |
| 其他 | 45 |

⇒ 注释里那两条结论（frontend 0 error、Python 沿用旧结论）**都需要重新实测**。

---

## §1 · 实测方法（**不需要全仓 clone**）

关键发现：**本地 `D:/my git/scratchpad` 虽 HEAD 落后且工作树脏，但对象库里有 main 的对象**
（`git cat-file -t <main-sha>` → `commit`）⇒ 可以用 `git archive` **精确导出**任意 commit 的子树：

```bash
# Python：导出该 commit 的全部 *.py + 全部嵌套配置文件
git archive <sha> -- '*.py' $(git ls-tree -r --name-only <sha> | \
    grep -E '(^|/)(pyproject\.toml|ruff\.toml|\.ruff\.toml|setup\.cfg|tox\.ini)$') | tar -x
ruff check .

# frontend：导出 frontend/ 后在临时目录 npm ci（**不动用户的工作树**）
git archive <sha> -- frontend | tar -x
cd frontend && npm ci --no-audit --no-fund && node scripts/run-eslint.mjs
```

⚠️ **踩到的坑**：`git archive <sha> -- '*.py' 'pyproject.toml'` **只会解出根目录那一个**
`pyproject.toml`（pathspec 不含斜杠时按根相对匹配），而仓库里有 **21 个** pyproject/ruff 配置
（含 `coupled/omnilimb-face/`、`vendor/martignac/.ruff.toml` 等）。ruff 是**逐文件向上发现配置**的
⇒ 少解配置文件会让结论失真。已改为显式列出全部 21 个路径。

---

## §2 · 实测结果

### 2.1 frontend —— ✅ 仍然全绿

| 项 | 值 |
|---|---|
| 命令 | `npm ci`（965 包 / **42 s**）+ `node scripts/run-eslint.mjs` |
| 实际范围 | `node node_modules/eslint/bin/eslint.js src electron eslint.config.js vite.config.ts` |
| 结果 | **exit code 0、stdout+stderr 合计 0 字节** ⇒ **0 error / 0 warning** |
| 期间变更 | `frontend/src/**` 5 个文件（见 §0）⇒ **重跑后仍全绿** |

### 2.2 Python —— ❌ **314 errors**（与注释里的旧结论矛盾）

| 规则 | 数量 | 说明 |
|---|---|---|
| **F405** | **254** | `undefined-local-with-import-star-usage` —— **全部集中在 `agentserver/agent_server_parts/**`**（工单204 任务一拆分产物） |
| I001 | 53 | unsorted-imports（可 `--fix`） |
| F541 | 3 | f-string 无占位符（可 `--fix`） |
| UP034 / SIM117 / UP012 / SIM300 | 各 1 | 均可 `--fix` |
| **合计** | **314** | 其中 **60 个可 `--fix` 自动修** |

`agentserver/agent_server_parts/` 各文件的错数：`openclaw.py` 76、`agents.py` 49、
`heartbeat.py` 28、`session.py` 25、`lifecycle.py` 24、`vision.py` 21、`travel.py` 18、
`dogtag.py` 14、`search.py` 8、`common.py` 2。

### 2.3 ⚠️ 关键对照：这不是 243/244/244b 引入的

同法在 **`875fef7676`（2026-10-12，即注释里那一次）** 实测：

```
Found 314 errors.   ← 分布逐项一致：F405 254 / I001 53 / F541 3 / UP034 1 / SIM117 1 / UP012 1 / SIM300 1
```

⇒ 两次快照的数字**完全相同**。结论：

- 这些错**不是 2026-10-12 之后引入的**，而是**那时就已经存在**；
- 所以注释里「沿用 2026-09-22 的结论（All checks passed）」**自 2026-09-22 之后就已经不成立**，
  2026-10-12 那次诚实地写了「Python 本次未复核」，但把它原样带了 3 天；
- 换言之：**这正是注释自己在开头警告的那种「时效性断言会腐烂」**，只不过腐烂的起点比记录的更早。

---

## §3 · 本次处置（只改注释，不动语义）

把 ci.yml 的「★ 最近一次实测」块（原第 **45..52** 行，8 行）替换为 2026-10-15 的完整记录（28 行），
含：两半的实测数字、`875fef7676` 的对照结论、「若启用 lint job 会红」的判断、
以及 §1 的复核命令与两个坑。

**刻意不动**的部分：`if: ${{ vars.ENABLE_LINT == 'true' }}` 闸门、`smoke` job、
`pip install ruff` 的未钉版本现状（本次只是**记录**它，不改它）。

### 验证（六项，全部通过）

| # | 检查 | 结果 |
|---|---|---|
| 1 | `yaml.safe_load` 前后对象**相等**（注释不影响 YAML 语义） | ✅ True |
| 2 | `difflib` 在 `n=0` 下的精确变动区间 = **原第 45..52 行** | ✅ 仅 8 行被替换 |
| 3 | 行尾：编辑前后均**全 CRLF**（该文件 138/138 CRLF，零裸 LF） | ✅ |
| 4 | **非注释行逐行未动**（剥离注释后两个列表相等） | ✅ True |
| 5 | `jobs.lint.if` 等关键键值不变 | ✅ |
| 6 | blob sha 自证（交付时） | 见 PR 正文 |

---

## §4 · 需要决策的一件事（不在本补丁范围内）

**若现在把 `ENABLE_LINT` 打开，`lint` job 会红**（前端绿 / 后端 314 红）。两条路：

1. **先清 314**：254 个 F405 需要把 `agentserver/agent_server_parts/**` 里的
   `from X import *` 改为**显式导入**。这不是机械修改 —— 得先弄清每个 `import *`
   实际用到哪些名字，属**真重构**，建议**单独开单**（并配回归，避免改出 NameError）。
   其余 60 个可 `--fix` 自动修。
2. **维持默认关闭**，把本段当作**已知欠账**引用（本次已把欠账写明在注释里）。

⚠️ 顺带记录：CI 里 `pip install ruff` **未钉版本**（拿 latest），而本机是 **0.16.8**。
本次数字基于 0.16.8；F405 / I001 这类规则不会从 314 变 0，但精确计数可能随上游版本小幅漂移。

---

## §5 · 复现方式

见 §1 的两段命令。要点复述：

- 用 `git archive` + **完整配置文件清单**（21 个）导出，别只解根 `pyproject.toml`；
- ruff 会在 **CWD** 建 `ruff_cache/`，跑完清掉（否则污染你的交付目录）；
- frontend 侧在**临时目录**里 `npm ci`，不要在用户的工作树里跑（会删掉它的 `node_modules`）。
