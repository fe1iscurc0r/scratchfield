# 生态情报：Agent Skills 规范 + MCP 服务器（2026-08-22 深夜）

> 来源：agentskills.io / hireblackout/awesome-mcp-servers / 行业博客
> 结论先行：**Agent Skills 规范已成行业标准，我们的 skills 体系需要对齐**

## 一、Agent Skills 规范（agentskills.io/specification）

**现状**：截至 2026-06，约 40 个产品支持该标准：
Claude / OpenAI Codex / GitHub Copilot / VS Code / Cursor / Gemini CLI / Goose / OpenCode / Databricks Genie Code / Snowflake Cortex Code

**规范核心**（SKILL.md 结构）：
- YAML frontmatter：`name` + `description` 两字段必填，其余可选
- Markdown body：渐进式披露（先触发后展开）
- 跨 agent 兼容：同一 skill 可在所有支持产品中运行

**对我们的影响**：
- 本地 186 个 skills 如果遵循规范 → 未来可跨 agent 用（Claude/Codex/Cursor）
- **gap 评估**：scratchpad skills/ 部分自研（huashu-nvwa 已对齐，graphify 官方支持 Hermes）——需要抽查几个 skills 的 frontmatter 是否规范
- **行动**：写一个 skills 规范体检脚本（扫描 name/description 缺失项）→ 批量修复

## 二、MCP 服务器生态（top 清单）

### Essential Trinity（必备三件套）

| MCP | 用途 | 安装 | 我们的状态 |
|-----|------|------|-----------|
| **Context7** | 拉最新库文档防幻觉（37k 下载，500+ Reddit） | `npx @upstash/context7-mcp` | ❌ 未接 |
| **Sequential Thinking** | 强制逐步推理（多步问题 +47% 准确率） | `npx @modelcontextprotocol/server-sequential-thinking` | ⚠️ 类似我们 prompt 有，MCP 未接 |
| **Filesystem** | 文件读写免复制 | 内置多数客户端 | ✅ 已有 read/write 工具 |

### Tier 1 核心开发（名单摘录，后续可按需接入）

- GitHub MCP（官方，PR/issue/repo 管理）— 已有 gh CLI 等效
- Playwright（浏览器自动化）— 已有 browser 工具
- Fetch/Web 搜索 — 已有 web_search
- PostgreSQL / SQLite MCP — SQLite 已有，pg 未接（外部服务清单里有 toolbox-postgres）

### 值得新接的（差距分析）

1. **Context7** ⭐ 最值得——防 API 幻觉（我们写代码时经常猜 API，这是痛点）
2. **Sequential Thinking** ⭐ 对复杂推理有帮助（但 LLM 本身有 CoT，边际价值存疑）
3. Puppeteer/Playwright MCP 化（已有浏览器工具，不重复）

## 三、结论与行动

| 行动 | 优先级 | 说明 |
|------|--------|------|
| skills 规范体检脚本 | P1 | 扫描 186 skills 的 frontmatter，对齐 agentskills.io |
| Context7 MCP 接入 | P1 | 防 API 幻觉，写代码质量提升 |
| Sequential Thinking | P2 | 可接可不接，LLM 自带 CoT |
| 其余 MCP | P3 | 按需点单 |

**一句话**：生态风口是"规范统一"（agentskills.io）——我们站在对的位置（已在用 SKILL.md），差的是系统性对齐 + Context7 这个防幻觉神器。
