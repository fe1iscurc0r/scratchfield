# extensions.py 域边界勘察（卷190-A1 · PR 第一 commit）

> 2026-10-02 · 目标：`apiserver/routes/extensions.py`（**2932 行**）→ 按领域拆包
> 工单：`TRAE_WORKORDER_PROMPT_AGENT_190.md` 任务A1
> 复现：`.venv/Scripts/python.exe tools/extract_extensions_routes.py`（解析脚本）

## 一、规模与构成

| 项 | 数量 |
|---|---|
| 总行数 | **2932** |
| 路由（`@router.*`） | **40** |
| 顶层函数 | **105**（40 个路由 handler + 65 个 helper） |
| 模块级常量/正则 | 15（含 `OPENCLAW_MARKET_ITEMS` 大列表，L74~L138） |
| 顶层块总数 | 121 |

## 二、路由域分布（按一级前缀）

| 域 | 路由数 | 行号跨度 | 代表端点 |
|---|---|---|---|
| **/travel** | 13 | L2262–2534 | `POST /travel/sessions`、`GET /travel/status`、`POST /travel/stop` |
| **/mcp** | 8 | L915–1256 | `GET/PUT /mcp/assembly`、`GET /mcp/services`、`PUT/DELETE /mcp/services/{name}`、`POST /mcp/import` |
| **/openclaw** | 7 | L583–770 | `GET /openclaw/market/items`、`/openclaw/gateway/{status,start,stop}`、`/openclaw/tasks` |
| **/skills** | 4 | L1778–1900 | `GET /skills/catalog`、`POST /skills/import`、`POST /skills/clone`、`DELETE /skills/{name}` |
| **/memory** | 4 | L2516–2810 | `GET /memory/stats`、`/memory/quintuples`、`/memory/graph/summary`、`/memory/quintuples/search` |
| **/hub** | 2 | L1911–2010 | `POST /hub/skills/install`、`POST /hub/mcp/install` |
| **/upload** | 2 | L2052–2100 | `POST /upload/document`、`POST /upload/parse` |
| **（无前缀）** | — | L2833 | `proxy_search`（搜索代理） |

> 关键观察：**域块在文件里是交错的**（不是连续大块）——例如 `/upload`(L2052) 夹在 `/hub`(L1911) 与
> travel helper (L2151) 之间。因此拆分**不能按行号整段切**，必须**按顶层块搬移**（脚本按块切分，见下）。

## 三、helper 归类（65 个）

| 归属 | helper（行号） |
|---|---|
| **openclaw/agent_browser** | `_agent_browser_bin_name` L340、`_resolve_packaged_openclaw_runtime_dir` L344、`_resolve_prebundled_agent_browser_cmd` L363、`_agent_browser_browser_cache_dirs` L371、`_has_agent_browser_native_bundle` L378、`_has_agent_browser_browser_cache` L390、`_remove_agent_browser_browser_cache` L405、`_install_agent_browser` L468 |
| **market/hub** | `_build_market_item` L534、`_get_market_items_status` L549、`_fetch_hub_payload` L1635、`_parse_hub_skill_payload` L1659、`_parse_hub_mcp_payload` L1671 |
| **skills** | `_write_skill_file` L183、`_normalize_skill_name` L187、`_resolve_child_dir` L207、`_resolve_skill_dir` L220、`_resolve_agent_skills_dir` L224、`_write_skill_file_to_dir` L229、`_load_agents_manifest` L237、`_get_agent_record` L248、`_parse_skill_summary` L255、`_list_skill_dir` L307、`_copy_template_dir` L326、`_render_skill_file_content` L1535、`_write_skill_to_scope` L1553、`_delete_skill_from_scope` L1583、`_read_skill_content_from_scope` L1611、`_build_skill_catalog` L1721 |
| **mcp/mcporter** | `_update_mcporter_firecrawl_config` L416、`_ensure_mcporter_storage` L444 |
| **memory** | `_normalize_memory_quintuple_item` L1692、`_quintuple_degree` L2557、`_apply_quintuple_filters` L2574、`_fetch_all_quintuples` L2614 |
| **travel** | `_create_travel_session_and_dispatch` L2151、`_cancel_travel_session` L2233 |
| **通用/_common** | `_run_command` L140、`_download_text` L174、`_telemetry_config_keys` L562、`_emit_extensions_telemetry` L569 |

## 四、拆分方案（8 个模块 + 聚合入口）

```
apiserver/routes/
├── extensions.py              # 薄壳：from .extensions_parts import *（外部 import 不断）
└── extensions_parts/          # 新包
    ├── __init__.py            # router = APIRouter() + include_router(各子 router)
    ├── _common.py             # 公共常量 + _run_command/_download_text/遥测 helper
    ├── openclaw.py            # /openclaw ×7 + agent_browser helper ×8
    ├── mcp.py                 # /mcp ×8 + mcporter helper ×2
    ├── skills.py              # /skills ×4 + skill helper ×16
    ├── market.py              # /hub ×2 + market helper ×5
    ├── upload.py              # /upload ×2
    ├── travel.py              # /travel ×13 + travel helper ×2
    └── memory.py              # /memory ×4 + memory helper ×4
```

**为什么不是工单假设的 market/install/registry/admin**：工单原文即写明"预期拆分（**按勘察定**，以下是假设）"。
实测域分布与假设不同——本文件里"市场/安装"仅 10 个端点，而 travel(13)/mcp(8)/skills(4+16 helper) 才是大宗；
若强行按假设名，travel/memory/upload 无处安放。故**按实际域**划分，模块名直白反映路由前缀。

**前缀不变**：每个子模块自持 `router = APIRouter()`，`__init__.py` 用 `include_router()` 聚合，
路径不加重写前缀 ⇒ 40 个端点路径逐字不变。

## 五、依赖与风险（开工前已识别）

| 风险 | 说明 | 对策 |
|---|---|---|
| **循环 import** | `extensions.py:37` 反向 import `apiserver.api_server`（`FileUploadResponse`、`_call_agentserver`），而 `api_server` 又 import `extensions_router` | 保持**同位置、同顺序**的 import（不放 `_common`）或在函数内延迟 import；拆完必须跑通 `import apiserver.api_server` |
| **模块级常量被多域共用** | `NAGA_DATA_DIR`/`NAGA_SKILLS_DIR`/`MCPORTER_DIR` 等被 skills/mcp/market 共用 | 全部收进 `_common.py`，子模块显式 `from ._common import (...)` |
| **大常量列表** | `OPENCLAW_MARKET_ITEMS`（L74~L138，约 65 行）只在 market/openclaw 用 | 随 market.py 走 |
| **Pydantic 请求模型** | `SkillImportRequest`/`SkillCloneRequest`/`HubInstallRequest` 等分散 | 随各自域模块 |
| **行为零变化** | 工单红线：不改逻辑/签名/文案 | 纯搬移；`git diff` 逐块核对（搬移块应逐字节一致） |

## 六、验收与验证策略

1. `python -c "import apiserver.api_server"` 通过（循环 import 未破）
2. `grep -rn "from apiserver.routes.extensions import" --include="*.py"` 的调用方全部照常工作
3. 路由清单对比：拆分前后各 **40 条**，`(method, path)` 集合**逐条相同**
4. `pytest apiserver/tests/ -q` 不回归
5. 薄壳 re-export 生效（`from apiserver.routes.extensions import router, list_skill_catalog` 可导入）

## 附：复现方式

```bash
.venv/Scripts/python.exe tools/extract_extensions_routes.py   # 输出 40 路由 + 105 顶层定义的行号清单
python scripts/check_file_size.py                             # 拆完后 extensions 相关文件应全部 <=400 行
```
