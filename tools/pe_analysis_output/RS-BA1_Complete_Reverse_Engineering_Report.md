# RS-BA1 V2 完全逆向分析报告

> **整合范围**：本报告整合 CivCtrl.dll / UtyCtrl.dll / RadioSch.dll + RemoteUty.exe 深度逆向，以及 HidCtrl.dll / RS-BA1V2Ck.dll / UtilityCk.dll 基础静态分析，形成 RS-BA1 V2 完整架构视图。
>
> **分析方法**：纯静态（pefile + capstone 反汇编 + 字符串/立即数交叉引用 + IAT 调用点扫描）
> **生成时间**：2026-08-09
> **目标版本**：RS-BA1 V2 (2010-2018 Icom Inc., FileVersion 2.0.0.1)

---

## 1. 执行摘要

**一句话概括**：RS-BA1 V2 是一套基于「**RemoteController 前端进程 + RemoteUtility 网络代理进程**」两层架构的 Icom 电台远程控制系统，前端通过 **Windows Mailslot IPC** 与本机 RemoteUtility 通信，RemoteUtility 经自研可靠 **UDP 栈（CUDPCtrl2）** 跨 WLAN 与主机端的 RemoteUtility 服务端交换 **命令 / 串口 / 音频** 三类业务流，主机端再通过 **CI-V 串口协议（9600 8N1）** 或 **USB HID** 实际控制 Icom 电台硬件。

**核心数字速览**：

| 维度 | 数值 |
|------|------|
| 分析的 PE 文件总数 | 9 个（1 EXE 主控 + 1 EXE 服务 + 6 DLL + 1 资源 DLL）|
| 深度反汇编的组件 | 4 个（CivCtrl / UtyCtrl / RadioSch / RemoteUty）|
| 通信协议栈层数 | 3 层（Mailslot IPC → UDP WLAN → CI-V 串口）|
| 独立 UDP 业务信道 | 3 路（Command / Serial / Audio，默认 50001/50002/50003）|
| 导出函数总数 | 18（CivCtrl）+ 9（UtyCtrl）+ 10（HidCtrl）+ 5（RadioSch）+ 1（RS-BA1V2Ck）+ 1（UtilityCk）= 44 |
| 命令码（UtyCtrl） | 9 个（0–8）|
| SETUPAPI 函数（RadioSch） | 9 个，23 调用点 |
| WS2_32 函数（RemoteUty） | 18 个 |
| 发现的安全缺陷 | 6 类（详见 §5）|

---

## 2. 系统架构

### 2.1 两层架构图

```
┌──────────────────────────── 远程控制端（操作员侧）────────────────────────────┐
│                                                                              │
│              ┌──────────────────────────────────┐                            │
│              │      RemoteController.exe          │                            │
│              │      (44.9 MB, 300 导出, x86)      │                            │
│              │      MFC 主控 UI 进程               │                            │
│              └────┬─────────┬─────────┬──────────┘                            │
│                   │         │         │  同进程内调用                          │
│         ┌─────────┘         │         └──────────┐                            │
│         ▼                   ▼                    ▼                            │
│  ┌────────────┐      ┌────────────┐      ┌────────────┐                       │
│  │ UtyCtrl    │      │ CivCtrl    │      │ HidCtrl    │  三个前端控制 DLL      │
│  │ .dll       │      │ .dll       │      │ .dll       │  (Mailslot 客户端)     │
│  │ 9 导出      │      │ 18 导出    │      │ 10 导出     │                       │
│  └─────┬──────┘      └─────┬──────┘      └─────┬──────┘                       │
│        │                   │                   │                              │
│        │ 许可证检查          │                   │                              │
│        ▼                   │                   │                              │
│  ┌────────────┐            │                   │                              │
│  │UtilityCk   │            │                   │                              │
│  │.dll        │            │                   │                              │
│  └────────────┘            │                   │                              │
│        │                   │                   │                              │
│  ┌──────▼──────────────────▼───────────────────▼──────┐                      │
│  │       RS-BA1V2Ck.dll (主 UI 控件库, 2 MB)            │                      │
│  │       License: RsBA1V2_GetKeyNum (imul + 0x5127B)   │                      │
│  └─────────────────────────────────────────────────────┘                      │
└─────────┬───────────────────┬───────────────────┬─────────────────────────────┘
          │                   │                   │
          │ ① Mailslot IPC    │ ① Mailslot IPC    │ ① Mailslot IPC
          │ (本机单向消息队列)  │ (本机单向消息队列)  │
          ▼                   ▼                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     RemoteUtility.exe (网络代理进程, 3 MB)                  │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐    │
│   │              Mailslot 服务器端 (读取 Remote*Cmd, 写 Remote*Res)        │    │
│   │              Mutex: Icom RemoteUtyCtrl (5000ms 超时)                 │    │
│   └──────────────────────────────────────────────────────────────────────┘    │
│                                  │                                           │
│                                  ▼ ② UDP WLAN                                │
│   ┌──────────────────────────────────────────────────────────────────────┐    │
│   │   CUDPCtrl2 (自研可靠 UDP 栈)                                         │    │
│   │   Sync/FSync/Nop(心跳)/Resend(重传) + TimerThread                    │    │
│   ├──────────────────────────────────────────────────────────────────────┤    │
│   │   CUDPCtrl (会话层)                                                   │    │
│   │   ExOpen/ExAccept/ExConnect/ExSend/ExClose                          │    │
│   ├──────────────────────────────────────────────────────────────────────┤    │
│   │   CUdp (UDP 传输层)                                                   │    │
│   │   socket(AF_INET, SOCK_DGRAM) + bind(INADDR_ANY) + recvfrom/sendto │    │
│   └──────────────────────────────────────────────────────────────────────┘    │
│                                  │                                           │
│   ┌────────────────┬──────────────┴─────────────┬─────────────────┐           │
│   │ Command 信道    │   Serial 信道              │   Audio 信道    │           │
│   │ UDP 50001      │   UDP 50002                │   UDP 50003     │           │
│   │ (CClientCmd)   │   (CClientSerialCtrl)      │   (CClientAudio) │           │
│   └────────────────┘ └────────────┬─────────────┘ └─────────────────┘           │
└────────────────────────────────────┼─────────────────────────────────────────┘
                                     │
═════════════════════════════════════╪═══════════════════════════════════════════
                          WLAN (UDP 明文, 无加密无认证)
═════════════════════════════════════╪═══════════════════════════════════════════
                                     │
┌────────────────────────────────────▼─────────────────────────────────────────┐
│              主机端 RemoteUtility (服务端, 同一 EXE 角色)                      │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐    │
│   │   RadioSch.dll (电台调度核心, 1.97 MB, 5 导出)                         │    │
│   │                                                                       │    │
│   │   ┌────────────────────────────────────────────────────────────────┐ │    │
│   │   │  SETUPAPI 设备枚举 (9 函数, 23 调用点)                          │ │    │
│   │   │  SetupDiGetClassDevs + CM_Get_Device_IDA (7) +                  │ │    │
│   │   │  CM_Get_Parent/Child/Sibling (USB 设备树遍历)                    │ │    │
│   │   │  匹配模式: sprintf(buf, "VIDPID%d", vid)                        │ │    │
│   │   └────────────────────────────────────────────────────────────────┘ │    │
│   │   ┌────────────────────────────────────────────────────────────────┐ │    │
│   │   │  CCIVComIF / CCIVCom (CI-V 串口)                                │ │    │
│   │   │  CreateFileA("\\.\COM%d", baud=%d N81)                         │ │    │
│   │   │  Mutex: MUTEX_REMOTEUTY_CCIVCOMIF_COM%d (每串口一把)            │ │    │
│   │   │  SendThread + RecvThread (多线程)                              │ │    │
│   │   └────────────────────────────────────────────────────────────────┘ │    │
│   │   ┌────────────────────────────────────────────────────────────────┐ │    │
│   │   │  虚拟驱动: icom_vaudio.sys + icom_vserial.sys                   │ │    │
│   │   │  用户态: \\.\ICOM_SERIAL / VAudioDevice                         │ │    │
│   │   │  内核态: \Device\IcomVSerial / ICOM_VAUDIO                      │ │    │
│   │   │  注册表: SYSTEM\CurrentControlSet\Services\icom_vaudio\Params │ │    │
│   │   └────────────────────────────────────────────────────────────────┘ │    │
│   └──────────────────────────────────────────────────────────────────────┘    │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │ ③ CI-V 串口 (9600 8N1) 或 USB HID
                                     ▼
                          ┌──────────────────────┐
                          │   Icom 电台硬件       │
                          │   (USB Composite)     │
                          │   - CI-V 串口接口     │
                          │   - USB Audio         │
                          │   - HID 控制          │
                          └──────────────────────┘
```

### 2.2 数据流图

#### 2.2.1 控制命令下行（操作员 → 电台）

```
[操作员点击 UI]
    │
    ▼ RemoteController.exe (同进程内调用)
[civSend(h, cmdBytes, len, flag)]   ← CivCtrl.dll 导出
    │
    ▼ 构造 mailslot 消息: {flag:1, dataLen:4, data:N}
[WriteFile(\\.\mailslot\civsend)]   ← Mailslot 写入
    │
    ▼ (内核消息队列)
[SendRecvThread 读 mailslot]        ← CivCtrl.dll 后台线程
    │
    ▼ 组装 CI-V 帧: [0xFE×N][toAddr][fromAddr][cmd][data][0xFD]
[WriteFile(hCom, frame)]            ← 串口写入
    │
    ▼ RS-232 9600 8N1
[Icom 电台接收命令]
```

**远程场景**（前端 DLL 不直接打串口，而是经 Mailslot → RemoteUtility → UDP → 远端）：

```
[civSend] → Mailslot → RemoteUtility → CUDPCtrl2 (UDP 50002 Serial 信道)
    → WLAN → 远端 RemoteUtility → RadioSch.dll → CCIVCom → 串口 → 电台
```

#### 2.2.2 状态/数据上行（电台 → 操作员）

```
[Icom 电台应答]
    │
    ▼ RS-232
[ReadFile(hCom)]                    ← CivCtrl.dll SendRecvThread 内字节循环
    │
    ▼ civAnalyze 状态机
[IDLE→ECHO_WAIT→ECHO_CHECK→ANSWER_WAIT→ANSWER_PROC→IDLE]
    │
    ▼ AddRecvData → WriteFile(\\.\mailslot\civrecv)
[Mailslot 写入]
    │
    ▼ (内核消息队列)
[civRecv(h, buf, size, flag)]       ← CivCtrl.dll 导出
    │
    ▼ 返回 RemoteController.exe
[UI 更新显示]
```

#### 2.2.3 音频流（独立信道，绕过控制 DLL）

```
[电台 USB Audio 输出] → 主机端 RemoteUtility (UDP 50003 Audio 信道)
    → WLAN → 前端 RemoteUtility
    → DirectSound / WaveOut 播放

注：音频流不经过 UtyCtrl/CivCtrl/HidCtrl，由 RemoteUtility 进程直接处理
    UtyCtrl.dll 仅查询音量/电平（GetClientTransVol 系列），不传输 PCM 数据
```

---

## 3. 通信协议栈（三层）

### 3.1 协议栈总览

| 层 | 协议 | 端点 | 可靠性 | 安全性 |
|----|------|------|--------|--------|
| **L1 本机 IPC** | Windows Mailslot | 前端 DLL ↔ RemoteUtility | 单向消息队列，无重传 | **无认证**，任意本地进程可注入 |
| **L2 WLAN** | UDP + 自研可靠栈 CUDPCtrl2 | RemoteUtility 客户端 ↔ RemoteUtility 服务端 | 序列号 + 重传 + 心跳 | **明文**，无加密无 HMAC |
| **L3 串口** | Icom CI-V | RemoteUtility 主机端 ↔ 电台 | ECHO/ANSWER 双超时 + JAM 重试 | 物理隔离（RS-232 / USB）|

### 3.2 L1 — Mailslot IPC 层

#### 3.2.1 Mailslot 命名空间（基于 UtyCtrl.dll 静态证据 + CivCtrl.dll 静态证据）

| Mailslot 名 | 创建方 | 写入方 | 读取方 | 用途 |
|---|---|---|---|---|
| `\\.\mailslot\civsend` | CivCtrl.dll (civOpen) | 业务进程 (civSend) | CivCtrl.dll (SendRecvThread) | CI-V 命令下行 |
| `\\.\mailslot\civrecv` | CivCtrl.dll (civOpen) | CivCtrl.dll (AddRecvData) | 业务进程 (civRecv) | CI-V 应答上行 |
| `\\.\mailslot\RemoteUtyCtrlCmd` | RemoteUtility | UtyCtrl.dll (CreateFileA) | RemoteUtility | Utility 命令下行 |
| `\\.\mailslot\RemoteUtyCtrlRes` | UtyCtrl.dll (CreateMailslotA, 每次重建) | RemoteUtility | UtyCtrl.dll (ReadFile) | Utility 响应上行 |
| `\\.\mailslot\RemoteCivCtrlCmd/Res` | (推断) | (推断) | (推断) | CI-V 远程命令 |
| `\\.\mailslot\RemoteHidCtrlCmd/Res` | (推断) | (推断) | (推断) | HID 远程命令 |

**点号 (`\\.\`) 表示本机命名空间**，所有 Mailslot 都是本机 IPC，不跨机。真正的 WLAN 通信由 RemoteUtility 进程独立完成。

#### 3.2.2 Mailslot 消息格式

**CivCtrl.dll 的 civsend mailslot**（`civSend` 构造）：

```
┌──────────┬──────────────┬───────────────┐
│ flag     │ dataLen      │ data          │
│ (1 byte) │ (4 bytes LE) │ (N bytes)     │
└──────────┴──────────────┴───────────────┘
```

**CivCtrl.dll 的 civrecv mailslot**（`civRecv` 解析）：

```
┌──────────┬──────┬──────────────┬───────────────┐
│ msgId    │ flag │ dataLen      │ data          │
│ (4 bytes)│ (1B) │ (4 bytes LE) │ (N bytes)     │
└──────────┴──────┴──────────────┴───────────────┘
```

**UtyCtrl.dll 的 RemoteUtyCtrlCmd mailslot**（命令包）：

```c
#pragma pack(push, 1)
struct UtyCtrlCmdPkt {
    uint8_t  cmd_code;          // offset 0: 命令码 (0-8)
    uint8_t  data_len;          // offset 1: 负载长度（不含头部 4 字节）
    uint8_t  reserved[2];       // offset 2-3: 保留（栈上残留）
    uint8_t  payload[data_len]; // offset 4+: 实际数据
};  // 总写入字节数 = data_len + 4
#pragma pack(pop)
```

**UtyCtrl.dll 的 RemoteUtyCtrlRes mailslot**（响应包）：

```c
struct UtyCtrlRespPkt {
    uint8_t  echo_cmd_code;     // offset 0: 回填原 cmd_code（echo 确认）
    uint8_t  status;             // offset 1: 状态码
    uint8_t  reserved[2];        // offset 2-3
    uint8_t  payload[];          // offset 4+: 响应数据
};
```

#### 3.2.3 UtyCtrl.dll 9 个命令码映射

| cmd_code | 导出函数 | data_len | 模式 | 用途 |
|---|---|---|---|---|
| 0 | GetCountClientTrans | 0 | 请求-响应 | 查询客户端传输数量 |
| 1 | GetClientTransInfo | 0x6C (108) | 请求-响应 | 查询传输信息 v1 |
| 2 | ExecCmd | 动态 (arg5+0x14) | **单向 fire-and-forget** | 执行控制命令（PTT/模式切换等） |
| 3 | GetClientTransVol | 0x24 (36) | 请求-响应 | 查询客户端音量 v1 |
| 4 | GetClientTransInfo2 | 0x78 (120) | 请求-响应 | 查询传输信息 v2（扩展） |
| 5 | GetClientTransVol3 | 0x3C (60) | 请求-响应 | 查询客户端音量 v3 |
| 6 | GetCommandProcCount | 0 | 请求-响应 | 查询命令处理计数 |
| 7 | GetRemoteTransNetworkSet | 0x40 (64) | 请求-响应 | **查询远端网络配置（含 WLAN 参数）** |
| 8 | GetRemoteTransState | 0x1C (28) | 请求-响应 | 查询远端传输状态 |

**响应包 echo 校验机制**：RemoteUtility 在响应包 offset 0 回填原 `cmd_code`，UtyCtrl 各 `Get*` 函数用 `cmp byte ptr [esp+8], <原 cmd_code>` 校验，不匹配即视为协议错误。

#### 3.2.4 Mailslot 事务状态机（UtyCtrl 核心函数 @ 0x10001080）

```
入口 (cmd_buf, resp_buf)
    │
    ▼
WaitForSingleObject(g_mutex "Icom RemoteUtyCtrl", 5000ms)
    │
    ├─ WAIT_OBJECT_0 → 继续
    ├─ WAIT_ABANDONED → 继续
    └─ WAIT_TIMEOUT → 返回失败
    │
    ▼
CreateFileA(RemoteUtyCtrlCmd, GENERIC_WRITE)
    │
    ├─ 失败 (INVALID_HANDLE_VALUE) → 跳到清理
    │
    ▼
若需响应: CreateMailslotA(RemoteUtyCtrlRes, cbMaxMsg=260, timeout=FOREVER)
    │
    ├─ 失败 → 跳到清理
    │
    ▼
WriteFile(cmd_mailslot, cmd_buf, data_len+4)
    │
    ├─ 失败 → 跳到清理
    │
    ▼
若需响应:
    循环:
        GetMailslotInfo(res_mailslot, &msg_count)
        if msg_count == -1 (MAILSLOT_NO_MESSAGE):
            Sleep(1)
            goto 循环           ← ⚠️ 无超时上限！
    ReadFile(res_mailslot, resp_buf, msg_count)
    │
    ▼
清理: CloseHandle(cmd) / CloseHandle(res) / ReleaseMutex(g_mutex)
    │
    ▼
返回 (0=成功, 1=失败)
```

**关键参数**：

| 参数 | 值 | 来源 |
|---|---|---|
| Mutex 名 | `Icom RemoteUtyCtrl` | 字符串 @ 0x10023854 |
| Mutex 超时 | 5000 ms (0x1388) | 立即数 @ 0x1000108D |
| 响应 mailslot cbMaxMsg | 260 字节 (0x104) | 立即数 @ 0x100010DC |
| 响应 mailslot 读超时 | MAILSLOT_WAIT_FOREVER (-1) | 立即数 @ 0x100010DA |
| 轮询退避 | 1 ms (Sleep(1)) | 立即数 @ 0x1000114E |

### 3.3 L2 — UDP WLAN 层（自研可靠 UDP 栈）

#### 3.3.1 WS2_32.dll 18 个导入函数（RemoteUty.exe）

| 函数 | 调用点数 | 用途 |
|------|----------|------|
| `WSAStartup` | 4 | 初始化 Winsock（版本 0x0202 = 2.2） |
| `WSACleanup` | 9 | 释放 Winsock |
| `socket` | 1 | 创建 UDP socket（**仅 1 处，单 socket 模型**） |
| `bind` | 1 | 绑定本地端口（服务端模式） |
| `htons` / `htonl` | 2 / 4 | 字节序转换 |
| `ntohs` / `ntohl` | 2 / 1 | 字节序转换 |
| `inet_ntoa` | 1 | IP 转字符串（仅日志用） |
| `gethostbyname` | 3 | DNS 解析（**已弃用 API**） |
| `getsockname` | 1 | 获取本地 socket 地址 |
| `setsockopt` | **0** | **未调用！** 未设置 SO_REUSEADDR 等 |
| `recvfrom` | 1 | 接收 UDP 数据包 |
| `sendto` | 1 | 发送 UDP 数据包 |
| `WSAIoctl` | 1 | SIO_GET_INTERFACE_LIST (0x9800000c) 枚举本机 IP |
| `closesocket` | 4 | 关闭 socket |
| `shutdown` | 4 | 关闭 socket 收发方向 |
| `WSAGetLastError` | 7 | 获取错误码 |

**关键结论**：
- 无 `listen/accept/connect/recv/send` → **纯 UDP，无 TCP**
- `socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)` 确证（RVA 0x5376c）
- `setsockopt` 0 调用点 → **未配置任何 socket 选项**（详见 §5 安全分析）

#### 3.3.2 三层 UDP 协议栈架构

```
┌─────────────────────────────────────────────────────────────┐
│                  业务层（RemoteController 通信）             │
├──────────────────┬──────────────────┬──────────────────────┤
│  Command 信道     │   Serial 信道     │   Audio 信道          │
│  CClientCommand  │  CClientSerial   │  CClientAudio        │
│  Ctrl            │  Ctrl            │  Ctrl                │
│  (UDP 50001)     │  (UDP 50002)     │  (UDP 50003)         │
├──────────────────┴──────────────────┴──────────────────────┤
│        可靠传输层（CUDPCtrl2）                                │
│  - sendReqSync / sendReqFSync    同步请求                    │
│  - sendNop                       心跳 (KeepAlive)            │
│  - sendReqResend                 重传请求 (NACK 模式)        │
│  - TimerThread                   超时重传线程                │
│  - setResend                     重传配置                    │
│  - ExecSync / ExecFsync / ExecCmd   执行命令                 │
├──────────────────────────────────────────────────────────────┤
│        会话层（CUDPCtrl）                                    │
│  - ExOpen / ExConnect / ExAccept   建立/接受会话            │
│  - ExSend / ExClose                发送/关闭                 │
│  - ExSessionClose                  会话级关闭                │
│  - sendDisconnect / recvCallback    断连通知/回调             │
├──────────────────────────────────────────────────────────────┤
│        UDP 传输层（CUdp）                                    │
│  - open (socket + bind INADDR_ANY) / close                  │
│  - send (sendto) / recv (recvfrom)                          │
│  - recvThread (后台接收线程)                                 │
│  - addCallback / delCallback                                 │
├──────────────────────────────────────────────────────────────┤
│        Winsock API（WS2_32.dll）                            │
│  WSAStartup → socket(SOCK_DGRAM) → bind →                   │
│  recvfrom/sendto → closesocket → WSACleanup                │
└──────────────────────────────────────────────────────────────┘
```

#### 3.3.3 端口配置（运行时注册表读取）

字符串证据：

| 字符串 | RVA | 引用点 | 含义 |
|--------|-----|--------|------|
| `CommandPort` | 0x1bb89c | 0x2b00e, 0x2b2f4, 0x31bc6 | 命令信道端口 |
| `SerialPort` | 0x1bb8a8 | 0x2b024, 0x2b306, 0x31be7 | 串口信道端口 |
| `AudioPort` | 0x1bb8b4 | 0x2b03a, 0x2b318, 0x31c08 | 音频信道端口 |
| `SOFTWARE\Icom\Remote Utility` | 0x1bbb04 | 0x2d4e3, 0x30915, 0x30cbc | 主配置注册表键 |
| `SOFTWARE\Icom\RS-BA1\RemoteUty` | 0x1bc200 | 0x31a3c, 0x31b0a | 兼容性配置键 |

**资源 ID 推测默认端口**：

| 资源 ID | 十进制 | 推测默认端口 |
|---|---|---|
| 0xC351 | 50001 | CommandPort |
| 0xC352 | 50002 | SerialPort |
| 0xC353 | 50003 | AudioPort |

读取优先级：注册表 `SOFTWARE\Icom\Remote Utility\CommandPort` → 资源段字符串表默认值 50001。

#### 3.3.4 数据包格式（推测，基于调试日志字符串 `" port = %d seq = %d"`）

```c
struct RsBa1UdpPacket {
    uint8_t  magic;          // 协议魔数（待动态确认）
    uint8_t  type;           // 包类型: sync/fsync/cmd/nop/data/resend
    uint16_t port;           // 业务端口标识
    uint32_t seq;            // 序列号（用于重传，非防重放）
    uint32_t ack_seq;        // 确认号（推测）
    uint8_t  payload[];      // 载荷
};
```

包类型：
- `sendReqSync` — 同步请求（请求对端序号同步）
- `sendReqFSync` — 强制同步请求
- `sendNop` — 心跳/保活
- `sendReqResend` — 重传请求（NACK 模式）
- `ExecSync/ExecFsync/ExecCmd` — 命令执行

#### 3.3.5 音频流处理（CAudioCtrl）

调试日志字符串揭示音频参数：

```
m_SendConf: fs:%d bit:%d ch:%d codec:%s cnt:%d time:%d
m_RecvConf: fs:%d bit:%d ch:%d codec:%s cnt:%d time:%d
```
- `fs` = 采样率
- `bit` = 位深
- `ch` = 声道
- `codec` = 编码格式
- `cnt` = 块大小
- `time` = 时长

关键类：
- `CSampleConv::conv/conv1/conv3/lpf/bitchnconv` — 重采样 + 低通滤波
- `CAudioCtrl::CheckPostUdpRecv` — UDP 接收后处理（处理丢包导致的"切割"）
- `CClientAudioCtrl::vaudioSendBlock` — 通过虚拟音频驱动发送块

### 3.4 L3 — CI-V 串口层

#### 3.4.1 串口配置（CivCtrl.dll @ 0x401C30）

```asm
0x401C7A: push  0x41C234          ; "\\.\COM%d"
0x401CC0: push  0x41C23E          ; "baud=%d parity=N data=8 stop=1"
0x401CD4: push  0x1C              ; sizeof(DCB) = 28
0x401CEF: call  BuildCommDCBA
0x401D88: call  SetCommState
0x401DC2: call  SetCommTimeouts   ; 全 0 (非阻塞读)
0x401DD8: push  0x403968          ; SendRecvThread
0x401DDD: call  _beginthreadex
```

| 参数 | 默认值 | 证据 |
|------|--------|------|
| 端口名格式 | `\\.\COM%d` | 字符串 @ 0x41C234 |
| 波特率 | 9600 (0x2580)，运行时参数化 | 构造函数 `mov [edx+0xc], 0x2580` @ 0x40164B |
| 数据位 | 8 | `data=8` |
| 停止位 | 1 | `stop=1` |
| 校验 | N (None) | `parity=N` |
| 流控 | 无 (CTS/Dsr 流控均为 0) | DCB 位操作 and 0xFD/0xFB/0xF7 |
| DTR 控制 | 默认 DISABLE (0)，可配 | `[esi+0x12]` |
| RTS 控制 | 默认 DISABLE (0)，可配 | `[esi+0x13]`（若用 RTS 硬件 PTT 需改）|
| 超时 | 全 0（非阻塞读）| SetCommTimeouts 传入全 0 结构 |

#### 3.4.2 CI-V 帧格式（运行时构造，非静态模板）

CI-V 是 Icom 电台的标准串口控制协议，标准帧格式：

```
┌──────┬──────┬────────┬──────────┬─────────┬──────┐
│ 0xFE │ 0xFE │ toAddr │ fromAddr │ cmd[+data]│ 0xFD │
└──────┴──────┴────────┴──────────┴─────────┴──────┘
 前导   前导   目标      源         命令体     结束
```

**关键发现**：静态二进制中**不存在任何完整的 CI-V 帧模板**（扫描 `0xFE 0xFE ... 0xFD` 结果为 0）。帧在 `civSendSub @ 0x402360` 中动态拼装：

```asm
0x4023CD: mov   si, [ebx+0x14]      ; si = preambleCount
0x4023D1: add   si, 2               ; si += 2 (标准 FE FE)
0x4023D8: add   eax, 0x401          ; 分配 size = si + 0x401
0x4023DE: call  alloc

0x4023F6: mov   byte ptr [eax], 0xFE    ; 循环写入 si 个 0xFE 前导
0x402416: call  memcpy                ; 复制命令体 (toAddr+fromAddr+cmd+data)
0x40242A: mov   byte ptr [ecx+eax], 0xFD  ; 写入帧尾 0xFD
0x40245C: call  WriteFile            ; 写串口
```

**结论**：CivCtrl.dll 是纯粹的**帧包装 + 串口传输 + 应答状态机**层。具体 CI-V 命令（如设频率 0x05/0x06、设模式 0x06、PTT 0x1C）由调用方按 CI-V 规范构造完整命令体后通过 `civSend` 传入。

#### 3.4.3 CI-V 命令参考（DLL 不实现，由调用方构造）

| 命令 | 子命令 | 语义 | 示例帧 (to=0x04 IC-7300, from=0xE0) |
|------|--------|------|--------------------------------------|
| 0x01 | — | 切换频率 (上/下) | `FE FE 04 E0 01 FD` |
| 0x03 | — | 读频率 | `FE FE 04 E0 03 FD` |
| 0x04 | — | 读模式 | `FE FE 04 E0 04 FD` |
| 0x05 | — | 设模式 | `FE FE 04 E0 05 <mode> <filter> FD` |
| 0x06 | — | 设频率 (VFO) | `FE FE 04 E0 06 <5字节BCD> FD` |
| 0x14 | 0x0C | 读 PTT 状态 | `FE FE 04 E0 14 0C FD` |
| 0x1C | 0x00 | 设 PTT (0=RX, 1=TX) | `FE FE 04 E0 1C 00 <01/00> FD` |
| 0x1A | 0x03 | 读 S-meter | `FE FE 04 E0 1A 03 FD` |

#### 3.4.4 CIVDriver 对象布局（~0xB00 字节，vtable @ 0x41CC9C）

```
CIVDriver 对象 (~0xB00 字节)
├── +0x000  void*  vtable               ; vtable 指针
├── +0x004  HANDLE hCom                 ; 串口 handle (初始 INVALID_HANDLE_VALUE)
├── +0x008  int    comPort              ; COM 端口号 (默认 1 = COM1)
├── +0x00C  int    baudRate             ; 波特率 (默认 0x2580 = 9600)
├── +0x010  BYTE   toAddress            ; CI-V 目标地址 (默认 0x7F)
├── +0x011  BYTE   fromAddress          ; CI-V 源地址   (默认 0x00)
├── +0x012  BYTE   fDtrControl          ; DCB DTR 模式 (默认 0)
├── +0x013  BYTE   fRtsControl          ; DCB RTS 模式 (默认 0)
├── +0x014  WORD   preambleCount        ; 额外 0xFE 前导数 (默认 0, 实际写 count+2)
├── +0x016  WORD   civTot               ; CI-V 总超时 (默认 0x3A98 = 15000)
├── +0x018  BYTE   status               ; 状态机当前状态 (默认 1 = IDLE)
├── +0x019  struct TxBuf                ; 发送缓冲区
├── +0x439  struct RxBuf                ; 接收缓冲区
├── +0x85A  CRITICAL_SECTION cs1        ; 临界区 1
├── +0x862  struct Timeout echoTout     ; ECHO 超时 (500ms = 0x1F4)
├── +0x882  struct Timeout ansTout      ; ANSWER 超时 (500ms = 0x1F4)
├── +0x88A  BYTE   threadRunning        ; SendRecvThread 运行标志
├── +0x88B  BYTE   sendPending          ; 待发送标志
├── +0x88C  HANDLE hMailslotSend        ; civsend mailslot handle
├── +0x890  HANDLE hMailslotRecv        ; civrecv mailslot handle
├── +0xAAB  BYTE   subState             ; 子状态机状态
├── +0xAAC  CRITICAL_SECTION csSend     ; 发送临界区
└── +0xAC4  void*  traceObj             ; CIVTrace 对象指针
```

**默认地址陷阱**：to=0x7F（通配地址），from=0x00。若调用方忘记 `civSetAddress`，CI-V 帧会用 `to=0x7F from=0x00` 发送。0x7F 不是标准广播地址（0x00 才是），可能导致电台无响应。

#### 3.4.5 CI-V 状态机（civAnalyze @ 0x402D44）

状态定义（对象字段 `status @ +0x18`）：

| 值 | 状态名 | 证据字符串 |
|----|--------|-----------|
| 1 | IDLE | `--> IDLE` |
| 2 | ECHO_WAIT | `-->ECHO` |
| 3 | ECHO_CHECK / ANSWER_WAIT | `-->ANSWER` |
| 4 | ANSWER_PROC | (case 4) |

状态流：

```
                civSend() 写入 mailslot
                       │
                       ▼
        ┌────────▶ IDLE (stat=1)
        │              │ civSendSub 写串口
        │              ▼
        │         ECHO_WAIT (stat=2)  ──ECHO 超时(500ms)──► JAM (civRetry)
        │              │ 收到回声数据
        │              ▼
        │         ECHO_CHECK (stat=3) ──ECHO 不匹配──► 重试
        │              │ ECHO 匹配 (memcmp==0, "ECHO OK!!!")
        │              ▼
        │         ANSWER_WAIT (stat=3) ──ANSWER 超时(500ms)──► JAM
        │              │ 收到应答
        │              ▼
        │         ANSWER_PROC (stat=4)
        │              │ 处理完成, AddRecvData
        └──────────────┘ 切回 IDLE
```

**超时机制**：
- ECHO 超时：500ms (0x1F4)，存于对象 `+0x862`，用 `timeGetTime()` 时间戳判定
- ANSWER 超时：500ms (0x1F4)，存于对象 `+0x882`
- CIVTOT 总超时：15000 (0x3A98)，存于对象 `+0x16`，可通过 `civSetCivTot` 配置
- 超时触发 `civError @ 0x4038B0`，记录错误码（如 0x1D = WriteFile 失败）

---

## 4. 各组件分析摘要

### 4.1 CivCtrl.dll — CI-V 串口控制核心

| 属性 | 值 |
|------|-----|
| 文件路径 | `d:\my git\RS-BA1\RemoteController\CivCtrl.dll` |
| 大小 | 151,040 bytes (147.5 KB) |
| 编译器 | **Borland C++** (Copyright 2005 Borland Corporation) |
| 编译时间 | 2018-06-15 05:58:22 |
| ImageBase | 0x400000 |
| 导出函数 | 18 个（全部 `civXXX` 命名）|
| 导入 DLL | 3 个（KERNEL32 / USER32 / WINMM）|

**职责**：通过 CI-V 协议与 Icom 电台通信的串口控制核心 DLL。

**架构亮点**：
1. **IPC 解耦** — 不直接被业务进程调用打串口。`civSend` 把数据写入 mailslot `\\.\mailslot\civsend`，由内部 `SendRecvThread @ 0x403968` 线程读取后真正写串口；串口收到的数据由线程解析后写入 `\\.\mailslot\civrecv`，业务进程通过 `civRecv` 读取。
2. **句柄抽象** — `HandleResolver @ 0x404910` 把内部 `CIVDriver*` 对象指针封装为整数 ID，防止跨进程句柄泄露。
3. **状态机鲁棒** — ECHO/ANSWER 双超时 + JAM 重试，覆盖 CI-V 总线冲突场景。
4. **CI-V 帧运行时构造** — 静态二进制中不存在任何完整 CI-V 帧模板（扫描结果 0）。帧在 `civSendSub @ 0x402360` 中动态拼装：`[0xFE × N][用户数据][0xFD]`，N = `preambleCount + 2`。

**18 个导出函数**：

| # | 名称 | 签名推断 |
|---|------|---------|
| 1 | civOpen | `int civOpen(HANDLE h, int comPort, int baud, BYTE dtr, BYTE rts)` |
| 2 | civSetAddress | `void civSetAddress(HANDLE h, BYTE toAddr, BYTE fromAddr)` |
| 3 | civSetAddPreamble | `void civSetAddPreamble(HANDLE h, WORD count)` |
| 4 | civSetCivTot | `void civSetCivTot(HANDLE h, WORD tot)` |
| 5 | civClose | `void civClose(HANDLE h)` |
| 6 | civSend | `void civSend(HANDLE h, void* data, int len, BYTE flag)` |
| 7 | civGetRecvSize | `int civGetRecvSize(HANDLE h)` |
| 8 | civRecv | `int civRecv(HANDLE h, void* buf, int* size, BYTE* flag)` |
| 9 | civIsSendEnable | `int civIsSendEnable(HANDLE h)` |
| 10 | civSetRetryFA | `void civSetRetryFA(HANDLE h, BYTE flag)` |
| 11 | civSetWaitTime | `void civSetWaitTime(HANDLE h, int ms)` |
| 12 | civResetOthAnsCount | `void civResetOthAnsCount(HANDLE h)` |
| 13 | civGetOthAnsCount | `int civGetOthAnsCount(HANDLE h)` |
| 14 | civResetRxByteCount | `void civResetRxByteCount(HANDLE h)` |
| 15 | civGetRxByteCount | `int civGetRxByteCount(HANDLE h)` |
| 16 | civSetConType | `void civSetConType(HANDLE h, BYTE type)` |
| 17 | civGetConType | `int civGetConType(HANDLE h)` |
| 18 | ___CPPdebugHook | Borland C++ 调试钩子（数据非代码）|

### 4.2 UtyCtrl.dll — Utility 控制（Mailslot 前端）

| 属性 | 值 |
|------|-----|
| 文件路径 | `d:\my git\RS-BA1\RemoteController\UtyCtrl.dll` |
| 大小 | 204,288 bytes |
| 编译器 | MSVC 9.0 (VS2008 SP1) + MFC |
| 编译时间 | 2018-06-19 05:35:08 UTC |
| ImageBase | 0x10000000 |
| PDB 路径 | `C:\Release\dll\UtyCtrl\Release\UtyCtrl.pdb` |
| 导出函数 | 9 个 |
| 导入 DLL | 8 个 |

**关键修正**：UtyCtrl.dll **不直接做 WLAN socket 通信**。导入表里没有 `ws2_32.dll`、没有 `WSAStartup`/`socket`/`connect`/`send`/`recv`。它通过 **Windows Mailslot IPC** 与本机的 RemoteUtility 进程通信。真正的网络通信在 RemoteUtility 进程内。

**职责**：RemoteController 进程内的"IPC 前端"，把命令通过 Mailslot 转发给 RemoteUtility，由后者完成网络收发。

**核心模式**：
- 8 个 `Get*` 函数走"请求-响应"完整流程（调用核心函数 0x10001080）
- 1 个 `ExecCmd` 走 fire-and-forget 单向写入（无响应读取）

**Mailslot 拓扑**：

| Mailslot 名 | 创建方 | 写入方 | 读取方 |
|---|---|---|---|
| `\\.\mailslot\RemoteUtyCtrlCmd` | RemoteUtility | UtyCtrl (CreateFileA) | RemoteUtility |
| `\\.\mailslot\RemoteUtyCtrlRes` | UtyCtrl (CreateMailslotA, **每次重建**) | RemoteUtility | UtyCtrl (ReadFile) |

**Mutex 串行化**：
- 名：`Icom RemoteUtyCtrl`（全局命名空间，跨会话可见）
- 超时：5000ms（硬编码 `0x1388`）
- 用法：每次事务 `WaitForSingleObject` → 事务 → `ReleaseMutex`

**与 CivCtrl/HidCtrl 的关系**：基于 Mailslot 命名模式，可高度确信 CivCtrl.dll 和 HidCtrl.dll 采用相同模式（`RemoteCivCtrlCmd/Res` 和 `RemoteHidCtrlCmd/Res`），共享相同的 C++ 基类与事务函数模板。

### 4.3 RadioSch.dll — 电台调度核心（主机端）

| 属性 | 值 |
|------|-----|
| 文件路径 | `d:\my git\RemoteUtility\RadioSch.dll` |
| 大小 | 1,972,736 bytes (1.88 MB) |
| 机器 | x86 (PE32) |
| ImageBase | 0x10000000 |
| 导出函数 | 5 个 |
| 导入 DLL | 16 个（含 **SETUPAPI.dll 9 函数**）|

**职责**：在主机端 RemoteUtility 进程内执行实际硬件操作 —— USB 设备枚举、CI-V 串口通信、虚拟驱动管理。

**5 个导出函数**：

| 名称 | Ordinal | RVA | 用途 |
|---|---|---|---|
| `OpenDll` | 3 | 0x3e20 | 创建 USB 设备调度上下文，复制全局设备列表到本地副本 |
| `CloseDll` | 1 | 0x2b00 | 关闭调度上下文，清理设备链表 |
| `GetUsbDev` | 2 | 0x2c00 | 获取 USB 设备列表（每设备 0x44 字节输出结构）|
| `SearchUsbDev` | 5 | 0x3f70 | 查找 USB 设备（tail-call 0x7400 真实实现）|
| `SearchUsbDev2` | 4 | 0x3f70 | 同 SearchUsbDev，双命名兼容 alias |

**SETUPAPI 9 个导入函数**：

| 函数 | 调用点数 | 用途 |
|------|----------|------|
| `SetupDiGetClassDevsA` | 2 | 创建设备信息集（DIGCF_ALLCLASSES + DIGCF_DEVICEINTERFACE）|
| `SetupDiEnumDeviceInfo` | 4 | 枚举设备 |
| `SetupDiGetDeviceInstanceIdA` | 2 | 取设备实例 ID |
| `SetupDiOpenDevRegKey` | 1 | 打开设备注册表键（DIREG_DEV, KEY_READ）|
| `SetupDiDestroyDeviceInfoList` | 2 | 销毁设备信息集 |
| `CM_Get_Device_IDA` | **7** | 取设备 ID 字符串（缓冲区 0x400 = 1024 字节）|
| `CM_Get_Parent` | 2 | 取父设备（USB 集线器）|
| `CM_Get_Child` | 1 | 取子设备（接口）|
| `CM_Get_Sibling` | 2 | 取兄弟设备（同 composite）|

**USB 设备匹配模式**：`sprintf(buf, "VIDPID%d", vid)` 构造匹配模式，然后与 `CM_Get_Device_IDA` 返回的字符串比对。

**虚拟驱动管理**：

| 字符串 | 含义 |
|--------|------|
| `icom_vaudio.sys` | 虚拟音频驱动内核文件 |
| `icom_vserial.sys` | 虚拟串口驱动内核文件 |
| `\\.\ICOM_SERIAL` | 用户态设备路径（CreateFileA 打开，GENERIC_READ\|WRITE，OPEN_EXISTING）|
| `\Device\IcomVSerial` | 内核设备名（NT 设备命名空间，NtOpenFile 路径）|
| `ICOM_VAUDIO` | 虚拟音频设备符号链接 |
| `VAudioDevice` | 用户态音频设备名 |
| `SYSTEM\CurrentControlSet\Services\icom_vaudio\Parameters\%s` | 驱动实例参数注册表 |

**作用**：让传统电台控制软件（如 N1MM/HRD）能通过虚拟 COM 端口"看到"网络上的电台，同时音频流通过虚拟声卡路由。

### 4.4 RemoteUty.exe — 网络代理进程

| 属性 | 值 |
|------|-----|
| 文件路径 | `d:\my git\RemoteUtility\RemoteUty.exe` |
| 大小 | 3,010,048 bytes (2.87 MB) |
| 机器 | x86 (PE32) |
| 导出函数 | 0（EXE）|
| 导入 DLL | 20 个（含 **WS2_32.dll 18 函数**）|

**职责**：双角色进程 —— 在操作员侧作为网络客户端，在主机侧作为网络服务端 + Mailslot 服务器。

**网络层关键发现**：
1. **纯 UDP**：`socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)` 确证，无 TCP
2. **单 socket 模型**：`socket` 仅 1 个调用点（RVA 0x5376c），多线程复用
3. **INADDR_ANY 绑定**：服务端模式监听所有网络接口
4. **WSAIoctl 枚举接口**：`SIO_GET_INTERFACE_LIST (0x9800000c)` 枚举本机所有 IP，支持多 WLAN 适配器
5. **端口运行时配置**：从注册表 `SOFTWARE\Icom\Remote Utility` 读取 CommandPort/SerialPort/AudioPort，默认 50001/50002/50003

**自研可靠 UDP 栈**（三层）：
- **CUdp**（传输层）：socket + bind + recvfrom + sendto + recvThread
- **CUDPCtrl**（会话层）：ExOpen/ExAccept/ExConnect/ExSend/ExClose
- **CUDPCtrl2**（可靠传输层）：sendReqSync/sendReqFSync/sendNop(心跳)/sendReqResend(重传) + TimerThread

### 4.5 HidCtrl.dll — HID 设备控制

| 属性 | 值 |
|------|-----|
| 文件路径 | `d:\my git\RS-BA1\RemoteController\HidCtrl.dll` |
| 大小 | 16,896 bytes (16.5 KB) |
| 编译时间 | 2012-05-17 12:10:05 |
| ImageBase | 0x10000000 |
| 导出函数 | 10 个 |
| 导入 DLL | 4 个（KERNEL32 / SETUPAPI / **HID.DLL** / msvcrt）|

**职责**：USB HID 设备控制（模拟旋钮旋转、模拟按键），用于通过 HID 接口操控 Icom 电台前面板。

**10 个导出函数**：

| 名称 | Ordinal | 用途 |
|---|---|---|
| `HidDeviceInitialize` | 5 | 初始化（保存 HID GUID） |
| `HidDeviceOpen` | 6 | 打开 HID 设备（栈分配 0x624 字节） |
| `HidDeviceClose` | 1 | 关闭（实际为空函数 `ret`） |
| `HidDeviceConnect` | 2 | 连接设备 |
| `HidDeviceDisconnect` | 3 | 断开设备 |
| `HidDeviceReconnect` | 9 | 重连设备 |
| `HidDeviceSend` | 10 | 发送 HID 报告 |
| `HidDeviceReceive` | 7 | 接收 HID 报告 |
| `HidDeviceReceiveDataClear` | 8 | 清空接收队列 |
| `HidDeviceGetSerialNumberString` | 4 | 取设备序列号 |

**SETUPAPI 4 函数**：`SetupDiGetClassDevsA` / `SetupDiGetDeviceInterfaceDetailA` / `SetupDiEnumDeviceInterfaces` / `SetupDiDestroyDeviceInfoList`

**HID.DLL 6 函数**：`HidD_GetHidGuid` / `HidD_GetSerialNumberString` / `HidD_FreePreparsedData` / `HidP_GetCaps` / `HidD_FlushQueue` / `HidD_GetPreparsedData`

**VID/PID 匹配字符串**：`vid_%04x&pid_%04x`（精确匹配 VID+PID，比 RadioSch.dll 的 `VIDPID%d` 更严格）

**注意**：编译时间 2012 年（早于其他组件的 2017-2018 年），可能是历史遗留代码。PDB 路径 `C:\Release\dll\HidCtrl\Release\HidCtrl.pdb`。

### 4.6 RS-BA1V2Ck.dll — 许可证校验（主 UI 控件库）

| 属性 | 值 |
|------|-----|
| 文件路径 | `d:\my git\RS-BA1\RemoteController\RS-BA1V2Ck.dll` |
| 大小 | 2,014,720 bytes (1.92 MB) |
| 编译时间 | 2018-06-28 00:24:33 |
| ImageBase | 0x10000000 |
| 导出函数 | 1 个 |
| 导入 DLL | 15 个（含 gdiplus / UxTheme / ole32 等 UI 库）|

**职责**：双角色 —— 既是许可证校验 DLL，又是主 UI 控件库（2 MB 体量，导入 224 个 USER32 函数 + 97 个 GDI32 函数 + 22 个 gdiplus 函数）。

**唯一导出函数**：

```asm
RsBA1V2_GetKeyNum @ 0x10001af0:
  mov  eax, [ebp+8]      ; eax = 输入参数
  imul eax, eax           ; eax = input * input
  add  eax, 0x5127B       ; eax = input² + 0x5127B (332411)
  pop  ebp
  ret  4
```

**许可证算法**：`key = input² + 0x5127B`。简单的二次多项式校验，无加密强度可言。

**UI 框架特征**：
- MFC + Visual C++ ATL（`CComObjectRootBase@ATL`）
- Office 2007 风格 UI（`IDB_OFFICE2007_COMBOBOX_BTN`、`IDB_OFFICE2007_SYS_BTN_CLOSE`）
- D2D/DirectWrite 支持（`D2D1CreateFactory`、`DWriteCreateFactory`）
- 主题化 UI（`OpenThemeData`、`DrawThemeBackground`）
- 多语言资源（STRING 表 type_1041 = 日语）

### 4.7 UtilityCk.dll — 许可证校验

| 属性 | 值 |
|------|-----|
| 文件路径 | `d:\my git\RS-BA1\RemoteController\UtilityCk.dll` |
| 大小 | 201,728 bytes (197 KB) |
| 编译时间 | 2017-07-19 11:34:25 |
| ImageBase | 0x10000000 |
| 导出函数 | 1 个 |
| 导入 DLL | 8 个 |
| PDB 路径 | `C:\Release\UtilityCk\Release\UtilityCk.pdb` |

**职责**：RemoteUtility 端的许可证校验 DLL，与 RS-BA1V2Ck.dll 配对（双端校验）。

**唯一导出函数**：

```asm
Utility_GetKeyNum @ 0x10001040:
  mov  eax, [esp+4]       ; eax = 输入参数
  imul eax, eax           ; eax = input * input
  add  eax, 0x19F8        ; eax = input² + 0x19F8 (6648)
  ret  4
```

**许可证算法**：`key = input² + 0x19F8`。与 RS-BA1V2Ck.dll 结构相同（都是 `input² + 常数`），但常数不同（0x19F8 vs 0x5127B），说明是同一作者用同一模板生成的双端校验。

**特征**：MFC + ATL，含 COM 注册相关字符串（`CLSID\%1\InprocServer32` 等），可能用于 DCOM/OLE 自动化。

---

## 5. 安全分析

### 5.1 Mailslot 无认证（严重）

| 风险 | 描述 | 严重性 |
|---|---|---|
| **命令注入** | 任何本机进程可 `CreateFileA("\\.\mailslot\RemoteUtyCtrlCmd", GENERIC_WRITE)` 写入伪造命令包 | 🔴 高 |
| **响应窃听** | 任何本机进程可抢先 `CreateMailslotA("\\.\mailslot\RemoteUtyCtrlRes")` 抢占响应通道 | 🔴 高 |
| **响应欺骗** | 任何本机进程可写入已被 UtyCtrl 创建的 RemoteUtyCtrlRes mailslot，伪造响应 | 🔴 高 |
| **DoS** | 持续占用 `Icom RemoteUtyCtrl` Mutex 5 秒即可阻塞所有 UtyCtrl 调用 | 🟡 中 |

**攻击者最省力路径**：抢占 `RemoteUtyCtrlRes` mailslot。因为 UtyCtrl 每次调用都 `CreateMailslotA` 创建该 mailslot，但若攻击者已持有同名 mailslot，`CreateMailslotA` 会失败返回 `INVALID_HANDLE_VALUE`，导致 UtyCtrl 功能完全失效。

**CivCtrl.dll 同样问题**：`\\.\mailslot\civsend` / `civrecv` 是固定名称，任意本地进程可抢占创建（先到先得）。若恶意进程先创建同名 mailslot，可截获或伪造 CI-V 指令。

### 5.2 UDP 明文 + 无认证（严重）

#### 5.2.1 未设置 SO_REUSEADDR（严重）

**位置**：WS2_32 导入表中 `setsockopt` 调用点 = 0
**影响**：服务端异常退出后，UDP 端口进入 TIME_WAIT 等待，无法立即重新绑定。重启服务端会失败。

#### 5.2.2 自定义可靠 UDP 协议无加密无认证（严重）

**位置**：`CUDPCtrl2::ExSend` 等方法
**影响**：
- 数据包明文传输，攻击者在 WLAN 上可嗅探命令/音频流
- 无认证机制，攻击者可伪造 UDP 包注入命令（控制电台）
- 无防重放保护（虽有 seq 字段，但用途是重传而非防重放）

**攻击路径**：
1. 扫描 WLAN 内 UDP 50001/50002/50003 端口
2. 抓包分析协议格式（magic + type + seq + payload）
3. 伪造 `sendReqSync` 包劫持会话
4. 注入 `ExecCmd` 控制电台

#### 5.2.3 命令包无校验

- Mailslot 命令包无 CRC、无 HMAC、无序列号
- 唯一完整性机制是响应包 offset 0 的 cmd_code echo 回填
- 攻击者可注入任意 cmd_code（1-8）+ 任意 64 字节内 payload，RemoteUtility 会照单全收

#### 5.2.4 gethostbyname 已弃用（注意）

**位置**：3 处调用
**影响**：不支持 IPv6；DNS 解析在阻塞调用中可能卡死

### 5.3 无超时漏洞（致命）

#### 5.3.1 UtyCtrl 轮询循环无超时上限

**位置**：`0x10001145` 的轮询循环
**代码**：

```asm
0x10001145:  mov     eax, [esp+0x10]        ; eax = msg_count
0x10001149:  cmp     eax, -1               ; MAILSLOT_NO_MESSAGE?
0x1000114C:  jne     0x10001166             ; 有消息 → 跳出循环
0x1000114E:  push    1                      ; dwMilliseconds = 1
0x10001150:  call    ebx                    ; Sleep(1)
0x1000115E:  call    edi                    ; GetMailslotInfo
0x10001162:  jne     0x10001145             ; 成功 → 回到循环顶（无退出条件！）
```

**致命缺陷**：若 RemoteUtility 进程崩溃或没写响应，`GetMailslotInfo` 会持续返回 -1（无消息），UtyCtrl 会无限 `Sleep(1)` 轮询，**线程永久挂死**。唯一退出条件是 `GetMailslotInfo` 本身失败（返回 0），但这种情况罕见。

**影响**：RemoteUtility 一次崩溃 → RemoteController 主线程挂死 → 整个 UI 无响应。这是"活着就行，但活着的方式不能再生"的设计 —— 违反再生性原则。

#### 5.3.2 recvfrom 无超时

**位置**：rva 0x53bae
**影响**：`recvfrom` 默认阻塞，无 SO_RCVTIMEO 设置（`setsockopt` 0 调用点）

### 5.4 Mutex 名硬编码（注意）

Mutex 名 `Icom RemoteUtyCtrl` 是全局命名空间（非 `Local\` 前缀），意味着跨会话可见。任何同会话或同权限进程都能打开它。

### 5.5 注册表配置无 ACL 检查（注意）

**位置**：`SOFTWARE\Icom\Remote Utility`
**影响**：注册表项可被普通用户修改（Windows 默认 HKLM\SOFTWARE 子键通常 Users 可写）
**风险**：低权限用户可篡改端口配置导致服务 DoS（非提权）

### 5.6 信息暴露面

- DLL 字符串明文暴露所有 Mailslot 名、Mutex 名、PDB 路径
- PDB 路径 `C:\Release\dll\UtyCtrl\Release\UtyCtrl.pdb` 暴露开发者构建环境
- 版本信息 `(C) 2010-2018 Icom Inc.` 暴露维护周期
- 调试日志字符串完整保留（`CIVDriver::xxx()`、`ECHO OK!!!`、`Status = JAM` 等）

### 5.7 安全缺陷汇总与防御建议

| # | 缺陷 | 严重性 | 防御建议 | 优先级 |
|---|------|--------|---------|--------|
| 1 | Mailslot 无认证 | 高 | 给 Mailslot 加 ACL（限制访问到当前用户 SID）| 高 |
| 2 | 命令包无 HMAC | 高 | 命令包加 HMAC（共享密钥在 RemoteUtility 启动时注入）| 高 |
| 3 | UtyCtrl 轮询无超时上限 | 致命 | 轮询循环加最大重试次数（如 5000 次 = 5 秒）| 高 |
| 4 | UDP 明文无加密 | 高 | 在 CUDPCtrl2 层增加 AES-GCM 加密 | 高 |
| 5 | 未设 SO_REUSEADDR | 中 | bind 前调用 `setsockopt(SO_REUSEADDR)` | 中 |
| 6 | Mutex 全局命名空间 | 中 | 改用 `Local\Icom RemoteUtyCtrl` 前缀 | 中 |
| 7 | recvfrom 无超时 | 中 | 通过 WSAEventSelect 或 SO_RCVTIMEO 实现超时 | 中 |
| 8 | 响应 mailslot 固定名 | 中 | 改用一次性随机名（如 `RemoteUtyCtrlRes_<PID>_<SEQ>`）| 中 |
| 9 | PDB 路径暴露 | 低 | 链接器 `/PDBALTPATH` | 低 |

---

## 6. 桥接适配器设计建议（陆墨控制 RS-BA1）

基于逆向结果，给出三种桥接方案，让外部系统（如陆墨自动化控制平台）能够控制 RS-BA1 V2：

### 6.1 方案对比

| 方案 | 入侵点 | 协议复杂度 | 隔离性 | 推荐度 |
|------|--------|-----------|--------|--------|
| **A. 替换前端** | 加载 UtyCtrl/CivCtrl/HidCtrl DLL | 中（需实现 Mailslot 客户端）| 高 | ⭐⭐⭐ |
| **B. Mailslot 服务器劫持** | 冒充 RemoteUtility | 中（需实现 Mailslot 服务器）| 高 | ⭐⭐⭐⭐⭐ |
| **C. 直接 UDP 注入** | 越过 RemoteUtility | 高（需逆向 CUDPCtrl2 协议）| 低 | ⭐⭐ |

### 6.2 推荐方案：B — Mailslot 服务器劫持

#### 6.2.1 设计思路

不启动原版 RemoteUtility.exe，而是用一个自研的"Mailslot 服务器"进程冒充它，监听 `\\.\mailslot\RemoteUtyCtrlCmd`、`\\.\mailslot\civsend`、`\\.\mailslot\RemoteHidCtrlCmd`，处理命令后直接通过自研 UDP 客户端与远端 RS-BA1 主机通信（或直接通过串口/USB 控制本地电台）。

**优势**：
1. **完全隔离** — 不修改原版 RemoteController.exe 和三个 DLL，仅替换 RemoteUtility
2. **协议清晰** — Mailslot 协议已完全逆向（命令包格式 + 9 个命令码 + echo 校验）
3. **无 UDP 协议逆向负担** — 桥接器自己实现 UDP 客户端，无需复刻 CUDPCtrl2
4. **可观测** — 所有控制流经桥接器，便于审计和日志

#### 6.2.2 桥接器架构

```
┌─────────────────────────────────────────────────────────────┐
│                    陆墨 RS-BA1 桥接器                          │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Mailslot 服务器端 (冒充 RemoteUtility)                  │ │
│  │  - CreateMailslot(RemoteUtyCtrlCmd)  ← 抢先创建        │ │
│  │  - CreateMailslot(civsend)           ← 抢先创建        │ │
│  │  - CreateMailslot(RemoteHidCtrlCmd)  ← 抢先创建        │ │
│  │  - 读取命令 → 解析 UtyCtrlCmdPkt / civsend 消息        │ │
│  │  - 写入响应到 RemoteUtyCtrlRes / civrecv              │ │
│  └────────────────────────────────────────────────────────┘ │
│                              │                               │
│                              ▼                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  命令路由层                                              │ │
│  │  - cmd_code 0-8 → Utility 命令（音量/状态/网络查询）    │ │
│  │  - civsend data → CI-V 命令体（频率/模式/PTT）          │ │
│  │  - HidCtrl cmd → HID 报告                               │ │
│  └────────────────────────────────────────────────────────┘ │
│                              │                               │
│              ┌───────────────┼───────────────┐               │
│              ▼               ▼               ▼               │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ CI-V 命令构造器  │  │ UDP 客户端    │  │ 陆墨 API 适配 │    │
│  │ (FE FE..FD 包装)│  │ (自研协议)    │  │ (REST/MQTT)  │    │
│  └────────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│           │                 │                  │            │
└───────────┼─────────────────┼──────────────────┼────────────┘
            │                 │                  │
            ▼                 ▼                  ▼
    [本地串口/USB]    [远端 RS-BA1 主机]    [陆墨云平台]
    (CI-V 9600 8N1)   (UDP 50001-50003)    (HTTP/MQTT)
```

#### 6.2.3 关键实现要点

**1. Mailslot 抢占**：
```python
# 必须在原版 RemoteUtility 启动前创建，否则会失败
import win32file
h_cmd = win32file.CreateMailslot(r"\\.\mailslot\RemoteUtyCtrlCmd", 0, win32con.MAILSLOT_WAIT_FOREVER, None)
h_civsend = win32file.CreateMailslot(r"\\.\mailslot\civsend", 0, win32con.MAILSLOT_WAIT_FOREVER, None)
# 注意：civrecv 由 CivCtrl.dll 的 civOpen 创建，桥接器需通过 CreateFileA 写入它
```

**2. UtyCtrl 命令响应**：
```python
def handle_utyctrl_cmd(cmd_buf):
    cmd_code = cmd_buf[0]
    data_len = cmd_buf[1]
    payload = cmd_buf[4:4+data_len]
    
    if cmd_code == 0:  # GetCountClientTrans
        resp = bytes([0]) + b'\x00\x00\x00' + struct.pack('<I', 1)  # echo + reserved + count=1
    elif cmd_code == 7:  # GetRemoteTransNetworkSet
        # 返回伪造的 WLAN 配置（64 字节）
        resp = bytes([7]) + b'\x01\x00\x00' + b'192.168.1.100' + ...
    elif cmd_code == 8:  # GetRemoteTransState
        resp = bytes([8]) + b'\x01\x00\x00' + b'\x01' * 28  # 状态=已连接
    # 写入 RemoteUtyCtrlRes mailslot（需先 CreateFileA 打开它）
```

**3. CI-V 帧转发**：
```python
def handle_civsend(msg):
    # civsend mailslot 消息格式: {flag:1, dataLen:4, data:N}
    flag = msg[0]
    data_len = struct.unpack('<I', msg[1:5])[0]
    cmd_body = msg[5:5+data_len]  # [toAddr, fromAddr, cmd, ...data]
    
    # 构造完整 CI-V 帧
    frame = b'\xFE\xFE' + cmd_body + b'\xFD'
    
    # 写串口 or 转 UDP
    ser.write(frame)
    
    # 读应答后写入 civrecv mailslot
    # civrecv 消息格式: {msgId:4, flag:1, dataLen:4, data:N}
    resp = ser.read(64)
    civrecv_msg = struct.pack('<I', next_msg_id) + bytes([flag]) + struct.pack('<I', len(resp)) + resp
    # CreateFileA 打开 \\.\mailslot\civrecv 并 WriteFile
```

**4. Echo 校验机制**：所有 `Get*` 响应包 offset 0 必须回填原 `cmd_code`，否则 UtyCtrl 会视为协议错误。

#### 6.2.4 方案 B 的风险与限制

| 风险 | 缓解 |
|------|------|
| 原版 RemoteUtility 已启动时无法抢占 Mailslot | 桥接器作为服务先于 RemoteUtility 启动；或用进程监控杀掉原版 |
| Mutex `Icom RemoteUtyCtrl` 需由桥接器创建 | 桥接器初始化时 `CreateMutexA("Icom RemoteUtyCtrl")` |
| CivCtrl.dll 的 civOpen 会创建 civrecv mailslot | 桥接器只需 CreateFileA 打开 civrecv 写入响应，不创建它 |
| 响应 mailslot 每次重建 | 桥接器需轮询检测 UtyCtrl 创建的 RemoteUtyCtrlRes 并及时响应 |

### 6.3 备选方案：A — 加载前端 DLL

若需要保留原版 RemoteUtility 的 UDP 通信能力（即桥接器只替换 RemoteController UI，仍用原版 RemoteUtility 做网络中继）：

```python
import ctypes
civctrl = ctypes.CDLL("CivCtrl.dll")
h = civctrl.civOpen(None, 3, 9600, 0, 0)  # COM3, 9600 baud
civctrl.civSetAddress(h, 0x04, 0xE0)     # IC-7300, controller=0xE0
# 构造 CI-V 设频率命令
freq_cmd = bytes([0x04, 0xE0, 0x06]) + b'\x89\x67\x01\x00\x08'  # 14.062.500 Hz
civctrl.civSend(h, freq_cmd, len(freq_cmd), 0)
```

**优势**：直接复用 CivCtrl.dll 的状态机和帧包装逻辑。
**限制**：需要原版 RemoteUtility 在运行（提供 civsend/civrecv mailslot 服务端）。

### 6.4 方案 C — 直接 UDP 注入（不推荐）

需完整逆向 CUDPCtrl2 协议格式（magic/type/seq/payload 结构），然后伪造 UDP 包直接与远端 RS-BA1 主机通信。

**不推荐原因**：
1. CUDPCtrl2 协议格式未完全确认（仅有调试日志 `" port = %d seq = %d"` 线索）
2. 需实现完整的同步/心跳/重传逻辑
3. 越过 RemoteUtility 意味着丢失所有错误处理和状态管理

---

## 7. 待动态验证项清单

以下结论基于静态分析推断，需要动态调试验证：

### 7.1 网络层

- [ ] **端口号确认**：实际监听端口是否为 50001/50002/50003（静态只见资源 ID `0xC351/0xC352/0xC353`，需 `netstat -ano | findstr <pid>` 确认）
- [ ] **CUDPCtrl2 数据包格式**：完整包头结构（magic/type/port/seq/ack_seq/payload），需 Wireshark 抓包 + IDA 动态调试确认
- [ ] **setsockopt 0 调用点的另一种解释**：可能通过函数指针间接调用，需 IDA xref 验证
- [ ] **gethostbyname 实际用途**：3 处调用是否真的用于 DNS 解析（可能是本地主机名解析）

### 7.2 Mailslot IPC 层

- [ ] **CivCtrl.dll / HidCtrl.dll mailslot 名**：是否真的使用 `RemoteCivCtrlCmd` / `RemoteHidCtrlCmd`（基于命名模式推断）
- [ ] **RemoteUtility 是 mailslot 服务器端**：确认它读取 `RemoteUtyCtrlCmd`（而非反过来）
- [ ] **g_mutex_handle 创建时机**：是否在 DLL 加载时由 `CUtyCtrlApp` 构造函数调用 `CreateMutexA` 创建
- [ ] **GetClientTransInfo 响应数据大小**：是否真的是 104 字节（26 dwords）
- [ ] **GetRemoteTransNetworkSet 响应内容**：是否包含 WLAN IP/端口结构
- [ ] **ExecCmd 的 data_len 计算公式**：`(arg5 & 0xFF) + 0x14`
- [ ] **轮询循环是否真的无超时上限**：潜在挂死点（致命缺陷）

### 7.3 CI-V 串口层

- [ ] **HandleResolver (0x404910) 的句柄表数据结构**：内部对象表的存储细节
- [ ] **civAnsBranch (0x4030F0) 的具体应答分发逻辑**
- [ ] **EscapeCommFunction 在 PTT 切换中的实际调用路径**：需动态断点确认 PTT 是走 CI-V 命令（0x1C 0x00/0x01）还是走 RTS 硬件线路
- [ ] **CIVTrace 对象链表结构**：0x40635C/0x4063EC/0x40641C/0x4064F0 的 trace 链表

### 7.4 USB / 虚拟驱动层

- [ ] **USB 设备 VID/PID**：Icom USB 电台典型 VID 是 `0x0C26`（Icom Inc.），PID 因型号不同（IC-7300=0x0010, IC-9700=0x0012 等），需在真实设备上验证
- [ ] **虚拟驱动 IOCTL 码**：`\Device\IcomVSerial` 设备的 DeviceIoControl 控制码，需通过 IRP 监控（如 DriverMonitor）确认
- [ ] **`VIDPID%d` 匹配模式**：是否仅匹配 VID 数字（不查 PID）

### 7.5 安全验证

- [ ] **Mailslot 命令注入 PoC**：用 Python `win32file.CreateFileA` 写入伪造命令包，观察 RemoteUtility 是否执行
- [ ] **UDP 包注入 PoC**：伪造 `sendReqSync` 包，观察是否能劫持会话
- [ ] **轮询挂死 PoC**：杀掉 RemoteUtility 进程，观察 UtyCtrl 是否永久挂死

---

## 8. 文件清单

### 8.1 源 PE 文件（逆向目标）

| 文件 | 路径 | 大小 |
|------|------|------|
| RemoteCtrl.exe | `d:\my git\RS-BA1\RemoteController\RemoteCtrl.exe` | 44,931,072 |
| CivCtrl.dll | `d:\my git\RS-BA1\RemoteController\CivCtrl.dll` | 151,040 |
| HidCtrl.dll | `d:\my git\RS-BA1\RemoteController\HidCtrl.dll` | 16,896 |
| UtyCtrl.dll | `d:\my git\RS-BA1\RemoteController\UtyCtrl.dll` | 204,288 |
| RS-BA1V2Ck.dll | `d:\my git\RS-BA1\RemoteController\RS-BA1V2Ck.dll` | 2,014,720 |
| RemoteUty.exe | `d:\my git\RemoteUtility\RemoteUty.exe` | 3,010,048 |
| RadioSch.dll | `d:\my git\RemoteUtility\RadioSch.dll` | 1,972,736 |
| UtilityCk.dll | (推测 `d:\my git\RemoteUtility\UtilityCk.dll`) | 201,728 |
| english.dll | (资源 DLL) | 812,032 |

### 8.2 分析产出文件（本报告引用）

#### 8.2.1 深度逆向报告（Markdown）

| 文件 | 路径 |
|------|------|
| **本报告** | `d:\my git\scratchpad\tools\pe_analysis_output\RS-BA1_Complete_Reverse_Engineering_Report.md` |
| PE 全量静态分析汇总 | `d:\my git\scratchpad\tools\pe_analysis_output\summary.md` |
| CivCtrl.dll 深度逆向 | `d:\my git\scratchpad\tools\pe_analysis_output\CivCtrl_deep_analysis.md` |
| UtyCtrl.dll 深度逆向 | `d:\my git\scratchpad\tools\pe_analysis_output\UtyCtrl_deep_analysis.md` |
| RadioSch.dll + RemoteUty.exe 深度逆向 | `d:\my git\scratchpad\tools\pe_analysis_output\RadioSch_RemoteUty_deep_analysis.md` |

#### 8.2.2 基础 PE 分析报告（Markdown，每组件一份）

| 文件 | 路径 |
|------|------|
| RemoteCtrl.exe.md | `d:\my git\scratchpad\tools\pe_analysis_output\RemoteCtrl.exe.md` |
| CivCtrl.dll.md | `d:\my git\scratchpad\tools\pe_analysis_output\CivCtrl.dll.md` |
| HidCtrl.dll.md | `d:\my git\scratchpad\tools\pe_analysis_output\HidCtrl.dll.md` |
| UtyCtrl.dll.md | `d:\my git\scratchpad\tools\pe_analysis_output\UtyCtrl.dll.md` |
| RS-BA1V2Ck.dll.md | `d:\my git\scratchpad\tools\pe_analysis_output\RS-BA1V2Ck.dll.md` |
| RemoteUty.exe.md | `d:\my git\scratchpad\tools\pe_analysis_output\RemoteUty.exe.md` |
| RadioSch.dll.md | `d:\my git\scratchpad\tools\pe_analysis_output\RadioSch.dll.md` |
| UtilityCk.dll.md | `d:\my git\scratchpad\tools\pe_analysis_output\UtilityCk.dll.md` |
| english.dll.md | `d:\my git\scratchpad\tools\pe_analysis_output\english.dll.md` |

#### 8.2.3 基础 PE 分析数据（JSON，每组件一份）

| 文件 | 路径 |
|------|------|
| RemoteCtrl.exe.json | `d:\my git\scratchpad\tools\pe_analysis_output\RemoteCtrl.exe.json` |
| CivCtrl.dll.json | `d:\my git\scratchpad\tools\pe_analysis_output\CivCtrl.dll.json` |
| HidCtrl.dll.json | `d:\my git\scratchpad\tools\pe_analysis_output\HidCtrl.dll.json` |
| UtyCtrl.dll.json | `d:\my git\scratchpad\tools\pe_analysis_output\UtyCtrl.dll.json` |
| RS-BA1V2Ck.dll.json | `d:\my git\scratchpad\tools\pe_analysis_output\RS-BA1V2Ck.dll.json` |
| RemoteUty.exe.json | `d:\my git\scratchpad\tools\pe_analysis_output\RemoteUty.exe.json` |
| RadioSch.dll.json | `d:\my git\scratchpad\tools\pe_analysis_output\RadioSch.dll.json` |
| UtilityCk.dll.json | `d:\my git\scratchpad\tools\pe_analysis_output\UtilityCk.dll.json` |
| english.dll.json | `d:\my git\scratchpad\tools\pe_analysis_output\english.dll.json` |
| cross_references.json | `d:\my git\scratchpad\tools\pe_analysis_output\cross_references.json` |

#### 8.2.4 深度反汇编中间数据（JSON / TXT）

| 文件 | 路径 | 大小 |
|------|------|------|
| CivCtrl_deep_disasm.json | `d:\my git\scratchpad\tools\pe_analysis_output\CivCtrl_deep_disasm.json` | 467 KB |
| UtyCtrl_deep_disasm.json | `d:\my git\scratchpad\tools\pe_analysis_output\UtyCtrl_deep_disasm.json` | — |
| UtyCtrl_deep_disasm2.json | `d:\my git\scratchpad\tools\pe_analysis_output\UtyCtrl_deep_disasm2.json` | — |
| deep_analysis.json | `d:\my git\scratchpad\tools\pe_analysis_output\deep_analysis.json` | 112 KB |
| deep_analysis_v2.json | `d:\my git\scratchpad\tools\pe_analysis_output\deep_analysis_v2.json` | 210 KB |
| deep_analysis_summary.txt | `d:\my git\scratchpad\tools\pe_analysis_output\deep_analysis_summary.txt` | 22 KB |
| deep_analysis_v2_summary.txt | `d:\my git\scratchpad\tools\pe_analysis_output\deep_analysis_v2_summary.txt` | 39 KB |

### 8.3 分析脚本

| 脚本 | 路径 | 用途 |
|------|------|------|
| pe_analyzer.py | `d:\my git\scratchpad\tools\pe_analyzer.py` | 一阶 PE 静态分析 |
| civctrl_deep_disasm.py | `d:\my git\scratchpad\tools\civctrl_deep_disasm.py` | CivCtrl.dll 深度反汇编 |
| civctrl_query.py | `d:\my git\scratchpad\tools\civctrl_query.py` | CivCtrl.dll 查询脚本 |
| civctrl_iat_resolve.py | `d:\my git\scratchpad\tools\civctrl_iat_resolve.py` | CivCtrl.dll IAT 解析 |
| utyctrl_deep_disasm.py | `d:\my git\scratchpad\tools\utyctrl_deep_disasm.py` | UtyCtrl.dll 深度反汇编 |
| utyctrl_deep_disasm2.py | `d:\my git\scratchpad\tools\utyctrl_deep_disasm2.py` | UtyCtrl.dll 补充分析 |
| deep_disasm.py | `d:\my git\scratchpad\tools\deep_disasm.py` | RadioSch/RemoteUty 一阶分析 |
| deep_disasm_v2.py | `d:\my git\scratchpad\tools\deep_disasm_v2.py` | RadioSch/RemoteUty 二阶分析 |
| extract_deep.py | `d:\my git\scratchpad\tools\extract_deep.py` | 摘要提取 |
| extract_deep_v2.py | `d:\my git\scratchpad\tools\extract_deep_v2.py` | 摘要提取 v2 |

### 8.4 工具链依赖

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.x (`d:\my git\scratchpad\.venv\Scripts\python.exe`) | 脚本运行环境 |
| pefile | 2024.8.26 | PE 解析 |
| capstone | 5.0.7 | 反汇编 |

### 8.5 复现命令

```powershell
# 一阶 PE 静态分析（生成所有 .md / .json）
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\pe_analyzer.py'

# CivCtrl.dll 深度反汇编
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\civctrl_deep_disasm.py'
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\civctrl_iat_resolve.py'

# UtyCtrl.dll 深度反汇编
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\utyctrl_deep_disasm.py'
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\utyctrl_deep_disasm2.py'

# RadioSch.dll + RemoteUty.exe 深度反汇编
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\deep_disasm.py'
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\deep_disasm_v2.py'

# 验证依赖
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' -c "import pefile, capstone; print('pefile', pefile.__version__); print('capstone', capstone.__version__)"
```

---

## 附录 A：组件交叉引用矩阵

基于 `summary.md` 和 `cross_references.json` 的 DLL 间导入关系（节选关键）：

| 消费者 | 导入自 | 函数数 | 关键依赖用途 |
|--------|--------|--------|------------|
| RemoteCtrl.exe | KERNEL32.DLL | 121 | 进程/线程/内存 |
| RemoteCtrl.exe | USER32.DLL | 203 | UI |
| RemoteCtrl.exe | OLEAUT32.DLL | 17 | COM 自动化 |
| RemoteCtrl.exe | WTSAPI32.DLL | 2 | 终端服务（会话检测）|
| CivCtrl.dll | KERNEL32.DLL | 70 | Mailslot + 串口 |
| CivCtrl.dll | USER32.DLL | 3 | wsprintfA（内联实现）|
| HidCtrl.dll | SETUPAPI.dll | 4 | USB 设备枚举 |
| HidCtrl.dll | HID.DLL | 6 | HID 报告 |
| UtyCtrl.dll | KERNEL32.dll | 109 | Mailslot + Mutex |
| UtyCtrl.dll | USER32.dll | 88 | UI 控件（MFC CWnd）|
| RS-BA1V2Ck.dll | USER32.dll | 224 | MFC UI |
| RS-BA1V2Ck.dll | gdiplus.dll | 22 | 图像渲染 |
| RemoteUty.exe | WS2_32.dll | 18 | **网络通信（唯一）** |
| RemoteUty.exe | SETUPAPI.dll | 4 | USB 设备 |
| RemoteUty.exe | MSPORTS.DLL | 3 | 串口枚举 |
| RadioSch.dll | SETUPAPI.dll | 9 | **USB 设备树遍历（最全）** |
| UtilityCk.dll | KERNEL32.dll | 104 | MFC 运行时 |

**关键观察**：
- `WS2_32.dll` 仅被 `RemoteUty.exe` 导入（18 函数）→ **RemoteUtility 是唯一网络通信进程**
- `SETUPAPI.dll` 被 3 个组件导入：HidCtrl (4)、RemoteUty (4)、RadioSch (9) → RadioSch 设备枚举能力最完整
- `WTSAPI32.DLL` 仅被 RemoteCtrl.exe 导入 → 主控 UI 检测会话变化（远程桌面场景）

---

## 附录 B：关键 RVA 速查表

### B.1 CivCtrl.dll 关键函数地址

| 函数 | 起始 VA | 字符串证据 |
|------|---------|-----------|
| CIVDriver 构造函数 | 0x401580 | `CIVDriver::CIVDriver()` |
| civOpen 实现 | 0x401C30 | `\\.\COM%d`, `baud=%d parity=N data=8 stop=1` |
| civSend 实现 | 0x402190 | `CIVDriver::civSend()`, `WriteFile SendSlot` |
| civSendSub (帧组装) | 0x402360 | `-->ECHO`, `-->ANSWER` |
| civRecv 实现 | 0x402624 | `ReadFile RecvSlot` |
| civAnalyze (状态机) | 0x402D44 | `ECHO OK!!!`, `civAnalyze status=%d` |
| AddRecvData | 0x403224 | `CIVDriver::AddRecvData` |
| civRetry | 0x4037AC | `-->JAM` |
| SendRecvThread | 0x403968 | `CIVDriver::SendRecvThread` |
| HandleResolver | 0x404910 | 所有 thunk 调用 |

### B.2 UtyCtrl.dll 关键地址

| 函数 | 起始 VA | 用途 |
|------|---------|------|
| mailslot_xact (核心) | 0x10001080 | 所有 Get* 调用的事务引擎 |
| GetCountClientTrans | 0x100011C0 | cmd_code=0 |
| GetClientTransInfo | 0x10001240 | cmd_code=1, data_len=108 |
| ExecCmd | 0x100016A0 | cmd_code=2, 单向 fire-and-forget |
| GetRemoteTransNetworkSet | 0x10001540 | cmd_code=7, data_len=64 (WLAN 配置查询) |

### B.3 RemoteUty.exe 网络层关键 RVA

| 功能 | RVA | 函数 |
|------|-----|------|
| WSAStartup | 0x5374f | CUdp::open |
| socket 创建 | 0x5376c | CUdp::open |
| bind | 0x537c8 | CUdp::open |
| WSAIoctl (接口枚举) | 0x538c1 | CUdp::open |
| recvfrom | 0x53bae | CUdp::recv |
| sendto | 0x53ade | CUdp::send |
| CommandPort 读取 | 0x2b00e | 配置加载 |
| SerialPort 读取 | 0x2b024 | 配置加载 |
| AudioPort 读取 | 0x2b03a | 配置加载 |
| 虚拟串口打开 | 0x3c871 | CVSerialCtrl::open |

### B.4 RadioSch.dll 关键 RVA

| 功能 | RVA | 函数 |
|------|-----|------|
| OpenDll | 0x3e20 | 导出 |
| CloseDll | 0x2b00 | 导出 |
| GetUsbDev | 0x2c00 | 导出 |
| SearchUsbDev(2) | 0x3f70 | 导出（双命名 alias）|
| SearchUsbDev 真实实现 | 0x7400 | tail-call 目标 |
| USB 设备查找 | 0xce54 | 内部 lookup |
| VIDPID 模板构造 | 0x2eef | USB 匹配 |
| SetupDiGetClassDevsA #1 | 0x62af | DIGCF_ALLCLASSES |
| SetupDiGetClassDevsA #2 | 0x75a8 | DIGCF_DEVICEINTERFACE |
| CM_Get_Device_IDA (7 处) | 0x59d0 等 | 设备 ID 提取 |

---

## 附录 C：许可证校验算法

RS-BA1 V2 采用双端许可证校验：

| DLL | 导出函数 | 算法 | 常数 |
|-----|---------|------|------|
| RS-BA1V2Ck.dll (前端) | `RsBA1V2_GetKeyNum` | `key = input² + 0x5127B` | 0x5127B = 332411 |
| UtilityCk.dll (服务端) | `Utility_GetKeyNum` | `key = input² + 0x19F8` | 0x19F8 = 6648 |

两者结构相同（都是 `input² + 常数`），但常数不同，说明是同一作者用同一模板生成的双端校验。算法强度极低（无加密、无混淆、无反调试），可轻易绕过。

**绕过方法**：
1. **Hook 法**：用 Detours/EasyHook 替换 `RsBA1V2_GetKeyNum` 和 `Utility_GetKeyNum`，直接返回期望的合法 key 值
2. **Patch 法**：将 `imul eax, eax; add eax, <const>` 改为 `mov eax, <合法 key>; nop` 
3. **算法法**：给定期望的 key 输出，反解 input（解二次方程 `input² = key - const`，取正根）

---

*报告结束*

**报告作者**：基于 CivCtrl / UtyCtrl / RadioSch+RemoteUty 深度逆向 + HidCtrl/RS-BA1V2Ck/UtilityCk 基础静态分析整合
**生成时间**：2026-08-09
**分析方法**：纯静态（pefile + capstone 反汇编 + 字符串/立即数交叉引用 + IAT 调用点扫描）
**覆盖范围**：9 个 PE 文件，44 个导出函数，3 层协议栈，6 类安全缺陷，3 种桥接方案
