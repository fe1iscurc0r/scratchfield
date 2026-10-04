# apify-data-mcp 勘察报告

> 工单：M-01 · apify-mcp-server 数据采集层勘察（只读）
> 智能体：MIKE（数据采集层）
> 日期：2026-08-28
> 结论摘要：**apify-mcp-server 可接入**，但"零成本"不成立——有 $5/月免费层（无需信用卡），超出即云计费；需 APIFY_TOKEN 为运行依赖（非否决项）。落点建议：**Lumo 情报模块（material_science 文献层）**，走 mcporter_bridge 外部接入为主、自建 handler 为辅。

---

## 一、上游事实核查（GitHub apify/apify-mcp-server，master 分支）

| 项目 | 实测值 |
|---|---|
| 仓库 | `apify/apify-mcp-server`（TypeScript，5193★，更新至 2026-08-28） |
| 许可 | MIT（GitHub API `license.spdx_id=MIT`） |
| npm 包 | `@apify/actors-mcp-server`，版本 0.15.4 |
| 默认分支 | `master`（README 走 `refs/heads/master`） |
| 协议/传输 | MCP server；托管端 **Streamable HTTP**（`https://mcp.apify.com`，已移除 `/sse` 旧端点）+ 本地 **stdio** |
| 鉴权 | `APIFY_TOKEN` 环境变量；托管端另支持 OAuth 或 `Authorization: Bearer <token>` 头 |
| 运行依赖 | **Node.js ≥ 22**（`.nvmrc`=24，`package.json engines.node>=22.0.0`）；Docker 可选（Docker Hub 有镜像）；pnpm 构建（`npx` 直接跑 dist，无需本地构建） |
| 安装/运行 | `npx @apify/actors-mcp-server`（本地 stdio）；托管直接连 `https://mcp.apify.com` |

**未认证可用**：`search-actors` / `fetch-actor-details` / `search-apify-docs` / `fetch-apify-docs` 四个工具在仅 `tools=search-actors` 等显式配置下无需 token；其余（含 `call-actor`、实际跑 Actor 取数据）都需要 APIFY_TOKEN。

---

## 二、能力清单表（预置工具）

默认工具集 = `actors` + `docs` + `apify/rag-web-browser` + `apify/web-fetch`（可用 `tools=` 参数显式裁剪）。

| 工具名 | 类别 | 作用 | 默认 |
|---|---|---|---|
| `search-actors` | actors | 搜 Apify Store 里的 Actor（爬虫/采集器） | ✅ |
| `fetch-actor-details` | actors | 取 Actor 详情：输入 schema、README、定价、输出 schema | ✅ |
| `call-actor` | actors | 调 Actor 跑一次并取结果（先 fetch-actor-details 拿 schema） | ✅ |
| `apify--rag-web-browser` | Actor | RAG 网页浏览：搜索 → 抓 top N URL → 返回内容 | ✅ |
| `apify--web-fetch` | Actor | 抓任意 URL，返回 Markdown/纯文本/HTML/链接（含 JS 渲染+反反爬） | ✅ |
| `search-apify-docs` | docs | 搜 Apify 文档 | ✅ |
| `fetch-apify-docs` | docs | 取文档页全文 | ✅ |
| `get-actor-run` | runs | 取某次 run 详情 | ⚡ 自动注入 |
| `get-dataset-items` | storage | 取数据集条目（过滤+分页） | ⚡ 自动注入 |
| `get-key-value-store-record` | storage | 取 KV 存储记录 | ⚡ 自动注入 |
| `abort-actor-run` | runs | 中止 run | ⚡ 自动注入 |
| `report-problem` | dev | 反馈问题 | ✅¹（仅 telemetry 开启且非 withheld 客户端） |

可选（`tools=` 显式启用）：`get-actor-run-list` / `get-actor-log` / `get-dataset` / `get-dataset-schema` / `get-key-value-store` / `get-key-value-store-keys` / `get-dataset-list` / `get-key-value-store-list` / `create-actor-task` / `get-actor-task` / `update-actor-task` / `publish-actor-task` / `unpublish-actor-task`。

> 调 Actor 后返回 run 元数据 + `summary`/`nextStep`，不直接含数据集条目——需按 `nextStep` 调 `get-dataset-items`（自动注入）拿正文。

---

## 三、依赖评估表

| 维度 | 结论 | 是否否决 |
|---|---|---|
| 运行环境 | Node ≥22（npx 免构建）；本仓天选7 已有 Node 运行时（mcporter_bridge 依赖 npx） | 否 |
| 鉴权 | APIFY_TOKEN（免费注册即得，无需信用卡） | 否（运行依赖） |
| 费用 | 免费层 $5/月（CU 计价，免费档 $0.2/CU，16GB 上限，5 并发）；超额度当月封禁至下月周期；另有 x402/AGI/Skyfire 按次付费 | 否（云计费为运行依赖，标注即可） |
| 许可 | MIT，只读参考/桥接无合规风险 | 否 |
| 网络 | 托管端需公网访问 mcp.apify.com；actor 结果经 Apify 云 | 否 |
| 数据合规 | 请求与 Actor 输入发往 Apify API 执行；隐私见 Apify Legal | 需知悉 |

**"零成本"判定：不成立。** 有 $5/月免费层（无信用卡门槛）可做少量调研/原型，但材料科研的批量文献/专利采集会消耗 CU 并触云计费。按工单硬约束，将"需付费 API"标注为运行依赖而非否决。

---

## 四、对照 Lumo 情报层现状（数据源覆盖）

Lumo 现有文献能力（SPEC-18 模块 C + material_science manifest）：
- `literature_search`：RAG 知识库内检索（本地已有内容，非实时采集）
- `matchat_search` / `matchat_chat` / `matchat_extract`：MatChat 2.0（松山湖 28 万篇论文知识库，AI 搜索/对话）
- 云服论文流水线（采集→精读）+ PDF→MD 本地入库

**空白**：没有直接的 arXiv/专利/新闻/期刊实时结构化采集入口。apify 可作为这一空白的外部补充。

| Lumo 想要的数据源 | Apify 对应 actor（实测搜到） | 免费/低费可跑 |
|---|---|---|
| arXiv 前沿文献 | `easyapi/arxiv-search-scraper`、`ryanclinton/arxiv-paper-search`、`parseforge/arxiv-scraper`、`scrapestorm/arxiv-article-metadata-scraper` | ✅（arXiv 本身开放 API，亦可自建，见接入方案） |
| 专利 | `khadinakbar/google-patents-scraper`、`johnvc/google-patents-api`、`constructive_calm/google-patents-intelligence`、`scrapier/google-patents-scraper` | ✅（免费层少量；批量计 CU） |
| 新闻 | `easyapi/google-news-scraper`、`data_xplorer/google-news-scraper-fast`、`xtracto/nytimes-scraper` | ✅（免费层少量） |
| 期刊/学术检索 | `easyapi/pubmed-search-scraper`、`ryanclinton/crossref-paper-search`、`ninhothedev/crossref-scraper`、`easyapi/google-scholar-scraper`、`johnvc/google-scholar-api` | ✅（PubMed/Crossref 有官方开放 API，亦可自建） |

---

## 五、接入建议

**主路径：mcporter_bridge 外部接入（推荐，零新代码）**
- 本仓已有现成桥接层 `mcpserver/mcporter_bridge.py`，通过 `mcporter` CLI 的 `list`/`call` 子命令加载外部 MCP 服务。
- `mcpserver/external_services.example.json` 已含 apify 占位条目（`type: http` + `url: https://mcp.apify.com` + `Authorization: Bearer ${APIFY_TOKEN}`）——**仅需启用并配 token 即可**。
- 待验证点：mcporter CLI 对 Streamable HTTP 远端（`type: http`）的支持程度；若仅支持 stdio，可改走 `npx @apify/actors-mcp-server` stdio 路径。

**辅路径：自建 handler 封装（若不想引入 Node/mcporter 链路）**
- 直接以 Python 调 Apify REST API（`https://api.apify.com/v2/acts/{actor}/runs`），token 走环境变量，复用本仓 `adapters/` 的凭证 fail-fast + 降级纪律模式。

**落点：Lumo 情报模块（`mcpserver/material_science` 文献层），非 rf_brain。**
- rf_brain 是射频解调链（无线电/卫星），与学术文献采集无关；"情报线"若指威胁情报则属 `sentinel_intel`（SPEC-09 K 线），也与材料科研文献不同域。
- 材料科研的"情报获取空白"落在 SPEC-18 模块 C（文献管理器）上游，即 material_science 的采集入口。

---

## 六、验收自检

- [x] 报告落盘 `docs/apify-data-mcp-勘察报告.md`
- [x] 能力清单表（二节，15+ 工具）
- [x] 依赖评估表（三节，5 维度，含"零成本不成立"结论）
- [x] 明确接入路径建议（五节：mcporter_bridge 为主、handler 为辅、落点 material_science）
- [x] 只读勘察未写码、未注册 Apify 账号、未 copy 上游代码、标注"需付费 API"为运行依赖
