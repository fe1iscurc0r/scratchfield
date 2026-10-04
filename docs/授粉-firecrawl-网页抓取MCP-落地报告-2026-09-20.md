# 授粉 · Firecrawl 网页抓取 MCP — 落地报告（2026-09-20）

> 卷140 交付 | 沈遥签
> 上游：firecrawl/firecrawl-mcp-server（7491★ · MIT ✅ gh api 核验 · 2026-09-20 仍在活跃更新）
> 落点：`mcpserver/firecrawl_adapter/`（client.py + adapter.py + manifest + test）

## 一、上游调研结论 + 一个必须先说的环境事实

**上游定位**：Firecrawl 官方 MCP Server，把网页变成结构化 markdown/JSON，
给 Cursor/Claude 等 agent 用。工具面含 `firecrawl_scrape` / `firecrawl_search` /
`firecrawl_crawl` / `firecrawl_map` / `firecrawl_extract` 等。

**API 契约（官方文档 2026-09-20 实测核实，非转述）**：
```
POST {base_url}/v2/scrape
headers: Authorization: Bearer <token>、Content-Type: application/json
body:    {"url": <必填>, "formats": ["markdown"], "onlyMainContent": true,
          "timeout": 1000-300000, "blockAds": true, "maxAge": 172800000, ...}
响应:    {"success": bool,
          "data": {"markdown": str, "metadata": {"title","sourceURL","statusCode",...},
                   "warning": str}}
```

**⚠️ 环境事实：本机无 Docker（实测 `docker --version` → FileNotFoundError）**。
工单要求"优先评估自托管"，但自托管 Firecrawl 依赖 Docker Compose——
**这一层在本机不可执行**。如实标注，并给出替代路线（见 §五）。

## 二、源 → 目标映射表

| # | 上游设计 | 本仓落点（实测行号） | 映射方式 |
|---|---|---|---|
| 1 | `firecrawl_scrape` 工具 | `client.py:128` `scrape_to_md()` + `adapter.py` 的 `firecrawl_scrape_to_md` | 直接对接其 HTTP API（不引 Node 运行时） |
| 2 | `onlyMainContent` 参数 | `client.py:128` 形参 `only_main_content`（默认 True） | 沿用 |
| 3 | `timeout` 参数 | `client.py:128` `timeout_ms`，钳位 1000-300000 | 沿用官方范围 |
| 4 | 云 API 的 Bearer 认证 | `client.py:89` `_post()`（route=cloud 才加 Authorization） | 沿用；**key 只在内存，不落任何文件** |
| 5 | （上游是 MCP Server 进程） | `adapter.py` 的 `FirecrawlBridge`（manifest 型，与 hamlog/pdf2md 同构） | **改造**：不引 Node/MCP 进程，直接用 Python 调 HTTP API——与仓内适配器体系一致 |
| 6 | （上游无 RSS 场景） | `adapter.py` `firecrawl_enrich_rss()` | **本仓扩展**：RSS 摘要条目 → 全文落盘（补本仓真实痛点） |
| 7 | （上游无降级策略） | `client.py:128` 自托管→云 fallback（`allow_cloud_fallback`） | 本仓扩展（应对"自托管不可用"） |
| 8 | （上游无健康检查） | `client.py:160` `health()` | 本仓扩展（运维用） |

## 三、核心数据结构共鸣（附行号）

| 结构 | 本仓对应物（文件:行） | 共鸣 | 差异 |
|---|---|---|---|
| `data.markdown` | `client.py:39` `ScrapeResult.markdown` | ★★★ | 本仓额外记录 `route`（self-host/cloud） |
| `data.metadata` | `ScrapeResult.title/url/status_code/meta` | ★★ | 只提感知所需字段 |
| `success: false` | `client.py:89` → 抛 `FirecrawlError` | ★★ | 本仓 fail-fast（不静默返回空） |
| `data.warning` | `ScrapeResult.warning`（fallback 时追加 `[回落到云 API]`） | ★★ | 本仓用它标注降级 |
| （无） | `adapter.py` 的 front-matter 落盘格式 | — | 本仓扩展：`source/title/url/fetched_at/route` → 供卷142 抽取管线读 |

## 四、与既有资产的分工（工单点名）

- **`bulk-web-download` skill（整站递归下载）**：那是"整站镜像"，
  本件是"**单页结构化抓取**"（markdown 正文 + 元数据）——**不重叠**（工单亦如此认定 ✅）
- **与卷139/142 的联动（工单要求预留）**：
  ```
  RSS 条目 ──[本卷 enrich_rss]──→ knowledge-base/inbox/*.md（带 front-matter）
                                        ↓
                          ──[卷142 kg_extract]──→ 三元组 ──[卷139 ingest]──→ 图谱
  ```
  落盘格式已按此链路设计（front-matter 里带 `url`，抽取时可作 `source_doc` citation）。

## 五、⚠️ Docker 缺失的替代路线（如实标注）

| 路线 | 可行性（本机实测） | 说明 |
|---|---|---|
| A. 自托管 Firecrawl（Docker Compose） | ❌ **不可执行** | 本机无 Docker。需用户自行安装 Docker Desktop 后 `docker compose up`，端口以 compose 配置为准（常见 3002） |
| B. 云 API（fallback，已实现） | ✅ 代码就绪，**未实机验证**（无 key） | 配 `FIRECRAWL_API_KEY` 即用；适配器默认在自托管不可达时自动回落 |
| C. 完全离线（mock 传输） | ✅ **已实测**（14 用例） | 单元测试全走注入的假传输，零网络 |

**适配器已把三条路都收进设计**：`FIRECRAWL_BASE_URL` 指自托管、`FIRECRAWL_API_URL`
+ `FIRECRAWL_API_KEY` 指云、`transport` 形参注入假传输用于离线测试。
因此**无论用户后续选哪条路，适配器无需改动**。

## 六、难度 × 收益评估

| 维度 | 评估 |
|---|---|
| **实现难度** | 低（适配器层）。真难点在**部署**（Docker 不在本机） |
| **收益** | 中。补"RSS 只拿摘要"的缺口；但收益兑现**依赖部署完成**（自托管或云 key） |
| **风险** | ①反爬（Firecrawl 自带代理/绕反爬，但中文站点质量未实测）②云 API 有额度/成本（已标注）③正文为空的静默风险（已 fail-fast 规避） |
| **不做** | 不引 Node 运行时跑上游 MCP Server（本仓 Python 栈直连 HTTP 更轻） |

## 七、验收实测

```bash
# 1) pytest 全过
$ pytest mcpserver/firecrawl_adapter/ -q
14 passed in 0.06s                        ← ✅

# 2) 自托管 curl 冒烟
$ curl -sf http://localhost:PORT/scrape_to_md -d '{"url":"..."}' | grep -c example
# ⚠️ 未执行——本机无 Docker，自托管实例起不来（见 §五路线 A）
# 等价的离线验证已做：假传输下 scrape_to_md 返回正文并断言含目标文本（见用例）
```

**验证边界（说清楚）**：
- ✅ 已验证：适配器逻辑、请求体形状（对照官方文档）、fail-fast、降级标注、落盘格式
- ❌ 未验证：真实 Firecrawl 实例端到端（需 Docker 或云 key）——**属"部署层未做"，不是"代码未做"**

## 八、测试中挖出的两个真缺陷（已修）

1. **传输层异常未转成链路错误**：host 不可达时裸 `OSError` 逃逸到调用方，
   违反 fail-fast 契约 → 已改为在 `_post()` 里包成 `FirecrawlError`（含诊断信息）
2. **字段名撞车**：`health()` 返回的 `status: <http_code>` 会覆盖桥接层的
   `status: "ok"` → 已改名为 `http_status`

## 九、交付清单

| 文件 | 说明 |
|---|---|
| `mcpserver/firecrawl_adapter/client.py` | FirecrawlClient（scrape + 自托管/云双路线 + health） |
| `mcpserver/firecrawl_adapter/adapter.py` | FirecrawlBridge（3 工具）+ inbox 落盘 |
| `mcpserver/firecrawl_adapter/agent-manifest.json` | 3 个 invocationCommands |
| `mcpserver/firecrawl_adapter/__init__.py` | 导出面 + Docker 缺失的如实标注 |
| `mcpserver/firecrawl_adapter/test_firecrawl_adapter.py` | 14 用例（全离线） |
