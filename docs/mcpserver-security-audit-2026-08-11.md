# mcpserver/ 只读代码审查报告

**审查范围**：`d:\my git\scratchpad\mcpserver\` 下存量已提交代码  
**已跳过**：paper_miner 包、llm4decompile.py、markitdown.py、adapters/paper_miner.py、biopred.py、build_dataset.py

---

## Critical（必须修复）

### C1. _launch_shortcut 使用 shell=True 拼接外部传入参数 → 命令注入

**位置**：`agent_app_launcher.py` L146-L157

**问题**：`args` 直接来自 MCP 任务字典（外部可通过 `HTTP POST /schedule`、`POST /call` 透传任意参数），经 `args.split()` 后与快捷方式路径组成 list，再以 `subprocess.Popen(cmd, shell=True)` 执行。

Windows 下 `shell=True` 会把整个命令行交给 `cmd.exe /c` 解析，args 中的 `&`、`|`、`"` 等 shell 元字符不会被转义。攻击者只需调用：

```json
{"service_name":"app_launcher","tool_name":"启动应用","app":"Chrome","args":"x\" & calc & \""}
```

即可实现任意命令执行。且 `/schedule` 接口无任何鉴权（见 H1），构成完整远程可利用链。

> 同文件 `_launch_executable` 已正确使用 `shell=False`，说明此处是疏漏而非有意。

**修复**：

```python
subprocess.Popen(cmd, shell=False)
```

（快捷方式 `.lnk` 由 Shell 关联直接执行，`shell=False` + list 在 Windows 上可正常工作；若需兼容无关联场景，可对 `.lnk` 显式用 `os.startfile` 或 `cmd.exe /c start "" "<lnk>"` 且不带用户参数拼接。）

---

## High（强烈建议修复）

### H1. /schedule 的 callback_url 未做任何校验即发起 HTTP 请求（SSRF），且 security_utils.validate_callback_url 写好了但从未被接线

**位置**：`mcp_server.py` L88-L89；`security_utils.py` L69-L81

**问题**：`schedule_task` 收到外部请求后直接 `asyncio.create_task(_send_callback(req.callback_url, ...))`，`_send_callback`（L141-L163）用 httpx 无条件 POST 到该地址，还带 3 次重试。攻击者可借此探测/攻击内网（如 `http://169.254.169.254/`、内网管理端口、本机 agent_server 的各接口）。

全仓 grep 确认：`security_utils.py` 中的 `validate_callback_url` / `is_private_url` / `sanitize_external_args` **没有任何一处调用方**——安全模块存在但完全未生效。

**修复**：在 `schedule_task` 中接线：

```python
from mcpserver.security_utils import validate_callback_url
if req.callback_url:
    ok, msg = validate_callback_url(req.callback_url)
    if not ok:
        raise HTTPException(status_code=400, detail=f"callback_url 不安全: {msg}")
```

> 注意：`is_private_url` 在 DNS 解析失败时返回 False（fail-open，`security_utils.py` L62-L63），建议同时改为解析失败即拒绝。

---

## Medium（建议修复）

### M1. PowerShell 解析 .lnk 时用 f-string 插值文件路径 → 恶意文件名可注入

**位置**：`comprehensive_app_scanner.py` L214-L225

**问题**：`_parse_lnk_powershell` 将 glob 扫到的 lnk_path（来源包括用户桌面 `%USERPROFILE%\Desktop`）直接插进双引号字符串拼给 `powershell -Command`。文件名含 `"` 或 `$(...)` 即可注入执行，例如桌面放一个名为 `a$(calc).lnk` 的文件，扫描时即触发。桌面/开始菜单可被下载文件、其他进程写入，属现实可触达的攻击面。

**修复**：改用参数化传递，避免字符串插值：

```python
result = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "(New-Object -ComObject WScript.Shell).CreateShortcut($args[0]).TargetPath",
     lnk_path],
    capture_output=True, text=True, timeout=5,
)
```

（`-Command` 后的 `$args` 可通过追加参数传入；或对路径做 `"` 过滤/转义校验。）

### M2. fire-and-forget asyncio.create_task 未持有引用，任务可能被 GC 中途回收

**位置**：`mcp_server.py` L89；同样问题见 L111

**问题**：事件循环只持有 Task 的弱引用，`asyncio.create_task(_send_callback(...))` 返回值未保存，回调任务（含最长 30s 超时 + 3 次重试）可能在完成前被垃圾回收器销毁——这是 Python 官方文档明确记载的陷阱（"Save a reference to the result of this function"）。回调丢失会静默发生，难以排查。

**修复**：维护模块级集合：

```python
_BACKGROUND_TASKS: set[asyncio.Task] = set()
task = asyncio.create_task(_send_callback(...))
_BACKGROUND_TASKS.add(task)
task.add_done_callback(_BACKGROUND_TASKS.discard)
```

### M3. 天气 Agent 的 time 动作被城市编码查找卡死，与 manifest 文档矛盾

**位置**：`agent_weather_time.py` L106-L134

**问题**：`handle()` 在分发任何 action 之前先强制解析城市编码（L107-L110），解析失败直接返回 error。但 `time/get_time` 动作本身不依赖城市；manifest 中也写明 time 的 city 为"可选，自动识别"。当本地 IP 城市探测失败（`_get_local_ip_and_city` 的正则依赖 ipip.net 页面格式，外部站点一改就失效）或城市不在 codes_map 时，纯时间查询也必然失败。这是确定性的流程编排缺陷。

**修复**：把 time 分支提前到城市编码校验之前处理，或仅对天气类动作要求城市编码。

### M4. _send_callback 对非 200 状态码立即无间隔重试

**位置**：`mcp_server.py` L153-L161

**问题**：`resp.status_code != 200` 时既不记日志也不 sleep，直接进入下一次循环，3 次重试在毫秒内打空，起不到重试作用还会对目标形成小突发。只有异常路径才有 1s 退避。

**修复**：非 200 分支同样 `logger.warning(...)` + `await asyncio.sleep(1)`。

---

## Low（可择机处理）

| # | 位置 | 问题 |
|---|------|------|
| L1 | `agent_weather_time.py` L32-L47 | `WeatherTimeTool.__init__` 里同步 `requests.get(timeout=5)` 阻塞注册流程（最坏 5s）；`WeatherTimeAgent.__init__` 还把用户公网 IP+城市打到 stderr（L146），建议脱敏。 |
| L2 | `agent_weather_time.py` L119-L120 | manifest 宣称"未来3天预报"，实际返回完整 d15（全部天数）；且 d3（`forecast[:3]`）取而不用。文档与行为不一致。 |
| L3 | `agent_weather_time.py` L52-L67 | `get_weather` 直接 `data['data']`、`body['forecast'][0]`，第三方 API 异常响应时抛 KeyError/IndexError——虽被上层兜住，但错误信息不友好，建议预检 `data.get("status")`。 |
| L4 | `city_code_map.py` | 整个文件（高德编码表）无任何引用，属死代码，建议删除以免与 `city_codes.py` 混淆。 |
| L5 | `registry_app_scanner.py` | 与 `comprehensive_app_scanner.py` 功能重复且已被后者取代（agent 只用 comprehensive），全文裸 `except:`，建议标记废弃或删除。 |
| L6 | `materialscience_agent.py` L63-L65 | `_matchat_executor`（ThreadPoolExecutor）无任何 shutdown 路径，`MCPManager.cleanup()`（`mcp_manager.py` L89-L91）是空实现；进程退出时 Playwright 工作线程只能靠 daemon 机制回收。建议在 cleanup 中统一关闭。 |
| L7 | `adapters/_common.py` L20-L26 | `NotRequired` 导入后从未使用（`CapabilityDict` 用 `total=False` 覆盖），三层 fallback 属无效代码。 |
| L8 | `mcporter_bridge.py` L23 | `_MCPORTER_SCHEMA_CACHE` 以 (name, mtime) 为 key，配置文件每次被 touch 都会新增条目且从不清理（`invalidate_mcporter_cache` 无调用方），长期运行缓慢膨胀。 |

---

## 正面确认（契约一致性检查结论）

| 检查项 | 结论 |
|--------|------|
| Adapter 契约 | ✅ agent_reach / vulnclaw / memclaw / headroom 四个 adapter 均完整实现 CAPABILITY（含 7 个必需键）/ healthcheck() / register()，CAPABILITY.name 与注册名对齐，凭证走环境变量无硬编码 |
| 门禁校验 | ✅ `_common.py` 的 validate_adapter 门禁、capability 冲突检测、`inject_vendor_path` 的路径逃逸防护（relative_to 边界校验）实现正确 |
| 注册框架 | ✅ `mcp_registry.py` 三表写入路径都遵循"实例创建成功才写缓存"的原子性约束，跨源冲突有 WARNING + conflict_sources 标记，`register_all_adapters` 带回滚半挂载工具逻辑，设计合理 |
| Subprocess 安全 | ✅ 除 C1/M1 外，mcporter_bridge 全部使用 list + shell=False，无 shell 注入；未发现 pickle/eval 等不安全反序列化，未发现硬编码密钥/token |

---

## 总体质量结论

模块整体架构质量较高：注册/门禁/降级框架设计严谨，adapter 契约执行一致，异常兜底和资源防护意识普遍到位。

**但存在一处可直接远程利用的命令注入（C1）和一处已建好却从未接线的 SSRF 防护（H1）**，两者都应优先修复——尤其 `security_utils.py` 整模块零调用，说明"写了安全工具但没接线"是该模块当前最大的系统性风险。

其余 Medium/Low 问题多为文档与行为不一致、死代码和小概率边界，可在常规迭代中消化。

---

*报告生成时间：2026-08-11 | 审查模式：只读*
