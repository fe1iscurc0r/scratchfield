# SPEC-11 —— 陆墨轻量 Gateway（方案 B：长自己的器官）

> 工单：陆墨接入 QQ/微信 | 日期：2026-08-24 | 状态：待评审
> 决策：**方案 B**（照 Hermes 形态给陆墨写轻量 gateway），弃用方案 A（点 OpenClaw 引信）
> 交付路径：`scratchpad/docs/SPEC-11-lumo-gateway-接入QQ微信.md` → work-specs(public)

---

## 〇、背景与决策记录

### 现状（代码级核实，2026-08-24）

`scratchpad/agentserver/openclaw/` 是 NagaAgent fork 自带的 OpenClaw Gateway 集成，代码全在但**没通电**：

| 文件 | 作用 | 状态 |
|------|------|------|
| `embedded_runtime.py` | 内嵌运行时，能拉起 node gateway（默认端口 20789） | ✅ 代码在 |
| `gateway_start.mjs` | Gateway 启动脚本（`OPENCLAW_GATEWAY_PORT`，默认 20789） | ✅ 代码在 |
| `ws_client.py` | WS 握手客户端（connect.challenge → hello-ok → chat.send），协议 v3 | ✅ 代码在 |
| `openclaw_client.py` | HTTP 客户端（`/openclaw/send`、`/wake`、`/tools/invoke`） | ✅ 代码在 |
| `vendor/openclaw/` | OpenClaw 完整源码 | ✅ 在仓库 |
| **端口 20789 / 18789** | **零进程监听** | ❌ 没起 |

### 为什么弃 A 选 B

OpenClaw 的 gateway 原生渠道是 WhatsApp/Telegram/Discord/iMessage/Slack——**没有 QQ**。README 自己写着："QQ 暂不建议作为 OpenClaw 原生渠道接入"。

- **A（点 OpenClaw）**：借壳。要自己写 QQ adapter 塞进 TS apps 体系，还要维护 node 运行时。
- **B（长自己的器官）**：一个 Python 服务，形态与云服 Hermes 完全一致（adapter 模式 + 消息队列 + 会话路由），直接复用陆墨已验证的对话管子。

**选 B。** 工程量可控，且与现有 Python 栈同构。

---

## 一、架构设计

### 总览

```
QQ Bot API v2 (WS 长连) ──┐
                          ├──→ [Gateway 核心] ──→ 陆墨 /persona/v1/chat/completions
微信 (weixin) ────────────┘        │                    (LUMO_PROXY_TOKEN 鉴权)
                                   │                        ↓
                          [消息队列 + 会话路由]        [回复回投 adapter]
```

**数据流（一条消息的完整生命周期）：**
1. 平台事件到达（QQ C2C/群 @ / 微信消息）
2. 平台 adapter 归一化为内部 `InboundMessage`（platform / user_id / group_id / content / msg_id）
3. 进入 `asyncio.Queue`（消息队列，解耦 + 限流）
4. 会话路由器解析 → 映射到陆墨 `session_id`（platform:user_id → session_id 持久化映射）
5. 调陆墨对话端点（非流式起步，SSE 流式 M2）
6. 回复通过原 adapter 回投（QQ REST API / 微信接口）

### 复用清单（不重造轮子）

| 复用对象 | 位置 | 用途 |
|----------|------|------|
| 陆墨 `/persona/v1/chat/completions` | `apiserver/routes/lumo_proxy.py` | **主对话通道**（已验证：人格+RAG+session 注入） |
| `LUMO_PROXY_TOKEN` 鉴权 | `lumo_proxy.py:39-76` | 跨进程铁律，Bearer + `hmac.compare_digest` |
| `ws_client.py` 握手模式 | `agentserver/openclaw/ws_client.py` | QQ WS 长连的 challenge/identify 参考（协议不同，模式同） |
| Hermes QQAdapter 思路 | 云服 Hermes `gateway/platforms/qqbot/adapter.py` | QQ Bot API v2 接入形态（官方 API wss://api.sgroup.qq.com） |
| `message_manager` session 体系 | `apiserver/message_manager.py` | 会话 ID 由陆墨侧生成，gateway 只维护映射表 |

---

## 二、模块拆分（新增代码，全部在 `scratchpad/agentserver/lumo_gateway/`）

```
lumo_gateway/
├── __init__.py
├── main.py                 # 入口：asyncio 事件循环，加载 adapters，启动队列消费者
├── config.py               # 配置：端口、LUMO_PROXY_TOKEN、平台凭据（环境变量优先）
├── models.py               # InboundMessage / OutboundMessage / SessionMap 数据类
├── queue.py                # 消息队列（asyncio.Queue + 消费者任务 + 背压）
├── session_router.py       # platform:user_id → 陆墨 session_id 映射（SQLite 持久化）
├── lumo_client.py          # 调陆墨 /persona/v1/chat/completions（httpx，Bearer LUMO_PROXY_TOKEN）
├── adapters/
│   ├── __init__.py
│   ├── base.py             # PlatformAdapter 抽象基类（connect / send / on_message）
│   ├── qqbot.py            # QQ Bot API v2：WS 收事件 + REST 出站
│   └── weixin.py           # 微信 adapter（M2）
└── health.py               # /health 健康检查（供 systemd 探活）
```

**PlatformAdapter 抽象（核心契约）：**

```python
class PlatformAdapter(ABC):
    platform: str                      # "qqbot" | "weixin" | ...
    async def connect(self) -> None:   # 建立平台连接（WS/长轮询）
    async def send(self, msg: OutboundMessage) -> None:  # 回投回复
    async def run(self, on_message: Callable[[InboundMessage], Awaitable[None]]) -> None:
        ...                            # 平台事件循环，回调投递到消息队列
```

---

## 三、接口契约

### 3.1 入站（平台事件 → 归一化）

```python
@dataclass
class InboundMessage:
    platform: str          # "qqbot" | "weixin"
    msg_id: str            # 平台消息 ID（去重用）
    user_id: str           # 平台用户 openid
    group_id: str | None   # 群聊 ID（私聊为 None）
    content: str           # 文本内容
    raw: dict              # 原始平台事件（排障用）
```

### 3.2 出站（gateway → 陆墨，主通道）

```
POST {LUMO_API_BASE}/persona/v1/chat/completions
Authorization: Bearer {LUMO_PROXY_TOKEN}
Content-Type: application/json

{
  "model": "lumo",
  "messages": [{"role": "user", "content": "..."}],
  "stream": false,
  "session_id": "qqbot:{user_id}",   # 会话路由产物
  "task_type": "conversation"
}
→ 200 {"choices": [{"message": {"content": "..."}}]}
```

**为什么用 `/persona` 而不是 `/chat`：**
- `/persona` 是**已验证的跨进程通道**（NEKO 融合 M1 已打通，含鉴权铁律）
- `/chat` 不在 `_PUBLIC_PATH_PREFIXES`（`api_server.py:210-215`），受全局 token 中间件保护，gateway 要额外处理登录 token——没必要
- `/persona` 自动注入陆墨人格 + RAG + session 历史，正好是聊天场景要的

**降级**：`/persona` 503（token 未配置）时，可降级到 `/chat`（本地免鉴权模式 `require_auth=False` 时可用），但默认不走。

### 3.3 会话路由

```
路由键：{platform}:{user_id}          # 私聊
         {platform}:{group_id}:{user_id}  # 群聊（每用户每群独立 session）
→ 映射到陆墨 session_id：直接用路由键字符串（陆墨 message_manager 接受任意字符串 session_id）
→ SQLite 持久化（gateway/data/sessions.db），重启不丢
```

---

## 四、鉴权设计

| 方向 | 机制 | 说明 |
|------|------|------|
| gateway → 陆墨 | `Authorization: Bearer {LUMO_PROXY_TOKEN}` | 复用 `lumo_proxy.require_proxy_token`（hmac 常量时间比较），**不新增鉴权代码** |
| QQ 平台 | `QQ_APP_ID` / `QQ_CLIENT_SECRET` | **独立 bot**（Hermes 的 1905310911 已被占用，一个 bot 只能一个 WS 连接） |
| 微信平台 | weixin 凭据 | M2 落地时确认 |
| gateway 自身 | 绑定 `127.0.0.1`，不对外暴露 | 如需远程管理走 frp/SSH，不新增公网端口 |

---

## 五、里程碑

| 阶段 | 内容 | 验收标准 |
|------|------|----------|
| **M1** | QQ C2C 私聊直连：QQAdapter + 队列 + session 路由 + lumo_client（非流式） | 真机 QQ 发消息 → 陆墨人格回复 → 回投成功；连续对话上下文连贯 |
| **M2** | 群聊 @ 消息 + SSE 流式回复 | 群里 @ 陆墨 → 流式回复；多用户 session 隔离 |
| **M3** | 微信 adapter + 多媒体（图片/文件） | 微信收发文本；图片转发给陆墨（vision 链路） |

**M1 是本次交付核心**，M2/M3 作为后续工单。

---

## 六、部署形态

- **位置**：云服（与陆墨 apiserver 同机，`127.0.0.1` 互调，零网络开销）
- **端口**：gateway 自身 `19090`（仅 loopback）；不占用 8000/8001/8003/8443 任何现有端口
- **进程管理**：systemd `lumo-gateway.service`，`Restart=always`，`StandardOutput=journal`
- **配置**：环境变量（`LUMO_API_BASE` / `LUMO_PROXY_TOKEN` / `QQ_APP_ID` / `QQ_CLIENT_SECRET` / `GATEWAY_PORT`），不落盘明文密钥
- **探活**：`GET 127.0.0.1:19090/health` → `{status, adapters: {qqbot: connected|down}}`

---

## 七、风险与坑（预登记）

| # | 风险 | 对策 |
|---|------|------|
| 1 | QQ bot 凭据：Hermes 已占用云服 bot 1905310911 | 需用户申请**新私域机器人**（或确认可复用同一个 bot 的第二种接入方式——但一个 bot 一个 WS 长连，大概率不行） |
| 2 | QQ API intent bit 漂移（2024-2025 调整过） | 按最新文档核对 `GROUP_AT_MESSAGE_CREATE` / `C2C_MESSAGE_CREATE` intent |
| 3 | `/persona` 未配置 `LUMO_PROXY_TOKEN` 时 503 | 启动前检查 env；fail-fast 日志 |
| 4 | 长回复超过 QQ 消息长度上限 | M1 非流式回复若超长，分段回投（按 2000 字切） |
| 5 | 重复事件/重连风暴 | `msg_id` 去重（LRU）；WS 断线指数退避重连 |
| 6 | 队列背压（消息风暴时） | 队列上限 + 丢弃策略 + 日志告警 |
| 7 | gateway 重启丢会话 | session 映射 SQLite 持久化；陆墨侧 session 本身已持久化 |

---

## 八、验收清单（M1）

- [ ] 云服启动 `lumo-gateway.service`，`/health` 显示 `qqbot: connected`
- [ ] 真机 QQ 私聊发送「你好」→ 收到陆墨（人格化）回复，回投成功
- [ ] 连续 5 轮对话上下文连贯（session 路由生效，陆墨记得上文）
- [ ] 重启 gateway → session 映射不丢
- [ ] 陆墨侧日志确认请求经 `/persona/v1/chat/completions`（非 `/chat`）
- [ ] 端口检查：`ss -tlnp` 无新增公网监听（仅 127.0.0.1:19090）

---

## 附：明确不做的事

- ❌ 不点 OpenClaw gateway（20789 保持空置；vendor 源码保留不动）
- ❌ 不写 OpenClaw TS 版 QQ adapter
- ❌ 不做多平台矩阵（M1 只 QQ，M2 微信，其余平台不做）
- ❌ 不新增公网端口 / 不做自带 Web UI
