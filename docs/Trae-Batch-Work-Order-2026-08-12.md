# Trae 批量工单 — 2026-08-12 紧急清仓

> 来源：沈遥（Hermes）  
> 施工者：林楠（Trae IDE）  
> 状态：用户出远门，能做的全做，不等任何人  
> 原则：零阻塞 → 纯代码/文档/分析，不需要用户输入

---

## 已完成 ✅（无需再动）

| 项目 | 提交 | 状态 |
|------|------|------|
| paper-miner 四靶子交付 | `b180b7e` | ✅ 已推 |
| GitHub Trending 六项目评估 | `af5d0a5` | ✅ 已推 |
| Agent Skills 互通映射 | `413ebd0` | ✅ 已推 |
| 8月11日安全审计(9模块) | `840c8a7` | ✅ 已推 |
| SCI综述计划 / 目标迁移计划 | `840c8a7` | ✅ 已推 |
| LLM4Decompile MCP SPEC | `950cc9a` | ✅ SPEC 就位 |

---

## 🔴 工单 1：LLM4Decompile MCP 封装

**SPEC**：`docs/LLM4Decompile-MCP-SPEC-v1.md`（已就位，直接照着施工）

**步骤**：
1. 下载模型 `LLM4Binary/llm4decompile-1.3b-v2-GGUF` Q4_K_M → 本地 models 目录
2. `pip install llama-cpp-python mcp capstone`
3. 按 SPEC 写 `inference.py` + `mcp_server.py`
4. 写 `test_polish.py` 测试 Ghidra 润色路径
5. 跑通 health check

**周期**：1-2 天  
**提交路径**：`scratchpad/llm4decompile-mcp/`（新建目录）

---

## 🔴 工单 2：安全审计 LOW 修复项批量清

**SPEC**：`docs/*-security-audit-2026-08-11.md`（9 个文件）

每个审计报告末尾有具体的修复清单。**只做 LOW 项**（MEDIUM/HIGH 留给沈遥审查后决定）。

**优先级排序**（按影响面）：

| 模块 | 审计文件 | 预估工作量 |
|------|---------|-----------|
| apiserver | `apiserver-security-audit-2026-08-11.md` | 0.5h |
| mcpserver | `mcpserver-security-audit-2026-08-11.md` | 0.5h |
| agentserver | `agentserver-security-audit-2026-08-11.md` | 0.5h |
| frontend | `frontend-security-audit-2026-08-11.md` | 0.5h |
| voice | `voice-security-audit-2026-08-11.md` | 0.3h |
| neko-electron-shell | `neko-electron-shell-security-audit-2026-08-11.md` | 0.3h |
| guide-rag-system | `guide-rag-system-security-audit-2026-08-11.md` | 0.5h |
| mod-summermemory | `mod-summermemory-tests-security-audit-2026-08-11.md` | 0.3h |
| scratchpad-repo | `scratchpad-repo-security-audit-2026-08-11.md` | 0.3h |

**注意**：
- 每修一个模块，单独 commit（`fix(apiserver): 安全审计LOW项修复`）
- 不要批量 commit——方便沈遥逐模块 review
- 如果某个 LOW 项修复需要动架构，跳过并标注 `[SKIP: 需要架构变更]`

**周期**：总计 3-4 小时，可以分批推

---

## 🟡 工单 3：GridSetup SDR 模块分析（如果可访问）

**前提**：GitHub 上 `rounakagrawal7/GridSetup` 可以 clone

**任务**：
1. `git clone --depth 1` GridSetup
2. 分析其 SDR/无线电集成方式（什么硬件？什么驱动/库？）
3. 提取卫星追踪数据源（什么 API？什么格式？）
4. 输出一份分析报告：`docs/GridSetup-Analysis-Report.md`

**报告模板**：
```
# GridSetup 分析报告
## SDR 集成
- 硬件支持: [列表]
- 驱动/库: [名称 + 许可]
- 数据流: [架构简图]
## 与 N.E.K.O. radio 层嫁接可行性
- 可直接复用: [列表]
- 需适配: [列表]
- 不可用: [列表 + 原因]
## 卫星追踪
- 数据源: [API/文件]
- 更新频率: [时间]
```

**周期**：2-3 小时（分析 + 写报告）  
**如果 GitHub 被墙 clone 不下来**：发 `git clone` 报错信息给沈遥，他用云服中转

---

## 🟡 工单 4：Trae 自己能做的事自查

翻一遍以下文件，如果里面有「待办」「TODO」「FIXME」标注的，评估能不能独立做：

```bash
# 在 scratchpad 里搜所有待办标记
grep -rn "TODO\|FIXME\|HACK\|XXX\|待办\|待做" --include="*.py" --include="*.md" --include="*.js" --include="*.ts" .
```

能做的直接做，不能做的汇总成「留给沈遥的待办清单」→ `docs/Trae-Blocked-TODO-2026-08-12.md`

**周期**：0.5h 扫描 + 不确定时间的执行

---

## ⚫ 不要碰的

- **不要改架构** — 安全审计 MEDIUM/HIGH 项、N.E.K.O. 拓扑变更
- **不要动 SCI 综述** — 等导师确认方向
- **不要动 Nostr/prime-agent** — 观望阶段
- **不要删文件** — 任何清理操作留给沈遥

---

## 提交规范

```
<type>(<scope>): <简短描述>

<详细说明（可选）>
```

- type: `feat` / `fix` / `docs` / `refactor` / `test`
- scope: 模块名（apiserver, mcpserver, llm4decompile-mcp 等）
- 每完成一个工单的**一个子任务**就 commit+push，不要攒

---

## 时间估算

| 工单 | 预估时间 | 可并行？ |
|------|---------|---------|
| 工单1 LLM4Decompile MCP | 1-2天 | 独立 |
| 工单2 安全审计LOW修复 | 3-4h | 独立 |
| 工单3 GridSetup分析 | 2-3h | 独立（需GitHub可达） |
| 工单4 TODO扫描 | 0.5h+ | 先做，可能产生新任务 |
| **总计** | **~2天** | 三线并行 |

---

## 紧急联系

如果遇到阻塞（网络不通、依赖装不上、模型下载失败、看不懂 SPEC）→ 在 Gitee 上提 issue 或直接 push 阻塞报告到 `docs/Trae-Blocked-*.md`，沈遥回来处理。
