# 工单 244d 完工报告 · 把 `ruff check .` 从 314 errors 清到 0

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）
> 日期：**2026-10-15** · 基线：main `9c7d2dcfbd`
> 触发：工单244c 实测发现「`ruff check .` = **314 errors**，且**非本轮引入**」——
> 当时把结论写进了 ci.yml 注释并列为**待决策项**；用户拍板「A 自己搞定（不碰 NEKO）」。
> 变更文件：**58 个**（1 新增 + 57 修改）

---

## §0 · 交付事实

| 项 | 值 |
|---|---|
| `ruff check .`（全仓） | **314 errors → 0**（`All checks passed!`） |
| 变更文件 | **58** = 1 新增（回归守卫）+ 57 修改 |
| 改动量 | **+134 −111**（归一化行尾后） |
| 行尾 | **58 个文件全部 LF** —— 与各自 **真 blob** 口径逐一致（见 §4.1 的坑） |
| 新增测试 | `tests/test_agent_server_parts_imports.py`（**26 用例**） |
| 相关测试 | 守卫 26 + smoke 6 = **32 passed**；更大批次 **127 passed / 1 skipped** |
| 回归 | **零**（前后失败清单差集：`只在 AFTER 失败 = 空`） |
| NEKO | **未触碰**（配置本就 exclude NEKO，实测 314 条里 **0 条**落在 NEKO） |

---

## §1 · 314 errors 到底是「哪个部分」的问题

**全部集中在「工单204 任务一」那次巨石拆分留下的星号导入**，其余是顺手可清的机械项：

| 规则 | 数量 | 位置 | 性质 |
|---|---|---|---|
| **F405** | **254** | **`agentserver/agent_server_parts/**`（10 个文件）** | `undefined-local-with-import-star-usage` —— **本次的主因** |
| I001 | 53 | 47 个文件（`agentserver`/`apiserver`/`mcpserver`/`system`/`tools`/`scripts`/`tests`/`github_haul`） | 导入块未排序（可自动修） |
| F541 | 3 | `github_haul/nuwa-skill/**` ×2、`tools/monolith_metrics.py` | 无占位符的多余 `f` 前缀 |
| UP034 / SIM117 / UP012 / SIM300 | 各 1 | `apiserver/routes/knowledge_openai.py` 等 | 可自动修 |

按顶层目录：`agentserver` **274**、`apiserver` 15、`github_haul` 8、`mcpserver` 7、
`tests` 3、`system` 3、`tools` 2、`scripts` 2。**`NEKO` 0**。

### 1.1 根因（一句话）

`tools/split_agent_server.py`（工单204 任务一的 codemod）给每个子模块生成的头部是::

    from .common import *  # noqa: F401,F403
    from .common import Modules, logger  # noqa: F401

`# noqa` 只压了 **F401/F403**，**压不住 F405** ——
于是「用到但不在显式导入里的名字」（`HTTPException` / `Any` / `config` / `asyncio` / …）
每次出现都被记一条 F405，累计 **254** 条。而 CI 的 lint job 默认被 `ENABLE_LINT` 关掉
⇒ **从拆分那天起没人发现**（与 ci.yml 注释里记的前端 369 error 是同一批事故的两个半边）。

---

## §2 · 两段处置

### 2.1 第一段：60 个机械修复（`ruff check . --fix`）

只跑**安全修复**（I001 53 / F541 3 / UP034 1 / SIM117 1 / UP012 1 / SIM300 1），
涉及 47 个文件、`+80 −93`。

**三处真正的语句改动**（逐条人工核对过，均语义等价）：

| 文件 | 改动 | 为什么等价 |
|---|---|---|
| `apiserver/routes/knowledge_openai.py` | 嵌套 `async with A: async with B:` → `async with A, B:`（SIM117） | Python 语言规范明确：合并 with 项等价，退出顺序仍为逆序 |
| `scripts/doctor.py` | `if (3, 13) <= v[:2]:` → `if v[:2] >= (3, 13):`（SIM300） | 元组比较换序，等价 |
| `github_haul/**` ×2、`tools/monolith_metrics.py` | 去掉无占位符字符串的 `f` 前缀（F541） | 无 `{}` ⇒ 去掉 `f` 后字符串恒等 |
| `tools/split_agent_server.py` | `.encode("utf-8")` → `.encode()`（UP012） | utf-8 是默认编码 |

### 2.2 第二段：254 个 F405（星号导入 → **显式名单**）

做法：**完全由 ruff 自己的 F405 报告驱动** —— 它点名的就是「只能来自星号导入」的名字；
与 `common.py` 的 star 可导出名求交后写成显式列表，**不多不少**。

- 覆盖 **9 个文件**（`health.py` 无 F405，其星号导入是纯冗余 ⇒ 直接删）
- **34 个去重名字**（254 是出现次数）
- 断言过：被点名的名字**全部**在 `common` 的导出集内（否则说明代码本就有真 bug）

**边界确认（改前就查过）**：

1. **没有任何下游代码按名从 part 模块导入** ——
   只有 `agent_server.py` 导入**模块本身**（导入即注册路由），并从 `common` 取 `Modules`、
   从 `lifecycle` 取 `app`（两者都保留）。
2. **没有模块级 `getattr()` / `globals()` / `eval`** —— 不存在动态名字查找。
3. `common.py` 的 `sys.path` 插入副作用**仍然保留**（显式导入同样会先加载 `common`）。

---

## §3 · 三层验证（这是本单最重要的部分）

### 3.1 静态：import 集合（多重集）逐文件比对

| 结果 | 文件数 | 含义 |
|---|---|---|
| **import 多重集完全不变** | **47** | 纯排序/换行，零增删 |
| import 变化 | **10** | **唯一**变化是 `from .common import *` → 显式名单（每个新增名都在 F405 点名集内） |
| 意外变化 | **0** | — |

### 3.2 运行时：入口契约等价

对修复前后的两棵源码树，在**独立子进程**里导入 `agentserver.agent_server`：

| 项 | before | after |
|---|---|---|
| 模块可导入 | ✅ | ✅ |
| `app` 存在 | ✅ | ✅ |
| **路由总数** | **75** | **75** |
| **路由集合（方法+路径）完全相同** | — | ✅ **True** |
| 入口导出名数 | 11 | 11 |

> 注：part 模块**自身的命名空间确实变窄了**（少了它们**用不到**的名字，例如 `agents` 37→23）。
> 这是**预期效果**（那些名字是星号导入的副产品），且已由 §2.2 的三条边界确认「无人依赖」。

### 3.3 回归：既有测试 + 失败清单差集

仓里**本来就有**安全网 `tests/test_agent_server_smoke.py`（工单204 任务一写的），
它断言「**路由总数必须等于拆分前基线 75**」+ 10 条关键路由 + `/health` **真调用**（TestClient）。

在同一个测试批次（9 个文件）上跑前后两棵树：

| | before | after |
|---|---|---|
| 失败 | **20** | **1** |
| 通过 | 108 | **127** |
| **只在 after 失败（= 我引入的回归）** | — | **空 ✅** |
| 只在 before 失败（= 我修好的） | — | 19（全是新守卫在旧树上的红） |
| 两边都失败（= **既有失败**） | — | 1（`test_voice_realtime_import_does_not_require_qwen_optional_dependency`） |

### 3.4 新增：把 lint 纪律变成**会真跑的测试**

`tests/test_agent_server_parts_imports.py`（26 用例，纯标准库 `ast`，**不依赖 ruff**）：

| 用例 | 守什么 |
|---|---|
| `test_no_star_import_in_parts` | 10 个 part 文件里**不得**再出现星号导入（**根因**） |
| `test_no_unresolvable_names_in_parts` | 每个文件「用到却全模块没人绑定、也不是内置名」的名字必须为空（**自带的 F405 等价检查**） |
| `test_parts_explicitly_import_from_common` | 每个 part 必须显式从 `.common` 取共享名 |
| `test_part_modules_are_importable` | 11 个 part 都必须能导入 |

**守卫有牙齿**（实测）：在**未修复**的树上跑 = **19 failed**；在修复后的树上 = **全绿**。

> 为什么值得单独做：CI 的 lint job 默认关闭 ⇒ 「靠 lint 守」等于没有守。
> 这条守卫在 `pytest` 里跑，**不依赖那个闸门**。

---

## §4 · 顺带发现（都值得记一笔）

### 4.1 ⚠️ `git archive` **不是** blob 忠实的（本次真踩到）

为了「不用全仓 clone 也能验」，我一直用 `git archive <sha>` 导子树。
但 **`git archive` 会按 `.gitattributes` 的 `eol` 属性做行尾转换** ——
本仓是 `* text=auto eol=crlf`，于是导出来的 `.py` **全是 CRLF**，
而它们 **真 blob 全是 LF**（`git cat-file blob <sha>:<path>` 实测 57/57 全是 LF）。

我一度按 archive 的假象把 10 个文件转成 CRLF、又全部转回 —— 白绕一圈。
**正确判据只有一个：取真 blob 字节**（`git cat-file blob` 或 API base64）。
⇒ 与 REFERENCE §R9「别信 tarball / git checkout」同源，本次把 **`git archive` 也拉进黑名单**。

### 4.2 `tools/split_agent_server.py` 是**已死**的 codemod

它的输入 `agentserver/agent_server.py` **已被它自己的输出**（约 30 行薄入口）取代
⇒ 重跑 `--write` 无意义且会破坏 `agent_server_parts/`。
已在文件头补「**已冻结**」说明（含「若将来真要重跑，必须先改 `gen_module()` 那行，否则 F405 全部复活」）。

---

## §5 · 未落地 / 需接手

1. **`ENABLE_LINT` 仍未打开**。清到 0 之后，打开它 lint job **应当变绿**（前端 244c 实测 0 error、
   后端本次清到 0）；但**没有实测过「job 真跑」**（受 GitHub 账单闸门限制，见 ci.yml 注释），
   故**不冒充已验证**。若将来恢复 CI 计费，建议先 `--dry-run` 式地只跑 lint 确认。
2. **`github_haul/nuwa-skill/**` 的 7 个文件**是技能示例脚本，本次只做了 I001/F541 机械修复。
   若它们属于「不该进 lint 范围」的素材，更合适的做法是把该目录加进 ruff 的 `exclude`
   （本次**未改配置** —— 那是策略决定，不该由修 lint 的人顺手做）。
3. **既有的 1 个失败**（`test_voice_realtime_import_does_not_require_qwen_optional_dependency`）
   与本单无关（前后都失败），留给对应模块的人。

---

## §6 · 复现方式

```bash
# 1) 取该 commit 的 *.py + **全部 21 个** pyproject/ruff 配置（注意 git archive 会转行尾！）
git archive <sha> -- '*.py' $(git ls-tree -r --name-only <sha> | \
    grep -E '(^|/)(pyproject\.toml|ruff\.toml|\.ruff\.toml|setup\.cfg|tox\.ini)$') | tar -x

# 2) 全仓 lint（跑完清 ruff_cache/，它在 CWD 建）
ruff check . --output-format=concise
ruff check . --statistics

# 3) 新增守卫 + 既有安全网
python -m pytest tests/test_agent_server_parts_imports.py tests/test_agent_server_smoke.py -q

# 4) 想自己验「真 blob 行尾」：
git cat-file blob <sha>:<path> | head -c 400 | xxd | grep -c 0d0a
```
