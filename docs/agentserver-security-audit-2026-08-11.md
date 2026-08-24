# agentserver/ 只读代码审查报告

**审查范围**：`d:\my git\scratchpad\agentserver\` 全部已提交代码（约40个跟踪文件，含 openclaw/、dogtag/ 子包及 mjs/sh 脚本）  
**交叉核对**：与 apiserver / mcpserver / system 接口一致性

---

## Critical（必须修复）

### C1. 整个服务无任何鉴权且监听 0.0.0.0，敏感操作完全暴露

**位置**：`agentserver/agent_server.py` L3123（`uvicorn.run(app, host="0.0.0.0", ...)`）、`agentserver/config.py` L24（默认 `host="0.0.0.0"`）

**问题**：全部 HTTP 端点没有任何 token/身份校验（未使用 apiserver.naga_auth 或中间件）。其中 `POST /openclaw/tools/invoke` 可透传调用任意 OpenClaw 工具（含 bash 类命令执行工具，见 `test_connection.sh` L47 的示例 payload），`/openclaw/install`、`/openclaw/gateway/start|stop`、`/openclaw/config/*` 等可控制系统进程与配置。局域网内任何主机都能直接远程操控，等同于远程命令执行面。

**修复建议**：绑定 127.0.0.1（如确需对外则加鉴权中间件）；对所有 `/openclaw/*` 等敏感端点加共享内部 token 校验（与 apiserver 之间已有 naga_auth 体系可复用）。

### C2. POST /openclaw/install 端点必然 500：引用了不存在的枚举成员

**位置**：`agentserver/agent_server.py` L1319–L1326；`agentserver/openclaw/installer.py` L18–L22

**问题**：端点代码执行 `method = InstallMethod.NPM if method_str == "npm" else InstallMethod.SCRIPT`，但 installer.py 中 `InstallMethod` 只有 `VENDOR` 和 `UNKNOWN` 两个成员。任何请求都会抛 `AttributeError`，被 except 捕获后返回 500，该端点功能完全失效。

**修复建议**：

```python
method = InstallMethod.VENDOR if method_str in ("npm", "vendor") else InstallMethod.UNKNOWN
```

或按实际需要补齐枚举成员并同步 installer 的分支逻辑。

---

## High（应尽快修复）

### H1. 测试脚本硬编码真实格式的 Gateway/Hooks token

**位置**：`agentserver/openclaw/test_connection.py` L18–L19、`agentserver/openclaw/test_connection.sh` L9–L10

**问题**：`GATEWAY_TOKEN = "9d3d8c24a1739f3a8a21653bbc218bc54f53ff1a5c5381de"` 等凭据已提交进仓库历史；若该 token 与某环境实际生成值相同则已泄露。

**修复建议**：改为从环境变量/`~/.naga/openclaw/openclaw.json` 读取，并轮换现有 token。

### H2. QQ 通知 URL 是空字符串桩，启用即必然失败

**位置**：`agentserver/travel_notifications.py` L99–L100（调用点 L145 `_deliver_qq_payload`）

**问题**：`_resolve_qq_notify_url()` 直接 `return ""`，随后对空 URL 发起 POST，httpx 会抛协议/URL 异常，QQ 通知通道 100% 失败，属于未完成桩代码进入主干。

**修复建议**：实现真实 URL 解析（如从 config 读取 notify 服务地址）；在实现前若配置启用了 QQ 通知，应显式报错或在入口处拦截，而不是走到请求时才失败。

### H3. 干员 Gateway 崩溃重启导致端口池泄漏，最终耗尽

**位置**：`agentserver/openclaw/instance_manager.py` L811–L829（`ensure_running`）、L831–L853（`_start_instance`）

**问题**：进程崩溃后 `ensure_running` 调 `_start_instance`，后者 `_allocate_port()` 分配新端口，但 `inst.port` 的旧端口从未归还（只有 `_stop_instance` 会 `_release_port`）。反复崩溃重启会持续消耗稀疏端口块（上限约 100 个），最终抛 "OpenClaw 端口池已耗尽"。

**修复建议**：在 `ensure_running` 标记 `inst.running = False` 后、重新启动前，先 `self._release_port(inst.port)`；或让 `_start_instance` 对已有 `inst.port` 优先复用。

### H4. Gateway 启动失败路径上 StreamReader 双消费者竞态，吞掉真实错误

**位置**：`agentserver/openclaw/embedded_runtime.py` L635–L650（`_pipe_gateway_logs` 后台 readline 任务）、L719–L724、L791–L797（失败时 `await proc.stderr.read()` / `stdout.read()`）

**问题**：`_pipe_gateway_logs` 已在后台持续消费同一 stdout/stderr StreamReader，失败路径又对同一 stream 调 `read()`。asyncio 对同一 StreamReader 并发读取会抛 RuntimeError（或互相抢数据），导致启动失败时要么再次异常、要么拿不到关键错误日志，排障困难。

**修复建议**：失败路径改为从 `_pipe_gateway_logs` 维护的日志缓冲（如 deque）取最近若干行，不再直接 `read()` 原始 stream；或启动失败时先取消后台 reader 任务再读残余数据。

### H5. apiserver.routes.forum 模块在仓库中不存在，论坛自动发帖功能必挂

**位置**：`agentserver/agent_server.py` L2306（`from apiserver.routes.forum import create_forum_post_internal`）

**问题**：全仓库不存在 `apiserver/routes/forum.py`（README 提及但未提交），旅行完成后的"自动发布论坛精华帖"每次都会 `ModuleNotFoundError`，被 except 记为 failed——功能处于静默死亡状态。

**修复建议**：补交/实现 `apiserver/routes/forum.py`（与 apiserver 批次核对）；或暂时移除该分支，避免所有 `post_to_forum=True` 的会话都记录一条失败事件。

---

## Medium（建议修复）

### M1. _kill_stale_on_port 无差别 SIGTERM 任意占用端口的进程，且不跨平台

**位置**：`agentserver/openclaw/instance_manager.py` L322–L345

**问题**：用 `lsof -ti tcp:{port}` 找到 PID 后直接 SIGTERM，不校验是否为 openclaw/gateway 残留（docstring 声称杀 openclaw 残留）；端口若被其他正常程序占用会被误杀。另外 lsof 仅 Unix 可用，Windows 下静默失败返回 0（docstring 却标注"跨平台"）。

**修复建议**：校验进程命令行包含 openclaw/node 特征再杀；Windows 改用 `netstat -ano` + `taskkill` 或 psutil。

### M2. ensure_running 未持锁，并发请求可重复拉起 Gateway 进程

**位置**：`agentserver/openclaw/instance_manager.py` L811–L829（类内已有 `_agent_locks` 但此处未用）；调用方 `agent_server.py` 多处直接 `await ensure_running(...)`

**问题**：两个并发请求同时发现进程未运行时，会各自 `_start_instance`，造成端口双重分配与孤儿进程。

**修复建议**：`ensure_running` 内以 `self._agent_locks[agent_id]`（get_or_create）包裹检测-启动逻辑。

### M3. set_openclaw_config 替换全局客户端时不关闭旧 AsyncClient

**位置**：`agentserver/openclaw/openclaw_client.py` L1538–L1541

**问题**：每次配置更新直接替换全局 OpenClawClient，旧实例的 httpx AsyncClient 未 `aclose()`，连接/socket 泄漏（该接口可被反复调用）。

**修复建议**：替换前 `await old_client.aclose()`（提供幂等关闭方法）。

### M4. send_message 异常路径任务永久停留 RUNNING；回复可能混入会话历史

**位置**：`agentserver/openclaw/openclaw_client.py` L376–L481（`send_message` / `_poll_for_reply`）

**问题**：① 响应解析异常或轮询抛异常时直接 break 返回，任务状态停在 RUNNING 且无错误信息，调用方看到"永久运行中"；② 轮询从 sessions_history 取最后一条 assistant 消息，未与本次请求前的历史做增量对比，可能把历史回复当作本次结果。

**修复建议**：异常时把任务标记 FAILED 并携带错误信息；记录请求前的最后消息时间戳/数量，轮询时只取其后新增的 assistant 消息。

### M5. _save_config meta 永不落盘，且写入失败时原文件已被移走

**位置**：`agentserver/openclaw/config_manager.py` L116–L137

**问题**：先把原文件 rename 成 .bak 再写新文件，`_update_meta()` 在写入之后调用，meta.lastTouchedAt/lastTouchedBy 永远不会出现在磁盘文件中；写入中途失败时主配置文件缺失（只能靠 .bak 手工恢复）。

**修复建议**：先 `self._update_meta()` 再写文件；更稳妥的做法是写临时文件后 `os.replace` 原子替换，成功后再另存备份。

### M6. enable_proactive_vision 内部 HTTPException 被外层 except 二次包装

**位置**：`agentserver/agent_server.py` L2553–L2578

**问题**：L2575 `raise HTTPException(500, "配置保存失败")` 被 L2576 `except Exception` 捕获后包装成 500 "操作失败: 配置保存失败"，语义重复且与相邻端点写法不一致（L2546–L2547 有 `except HTTPException: raise`）。

**修复建议**：

```python
    except HTTPException:
        raise
    except Exception as e:
        ...
```

### M7. checklist remove_item 在 batch_update() 上下文中删除会丢失

**位置**：`agentserver/dogtag/checklist.py` L152–L162（对比 L113–L149 的 add/update）

**问题**：add_item/update_item 都兼容 `_batch_checklist`，唯独 remove_item 独立 load/save；若在 `batch_update()` 内调用，退出上下文时批量快照会把删除覆盖回去。

**修复建议**：与 add/update 同样接入 `_batch_checklist`：`cl = _batch_checklist if _batch_checklist is not None else load_checklist()`，且仅在非批量时 save。

### M8. install_skill 用户输入直接进 CLI argv，存在参数注入

**位置**：`agentserver/openclaw/installer.py` L697–L702

**问题**：HTTP 传入的 skill_slug 直接拼入 `[..., "skills", "install", skill_slug]`；以 `-` 开头的值可能被 CLI 解释为选项（argv 注入，低危但经无鉴权端点放大）。

**修复建议**：校验 slug 格式（如 `^[A-Za-z0-9_-]+$` 且不以 `-` 开头），或插入 `"--"` 分隔符。

### M9. _allocate_port 在异步链路中 time.sleep 阻塞事件循环

**位置**：`agentserver/openclaw/instance_manager.py` L382–L385（`time.sleep(0.2)`，另有同步 `_check_port` socket 探测）

**问题**：该方法由 async 调用链（`_start_instance` ← HTTP 端点）触发，阻塞会卡住整个服务的事件循环。

**修复建议**：把端口探测/sleep 移到 `asyncio.to_thread`，或改为异步 socket 检查 + `await asyncio.sleep`。

---

## Low（可考虑）

| # | 位置 | 问题 |
|---|------|------|
| L1 | `openclaw/installer.py` L511–L516 | `start_gateway(background=False)` 用 `stdout=PIPE` 但从不读取也不持有引用，可能泄漏管道或导致子进程写满管道挂起。建议 `stdout=DEVNULL` 或显式 drain。 |
| L2 | `agent_server.py` L1585 | hooks token 明文回显，无鉴权端点在响应中返回刚生成的 hooks token；与 C1 叠加后任何人均可取走。建议不回显或仅脱敏回显。 |
| L3 | `agent_server.py` L1809 | `_run_travel_session` 每次调用都 `sys.path.insert(0, ...)`，应在模块加载时做一次。 |
| L4 | `instance_manager.py` | `_read_skill_file` 将 skill_name 直接拼进 `skills/{skill_name}/SKILL.md`，虽当前无调用方，建议删除或加路径规范化校验。 |
| L5 | `agentserver/utils.py` | `is_time_in_range` 中 start == end 时走 else 分支恒为 True，建议显式定义该边界语义。 |
| L6 | `openclaw/llm_config_bridge.py` | `inject_naga_llm_config` 会把飞书 app_secret 等写入 openclaw.json，建议至少收紧文件权限（0600）。 |

---

## 接口一致性核对结果

| 接口 | 核对结果 |
|------|----------|
| `/queue/push`、`/ws/broadcast`、`/proactive_message` | ✅ 均在 `apiserver/routes/tools.py` 存在，字段匹配 |
| apiserver 回调 `/dogtag/conversation_event` | ✅ 在 `agent_server.py` L3096 已定义 |
| mcpserver 回调 `/proactive_vision/reset_timer` | ✅ 在 `agent_server.py` L2699 已定义 |
| 旧路由 `/heartbeat/conversation_event` | ✅ 有兼容委托 |
| travel_service 引用函数签名 | ✅ 全部匹配 |
| mcpserver `/call` 契约 | ✅ screen_vision/look_screen 契约匹配 |
| **apiserver.routes.forum 模块** | ❌ **缺失**（H5） |

---

## 总体质量结论

模块整体结构清晰、异常兜底意识较强（大量 try/except + 日志），dogtag 调度与 screen_vision 子包质量良好、与 apiserver/mcpserver 接口基本对齐。

**但安全基线缺失是最大短板**：服务无鉴权且监听 0.0.0.0、仓库内硬编码 token，叠加可远程触发的工具调用端点，风险面过大。

此外存在若干确定性缺陷（InstallMethod 枚举不匹配、QQ 通知空 URL、forum 模块缺失、端口泄漏、StreamReader 竞态），均会导致对应功能必现故障或资源耗尽，建议按 Critical → High 顺序优先修复。

---

*报告生成时间：2026-08-11 | 审查模式：只读*
