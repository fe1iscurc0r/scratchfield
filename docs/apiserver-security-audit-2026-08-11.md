# apiserver/ 存量代码全量审查报告（只读）

**审查时间**：2026-08-11  
**审查范围**：`d:\my git\scratchpad\apiserver\` 全部已提交代码（含 `routes/` 子目录）  
**审查模式**：只读，未做任何修改

---

## 🔴 Critical

### C1. 认证中间件不校验 token，任意 Bearer token 可劫持全局登录态（认证绕过）

**文件**：`apiserver/api_server.py` L137-158、`apiserver/naga_auth.py` L338-347 / L395-410、`apiserver/routes/auth.py` L68-86

**问题**：`sync_auth_token` 中间件对任何携带 `Bearer xxx` 的请求，都会把客户端传来的任意 token 与全局已登录用户绑定进请求上下文，全程没有一次校验 token 是否等于服务端 `_access_token`：

```python
token = auth_header[7:]
if token:
    user = naga_auth.get_user_info()          # 全局用户，与该 token 无任何关系
    naga_auth.set_request_context(token, user)
```

而 `get_me()` 优先返回上下文用户（L341-343），`get_access_token()` 优先返回上下文 token（L416-418），导致攻击链成立（在 `require_auth=True` 模式下）：

1. 攻击者发送 `GET /auth/me` + `Authorization: Bearer <任意垃圾值>`；
2. `get_me` 因上下文存在直接返回已登录用户 → 200；
3. 随后 `restore_token(垃圾值)`：`_last_refresh_at` 距上次刷新超过 10s 宽限期时（L406-410），将全局 `_access_token` 替换为攻击者的垃圾值并续期 30 分钟；
4. 之后 `_verify_token`（`require_local_auth` 的校验函数，L540）判定该垃圾 token 合法 —— 所有受 `require_local_auth` 保护的接口（RAG、persona、appearance 等）全部被绕过。

注释自称"防止并发会话混淆"，实际是未验证即信任。

**修复建议**：

中间件在设置上下文前必须校验 token：

```python
if token and token == naga_auth.get_valid_global_token():  # 封装：有效才返回
    naga_auth.set_request_context(token, naga_auth.get_user_info())
```

同时 `restore_token` 不应无条件接受客户端 token 覆盖全局状态，应先验证 `token == _access_token`。

---

## 🟠 High

### H1. `/auth/refresh` 签名不匹配，接口 100% 失败

**文件**：`apiserver/routes/auth.py` L394 ↔ `apiserver/naga_auth.py` L363

**问题**：`naga_auth.refresh()` 定义为无参数：

```python
async def refresh() -> dict:          # naga_auth.py L363
```

但路由调用时传了一个参数：

```python
result = await naga_auth.refresh(rt_override)   # routes/auth.py L394
```

每次调用必然抛 `TypeError`，被 L396 的 `except Exception` 吞掉后统一返回 401「刷新失败」。即 token 刷新端点永远不可用，依赖它的非浏览器客户端/迁移流程全部失效。

> 其余调用点 `openai_proxy.py` L123、`llm_service.py` L441、`extensions.py` L2521 均按无参调用，只有这一处不一致。

**修复建议**：二选一——

- 调用侧改为 `await naga_auth.refresh()`（若不需要外部 refresh_token 覆盖）
- 给 `refresh` 增加 `rt_override: str | None = None` 参数并真正校验/替换 `_refresh_token`（注意：当前实现即使收到 body 里的 refresh_token 也完全没用它）

### H2. `session_id` 未校验 → 路径穿越，可写任意 `.json` 文件

**文件**：`apiserver/message_manager.py` L81-83 / L142-169 / L185-194；入口 `apiserver/routes/chat.py` L589、L726

**问题**：`_get_session_file` 直接拼接用户可控的 `session_id`：

```python
def _get_session_file(self, session_id: str) -> Path:
    return self.sessions_dir / f"{session_id}.json"
```

`create_session()` 对客户端传入的 `session_id` 不做任何格式校验（L149-169）。而 `/chat`、`/chat/stream` 无任何鉴权依赖且接受任意 `session_id`。

攻击者发送 `session_id = "../../evil"`，第一条消息触发 `add_message` → `_save_session_to_disk`（L101-103）即向 sessions 目录之外写入攻击者可部分控制内容的 JSON 文件（覆盖同名 `.json`）。

> 同目录的 `lumo_proxy.py` L96-101 对 `session_id` 做了 `^[a-zA-Z0-9_-]{1,64}$` 正则校验，说明这是遗漏而非设计。

**修复建议**：

在 `create_session` 入口统一校验（与 `lumo_proxy` 对齐）：

```python
import re
if session_id and not re.match(r'^[a-zA-Z0-9_-]{1,64}$', session_id):
    raise ValueError("非法 session_id")
```

或在 `_get_session_file` 中 resolve 后校验 `relative_to(self.sessions_dir)`。

---

## 🟡 Medium

### M1. `/system/config` GET/POST 无鉴权，且明文回显 API Key

**文件**：`apiserver/routes/system.py` L176-252

**问题**：
- `GET /system/config` 直接返回 `get_config_snapshot()` 全量配置（含 `api.api_key` 明文，`config_manager` 无脱敏逻辑），且该路由没有 `Depends(require_local_auth)`
- `POST /system/config` 同样无鉴权即可改写全部配置（包括 `api.base_url` —— 可把后续所有 LLM 流量重定向到攻击者服务器）

对比 `routes/rag.py`、`routes/persona.py`、`routes/appearance.py` 全部挂了 `require_local_auth`，此处是明显遗漏；一旦用户开启 `require_auth=True`，这些接口仍裸奔。

**修复建议**：
- 两个端点加 `auth: dict = Depends(require_local_auth)`
- GET 响应中对 `api_key`/`app_secret` 等敏感字段做掩码（如 `sk-****1234`），前端保存时已有 `preserve_existing_api_key_if_placeholder` 机制可配合

### M2. `/chat/stream` 响应头硬编码 `Access-Control-Allow-Origin: *`，绕过锚定的 CORS 策略；异常原文直接回显

**文件**：`apiserver/routes/chat.py` L1187、L1203-1210

**问题**：

项目专门用 `system/cors_config.py` 做了锚定正则的本地源 CORS（并注释强调防 `localhost.evil.com` 绕过），但流式响应手工塞入 `Access-Control-Allow-Origin: *` + `Access-Control-Allow-Headers: *`，与全局策略冲突。

另外 L1187 `yield f"data: error:{str(e)}"` 把内部异常（可能含 URL/端口/路径）直接推给客户端。`routes/tools.py` 的 L238、L322、L350、L382、L478、L560 同样在 500 detail 中拼接 `str(e)`。

**修复建议**：
- 删除手工 ACAO 头，交给统一 CORS 中间件
- 错误事件改为 `data: error:内部错误` 并把详情只写日志（参考 `routes/rag.py` 的脱敏做法）

### M3. WebSocketManager 迭代共享集合时未持锁，存在并发修改风险

**文件**：`apiserver/websocket_manager.py` L63-76、L88-120

**问题**：`send_to_session` / `broadcast` 在不持 `self._lock` 的情况下迭代 `self._connections[session_id]` 与 `self._global_connections` 并 `await ws.send_text`；期间另一协程的 `connect`/`disconnect`（持锁修改同一集合）可导致 `RuntimeError: Set changed size during iteration`，使广播整体失败。锁只在清理阶段使用，保护不完整。

**修复建议**：迭代前在锁内取快照：`conns = list(self._connections.get(session_id, ()))`，然后对快照发送；修改仍走锁。

---

## 🟢 Low

- **L1**：`apiserver/llm_service.py` L434-436 将 `access_token` 前 20 字符写入错误日志（`token={'set(' + _tk[:20] + '...)'}`），本地日志也会留痕，建议只记录长度或哈希。
- **L2**：`apiserver/routes/extensions.py` L133 `shell=(sys.platform == "win32")`：`shell=True` + list 参数在 Windows 下语义脆弱（经 cmd 拼接），目前调用点均为固定命令暂无注入面，建议统一改 `shell=False`（Windows 下 npm 用 `npm.cmd` 全路径即可）。
- **L3**：`apiserver/routes/tools.py` L26-32 的 `_clawdbot_replies` / `_live2d_actions` / `_music_commands` 为无上限内存队列，前端长期不轮询时无界增长，建议加长度上限（如 1000 条，超出丢弃最旧）。
- **L4**：`apiserver/naga_auth.py` L308-327 `login()` 无失败限速/锁定；`get_captcha` 返回固定答案且登录流程从不校验 captcha 参数 —— 本地单机可接受，但既然 `require_auth` 是可选加固模式，验证码形同虚设值得留意。

---

## 总体质量结论

该模块整体工程素养不错：CORS 锚定正则、RAG 上传白名单+路径校验、代理错误脱敏、事件防重放去重、telemetry 敏感字段过滤等加固点都做得扎实，跨模块接口（agentserver 的 `/dogtag/conversation_event`、`/travel/interrupt` 等）经核对一致。

**主要短板集中在认证链路**：中间件未验证 token 即建立请求上下文（C1）、refresh 接口签名错位（H1）、配置接口漏挂鉴权（M1），这三处组合起来使 `require_auth=True` 的加固模式实际不可靠。

其次是 session_id 输入校验在 chat 主链路上缺失（H2），建议与 lumo_proxy 的既有校验统一收口。

---

*报告生成时间：2026-08-11 | 审查模式：只读*
