# RS-BA1 Adapter 规划 — 陆墨电台遥控能力扩展 v1

> 让陆墨通过 MCP 工具调用控制 ICOM 电台，实现语音指令→频率切换→通联记录全链路。
>
> 逆向基础：`gitee.com/fe1iscurc0r/rs-ba1-reverse`（Phase 0-4 已完成）

---

## 一、背景

### 已有条件

| 层 | 已备条件 | 来源 |
|---|---|---|
| 协议层 | CI-V 协议规范完整提取（5 字节 BCD 频率、`FE FE TO FR DATA FD` 帧格式） | rs-ba1-reverse Phase 3 |
| 实现层 | Python 跨平台 CLI（pyserial + asyncio + pyaudio） | rs-ba1-reverse Phase 4 |
| 适配层 | MCP adapter 框架成熟（4 个 adapter 跑通，_common.py 公共设施完备） | scratchpad mcpserver/adapters/ |
| 决策层 | 陆墨 LLM 通过 MCP 工具注册表发现并调用能力 | scratchpad mcp_registry.py |
| 硬件层 | IC-705（CI-V 地址 0xA4，USB 串口 115200 baud） | 本地 RS-BA1/RemoteController/ |

### 控制链路

```
陆墨（LLM 决策）
  ↓ MCP 工具调用
rsba1 adapter（mcpserver/adapters/rsba1.py）
  ↓ Python import
rsba1 包（vendor/rs-ba1-reverse/phase4-crossplat/rsba1/）
  ↓ pyserial / UDP
IC-705（CI-V 协议）
```

---

## 二、Adapter 设计

### CAPABILITY 模块级常量

```python
CAPABILITY: dict = {
    "name": "rsba1",
    "displayName": "ICOM 电台遥控",
    "description": "通过 CI-V 协议控制 Icom RS-BA1 V2 远程电台（频率/模式/PTT/音频流）",
    "version": "0.1.0",
    "license": "Private",
    "vendor": "rs-ba1-reverse",
    "_from_adapter": "rsba1",
    "security_notice": "操作需业余无线电操作证，PTT 发射需确认频率授权",
    "deployment_mode": "serial_or_udp",
}
```

### 暴露的 MCP 工具

| 工具名 | 参数 | 返回 | 安全级别 |
|---|---|---|---|
| `rsba1_connect` | `port: str` / `baudrate: int = 115200` | `{"ok": bool, "radio": str}` | 只读 |
| `rsba1_get_frequency` | 无 | `{"ok": bool, "frequency_hz": int, "frequency_str": str}` | 只读 |
| `rsba1_set_frequency` | `frequency_hz: int` | `{"ok": bool, "frequency_hz": int}` | **写入** |
| `rsba1_get_mode` | 无 | `{"ok": bool, "mode": str}` | 只读 |
| `rsba1_set_mode` | `mode: str`（LSB/USB/AM/FM/CW/RTTY） | `{"ok": bool, "mode": str}` | **写入** |
| `rsba1_ptt` | `on: bool` | `{"ok": bool, "ptt": bool, "require_confirm": bool}` | **发射** |
| `rsba1_get_s_meter` | 无 | `{"ok": bool, "s_meter": float}` | 只读 |
| `rsba1_scan` | `start_hz: int` / `end_hz: int` / `step_hz: int` | `{"ok": bool, "signals": list}` | 只读 |
| `rsba1_disconnect` | 无 | `{"ok": bool}` | 只读 |

---

## 三、安全门禁设计

### 三级安全级别

```
┌─────────────────────────────────────────────────────┐
│  级别 1：只读（get_frequency / get_mode / s_meter） │
│  → 直接执行，无门禁                                  │
├─────────────────────────────────────────────────────┤
│  级别 2：写入（set_frequency / set_mode）            │
│  → 频率白名单校验                                    │
│  → 超出业余频段 → 拒绝 + WARNING                     │
├─────────────────────────────────────────────────────┤
│  级别 3：发射（PTT on）                               │
│  → 频率白名单校验                                    │
│  → 二次确认：返回 require_confirm=True               │
│  → 陆墨/用户再次调用确认后才执行                      │
└─────────────────────────────────────────────────────┘
```

### 频率白名单（中国业余频段）

```python
_AMATEUR_BANDS = [
    (1_800_000, 2_000_000),     # 160m
    (3_500_000, 3_900_000),     # 80m
    (7_000_000, 7_200_000),     # 40m
    (10_100_000, 10_150_000),   # 30m
    (14_000_000, 14_350_000),   # 20m
    (18_068_000, 18_168_000),   # 17m
    (21_000_000, 21_450_000),   # 15m
    (24_890_000, 24_990_000),   # 12m
    (28_000_000, 29_700_000),   # 10m
    (50_000_000, 54_000_000),   # 6m
    (144_000_000, 148_000_000), # 2m
    (430_000_000, 440_000_000), # 70cm
]

def _is_amateur_band(freq_hz: int) -> bool:
    return any(lo <= freq_hz <= hi for lo, hi in _AMATEUR_BANDS)
```

### PTT 二次确认流程

```
第一次调用 rsba1_ptt(on=True)
  → 校验当前频率在白名单内
  → 返回 {"ok": True, "ptt": False, "require_confirm": True}
  → 不发射

第二次调用 rsba1_ptt(on=True, confirm=True)
  → 校验 confirm=True
  → 执行 PTT on
  → 返回 {"ok": True, "ptt": True, "require_confirm": False}
```

---

## 四、vendor 纳入策略

### 目录结构

```
vendor/
└── top5/
    └── rs-ba1-reverse/          # 从 gitee clone
        └── phase4-crossplat/
            └── rsba1/
                ├── __init__.py
                ├── ci_v.py       # CI-V 串口通信
                ├── udp_link.py   # UDP 网络远程
                ├── audio.py      # 音频流
                ├── hid_link.py   # USB HID
                ├── models.py     # 电台型号表
                └── cli.py        # 命令行接口
```

### inject_vendor_path 配置

```python
inject_vendor_path("rs-ba1-reverse", "phase4-crossplat")
# sys.path 注入：
#   vendor/top5/rs-ba1-reverse/phase4-crossplat/
#   vendor/top5/rs-ba1-reverse/
```

### healthcheck 逻辑

```python
def healthcheck() -> bool:
    inject_vendor_path("rs-ba1-reverse", "phase4-crossplat")
    try:
        from rsba1.ci_v import CivController  # noqa: F401
        from rsba1.models import RADIO_MODELS  # noqa: F401
        return True
    except Exception as e:
        logger.warning("[adapter:rsba1] 导入 rsba1 包失败: %s", e)
        return False
```

---

## 五、陆墨场景设计

### 场景 1：语音指令切频率

```
用户："切到 20 米波段，14.270 兆赫 USB"
陆墨：
  ① rsba1_get_frequency() → 确认已连接
  ② rsba1_set_frequency(14270000) → 切频率
  ③ rsba1_set_mode("USB") → 切模式
  ④ 回复："已切换到 14.270 MHz USB 模式"
```

### 场景 2：自动扫描

```
用户："扫一下 40 米波段有没有人在通联"
陆墨：
  ① rsba1_scan(7000000, 7200000, 500) → 扫描 7.000-7.200 MHz
  ② 对有信号的频率逐个 rsba1_get_s_meter() → 信号强度排序
  ③ 回复："7.053 MHz 有 S7 信号，7.118 MHz 有 S5 信号"
```

### 场景 3：应急通信

```
用户："切换到紧急频率"
陆墨：
  ① rsba1_set_frequency(7050000) → 7.050 MHz（QRP 呼叫频率）
  ② rsba1_set_mode("CW")
  ③ 回复："已切换到 7.050 MHz CW 模式，QRP 呼叫频率"
```

### 场景 4：通联日志自动记录

```
通联结束后：
陆墨自动调 summer_memory / memclaw 写入：
  - 频率：14.270 MHz
  - 模式：USB
  - 时间：2026-08-09 15:30
  - 对方呼号：（LLM 从音频转录提取）
  - 信号报告：59
```

---

## 六、实施计划

| 阶段 | 任务 | 依赖 | 状态 |
|---|---|---|---|
| **P1** | vendor 纳入 rs-ba1-reverse 仓库 | gitee clone | 待开始 |
| **P2** | 编写 `adapters/rsba1.py` 适配器 | P1 | 待开始 |
| **P3** | 编写安全门禁（频率白名单 + PTT 二次确认） | P2 | 待开始 |
| **P4** | 编写测试用例（mock CI-V，不接真实硬件） | P3 | 待开始 |
| **P5** | 更新 `adapters/__init__.py` 注册表 | P2 | 待开始 |
| **P6** | 更新 `.env.example` + `requirements.txt` | P2 | 待开始 |
| **P7** | 硬件联调（IC-705 USB 连接测试） | P1-P6 | 待硬件 |

### 依赖

```
pyserial >= 3.5      # CI-V 串口通信
pyaudio >= 0.2.14    # 音频流（可选，先不纳入）
asyncio               # 标准库
```

---

## 七、风险评估

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| LLM 幻觉导致非法频率发射 | **HIGH** | 频率白名单 + PTT 二次确认 |
| CI-V 通信超时/无响应 | MEDIUM | 工具调用加 timeout + 重试限制（3 次） |
| USB 串口被其他程序占用 | MEDIUM | healthcheck 探测端口 + 友好报错 |
| rsba1 包 Python 3.11 兼容性 | LOW | Phase 4 已在 3.11 验证通过 |
| 音频流延迟 | LOW | Phase 1 不纳入音频，只做控制面 |

---

## 八、与现有系统的关系

```
scratchpad/
├── mcpserver/adapters/
│   ├── _common.py          # 公共设施（inject_vendor_path 等）
│   ├── __init__.py          # 注册表 + 门禁
│   ├── agent_reach.py       # 已有
│   ├── vulnclaw.py          # 已有
│   ├── memclaw.py           # 已有
│   ├── headroom.py          # 已有
│   └── rsba1.py             # ← 新增
├── vendor/top5/
│   ├── Agent-Reach/         # 已有
│   ├── VulnClaw/            # 已有
│   ├── caura-memclaw/       # 已有
│   ├── headroom/            # 已有
│   └── rs-ba1-reverse/      # ← 新增（从 gitee clone）
└── tests/
    └── test_mcp_adapters.py # ← 追加 rsba1 测试用例
```

---

## 九、法律合规

- 操作者须持有有效的业余无线电操作证
- 发射频率须在业余频段白名单内
- 遵守当地无线电管理法规
- CAPABILITY 中 `security_notice` 字段强制标注授权要求
- PTT 发射需二次确认，防止 LLM 误操作

---

> 规划版本：v1
> 创建时间：2026-08-09
> 上游仓库：gitee.com/fe1iscurc0r/rs-ba1-reverse
> 适配层基线：scratchpad mcpserver/adapters/ P1 三件套（_common.py + __init__.py 门禁 + Protocol 契约）

---

# v2 — 复用 RemoteUtility 架构修订

> 修订日期：2026-08-09
> 触发原因：用户明确需求"RS-BA1 有 GUI，我用 GUI，陆墨走自己的，不能走我这边吗"
> 实测依据：`tools/probe_remote_utility.py` 在 RemoteUtility 运行时探测 127.0.0.1:50001/50002/50003

## 十、核心架构变更：不抢串口，复用 RemoteUtility

### 10.1 v1 架构问题

v1 第四章 "vendor 纳入策略" 中 `rsba1/ci_v.py` 直接通过 pyserial 打开 IC-705 的 USB 串口（COMx）。

**致命问题**：用户的 RS-BA1 RemoteController.exe 通过 RemoteUtility.exe 已经占用了 IC-705 的 USB 串口。
Windows 串口是独占式打开，第二个进程 `CreateFile("COM3")` 会失败（ERROR_SHARING_VIOLATION）。
即陆墨的 MCP adapter 一旦启动，要么抢不到串口，要么强行抢占导致用户 GUI 失效。

### 10.2 v2 架构：复用 RemoteUtility 的 UDP server

```
┌─────────────────────────────────────────────────────────────────┐
│                     IC-705 (USB CI-V)                            │
│                          ↑                                       │
│                  pyserial / HID                                  │
│                          ↑                                       │
│  ┌─────────────────── RemoteUtility.exe ───────────────────┐     │
│  │  CUDPCtrl2 (可靠 UDP 栈)                                │     │
│  │  UDP server: 0.0.0.0:50001 (CommandPort)                │     │
│  │  UDP server: 0.0.0.0:50002 (SerialPort，可选)          │     │
│  │  UDP server: 0.0.0.0:50003 (AudioPort，可选)           │     │
│  │                                                          │     │
│  │  会话层 CUDPCtrl 按 (src_ip, src_port) 维护多会话       │     │
│  └──────┬───────────────────────────────────┬──────────────┘     │
│         │ UDP                               │ UDP                │
│         ↓                                   ↓                   │
│  ┌──────────────────┐               ┌──────────────────┐         │
│  │ RemoteController │               │  rsba1 adapter   │         │
│  │     (用户 GUI)   │               │   (陆墨 MCP)     │         │
│  │                  │               │                  │         │
│  │  UtyCtrl.dll     │               │  rsba1/udp_link │         │
│  │  ↓ Mailslot      │               │  ↓ 纯 UDP       │         │
│  │  ↓ 业务逻辑      │               │  ↓ 安全门禁     │         │
│  │  VCL GUI         │               │  ↓ MCP 工具     │         │
│  └──────────────────┘               └──────────────────┘         │
│         ↑                                   ↑                   │
│      用户操作                            陆墨 LLM                 │
└─────────────────────────────────────────────────────────────────┘
```

### 10.3 实测验证结果（2026-08-09）

`tools/probe_remote_utility.py` 在用户启动 RS-BA1 后探测：

| 测试维度 | 结果 | 含义 |
|---|---|---|
| 50001 bind 探测 | `WinError 10013`（权限拒绝） | RemoteUtility 占用 50001 ✓ |
| 50001 UDP sendto 1B 探测 | 无 10054 | RemoteUtility 在 50001 监听 ✓ |
| 50002/50003 sendto | 立即 10054（ICMP Port Unreachable） | 这两个端口未启用（用户只用了 USB 模式） |
| 50001 主动探测 48 种 magic/type 组合 | 0 响应 | RemoteUtility 静默丢弃无效包（无 magic 错误回包） |
| 多 client 并发（A + B 同时发到 50001） | **不互踢** | UDP server 接受多源地址 ✓ |
| A/B 收到响应 | 0 | 握手包 magic/序列错，需抓真实流量复刻协议 |

### 10.4 架构结论

**主方案：B2 — UDP 直连 RemoteUtility**

- 物理上可行：UDP server 天然支持多 client，RemoteUtility 不踢人
- 不抢串口：陆墨 adapter 只用 UDP，不碰 COM 口
- 与用户 GUI 共存：RemoteUtility 同时服务 RemoteController + rsba1 adapter

**降级方案：B1 — Mailslot 桥接**

- 触发条件：B2 握手无法复刻（CUDPCtrl2 协议过于复杂，序列号/重传/心跳无法准确模拟）
- 实现：adapter 模拟 RemoteController 写 Mailslot 给 RemoteUtility
- 缺点：Mailslot 是 Windows-only，与 RemoteController 抢 Mailslot 写权限，需要 RemoteController 不运行时才能用

**最坏降级：B0 — 独占串口**

- 触发条件：用户不开 RS-BA1 GUI，陆墨独占使用
- 实现：v1 原方案的 `ci_v.py` 直连 pyserial
- 保留为"单机模式"，healthcheck 检测到 50001 无监听时自动降级到 B0

## 十一、rsba1 核心包结构修订

### 11.1 三模式设计

```
vendor/top5/rs-ba1-reverse/phase4-crossplat/rsba1/
├── __init__.py
├── transport/
│   ├── __init__.py
│   ├── base.py              # 抽象 Transport（connect/send/recv/close）
│   ├── udp_remote.py        # ★ B2: UDP 直连 RemoteUtility (主)
│   ├── mailslot_bridge.py   # B1: Mailslot 桥接 (Windows 降级)
│   └── serial_direct.py     # B0: pyserial 直连 (独占模式)
├── protocol/
│   ├── __init__.py
│   ├── civ.py               # CI-V 帧构造/解析 (FE FE TO FR DATA FD)
│   ├── udp_pkt.py           # CUDPCtrl2 包构造/解析 (待抓包确认)
│   └── mailslot_msg.py      # Mailslot 9 命令码 (已完成逆向)
├── radio.py                 # Radio 抽象 (connect/freq/mode/ptt/s_meter)
├── safety.py                # ★ 频率白名单 + PTT 二次确认 (下沉)
├── cli.py                   # 模式 1: 独立 CLI
└── server.py                # 模式 3: FastAPI HTTP (可选)
```

### 11.2 核心库零 MCP 依赖原则

- `rsba1/` 包 **不 import** mcpserver，单独 `pip install` 即可用
- `safety.py` 是核心库的一部分，CLI/MCP/HTTP 三种入口共享同一套安全门禁
- MCP adapter (`mcpserver/adapters/rsba1.py`) 只是 `rsba1.radio.Radio` 的薄包装

### 11.3 transport 自动选择策略

```python
# rsba1/transport/__init__.py
def create_transport(config) -> Transport:
    # 1. 探测 RemoteUtility 是否在 50001 监听
    if _probe_udp_port(config.host, config.command_port, timeout=0.5):
        return UdpRemoteTransport(config)        # B2
    # 2. 探测 Mailslot 是否可用 (Windows only)
    if _probe_mailslot():
        return MailslotBridgeTransport(config)  # B1
    # 3. 降级：独占串口
    return SerialDirectTransport(config)         # B0
```

## 十二、v1 章节修订对照

| v1 章节 | v2 修订 |
|---|---|
| 四、vendor 纳入策略 | rsba1 包结构按 11.1 修订，新增 transport/ 和 protocol/ 子包 |
| 二、Adapter 设计 | MCP 工具仍为 9 个，但底层调用 `rsba1.radio.Radio` 而非直接 ci_v |
| 三、安全门禁 | safety.py 下沉到核心库，CLI/MCP/HTTP 共享 |
| 七、风险评估 | 新增"RemoteUtility 不响应握手包"风险（HIGH） |
| 八、与现有系统关系 | 新增 vendor/top5/rs-ba1-reverse 目录 |

## 十三、新增风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| CUDPCtrl2 协议握手无法复刻 | **HIGH** | 需 Wireshark 抓 RemoteController ↔ RemoteUtility 真实流量；若无法复刻则降级 B1 |
| RemoteUtility 单 client 限制（基于会话层） | MEDIUM | 实测未踢人，但 CUDPCtrl 可能限制响应只回主会话；需协议确认后才能断言 |
| Mailslot 抢占冲突（B1 降级） | MEDIUM | Mailslot 是多读者单写者，adapter 写入可能与 RemoteController 冲突 |
| 50002/50003 端口未启用 | LOW | 用户只用 USB 模式时未启用 WLAN 端口；B2 只用 50001 (CI-V 命令) 足够 |

## 十四、待动态验证项（B2 前置）

1. **Wireshark 抓包**：RemoteController 与 RemoteUtility 在 127.0.0.1 的 UDP 流量
   - 提取 CUDPCtrl2 magic 字节
   - 记录握手序列（sync/fsync/ack）
   - 确认序列号/确认号字段位置
2. **会话层验证**：第二个 client 发握手包后，RemoteUtility 是否给两个 client 都回 sync-ack
3. **命令码封装**：CI-V 帧如何包装在 CUDPCtrl2 payload 中
4. **心跳频率**：sendNop 的发送间隔（保活阈值）

## 十五、实施计划修订

| 阶段 | 任务 | 依赖 | 状态 |
|---|---|---|---|
| P1 | vendor 纳入 rs-ba1-reverse（git submodule 或 clone） | 无 | 待开始 |
| P2 | rsba1 核心包骨架（transport/protocol/safety 三层） | P1 | 待开始 |
| P3 | **抓包确认 CUDPCtrl2 协议**（Wireshark + RemoteController） | 无 | 待开始（P2 并行） |
| P4 | 实现 UdpRemoteTransport（B2 主方案） | P2 + P3 | 待开始 |
| P5 | 实现 SerialDirectTransport（B0 独占模式） | P2 | 待开始 |
| P6 | 编写 MCP adapter (rsba1.py) | P4 | 待开始 |
| P7 | 安全门禁 + 测试用例 | P2 | 待开始 |
| P8 | Mailslot 降级方案（B1，可选） | P2 | 远期 |
| P9 | 硬件联调（IC-705 + RemoteUtility + 陆墨并发） | P4-P7 | 待硬件 |

### 优先级排序（杜赞决策输入）

- **P0 阻塞**：P3 抓包确认协议（不解决则 B2 无法实施）
- **P1 高**：P1 vendor 纳入 + P2 核心包骨架（无依赖，可并行）
- **P2 中**：P5 B0 独占模式（保底方案，不依赖 P3）
- **P3 低**：P8 Mailslot 降级（B2 成功则跳过）

---

## 十六、多智能体审查结论（2026-08-09）

> 触发：v2 文档完成后启用沈遥（架构验证）+ 杜赞（优先级决策）双智能体审查。
> 结论高度一致，本节为合流决策，**取代前述 v2 章节中的方案选型**。

### 16.1 关键反信号（沈遥发现）

v2 §10.3 实测表里"50002/50003 未启用"被忽略了。RemoteUtility 是双角色进程——服务端模式才 bind 三端口，客户端模式只 connect 远端。本地 USB 模式下 50002/50003 未启用，说明 **RemoteUtility 此刻不在"远程服务端"角色**。

50001 在监听可能是本地回环 Command 信道（为同机 RemoteController 准备），或配置成"只接受本地 RemoteController"。**48 种 magic 零响应很可能不是 magic 错，而是会话层根本没启动远程接受逻辑**。

### 16.2 B2 方案不可行（沈遥结论）

**判断：当前证据下 B2 不可行。"UDP server 不踢多 client"无法推导出"会话层支持多 client"。**

依据链：
1. UDP recvfrom 是传输层行为，不是会话层语义。RFC 768 规定 UDP 无连接，recvfrom 必然接受任何源地址——这与"愿不愿意建立会话"是两件事。
2. 静态分析有反证据：`CUDPCtrl::ExOpen/ExAccept/ExConnect/ExClose` 是显式握手 API。"ExAccept" 暗示服务端有"接受新会话"判断逻辑，而 RemoteUtility 设计目标是 1:1 服务 RemoteController。
3. 零响应是反信号：如果会话层支持多 client，即使 magic 错也应返回协议错误包（NACK/reset）。48 种组合零响应 = 静默丢弃 = "非主 client 来源"被识别为无效。
4. 即使复刻出握手包，第二个 client 发握手后服务端要么静默丢弃，要么把主 client 切换到陆墨——后者直接踢掉用户 GUI，违反"不干扰用户"初始需求。

**B2 即使成功也有副作用**：RemoteUtility 是单 socket + 单 recvfrom + 单 sendto 模型，陆墨 adapter 注入的 UDP 流量会和 RemoteController 抢同一个 recvfrom 循环，影响 GUI 响应延迟。

### 16.3 主方案改为 B0（合流决策）

**主方案：B0 独占串口，B2 降为远期探索。B1 Mailslot 不做。**

| 维度 | B0 独占串口 | B2 UDP 直连 |
|---|---|---|
| 与 GUI 共存 | 互斥（用户开 GUI 时陆墨退避） | 并发（但可能干扰 GUI） |
| 协议逆向成本 | 已完成（CI-V 已逆向） | 未完成（CUDPCtrl2 待抓包） |
| 实施周期 | 2-3 天 | 1-2 周（含抓包+复刻+调试） |
| 用户场景匹配 | 完全匹配"陆墨走自己的" | 部分匹配 |
| 失败兜底 | 无需兜底（v1 已验证） | 需 B0 兜底 |

**用户场景翻译**："RS-BA1 有 GUI 我用 GUI，陆墨走自己的" → 核心需求是"陆墨不干扰用户 GUI 时段"。B0 完美匹配：用户开 GUI → RemoteUtility 占串口 → 陆墨 healthcheck 检测到串口被占 → 退避不启动；用户关 GUI → 串口空闲 → 陆墨独占。

**B1 Mailslot 砍掉理由**（杜赞）：Mailslot 是多读者单写者，adapter 写入与 RemoteController 互斥。**本质还是抢**，只是抢的东西从串口换成了 Mailslot。B2 成功则 B1 冗余，B2 失败则 B0 已够用。三个 transport 同时维护是过度设计。

### 16.4 包结构精简（沈遥建议）

v2 §11.1 列了 6 个 transport/protocol 文件，其中 4 个是空壳。**接口预留 ≠ 实现预留**。空壳会诱导后续开发者去填，反而拖慢主路径。

**精简后结构**：

```
rsba1/
├── __init__.py
├── transport/
│   ├── __init__.py
│   ├── base.py              # 抽象 Transport（connect/send/recv/close）
│   └── serial_direct.py     # ★ B0 唯一实现
├── protocol/
│   ├── __init__.py
│   └── civ.py               # CI-V 帧（已逆向完成）
├── radio.py                 # Radio 抽象（接收 Transport 实例，依赖注入）
├── safety.py                # 频率白名单 + PTT 二次确认（下沉）
└── cli.py                   # 独立 CLI
```

等 B2 协议真逆向出来了，再补 `transport/udp_remote.py` + `protocol/udp_pkt.py`。接口已就位，扩展点清晰。

### 16.5 transport 选择逻辑上提（沈遥建议）

v2 §11.3 的 `create_transport` 探测逻辑放在核心库违反单一职责——核心库应该只提供"能用什么 transport"，不应该决定"选哪个 transport"。后者是部署策略，属于 adapter 层。

**依赖注入方式**：

```python
# 核心库 rsba1/radio.py
class Radio:
    def __init__(self, transport: Transport):
        self._transport = transport  # 只接收，不关心从哪来

# adapter 层 mcpserver/adapters/rsba1.py
def _select_transport(config) -> Transport:
    # 探测逻辑放这里
    if _probe_serial_busy(config.com_port):
        return None  # 串口被占，陆墨退避
    return SerialDirectTransport(config)

def get_radio(config) -> Radio | None:
    t = _select_transport(config)
    return Radio(t) if t else None
```

CLI 用核心库时可自决 transport，MCP adapter 用探测策略。核心库保持纯粹，可测试性高（mock transport 容易）。

### 16.6 MVP 范围（杜赞决策）

9 个工具砍到 6 个：

**保留**：`rsba1_connect` / `rsba1_disconnect` / `rsba1_get_frequency` / `rsba1_set_frequency` / `rsba1_get_s_meter` / `rsba1_ptt`

**砍掉**：
- `get_mode` / `set_mode` → 模式切换非必需，频率写路径已由 `set_frequency` 验证。增量 1 天，MVP 后补。
- `rsba1_scan` → 复合工具（依赖 s_meter + 多次 set_freq + 步进逻辑），MVP 不需要。增量 2 天，MVP 后补。

**保留 `ptt` 的理由**：它是安全门禁的最严测试（发射级 + 二次确认），不留等于没验证门禁。

### 16.7 测试策略（杜赞决策）

三层测试，硬件最后：

| 层级 | 工具 | 杀 bug 比例 | 验证目标 |
|---|---|---|---|
| 单元测试 | mock serial | 70% | CI-V 帧构造/解析、安全门禁白名单、PTT 二次确认状态机 |
| 集成测试 | com0com 虚拟串口对 | 20% | 串口收发字节流验证 |
| 硬件联调 | 真实 IC-705 USB | 10% | 电台真实响应行为（CI-V 地址、BCD 编码、S-meter 返回值） |

### 16.8 修订后实施计划

| 步骤 | 任务 | 依赖 | 验证标准 |
|---|---|---|---|
| 1 | P1 vendor 纳入 rs-ba1-reverse | 无 | `healthcheck()` 返回 True，`from rsba1.protocol.civ import CivController` 可导入 |
| 2 | P2 rsba1 核心包骨架（精简结构） | P1 | 抽象类定义完成，`SerialDirectTransport` 可实例化（未连硬件） |
| 3 | P5 SerialDirectTransport + P7 safety + 单元测试 | P2 | mock serial 下 connect→set_freq→get_freq→ptt 全链路单测通过 |
| 4 | P6 MCP adapter rsba1.py（6 工具）+ com0com 集成测试 | P3 | com0com 虚拟串口对上跑通 6 工具集成测试 |
| 5 | P9 硬件联调（IC-705 USB） | P4 | 真实电台：connect 成功、频率读取正确、set_freq 后 get_freq 一致、ptt 二次确认生效 |

**并行支线（不阻塞主线）**：P3 抓包。用户配合 30 分钟，Wireshark 抓 RemoteController↔RemoteUtility 流量囤数据。B2 实施时（MVP 之后）直接用。

**第一个可上线里程碑**：步骤 4 完成 = B0 MVP 可用。用户关掉 RS-BA1 GUI，陆墨通过 MCP 独占控制 IC-705，6 个工具全跑通。

### 16.9 P3 替代方案（如果未来启动 B2）

不要用盲扫 48 种 magic 的方式。改用静态逆向 + 动态 hook 双管齐下：

**方案 A（推荐）：静态逆向提取 magic**
- 从调试日志字符串 `" port = %d seq = %d"` 反向交叉引用，定位到包构造函数
- magic 一定是某个 `mov byte ptr [eax], 0xXX` 立即数
- 工具链已就位：仓库里有 capstone 5.0.7 + pefile 2024.8.26
- 优势：不需要启动 RemoteController，纯静态可复现
- 劣势：只能拿到 magic 字节，拿不到握手时序

**方案 B：frida 动态 hook sendto/recvfrom**
- hook RVA 0x53ade (sendto) 和 0x53bae (recvfrom)，dump 每个包的完整字节 + 调用栈
- 优势：能看到包构造时的上下文，比 Wireshark 信息密度高
- 劣势：需要 frida 环境和 RemoteController 运行

**最优组合：A + B**。先用 A 静态提取 magic 和包结构骨架，再用 B 动态验证握手时序。比纯 Wireshark 抓包快 3-5 倍，且信息更完整。
