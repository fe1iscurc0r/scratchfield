# apify-接入方案

> 工单：M-02 · apify 可行时的接入方案（设计，不实现）
> 智能体：MIKE（数据采集层）
> 日期：2026-08-28
> 依据：M-01 勘察报告（apify 可行：$5/月免费层 + MIT + Node≥22，APIFY_TOKEN 为运行依赖非否决）

## 一、结论

M-01 判定 apify **可行**（非"必须付费/云计费"的否决情形），故本单按工单要求改为**设计接入方案**，不写码。等用户决定注册 Apify 账号、申请 token 后再落地。

## 二、接入路径总览

两条路径，主推 A（零新代码、复用现成桥接层），B 为不引 Node/mcporter 链路的备选。

### 路径 A：mcporter_bridge 外部接入（推荐）

复用 `mcpserver/mcporter_bridge.py` 的 `ExternalMCPAgent`，将 apify 作为外部 MCP 服务注册进 `MCP_REGISTRY`，与本地 manifest agent 共享统一调度。

- 配置入口：`~/.mcporter/config.json` 的 `mcpServers.apify`
- 模板已存在：`mcpserver/external_services.example.json` 中 `apify` 条目（`type: http` + `url: https://mcp.apify.com` + `Authorization: Bearer ${APIFY_TOKEN}`）
- 启用动作（用户侧，非本次执行）：
  1. 注册 Apify 账号，拿到 APIFY_TOKEN
  2. 将 `external_services.example.json` 的 `apify` 条目合入 `~/.mcporter/config.json`，把 `_disabled` 由 `true` 改 `false`
  3. 把 `${APIFY_TOKEN}` 替换为真实 token 或注入环境变量
- 调用链路：`POST /schedule` → `MCPManager.unified_call()` → `ExternalMCPAgent.handle_handoff()` → `mcporter call --config ~/.mcporter/config.json apify.<tool> ...`

**待验证点（落地时第一步）**：
- mcporter CLI 对 Streamable HTTP 远端（`type: http`）的支持程度。
- 若 mcporter 仅稳定支持 stdio，改用 stdio 形态：
  ```json
  {
    "mcpServers": {
      "apify": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@apify/actors-mcp-server"],
        "env": { "APIFY_TOKEN": "${APIFY_TOKEN}" }
      }
    }
  }
  ```
  此形态走 `npx @apify/actors-mcp-server`（Node≥22），与本仓 `mcporter_bridge._resolve_mcporter_launcher` 已具备的 npx 回退一致。

### 路径 B：自建 handler 封装（备选，Python 直连 Apify REST API）

不引入 Node/mcporter 链路，直接以 Python 调 Apify REST API，复用本仓 `adapters/` 的凭证 fail-fast + 降级纪律。

**封装签名（设计，未实现）**：

```python
# mcpserver/data_collect/apify_handler.py  （路径 B 时的落点，当前不建）
class ApifyHandler:
    """Apify REST API 的 Python 薄封装。

    鉴权：APIFY_TOKEN 环境变量（不硬编码）。
    降级：网络失败/超时 → {"ok": False, "error": ...}，永不抛错（照 adapters/context7.py）。
    """

    def __init__(self, token: str | None = None, base_url: str = "https://api.apify.com/v2") -> None:
        self.token = token or os.environ.get("APIFY_TOKEN")
        # 凭证 fail-fast：无 token 时构造抛 RuntimeError，由 adapter 健康检查捕获跳过

    def search_actors(self, query: str, limit: int = 10) -> dict:
        """GET {base}/store?search={query}&limit={limit} → {"ok": bool, "items": [...]}"""

    def fetch_actor(self, actor_id: str) -> dict:
        """GET {base}/acts/{actor_id} → 输入 schema / 定价 / 描述"""

    def call_actor(self, actor_id: str, run_input: dict, max_results: int = 10) -> dict:
        """POST {base}/acts/{actor_id}/runs?token=... → 返回 run 元数据 + datasetId（不直接含条目）"""

    def get_dataset_items(self, dataset_id: str, limit: int = 10) -> dict:
        """GET {base}/datasets/{dataset_id}/items?token=... → 分页取正文"""

    def fetch_url(self, url: str, format: str = "markdown") -> dict:
        """对应 apify/web-fetch：GET 任意 URL 转 Markdown/文本/HTML/链接"""
```

对应 MCP 工具（2 个，覆盖 Lumo 最需要的数据源）：

| 工具名 | 函数 | 数据源 |
|---|---|---|
| `arxiv_search` | 包装 `call_actor(actor="easyapi/arxiv-search-scraper", ...)` 或直连 arXiv 开放 API | arXiv 前沿文献 |
| `fetch_feed` | 包装 `call_actor(actor="easyapi/google-news-scraper", ...)` 或 stdlib RSS 抓取 | 新闻/期刊 RSS |

> 说明：路径 B 是"若不想走 mcporter 链路"的备选。当前 M-02 处于"apify 可行"分支，**只交付本方案，不实现上述代码**。

## 三、推荐落点

**`mcpserver/material_science`（Lumo 情报模块 · 文献层）**，作为 SPEC-18 模块 C（文献管理器）的上游采集入口：

- 现有 `literature_search`（RAG 检索）与 `matchat_search`（MatChat AI 搜索）覆盖"已入库内容/定向问答"，缺"实时结构化采集"。
- apify 采集结果（arXiv 元数据/专利/新闻/期刊）先落本地 SQLite（模块 C 的文献库），再喂 ELN 实验记录引用。
- **不落 rf_brain**：rf_brain 是射频解调链，与学术文献不同域。

## 四、落地前置条件（用户决策，非本次执行）

1. 是否注册 Apify 账号并申请 APIFY_TOKEN（工单硬约束：这是用户决策，MIKE 不代办）。
2. 是否接受 $5/月免费层之外的云计费（材料科研批量采集大概率超免费层）。
3. 选路径 A（mcporter 桥接）还是路径 B（自建 handler）。
4. 确认 mcporter CLI 对 Streamable HTTP 的支持情况（路径 A 的待验证点）。

## 五、验收自检

- [x] `docs/apify-接入方案.md` 落盘
- [x] 含接入路径签名（路径 B 的 `ApifyHandler` 类 + 2 个工具函数签名）
- [x] 明确推荐 mcporter_bridge 为主、handler 为辅
- [x] 未写实现代码（符合"apify 可行时不写码"分支）
