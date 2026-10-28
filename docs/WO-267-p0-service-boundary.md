# WO-267 施工记录 —— P0-1 / P0-3 / P0-4 / P0-5 / P0-6 本机服务边界收回

- **工单**：`_workorders/2026-10-22/TRAE_WORKORDER_PROMPT_AGENT_267.md`
- **定罪基线**：`main@61835ad63625b6777ec880554536a87b8d46848c`（2026-10-21T22:25:25Z；审查报告对照表 #1 / #3 / #4 / #5 / #6）
- **交付基线**：`main@c79b54e67acf45e47c621370f7c68e5a3a920587`（2026-10-22T04:25:31Z）
- **分支**：`wo/267-service-boundary`（一个 PR，不写 main）
- **交付坐标**：提交 `98bfba6097190455d3b99cd0eaca0f2c449c91ad`（父 = `main@c79b54e6`），**PR #398**，
  19 文件 `+2547/−33`，`mergeable=clean`。合并前的回滚点 = `main` 未被写入，仍为 `c79b54e67acf45e47c621370f7c68e5a3a920587`。
  评审报告对照表 #1/#3/#4/#5/#6 的处置回填提交在另一条线上：`docs/full-repo-review-2026-10-21/README.md`
  的分支提交 `7d870c10c89ca855ed508dcd5ad1300a3322432f`（PR #390）。
- **环境**：本机两个 NEKO 冻结 Python 环境（`C:\Users\ASUS\python-sdk\python3.13.2`、`NEKO/N.E.K.O/.venv`＝py3.11.15）**一字节未装、未改**，全部是只读跑；根侧用 `scratchpad-unified/.venv`（py3.12.13）。产物写到仓库外的 `D:\my git\_wo267\`。
- **密钥口径**：本文与 `matrix.log` 里出现的令牌一律只写变量名与长度，值全部打码（沿用 WO-268 立的规矩）。

## 基线核对（为什么交付基线不是定罪基线）

`GET /repos/.../compare/61835ad63625...c79b54e67acf` → `status=ahead, ahead_by=13, behind_by=0`，41 个变更文件与本单触碰的 18 个文件**零交叠**。
⇒ 从定罪基线取的改动能原样叠到当前 main tip，不会回退他人在这期间动过的文件。

## 一句话

五条 P0 是同一个组合：**默认绑全网卡 + 鉴权是 opt-in**。main 上同时存在 `host="0.0.0.0"`、
`MONITOR_HOST` 默认 `0.0.0.0`、`MONITOR_TOKEN` 默认空串、`/call` 与 `/openclaw/install` 零鉴权、
`/user_live2d/` 与 `/workshop/` 在免鉴权短路名单里。本单把这个组合拆掉：

**默认只绑回环 ⇒ 本机自用不需要令牌；确需跨机必须显式 `NEKO_ALLOW_REMOTE=1` 且给 ≥32 位
`NEKO_AUTH_TOKEN`，缺任一项在 `bind()` 之前 `exit 78`。** 不存在「先起服务再补鉴权」这一态。

## 统一环境变量口径（三个服务共用，不再各写一套）

| 变量 | 默认 | 语义 |
|---|---|---|
| `NEKO_BIND_HOST` | `127.0.0.1` | 监听地址。历史名 `NEKO_MONITOR_HOST` / `MONITOR_HOST` 继续可用，**新名优先**，默认值已改 |
| `NEKO_ALLOW_REMOTE` | 未设 | 只有字面量 `1` 才允许非回环绑定。`true` / `yes` / `on` 一律算关闭 |
| `NEKO_AUTH_TOKEN` | 未设 | 非空且长度 ≥32 才算有效。历史名 `NEKO_MONITOR_TOKEN` / `MONITOR_TOKEN` 继续可用 |
| `NEKO_ALLOW_INSTALL` | 未设 | `/openclaw/install` 的第二道门（T3 要求的「显式开关」） |

为什么非回环绑定时**连 127.0.0.1 来源也要令牌**：绑了通配地址之后，本机进程和局域网进程共用
同一个监听套接字，「来源是否回环」不再是可信区分——DNS 重绑定和本机恶意软件面前，回环来源检查
一起失效。所以只有两种合法形态：只绑回环（本机自用、免令牌），或开远程（所有人都带令牌）。
`system/net_boundary.py` 的模块注释里钉着这段理由，别在将来把它「优化」回去。

`NEKO_ALLOW_REMOTE` 只认字面量 `1` 也是同一个道理：这是安全闸门，拼错的值必须落在**关闭**那一侧。

---

## 改了什么（18 个文件：14 改 + 4 新增）

### 新增的两份策略实现

| 文件 | 行数 | 内容 |
|---|---|---|
| `system/net_boundary.py` | **437（新增）** | 根侧唯一策略源：`normalize_bind_host` / `is_loopback_host`（名字 + 整段 `127/8` + `::1` + IPv4 映射的 IPv6 回环）/ `is_wildcard_host` / `bind_pair` / `evaluate_startup_policy` / `enforce_startup_policy`（不过就 `SystemExit(78)`）/ `authorize_request`（单请求纯函数判定）/ `LocalBoundaryMiddleware`（默认拒绝的 ASGI 闸门）/ `boundary_snapshot`（给健康检查，不回显令牌） |
| `NEKO/N.E.K.O/utils/net_boundary.py` | **288（新增）** | NEKO 侧镜像实现。NEKO 是与根启动器**分进程**运行的独立应用，import 不到根侧模块，所以是第二份；额外带历史变量名兼容与 `auth_token_source()` |
| `tests/test_net_boundary_policy.py` | **538（新增）** | 根侧表驱动测试 |
| `NEKO/N.E.K.O/tests/unit/test_net_boundary_policy.py` | **584（新增）** | NEKO 侧同一张决策表 + Monitor 中间件与 `/api/agent` 依赖的真实驱动测试 |

两份实现会漂移，所以把判据钉在**同一张表**上：两边的 `STARTUP_TABLE`（13 行）与 `REQUEST_TABLE`
（13 行）内容逐行对齐，各自的测试文件里还有源码契约断言。改一边不改另一边，另一侧就红。

### T1 · 启动器不再写死 `0.0.0.0`

| 位置 | 改动 |
|---|---|
| `main.py`（+42/−12） | 主入口在**任何服务启动之前**调 `enforce_startup_policy`：`NEKO_BIND_HOST` 优先于 `config.api_server.host`，判不过就整个进程退出。`_start_mcp_server` / `_start_agent_server` 的 `host="0.0.0.0"` 改成 `effective_bind_host()`；端口预检从写死 `"0.0.0.0"` 改为 `bind_pair(effective_bind_host())` |
| `main.py` 端口预检 | 原来用 `AF_INET` + `"0.0.0.0"` 探测：绑 IPv6 字面量时探测会**误报端口空闲**，而绑通配地址的探测本身等于「在服务启动前先在所有网卡上开一个临时监听套接字」——自己先制造一次暴露面。现在按即将监听的同一地址族、同一地址探测 |
| `agentserver/config.py`（+3/−1） | `UvicornConfig.host` 默认 `"0.0.0.0"` → `"127.0.0.1"`。这行不在工单的行号清单里，验收 grep（找 `host="0.0.0.0"` 字面量）也看不见它，但它是同一颗雷：任何按 `UvicornConfig()` 起的服务默认绑全网卡 |
| `agentserver/agent_server.py`（+8/−2） | 独立入口（`python -m agentserver.agent_server`）加 `enforce_startup_policy`，注释里原先那句「仅绑定 loopback，禁止局域网直连」现在才真的成立 |
| `frontend/main.py`（+3/−1） | 前端静态壳同源问题：默认改回环，跨机走同一判据 |
| `sitaware/api_server.py`（+4/−1） | `main()` 里 `bind_host = enforce_startup_policy("sitaware 事件服务")`，`uvicorn.run` 用它 |

### T2 / T3 · 写路由挂默认拒绝的闸门（根侧中间件）

| 位置 | 改动 |
|---|---|
| `mcpserver/mcp_server.py`（+13） | `app.add_middleware(LocalBoundaryMiddleware, component="mcp-server", public_paths=("/status",))`，挂在 `apply_local_cors(app)` **之前** |
| `agentserver/agent_server_parts/lifecycle.py`（+11） | 同一中间件，`component="agent-server"`、`public_paths=("/health",)` |
| `agentserver/agent_server_parts/openclaw.py`（+9） | `/openclaw/install` 额外要求 `NEKO_ALLOW_INSTALL=1`；`/openclaw/tools/invoke` 随中间件进保护面 |

三个决定，都是有意为之，写下来免得被当成随手改的：

1. **用中间件，不用逐路由 `Depends`**。P0-1 能挂两年，一部分原因就是把鉴权当成每条路由自己的自觉；
   `mcpserver` 的写路由已经有 `/call`、`/schedule`、`/chains/run`、`/trust/assess` 四条，将来新加的
   写路由要**默认**落在保护面里。`agentserver` 更明显：路由散在 8 个 parts 模块里。
2. **边界先挂、CORS 后挂**。Starlette 的 `add_middleware` 是栈式插入（最后加的在最外层），
   所以 CORS 留在最外层，被拒的 401/403 才能带着跨源响应头回到浏览器——否则用户只看到
   「blocked by CORS policy」而看不到真正的拒绝原因。`tests/test_net_boundary_policy.py` 里有
   针对中间件顺序的装配断言（`test_mcp_app_registers_the_boundary_middleware` /
   `test_agent_app_registers_the_boundary_middleware`），改乱顺序会红。
3. **安装面要两道门**。边界令牌只证明「你是谁」，不证明「现在该不该往本机装代码」：
   `/openclaw/install` 即使带着合法令牌，没有 `NEKO_ALLOW_INSTALL=1` 仍然是 403。

### T4 / T5 · NEKO Monitor

| 位置 | 改动 |
|---|---|
| `NEKO/N.E.K.O/config/network.py`（+20/−5） | `_read_str_env("MONITOR_HOST", "0.0.0.0")` → `read_bind_host()`（默认 `127.0.0.1`）；`:186` 那句自认「保留历史 LAN 绑定、鉴权 opt-in」的注释连同其理由一起删掉。`MONITOR_TOKEN = read_auth_token()[0]`——**原值照旧返回**，因为「非空即开启鉴权」是 `monitor_auth` 的既有语义，≥32 的硬要求只用在「要不要允许非回环监听」这一处启动判定上，不改既有鉴权语义 |
| `NEKO/N.E.K.O/config/__init__.py`（+4） | 把 `ALLOW_REMOTE` / `AUTH_TOKEN_STATE` 与 `read_bind_host` 一并导出，供启动入口与快照使用 |
| `NEKO/N.E.K.O/app/monitor.py`（+8/−6） | `if __name__ == "__main__"` 里 `bind_host = enforce_startup_policy("Monitor 服务", bind_host=MONITOR_HOST)`，`uvicorn.run` 用它；模块顶部的「设计上要能被外部客户端访问所以默认 0.0.0.0」注释替换成新口径 |
| `NEKO/N.E.K.O/app/monitor_auth.py`（+6/−1） | `_PUBLIC_PATH_PREFIXES` 由 `("/static/", "/user_live2d/", "/user_live2d_local/", "/workshop/")` 收成 `("/static/",)`。monitor 挂的是用户 `Documents` 下的 Live2D 目录和 Steam 工坊目录——旧写法意味着「已经配了 `MONITOR_TOKEN`」的部署里，任何人仍可无凭据批量下载付费模型。被摘掉的三条改走 viewer 会话 cookie；没配 token 时中间件整体短路（本机自用），不会出现「本机 UI 突然要凭据」 |

### T6 · `/api/agent/*`

| 位置 | 改动 |
|---|---|
| `NEKO/N.E.K.O/main_routers/agent_router.py`（+85/−2） | `APIRouter(prefix="/api/agent", dependencies=[Depends(agent_mutation_boundary)])`——前缀级依赖，覆盖全部 20 条路由（测试里有 `len(router.dependencies) == 1` 与路由条数的断言）。两道判定：① 变更类请求的浏览器 `Origin` 必须是同源或回环源（`is_http_browser_origin_allowed`）或带合法令牌，否则 403；② `authorize_request` 决定 401 |
| 同上 · `_route_is_disabled_by_deployment()` 让路规则 | `/api/agent/flags`、`/command`、`/admin/control`、`/tasks/{id}/cancel` 四条路由在「远端后端模式」下本来就短路返回 501 + 运维信封（issue #1023 的既有契约）。边界如果先把它们判成 401，运维拿到的是「你没权限」而不是「这个部署里这条路本来就关着」——**信息被降级**。所以对这 4 条路径，变更类请求在进边界判定之前先让路，由路由自己出 501；`/api/agent/internal/analyze_request` **不让路**（它没有短路），继续归边界管。两条都有测试钉住：`test_agent_remote_mode_envelope_survives_the_boundary`（×4 参数化，断 501 + `success is False` + 信封里有 `NEKO_ACTIVITY_TRACKER_REMOTE`）与 `test_agent_internal_bridge_is_not_exempt_from_the_boundary`（断 401） |

CORS 那一半**没有需要改的代码**：全仓核对下来根侧与 NEKO 侧都没有 `allow_origins=["*"]`
（`card_drop_router` 那处反射 origin 是先在 `_exact_origin_matches` 里比对配置好的 base URL 才反射）。
所以白名单沿用既有的 `system/cors_config.LOCAL_ORIGIN_REGEX`，边界判定与 CORS 判定共用同一个正则——
一份白名单，不会出现「CORS 放行、边界拒绝」这种两套口径互相打脸。这条以断言钉在测试里。

### T7 · 全部启动入口的启动期校验

`enforce_startup_policy` 落在 6 个入口：`main.py`（主启动器）、`agentserver/agent_server.py`、
`apiserver/start_server.py`（API 与 LLM 服务各自一道）、`sitaware/api_server.py`、
`NEKO/N.E.K.O/app/monitor.py`、装配壳（矩阵里的 mcp / `/api/agent` 壳与真实入口同函数）。

一个必须写下来的实现细节：**线程里抛 `SystemExit` 只杀那个线程**。主启动器里各服务跑在子线程，
如果把校验放在线程内部，「配置不合规」会降级成「某一个服务静默不启动」，用户看到的是
「起来了，但少一个」。所以只在**顶层**判一次、把结果写进 `record_bind_host()`，线程里的服务
读 `effective_bind_host()`，不再各自判一次。

---

## 验收实测输出

驱动脚本：`D:\my git\_wo267\matrix.sh`（仓库外，一次性）；完整原始日志：`D:\my git\_wo267\matrix.log`（令牌已打码）。
本机 LAN IPv4 = `10.33.56.93`；端口 agent=8001、mcp=8003、monitor=48913、`/api/agent` 装配壳=48921。

脚本里绕掉的三个本机坑，一并记在这里（它们会让「实测」看起来和真实行为不一样）：

1. Git Bash 里 `( cd d && cmd ) &` 的 `$!` 是 MSYS 内部 pid，与 `netstat` 报的 Win32 pid 不是一套数。
   按 `$!` 去 `taskkill` 打不中 python ⇒ 场景之间残留监听，**C 组的匿名请求会全打在 A 组残留的
   旧进程上、返回 200**，看起来像「鉴权没生效」。现在改为开场体检端口必须全空闲（占用即 ABORT，
   不碰别人起的进程）+ 收尾按端口收。
2. `python ... | head -n 6` 会让 python 在退出刷 stdout 时收到 SIGPIPE，`rc=120` 被误读成
   「fail-fast 没生效」。改成先落盘、再 tail。
3. 装配壳用绝对路径启动时 `sys.path[0]` 是壳所在目录，`import system` / `import utils` 直接失败
   ⇒ 显式 `PYTHONPATH`。

### 验收 1 · `grep -rn 'host="0.0.0.0"' main.py mcpserver/ agentserver/` → 0 命中

```
$ grep -rn 'host="0.0.0.0"' main.py mcpserver/ agentserver/ ; echo "hits=$(grep -rn 'host=\"0.0.0.0\"' main.py mcpserver/ agentserver/ | wc -l)"
hits=0
```

补充说明（工单允许「校验逻辑里出现的字符串除外，需在 PR 里说明」）：
`system/net_boundary.py` 的 `_WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", "::0", "*"})` 与
`bind_pair()` 里的 `"0.0.0.0"` 是**判定用的字面量**，位于 `tests/` 与策略模块内，不在上述三个路径；
`main.py` 里原先写死 `"0.0.0.0"` 的三处（`_start_mcp_server`、`_start_agent_server`、端口预检）已全部改掉。
另外 `agentserver/config.py` 的默认值是 `host: str = "0.0.0.0"` 这种**变量默认值**形态，验收 grep
抓不到它——已一并改为 `127.0.0.1`（见 T1 表）。

### 验收 2 · 启动矩阵四组

**A 默认启动（无任何 `NEKO_*` 边界变量）⇒ 只见 `127.0.0.1:<port>`**

```
[agent_root] :8001 已监听，win32 pid=20344
[mcp_root] :8003 已监听，win32 pid=21352
[monitor] :48913 已监听，win32 pid=17448
[agent_router_harness] :48921 已监听，win32 pid=32856
--- A1 监听面（期望：只有 127.0.0.1:<port>，无 0.0.0.0）---
  :8001 127.0.0.1:8001 LISTENING pid=20344
  :8003 127.0.0.1:8003 LISTENING pid=21352
  :48913 127.0.0.1:48913 LISTENING pid=17448
  :48921 127.0.0.1:48921 LISTENING pid=32856
```

同组的功能没有被关掉（本机自用口径不变）：

```
--- A2 本机回环仍可无令牌使用（GET /health 公开面）---
HTTP/1.1 200 OK
date: Thu, 22 Oct 2026 05:26:24 GMT
--- A6 非回环来源到「只绑回环」的服务：连接层就进不来 ---
[LAN → agent :8001/health]
curl: (7) Failed to connect to 10.33.56.93:8001 after 2041 ms: Could not connect to server
[LAN → mcp :8003/call]
curl: (7) Failed to connect to 10.33.56.93:8003 after 2030 ms: Could not connect to server
[cleanup] 矩阵端口已全空闲
```

A6 是「只绑回环」最硬的一条证据：不是应用层拒绝，是**连接层根本握不上手**（`curl (7)`，
2 秒超时）。这一态在 WO-267 之前不可能出现——那时候同一台机器上这四个服务全在 `0.0.0.0` 上。

**B `NEKO_BIND_HOST=0.0.0.0` 且无 token ⇒ 监听前 `exit 78`，stderr 明确含 `NEKO_AUTH_TOKEN`**

六个入口逐个实测，全部 `exit=78`。第一条给完整原文（含它自己的命令行头），其余五条列组件标签
与首行拒绝原因——六条的 stderr 结构与第一条完全一致，差异只有组件名和 `拒绝启动：` 后面那句：

```
--- B_agentserver (cwd=D:/my git/scratchpad-unified) env NEKO_BIND_HOST=0.0.0.0 D:/my git/scratchpad-unified/.venv/Scripts/python.exe -m agentserver.agent_server  ---
exit=78
[net_boundary] agentserver 独立入口 拒绝启动：绑定地址 '0.0.0.0' 不在回环范围内。
[net_boundary]   - NEKO_ALLOW_REMOTE=1 未设置：非回环绑定 '0.0.0.0' 需要显式打开远程访问
[net_boundary]   - NEKO_AUTH_TOKEN 未设置：非回环绑定必须同时提供长度 ≥32 的访问令牌
[net_boundary]   修法：删掉 NEKO_BIND_HOST 让它只绑 127.0.0.1；确需跨机才同时给 NEKO_BIND_HOST=<网卡地址> NEKO_ALLOW_REMOTE=1 NEKO_AUTH_TOKEN=<≥32 字符令牌>
```

| 入口 | `exit=` | `[net_boundary] <组件标签> 拒绝启动：绑定地址 '0.0.0.0' 不在回环范围内。` |
|---|---|---|
| `B_mcpshell`（`run_mcp.py` 装配壳，起真实 `mcpserver`） | 78 | `mcp-server（WO-267 矩阵壳）` |
| `B_sitaware`（`-m sitaware.api_server`） | 78 | `sitaware 事件服务` |
| `B_apiserver`（`-m apiserver.start_server api`） | 78 | `陆墨 API 服务器（独立入口）` |
| `B_neko_monitor`（`-m app.monitor`） | 78 | `Monitor 服务` |
| `B_neko_router`（`run_agent_router.py` 装配壳，挂真实 `agent_router`） | 78 | `NEKO /api/agent（WO-267 矩阵壳）` |

`main.py`（主启动器）那一行**没有跑运行时**，用源码复核代替，原因见下面「⛔ 未跑的一态」。
四组门禁补充（证明「三项都要」不是只查 token）：

```
B 附 1 非回环 + 令牌齐 + ALLOW_REMOTE 未设 ⇒ exit=78，原因只列 NEKO_ALLOW_REMOTE
B 附 2 非回环 + ALLOW_REMOTE=1 + 无令牌   ⇒ exit=78，原因只列 NEKO_AUTH_TOKEN
B 附 3 非回环 + ALLOW_REMOTE=1 + 令牌过短 ⇒ exit=78：NEKO_AUTH_TOKEN 长度 15 < 32：过短令牌不视为已鉴权
B 附 4 非回环 + ALLOW_REMOTE=true + 合法令牌 ⇒ exit=78（拼错的值算关闭）
```

B 附 3 的 `too-short-token` 是我自己造的 15 字符占位串，**不是任何真实凭据**；日志里出现真实
令牌照例打码（`NEKO_AUTH_TOKEN=<masked 凭据未回显>`），全篇只报变量名与长度，不报值。

**C `0.0.0.0` + `NEKO_ALLOW_REMOTE=1` + ≥32 位 token ⇒ 服务起来；带 header 200，不带 401**

```
边界快照（只报状态与来源变量名，不回显令牌值）：
  root : {'bind_host': '0.0.0.0', 'loopback_only': False, 'allow_remote': True, 'auth_token_state': 'ok', 'min_token_length': 32}
  NEKO : {'bind_host': '0.0.0.0', 'loopback_only': False, 'allow_remote': True, 'auth_token_state': 'ok', 'auth_token_source': 'NEKO_AUTH_TOKEN', 'min_token_length': 32}
--- C1 监听面（期望：0.0.0.0:<port>，显式打开远程后才允许）---
  :8001 0.0.0.0:8001 LISTENING pid=25112
  :8003 0.0.0.0:8003 LISTENING pid=18156
  :48913 0.0.0.0:48913 LISTENING pid=30504
  :48921 0.0.0.0:48921 LISTENING pid=20720
--- C2 匿名（无令牌头）GET ⇒ 401（绑通配后回环来源也不再是可信区分）---
HTTP/1.1 401 Unauthorized
--- C2b 局域网地址来源、仍无令牌 ⇒ 401 ---
HTTP/1.1 401 Unauthorized
--- C2c 三个写路由匿名（无令牌）⇒ 不再 200 ---
[mcp /call]                                       HTTP/1.1 401 Unauthorized
[agent /openclaw/install]                         HTTP/1.1 401 Unauthorized
[agent /openclaw/tools/invoke]                    HTTP/1.1 401 Unauthorized
[NEKO /api/agent/flags]                           HTTP/1.1 401 Unauthorized
[NEKO /api/agent/health 匿名 GET，暴露态下读面同样要令牌]  HTTP/1.1 401 Unauthorized
--- C3 带正确令牌 ⇒ 401 消失（剩下的码由路由/业务自己决定）---
[GET /heartbeat/config]                           HTTP/1.1 200 OK
[POST /openclaw/install 带令牌 ⇒ 安装面另有 NEKO_ALLOW_INSTALL 闸门]  HTTP/1.1 403 Forbidden
[mcp /call 带 X-Neko-Token]                       HTTP/1.1 422 Unprocessable Entity
[NEKO /api/agent/flags 带 X-Neko-Token]           HTTP/1.1 500 Internal Server Error
--- C4 长度够但值不对的令牌 ⇒ 401 ---              HTTP/1.1 401 Unauthorized
--- C5 Monitor：匿名 /user_live2d/ 被拦，带令牌进入路由（由应用决定 200/404）---
[匿名 /user_live2d/]                              HTTP/1.1 401 Unauthorized
[带令牌 /user_live2d/]                            HTTP/1.1 404 Not Found
[cleanup] 矩阵端口已全空闲
```

上面各行为了排版把日志里每条响应下面的 `date:` 行合掉了；`HTTP/1.1 …` 状态行逐字照抄，
C 组这些请求的 `date` 全是 `Thu, 22 Oct 2026 05:26:5x GMT`（同一次运行）。

422 / 500 / 404 这些**非 401** 的码正是这组要的对照：闸门没有变成无差别拦死，带对令牌的请求
确实进到了路由与业务层。`/api/agent/flags` 的 500 是矩阵装配壳没有 main_server 那套 config/session
管理器（壳只挂真实 router），不是边界造成的；502 同理（`/api/agent/health` 要代理 tool_server，
壳里没起）。`/openclaw/install` 带合法令牌仍然 403 是 T3 的第二道门。

**D 无凭据 `/user_live2d/<文件>`、`/workshop/<文件>` ⇒ 401/403**

D 组的形态是「配了 token 但只绑回环」——这也是历史上最容易出事的一种部署（配置者以为
「我配了 MONITOR_TOKEN，那就是安全的」，而公开前缀名单照样把那三个目录整目录敞开）。

```
--- D0 监听面（配了令牌但没开远程 ⇒ 仍只 127.0.0.1）---
  :48913 127.0.0.1:48913 LISTENING pid=13780
--- D1 未鉴权 /user_live2d/**（WO-267 前是免鉴权整目录可读）---   HTTP/1.1 401 Unauthorized
--- D2 未鉴权 /workshop/** ---      HTTP/1.1 401 Unauthorized
--- D3 未鉴权 /sync/**（生产者写面）--- HTTP/1.1 401 Unauthorized
--- D4 对照：/static/** 仍在公开面 --- HTTP/1.1 404 Not Found（不在短路名单，进了应用层）
```

D5 控制实验（同一请求、只改 `_PUBLIC_PATH_PREFIXES` 一个变量，走 ASGI 传输不开端口）：

```
公开前缀 = 旧（WO-267 之前）: [('/user_live2d/wo267_probe.txt', 200), ('/user_live2d/', 404), ('/workshop/', 404), ('/static/', 404)]
公开前缀 = 新（WO-267 之后）: [('/user_live2d/wo267_probe.txt', 401), ('/user_live2d/', 401), ('/workshop/', 401), ('/static/', 404)]
```

旧名单下那个探针文件是**真的 200 被读走了**（探针写在 monitor 挂载的用户 Live2D 目录里，
跑完立刻删除，收口体检确认「探针文件已删除：不存在」）。这一条把 P0-5 从「推理」变成「实测」。

### 验收 3 · 三个写路由无 token 不再返回 200

| 路由 | A 组（绑回环、无 token）跨源浏览器 POST | C 组（绑 `0.0.0.0`、有 token 配置）匿名 POST |
|---|---|---|
| `mcpserver /call` | `403 Forbidden` | `401 Unauthorized` |
| `agentserver /openclaw/install` | `403 Forbidden` | `401 Unauthorized` |
| `agentserver /openclaw/tools/invoke` | `403 Forbidden` | `401 Unauthorized` |
| `NEKO /api/agent/flags` | `403 Forbidden` | `401 Unauthorized` |
| `NEKO /api/agent/health`（读面，暴露态） | — | `401 Unauthorized` |

A 组的 403 全部来自跨源判定（`Origin: https://evil.example`），并且对**后缀匹配骗术**
`Origin: http://localhost.evil.com` 同样是 403；同组的合法对照（`Origin: lumo-app://dist`、
`Origin: http://127.0.0.1:5173`、无 `Origin` 头的本机 CLI）全部进到应用层（422 / 200 / 502 / 500），
没有一条被误伤。

### 验收 4 · 既有测试前后失败集合一致

换树口径：`node swap.js to-pristine` 把 14 个改动文件还原成 `base@61835ad6` 的原始 blob 字节、
并把本单 4 个新增文件移走 ⇒ 跑一遍；再 `node swap.js to-changed` 换回交付态 ⇒ 跑第二遍。
每个文件在两个方向上都逐字节校验 sha（18/18 一致），所以这轮对照回退的**只有 WO-267**，
其余文件、其余用户的未提交改动一律没动。

**根侧 `tests/`（全量）**

| 状态 | pytest 汇总 |
|---|---|
| 改前 | `45 failed, 1617 passed, 19 skipped, 4 deselected, 10 warnings, 18 subtests passed in 295.66s (0:04:55)` |
| 改后 | `45 failed, 1710 passed, 19 skipped, 4 deselected, 10 warnings, 18 subtests passed in 268.08s (0:04:28)` |

FAILED/ERROR 名单按「文件::用例」归一后双向 `comm`：

```
只在改后失败（新增失败，必须为空）：   0 条
只在改前失败（本单顺带修好的）：       0 条
两侧共同失败（既有债）：               45 条
```

passed 从 1617 涨到 1710，多出的 **93 条就是本单新增的 `tests/test_net_boundary_policy.py`**，
全绿；45 条既有失败一条没多、一条没少（分布在 `test_toolknit_mcp` 14 条、`test_duckdb_workbench` 6 条、
`test_law_tagging` 4 条、`test_academic_interfaces` 4 条等 14 个文件里，成因与本单无关）。

**NEKO 侧全量 `tests/unit`——这一组不构成对照，如实标注**

```
改前：6341 warnings, 15 errors in 58.94s     （pytest rc=2）
改后：6334 warnings, 15 errors in 15.33s     （pytest rc=2）
```

两个状态都停在「15 个模块收集期报错 ⇒ pytest 直接中止 ⇒ **一条用例都没执行**」。那个「15 = 15」
只证明坏掉的模块数没变，别的什么也没证明。`tests/unit` 全量能收集 42352 条，本机两侧都不跑，
所以另开一轮定向对照。

**NEKO 侧定向 16 个相关测试文件**

圈法两步，缺一不可：① 按「谁 import 了本单改的 6 个 NEKO 文件（`config/network.py`、`config/__init__.py`、
`app/monitor.py`、`app/monitor_auth.py`、`main_routers/agent_router.py`、`utils/host_origin_guard.py`）」grep；
② 再补上**不 import 但按 HTTP 路径打到** `/api/agent/*`、`/user_live2d/`、`/workshop/` 的五个文件
（`test_computer_use_capture_bridge`、`test_openclaw_adapter_protocol`、`test_agent_rewrite_regression`、
`tests/frontend/test_agent_plugin_views`、`tests/frontend/test_home_prompt_flow`）—— 只做第①步会整批漏掉它们。

| 状态 | pytest 汇总（同一批 16 个文件） |
|---|---|
| 改前 | `62 failed, 421 passed, 43 warnings, 243 errors in 17.65s` |
| 改后 | `62 failed, 421 passed, 43 warnings, 243 errors in 13.91s` |

```
只在改后失败：0 条     只在改前失败：0 条     两侧共同失败：305 条（既有债）
本单新增的 NEKO 用例单独跑：88 passed, 4 warnings in 1.80s
```

#### 这轮对照抓到了一个真缺陷（而且是本单引入的）

第一轮定向对照里，NEKO 侧**多出 40 条失败**，全部来自既有的
`tests/unit/test_agent_router_remote_block.py::test_agent_mutation_endpoints_blocked_in_remote_mode`
（4 端点 × 5 个 env 值 × 2 个变量名）。追下去不是既有测试过时，而是本单的边界**抢答**了：
`TestClient` 的 client 是 `("testclient", 50000)`，不是回环，于是在远程部署模式
（`NEKO_ACTIVITY_TRACKER_REMOTE=1`）下 `/api/agent/flags` 这类请求被边界回成

```
401 {"detail":"非回环来源 'testclient' 访问变更路由被拒：本机服务只接受回环请求，跨机请设 NEKO_AUTH_TOKEN（≥32 字符）"}
```

把 issue #1023 与 `system_router` 的 `/api/screenshot` 对齐的那条运维契约盖掉了 —— 那边约定
501 + 错误里必须点名环境变量，前端按它统一显示「agent unavailable on remote backend」。

处置不是放宽边界，而是让路：**端点自己已经拒绝的那四个路径**在远程模式下交给端点回答
（同样是拒绝，只是不吞掉可 grep 的告警），而**没有实现远程短路的 `/internal/analyze_request`
刻意不在让路名单里** —— 一起放掉就等于在远程部署下开一个免鉴权的事件投递口。补两条钉住用例
（`test_agent_remote_mode_envelope_survives_the_boundary` 四条参数化 +
`test_agent_internal_bridge_is_not_exempt_from_the_boundary`），再用 N4/N5 两个变异实验证明这两条
用例各只打对自己的那一侧。修完后定向对照双向差为 0。

#### 对照工具自身的静默失败也记一笔

`swap.js` 的 manifest 早先对根侧文件先做 LF→CRLF 再记账，而本单两个新增文件在工作树里本来就是 LF
⇒ 换回时误报 2 个 `MISMATCH`。逐字节复核 `got` 与快照 sha **相等**，确认内容无损、纯粹是记账口径错了；
已改成一律按 `changed/` 快照的原始字节记账。这类「工具自己报错、看起来像内容被改坏」的假阳性，
如果不查清就直接信，会把一次干净的交付写成「还原失败」。

---

## 变异实验（证明测试真的会红）

按派单表的口径，每个新断言都要有「改坏 ⇒ FAIL」和「注入失败 ⇒ 行为仍然正确」两面。

「改坏 ⇒ FAIL」这一面用 9 条单行变异，工具是 `_wo267/mutate.js`：每条只改一处源码 ⇒ 只跑配套的策略
测试文件 ⇒ **finally 里立刻还原并逐字节校验 sha**（跑完 18 个文件仍全 CHANGED）。定位串命中次数不是
恰好 1 就跳过该条，避免改错地方。

| 变异 | 改坏点（一行） | 应红的用例 | 结果 |
|---|---|---|---|
| M1 | `system/net_boundary.py` 显式开关 `== "1"` ⇒ `in ("1","true","yes","on")` | `test_allow_remote_only_literal_one[true/yes/on]` + `test_openclaw_install_is_default_closed` | 红（4 条） |
| M2 | 根侧 `DEFAULT_BIND_HOST = "127.0.0.1"` ⇒ `"0.0.0.0"` | `test_default_bind_host_is_loopback`、`test_empty_bind_host_falls_back_to_loopback` | 红（2 条） |
| M3 | 根侧 `MIN_TOKEN_LENGTH = 32` ⇒ `1` | `test_token_is_tri_valued`、`test_token_value_never_leaks_into_snapshot`、2 行决策表 | 红（6 条） |
| M4 | 摘掉中间件里的跨源写闸门（`is_trusted_local_origin(...)` ⇒ 恒假） | `test_foreign_browser_origin_write_is_rejected` 四个 Origin 参数 | 红（4 条） |
| N1 | NEKO 侧同款开关放宽 | `test_allow_remote_only_literal_one[true/yes]` | 红（2 条） |
| N2 | `_PUBLIC_PATH_PREFIXES` 退回旧四条 | `test_monitor_public_prefixes_no_longer_cover_user_assets`、`test_monitor_asset_routes_require_token_once_auth_enabled`、`test_monitor_viewer_token_cannot_write_sync` | 红（3 条） |
| N3 | NEKO 侧默认绑定改回通配 | `test_default_bind_host_is_loopback`、`test_empty_bind_host_falls_back_to_loopback` | 红（2 条） |
| N4 | 把**没有**远程短路的 `/internal/analyze_request` 塞进让路名单 | `test_agent_internal_bridge_is_not_exempt_from_the_boundary` | 红（1 条） |
| N5 | 取消「远程模式让路」（`and False`） | `test_agent_remote_mode_envelope_survives_the_boundary` 四条参数化 | 红（4 条） |

N4/N5 是本轮真实发现那个缺陷之后**补出来的两面夹**：只钉「让路名单不许多」不够，还得钉
「让路本身不许取消」，否则实现往任何一个方向漂移都能绿。

「注入失败 ⇒ 行为仍然正确」那一面在矩阵里，不在测试里：
场景 B 的 4 个闸门变体（`NEKO_ALLOW_REMOTE=true` 仍关、15 位短令牌仍拒、空绑定回落回环）、
场景 A5 的合法对照（同源/回环 Origin 与无 Origin 的本机 CLI 都进到应用层，403 不是无差别拦死）、
场景 D5 的前缀对照（改回旧四条 ⇒ 探针文件真的 `200`；保持新值 ⇒ `401`）。

---

## 三处有意偏离工单的地方

1. **T6 的 CSRF 手段换了**。工单写「变更类要求一次性 token 或 CSRF 双提交」。实现换成
   **同源/本机壳 Origin 判定 + 非回环来源要令牌**。原因：前端约 15 处 agent fetch 目前都不带
   `X-CSRF-Token`（issue #1023 因此把这轮推迟了），要双提交就得动前端，而这一轮不能顺手改前端
   （硬边界）。同源判定不动前端、今天就能把「外部网页跨源 POST 驱动 agent」这条路堵死，
   令牌面留给真正的跨机访问。**代价**：本机任意进程仍可向 `/api/agent/*` 发不带 Origin 的写请求
   ——这与本机已能连 48913 端口等价，不是本单要收的面。工单要的「一次性 token」这条**没做**，
   记在这里而不是悄悄省掉。
2. **`/call` 从回环、无 token 仍然可用**。工单 T2 的原话是「未配置 token 时**只接受来自回环的连接**」，
   所以这是照办，不是放水：本机自用不需要令牌，非回环来源的变更请求 401/403，跨源浏览器写请求 403。
3. **NEKO 的 main / agent / memory / plugin 入口保持写死 `127.0.0.1`**，没让它们跟随
   `NEKO_BIND_HOST`。工单 T4 只点了 MONITOR，而这几处历史上就是回环；把它们改成可配置等于
   新增暴露面，与本单方向相反。

## 硬边界遵守

- `vendor/`、`NEKO/N.E.K.O/vendor/` 一字节未动；NEKO 上游引擎层没改造，只在本地入口加约束。
- `docs/workorders/INDEX-active.md` 未动、没新建 INDEX。
- 403 类预留项（分支保护 / rulesets / CodeQL / gitee 可见性）一律没碰。
- 无新依赖：`system/net_boundary.py` 与 `NEKO/N.E.K.O/utils/net_boundary.py` 只用标准库
  （`hmac` / `ipaddress` / `os` / `sys` / `dataclasses` / `re`）。
- 未格式化任何无关行：14 个改动文件的 diff 只有本单涉及的行（`git diff --stat` 对照见上表）。

## 遗留风险 / 待所有者拍板

1. **已有部署的行为变更**：历史上靠 `MONITOR_HOST` 默认 `0.0.0.0` 从局域网访问 monitor 的用户，
   升级后 monitor 只绑回环，局域网 UI 连不上。这是有意的默认收紧。恢复方式写在报错文本里，
   也抄在这里：`NEKO_BIND_HOST=<网卡地址> NEKO_ALLOW_REMOTE=1 NEKO_AUTH_TOKEN=<≥32 字符>` 三个一起给。
   需要一份「哪些机器在跨机用 monitor」的清单才能提前通知——**待所有者提供**，本机拿不到。
2. **CORS 白名单**：本轮没有新增白名单需求（根侧与 NEKO 侧都不存在 `allow_origins=["*"]`），
   边界判定直接复用 `system/cors_config.LOCAL_ORIGIN_REGEX`。若将来要把 Lumo 之外的壳接进来，
   需要所有者给出确切 origin 清单——**待所有者提供**。
3. `NEKO_AUTH_TOKEN` 的 ≥32 只用于**启动判定**；`monitor_auth` 既有的「token 非空即开启鉴权」语义
   未改（改它会连带改 viewer cookie 与 `/sync*` 的既有行为，超出本单范围）。也就是说：
   只绑回环 + 16 位短 token 的组合依然可用（本机自用），但它不会因此获得跨机监听。
4. **本机进程的信任边界仍在**：只绑回环时同机任意进程可写 `/call`、`/openclaw/tools/invoke`。
   这一层要靠 OS 用户隔离或 Unix socket 权限，不在本单。
5. `install` 的第二道门是环境变量，不是交互式确认；能改启动环境的攻击者仍能打开它。工单只要求
   「显式 `--allow-install` 类开关或 token scope 区分」，这里选了开关形态。**token scope**（把
   「只读令牌」和「可装令牌」分开）是更细的做法，未做，记录为可继续的方向。

## ⛔ 未跑的一态（如实记录，不伪造）

1. **`main.py` 主启动器的 B 组运行时那一行没跑**：矩阵里默认 `RUN_LAUNCHER=0` 跳过。原因不是
   做不到，而是它会拉起全家桶并**回收端口上的既有进程**（`kill_port_occupiers`），与同时在跑的
   回归测试/用户自己的栈抢端口，属于会影响共享状态的破坏性动作。改为源码复核：`main.py:916-923`
   调的就是同一个 `enforce_startup_policy`，且发生在任何 `Thread(...).start()` 之前；其判据与已实测
   的 5 个入口共用同一函数、同一张决策表（两侧各 13+13 行表驱动测试钉住）。
2. **NEKO 的验证跑在 SDK py3.13.2 上，不是 NEKO 自带的 `.venv`（py3.11.15）**。`.venv` 里没有
   pytest，而两个 NEKO 环境禁止安装（版本锁死，用户明确要求）。NEKO 新增测试全是同步用例，
   不依赖事件循环策略；CI 里按 `.venv` 跑时不受这个替换影响。
3. 未跑 CI。本机跑的是单元与集成层，CI 的门禁形态（P0-14/15/16）是 WO-273 的范围。
4. **NEKO 全量 `tests/unit` 没有有效对照**：两侧都在收集期中止（15 个模块报错），能收集的 42352 条
   在本机一条也没跑过。已用「16 个相关测试文件」的定向对照替代，但**它只覆盖与本单有依赖或路径
   关系的这批**，其余 NEKO 单测是否被本单影响，本机不可判定 —— 这一条不能靠「定向差为 0」掩盖。
5. 根侧那 45 条既有失败的成因未追（与 P0-14 的门禁形态同源，属 WO-273 范围）。本单只要求
   **前后集合一致**，不顺手修别人的债。
6. 让路名单（`_REMOTE_SHORT_CIRCUIT_PATHS`）与端点里 `_remote_backend_block()` 的调用点是**人工对齐**的：
   将来新增/删除短路点时，靠的是 N5 那条变异对应的钉住用例报警，而不是编译期约束。
