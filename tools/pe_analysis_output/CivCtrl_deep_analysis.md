# CivCtrl.dll 深度逆向分析报告

> 目标文件: `d:\my git\RS-BA1\RemoteController\CivCtrl.dll`
> 分析方式: 纯静态 (pefile + capstone 反汇编 + 字符串/立即数交叉引用)
> 分析工具: `d:\my git\scratchpad\tools\civctrl_deep_disasm.py`
> 中间数据: `CivCtrl_deep_disasm.json` (467KB, 含 18 导出 + 18 内部方法 + 14 状态机函数 + 9 IAT thunk 反汇编)
> 生成时间: 2026-08-09

---

## 0. 执行摘要

CivCtrl.dll 是 Icom RS-BA1 V2 的 **CI-V 串口控制核心 DLL**，负责通过 CI-V 协议与 Icom 电台通信。本次深度逆向揭示了以下关键事实：

1. **IPC 解耦架构** — DLL 不直接被业务进程调用打串口。`civSend` 把数据写入 mailslot `\\.\mailslot\civsend`，由 DLL 内部 `SendRecvThread` 线程读取后真正写串口；串口收到的数据由线程解析后写入 `\\.\mailslot\civrecv`，业务进程通过 `civRecv` 读取。这一设计允许 DLL 被多进程共享。
2. **串口参数** — `baud=%d parity=N data=8 stop=1`，波特率运行时参数化（默认 9600），8N1 无校验，通过 `BuildCommDCBA` + `SetCommState` 应用。
3. **CI-V 帧运行时构造** — 静态二进制中**不存在任何完整的 CI-V 帧模板**（扫描 0xFE FE ... FD 结果为 0）。帧在 [civSendSub @ 0x402360](file:///d:/my/git/RS-BA1/RemoteController/CivCtrl.dll) 中动态拼装：`[0xFE × N][用户数据][0xFD]`，N 由 `preambleCount` 字段控制（默认 0，实际写 2 个 0xFE）。
4. **状态机** — `civAnalyze @ 0x402d44` 实现 IDLE→ECHO→ANSWER→IDLE 状态流转，ECHO/ANSWER 各 500ms 超时，超时进入 JAM 状态由 `civRetry` 处理。
5. **编译器** — Borland C++（非 JSON 初判的 MSVC 2.0）。证据：`Borland C++ - Copyright 2005 Borland Corporation`、`borlndmm` 内存管理器、Borland 风格的 `@Borlndmm@SysGetMem$qqri` 修饰名。
6. **CI-V 地址默认值** — to=0x7F, from=0x00（需调用方通过 `civSetAddress` 重设为具体电台地址，如 IC-7300 的 0x04）。

---

## 1. 文件元数据

| 属性 | 值 |
|------|-----|
| 大小 | 151,040 bytes (147.5 KB) |
| 机器类型 | x86 (PE32) |
| 子系统 | Windows GUI (3) |
| ImageBase | 0x400000 |
| EntryPoint RVA | 0x10F8 |
| 时间戳 | 2018-06-15 05:58:22 |
| 编译器 | Borland C++ (Copyright 2005 Borland Corporation) |
| 版本资源 | FileVersion 2.0.0.1, CompanyName Icom Inc., (C) 2010-2018 Icom Inc. |
| 区段 | .text / .data / .tls / .idata / .edata / .rsrc / .reloc |

---

## 2. 导出函数表（18 个）

所有 `civXXX` 导出函数均为 **thunk 包装**：先调用 `HandleResolver @ 0x404910` 把外部句柄解析为内部 `CIVDriver*` 对象指针，再调用对应的成员方法。统一模式：

```asm
push ebp
mov  ebp, esp
push ebx
xor  ebx, ebx              ; 默认返回值 0
mov  eax, [ebp+8]          ; eax = handle (参数1)
push eax
call 0x404910              ; HandleResolver(handle) → CIVDriver*
pop  ecx
test eax, eax
je   skip                  ; 句柄无效则跳过
push <其他参数>
push eax                   ; this 指针
call <member_method>       ; 真正的成员方法
...
```

| # | 导出名 | Ord | RVA | VA | 实现函数 VA | 推断签名 |
|---|--------|-----|-----|-----|------------|---------|
| 1 | civOpen | 1 | 0x3D1C | 0x403D1C | 0x401C30 | `int civOpen(HANDLE h, int comPort, int baud, BYTE dtr, BYTE rts)` |
| 2 | civSetAddress | 2 | 0x3E44 | 0x403E44 | 0x401A40 | `void civSetAddress(HANDLE h, BYTE toAddr, BYTE fromAddr)` |
| 3 | civSetAddPreamble | 3 | 0x3E7C | 0x403E7C | 0x401A80 | `void civSetAddPreamble(HANDLE h, WORD count)` |
| 4 | civSetCivTot | 4 | 0x3EA0 | 0x403EA0 | 0x401A90 | `void civSetCivTot(HANDLE h, WORD tot)` |
| 5 | civClose | 5 | 0x3EC4 | 0x403EC4 | 0x401E28 | `void civClose(HANDLE h)` |
| 6 | civSend | 6 | 0x3EEC | 0x403EEC | 0x402190 | `void civSend(HANDLE h, void* data, int len, BYTE flag)` |
| 7 | civGetRecvSize | 7 | 0x3F18 | 0x403F18 | 0x4025EC | `int civGetRecvSize(HANDLE h)` |
| 8 | civRecv | 8 | 0x3F3C | 0x403F3C | 0x402624 | `int civRecv(HANDLE h, void* buf, int* size, BYTE* flag)` |
| 9 | civIsSendEnable | 9 | 0x3F70 | 0x403F70 | 0x401AA0 | `int civIsSendEnable(HANDLE h)` |
| 10 | civSetRetryFA | 10 | 0x3F94 | 0x403F94 | 0x401B14 | `void civSetRetryFA(HANDLE h, BYTE flag)` |
| 11 | civSetWaitTime | 11 | 0x3FB8 | 0x403FB8 | 0x401B2C | `void civSetWaitTime(HANDLE h, int ms)` |
| 12 | civResetOthAnsCount | 12 | 0x3FDC | 0x403FDC | 0x401B40 | `void civResetOthAnsCount(HANDLE h)` |
| 13 | civGetOthAnsCount | 13 | 0x3FF8 | 0x403FF8 | 0x401B50 | `int civGetOthAnsCount(HANDLE h)` |
| 14 | civResetRxByteCount | 14 | 0x401C | 0x40401C | 0x401BB4 | `void civResetRxByteCount(HANDLE h)` |
| 15 | civGetRxByteCount | 15 | 0x4038 | 0x404038 | 0x401BC4 | `int civGetRxByteCount(Handle h)` |
| 16 | civSetConType | 16 | 0x405C | 0x40405C | 0x401BD4 | `void civSetConType(HANDLE h, BYTE type)` |
| 17 | civGetConType | 17 | 0x4080 | 0x404080 | 0x401C0C | `int civGetConType(HANDLE h)` |
| 18 | ___CPPdebugHook | 18 | 0x1C0F8 | 0x41C0F8 | — | Borland C++ 调试钩子, 数据非代码 |

---

## 3. 系统架构

### 3.1 IPC 拓扑

```
┌─────────────────────────┐         ┌────────────────────────────────────┐
│  业务进程 (Remote-      │         │  CivCtrl.dll (加载在业务进程或      │
│  Controller.exe 主进程) │         │  独立串口服务进程)                   │
│                         │         │                                      │
│  civSend(h, data, len,  │  Write  │  ┌──────────────────────────────┐   │
│  flag) ─────────────────┼─────────┼─▶│ mailslot \\.\mailslot\civsend│   │
│                         │         │  └──────────────┬───────────────┘   │
│                         │         │                 │ ReadFile           │
│                         │         │                 ▼                    │
│  ┌────────────────┐     │         │  ┌──────────────────────────────┐   │
│  │ civRecv(h,...) │◀────┼─────────┼──│ SendRecvThread @ 0x403968    │   │
│  └────────────────┘     │  Read   │  │  (civOpen 时 CreateThread)   │   │
│         ▲               │         │  └──────────────┬───────────────┘   │
│         │               │         │                 │                    │
│         │               │         │  ┌──────────────▼───────────────┐   │
│         │               │         │  │ mailslot \\.\mailslot\civrecv│   │
│         │               │         │  └──────────────▲───────────────┘   │
│         │               │         │                 │ WriteFile          │
│         │               │         │  ┌──────────────┴───────────────┐   │
│         │               │         │  │ AddRecvData @ 0x403224       │   │
│         │               │         │  └──────────────────────────────┘   │
│                         │         │                                      │
│                         │         │  串口 I/O:                            │
│                         │         │  CreateFileA("\\.\COM%d")             │
│                         │         │  BuildCommDCBA + SetCommState         │
│                         │         │  WriteFile / ReadFile / EscapeComm    │
└─────────────────────────┘         └────────────────────────────────────┘
                                              │
                                              ▼
                                     ┌─────────────────┐
                                     │ Icom 电台 CI-V  │
                                     │ (RS-232 9600 8N1)│
                                     └─────────────────┘
```

### 3.2 关键设计要点

- **mailslot 单向通道** — `civsend` 与 `civrecv` 是两个独立的 mailslot，分别承载"业务→DLL"的发送指令和"DLL→业务"的接收数据。mailslot 是 Windows 内核提供的进程间单向消息队列，适合一对多广播。
- **句柄隔离** — `civOpen` 返回的 `HANDLE` 不是 Win32 句柄，而是 DLL 内部的"对象 ID"。`HandleResolver @ 0x404910` 通过该 ID 在内部表中查找 `CIVDriver*` 对象指针。这样即使 DLL 被多进程加载，对象表也能隔离。
- **后台线程** — `civOpen` 在配置完串口后立即 `CreateThread(SendRecvThread, this)`，线程在整个对象生命周期内运行主循环：读 mailslot → 推进状态机 → 读写串口。

### 3.3 关键函数地址表（通过字符串 xref 定位）

| 函数 | 起始 VA | 字符串证据 |
|------|---------|-----------|
| CIVDriver 构造函数 | 0x401580 | `CIVDriver::CIVDriver()` |
| civOpen 实现 | 0x401C30 | `CIVDriver::civOpen()`, `\\.\COM%d`, `baud=%d parity=N data=8 stop=1` |
| civReset | 0x402008 | civOpen 末尾调用 |
| IDLE 状态切换 | 0x402088 | `--> IDLE` |
| civSend 实现 | 0x402190 | `CIVDriver::civSend()`, `send data...`, `WriteFile SendSlot` |
| civSendSub (帧组装) | 0x402360 | `CIVDriver::civSendSub()`, `-->ECHO`, `-->ANSWER` |
| civRecv 实现 | 0x402624 | `CIVDriver::civRecv`, `ReadFile RecvSlot` |
| 字节级读取循环 | 0x402708 | `ReadFile %02X` |
| civCtrlBranch | 0x402B94 | `CIVDriver::civCtrlBranch()`, `recv transceive` |
| civAnalyze (状态机) | 0x402D44 | `CIVDriver::civAnalyze()`, `ECHO OK!!!`, `civAnalyze status=%d LenTx=%d LenRx=%d` |
| civAnsBranch | 0x4030F0 | `CIVDriver::civAnsBranch()` |
| AddRecvData | 0x403224 | `CIVDriver::AddRecvData` |
| JAM/IDLE 处理 | 0x403358 | `Status = JAM CIVTOT -> error`, `Status = IDLE SendRetry!!` |
| civRetry | 0x4037AC | `CIVDriver::civRetry()`, `-->JAM` |
| civError | 0x4038B0 | `CIVDriver::civError()` |
| SendRecvThread | 0x403968 | `CIVDriver::SendRecvThread` |
| HandleResolver | 0x404910 | 所有 thunk 调用 |
| HandleRelease | 0x40498C | civClose 调用 |

---

## 4. 串口配置深度分析

### 4.1 配置流程（[civOpen_impl @ 0x401C30](file:///d:/my/git/RS-BA1/RemoteController/CivCtrl.dll)）

反汇编关键序列：

```asm
; 1. 格式化 COM 端口名: "\\.\COM%d" % comPort
0x401C7A: push  0x41C234          ; "\\.\COM%d"  (参数: 格式串)
0x401C7F: push  edx               ; &buf
0x401C82: call  0x41347C          ; wsprintfA(buf, "\\.\COM%d", [esi+8])
                                  ;   [esi+8] = comPort (默认 1)

; 2. CreateFileA 打开串口
0x401C9D: push  0xC0000000        ; dwDesiredAccess = GENERIC_READ|GENERIC_WRITE
0x401CA2: push  ecx               ; lpFileName = "\\.\COMx"
0x401CA3: call  0x41BBA2          ; → jmp [0x427178] = CreateFileA
0x401CAA: mov   [esi+4], edi      ; this->hCom = handle (对象偏移 +4)
0x401CB0: cmp   edi, -1           ; 检查 INVALID_HANDLE_VALUE

; 3. 格式化 DCB 字符串: "baud=%d parity=N data=8 stop=1" % baudRate
0x401CC0: push  0x41C23E          ; "baud=%d parity=N data=8 stop=1"
0x401CC6: call  0x41347C          ; wsprintfA(buf, fmt, [esi+0xC])
                                  ;   [esi+0xC] = baudRate (默认 0x2580 = 9600)

; 4. 清零 DCB 结构 (28 字节 = 0x1C)
0x401CD4: push  0x1C              ; sizeof(DCB) = 28
0x401CD9: call  0x410C88          ; memset(&dcb, 0, 28)

; 5. BuildCommDCBA 解析 "baud=... parity=N data=8 stop=1" → DCB
0x401CEF: call  0x41BB90          ; → jmp [0x42716C] = BuildCommDCBA

; 6. 手动调整 DCB 位字段 (fBinary / fParity / fDtrControl / fRtsControl)
0x401CFA-0x401D83: and/or byte ptr [ebp-0x140], imm8
                  ; DCB.Flags 位操作:
                  ;   fBinary = 1 (强制二进制模式)
                  ;   fParity = 0 (无奇偶校验检查)
                  ;   fOutxCtsFlow = 0
                  ;   fOutxDsrFlow = 0
                  ;   fDtrControl = [esi+0x12] (默认 0 = DTR_CONTROL_DISABLE)
                  ;   fRtsControl = [esi+0x13] (默认 0 = RTS_CONTROL_DISABLE)

; 7. SetCommState 应用 DCB
0x401D88: call  0x41BCC8          ; → jmp [0x42723C] = SetCommState(hCom, &dcb)

; 8. SetCommTimeouts
0x401DC2: call  0x41BCCE          ; → jmp [0x427240] = SetCommTimeouts
                                  ;   timeouts: ReadIntervalTimeout=-1,
                                  ;             ReadTotalTimeoutMultiplier=0,
                                  ;             ReadTotalTimeoutConstant=0,
                                  ;             WriteTotalTimeoutMultiplier=0,
                                  ;             WriteTotalTimeoutConstant=0

; 9. EscapeCommFunction (可能用于初始 DTR/RTS 状态)
0x401DCD: push  7                 ; SETDTR? 或 CLRRTS
0x401DC2: call  0x41BBC6          ; → jmp [0x427190] = EscapeCommFunction

; 10. CreateThread(SendRecvThread)
0x401DD8: push  0x403968          ; lpStartAddress = SendRecvThread
0x401DDD: call  0x419E94          ; _beginthreadex wrapper
```

### 4.2 串口参数总结

| 参数 | 值 | 证据 |
|------|-----|------|
| 端口名格式 | `\\.\COM%d` | 字符串 @ 0x41C234 |
| 波特率 | 运行时参数化, 默认 9600 (0x2580) | 构造函数 `mov [edx+0xc], 0x2580` @ 0x40164B |
| 数据位 | 8 | `data=8` |
| 停止位 | 1 | `stop=1` |
| 校验 | N (None, 无校验) | `parity=N` |
| 流控 | 无 (CTS/Dsr 流控均为 0) | DCB 位操作 and 0xFD/0xFB/0xF7 |
| DTR 控制 | 默认 DISABLE (0), 可配 | `[esi+0x12]`, 通过 setter 0x401A60 设置 |
| RTS 控制 | 默认 DISABLE (0), 可配 | `[esi+0x13]`, 通过 setter 0x401A70 设置 |
| 超时 | 全 0 (非阻塞读) | SetCommTimeouts 传入全 0 结构 |
| DCB 大小 | 28 字节 (0x1C) | `push 0x1C` @ 0x401CD4 |

### 4.3 IAT Thunk 映射表

DLL 使用 Borland 风格的 `jmp dword ptr [iat]` thunk 表（位于 0x41BB90 起，每项 6 字节）。已解析的关键映射：

| Thunk VA | IAT VA | API | 用途 |
|----------|--------|-----|------|
| 0x41BB90 | 0x42716C | BuildCommDCBA | 解析 "baud=..." 串为 DCB |
| 0x41BB96 | 0x427170 | ClearCommError | 查询串口错误/队列状态 |
| 0x41BB9C | 0x427174 | CloseHandle | 关闭 handle |
| 0x41BBA2 | 0x427178 | CreateFileA | 打开 COM 端口 |
| 0x41BBA8 | 0x42717C | CreateMailslotA | 创建 mailslot |
| 0x41BBAE | 0x427180 | CreateThread | 启动 SendRecvThread |
| 0x41BBC0 | 0x42718C | EnterCriticalSection | 进入临界区 |
| 0x41BBC6 | 0x427190 | EscapeCommFunction | DTR/RTS 电平控制 (PTT) |
| 0x41BCA4 | 0x4271?? | LeaveCriticalSection | 离开临界区 |
| 0x41BC1A | 0x4271C8 | GetMailslotInfo | 查询 mailslot 消息大小 |
| 0x41BCBC | 0x427234 | ReadFile | 读串口 / 读 mailslot |
| 0x41BCC8 | 0x42723C | SetCommState | 应用 DCB |
| 0x41BCCE | 0x427240 | SetCommTimeouts | 设置超时 |
| 0x41BD2E | 0x427280 | WriteFile | 写串口 / 写 mailslot |
| 0x41BD48 | 0x4272B0 | timeGetTime | 高精度时间戳 (超时判定) |
| 0x4272A0 | (USER32) | wsprintfA | 格式化 (Borland 内联实现 @ 0x41347C) |

---

## 5. CIVDriver 对象布局

通过 setter 区（0x401A40–0x401C0C 连续小函数）和构造函数（0x401580）的字段写入反推：

```
CIVDriver 对象 (~0xB00 字节, vtable @ 0x41CC9C)
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
├── +0x019  struct TxBuf                ; 发送缓冲区 (含长度字段 @ +0x404, 数据 @ +0x408)
│   └── +0x41D  int   txDataLen         ; 待发命令数据长度
├── +0x439  struct RxBuf                ; 接收缓冲区 (同结构)
├── +0x83D  int    lenRx                ; 接收数据长度
├── +0x85A  CRITICAL_SECTION cs1        ; 临界区 1
├── +0x862  struct Timeout echoTout     ; ECHO 超时 (时间戳 + 0x1F4=500ms)
├── +0x86A  struct Timeout tout2        ; 超时结构 2
├── +0x872  struct Timeout tout3        ; 超时结构 3
├── +0x87A  struct Timeout tout4        ; 超时结构 4 (civOpen 设 0x15F90)
├── +0x882  struct Timeout ansTout      ; ANSWER 超时
├── +0x88A  BYTE   threadRunning        ; SendRecvThread 运行标志
├── +0x88B  BYTE   sendPending          ; 待发送标志 (有 mailslot 消息时置 1)
├── +0x88C  HANDLE hMailslotSend        ; civsend mailslot handle (SendRecvThread 读)
├── +0x890  HANDLE hMailslotRecv        ; civrecv mailslot handle (civRecv 读)
├── +0x894  char[]  mailslotRecvPath    ; civrecv mailslot 路径字符串
├── +0xA9C  BYTE   field_A9C            ; (初始 0)
├── +0xAAB  BYTE   subState             ; 子状态机状态 (3↔5, 4↔2 转换)
├── +0xAAC  CRITICAL_SECTION csSend     ; 发送临界区 (civSend/civSendSub 共用)
└── +0xAC4  void*  traceObj             ; CIVTrace 对象指针
```

---

## 6. CI-V 协议实现

### 6.1 CI-V 帧格式（运行时构造）

CI-V 是 Icom 电台的串口控制协议，标准帧格式：

```
┌──────┬──────┬────────┬──────────┬─────────┬──────┐
│ 0xFE │ 0xFE │ toAddr │ fromAddr │ cmd[+data]│ 0xFD │
└──────┴──────┴────────┴──────────┴─────────┴──────┘
 前导   前导   目标      源         命令体     结束
```

### 6.2 帧组装证据（[civSendSub @ 0x402360](file:///d:/my/git/RS-BA1/RemoteController/CivCtrl.dll)）

```asm
; 读取 preambleCount, 计算总前导字节数 = preambleCount + 2
0x4023CD: mov   si, [ebx+0x14]      ; si = preambleCount
0x4023D1: add   si, 2               ; si += 2 (标准 FE FE)
0x4023D8: add   eax, 0x401          ; 分配 size = si + 0x401 (预留缓冲)
0x4023DE: call  0x40C2D4            ; alloc(si + 0x401)

; 循环写入 si 个 0xFE 前导字节
0x4023F6: mov   byte ptr [eax], 0xFE    ; buf[i] = 0xFE
0x4023F9: inc   edx
0x4023FA: inc   eax
0x4023FE: cmp   edx, ecx
0x402400: jl    0x4023F6               ; 循环 si 次

; 复制用户命令数据 (toAddr + fromAddr + cmd + data) 到前导之后
0x402405: mov   edx, [ebx+0x41D]       ; edx = txDataLen
0x40240B: lea   eax, [ebx+0x1D]        ; eax = &txDataBuf (对象偏移 0x1D)
0x402416: call  0x410BF4               ; memcpy(buf+si, txDataBuf, txDataLen)

; 在帧尾写入 0xFD 结束符
0x40242A: mov   byte ptr [ecx+eax], 0xFD   ; buf[si + txDataLen] = 0xFD

; 调用 WriteFile 写入串口
0x40243E: call  0x402188               ; 日志 " size=%d"
0x40245C: call  0x41BD2E               ; WriteFile(hCom, buf, totalLen, ...)
```

### 6.3 静态帧扫描结果

在 `.text`、`.data`、`.rdata`、`.idata` 全部区段扫描 `0xFE 0xFE ... 0xFD` 模式（中间无 0xFE/0xFD，长度 5–32 字节）：

```
扫描结果: 0 个静态 CI-V 帧
```

**结论**：DLL 不预存任何 CI-V 命令模板。所有 CI-V 帧的命令体（`toAddr + fromAddr + cmd + data`）由调用方通过 `civSend` 参数传入，DLL 仅负责包装前导/结束符。

### 6.4 立即数 0xFE / 0xFD 使用点

扫描 `.text` 段中所有使用立即数 0xFE 或 0xFD 的指令，共 33 处。关键帧构造证据：

| VA | 指令 | 所在函数 | 语义 |
|----|------|---------|------|
| 0x4023F6 | `mov byte ptr [eax], 0xFE` | civSendSub | 写入前导字节 0xFE (循环) |
| 0x402403 | `mov bh, 0xFE` | civSendSub | bh = 0xFE (常量暂存) |
| 0x40242A | `mov byte ptr [ecx+eax], 0xFD` | civSendSub | 写入帧结束符 0xFD |
| 0x402DB3 | `xor al, 0xFE` | civAnalyze | 与 0xFE 异或 (ECHO 比对/校验) |
| 0x401032 | `mov ah, 0xFE` | func @ 0x401020 | 辅助函数 (待分析) |
| 0x401241 | `mov eax, 0xFE` | (匿名) | 帧常量加载 |
| 0x401262 | `mov eax, 0xFD` | (匿名) | 帧常量加载 |

其余 0xFE/0xFD 使用点位于 Borland RTL（异常处理、locale）和 DCB 位字段操作（0x401C30 内的 `and byte ptr [dcb], 0xFD` 等），与 CI-V 无关。

### 6.5 频率/模式/PTT 命令

**DLL 本身不实现任何具体 CI-V 命令的构造**（如设频率 0x05/0x06、设模式 0x06、PTT 0x1C）。这些命令由调用方（RemoteController.exe 上层）按 CI-V 协议规范构造完整命令体后，通过 `civSend(handle, cmdBytes, len, flag)` 传入。DLL 是纯粹的**帧包装 + 串口传输 + 应答状态机**层。

PTT 控制相关线索：
- `EscapeCommFunction` (thunk 0x41BBC6) 可用于 RTS/DTR 电平控制，但 civOpen 中调用参数为 `7`（SETDTR 或 CLRRTS），具体 PTT 是走 CI-V 命令（0x1C 0x00/0x01）还是走 RTS 硬件线路，取决于上层配置——对象字段 `fRtsControl @ +0x13` 若设为 `0x03` (RTS_CONTROL_TOGGLE) 或硬件 PTT 模式，则 EscapeCommFunction 会用于关键 PTT 切换。

---

## 7. 状态机分析

### 7.1 状态定义（对象字段 `status @ +0x18`）

| 值 | 状态名 | 证据字符串 | 处理函数 |
|----|--------|-----------|---------|
| 1 | IDLE | `--> IDLE` | civRetry (0x4037AC) 触发重试 |
| 2 | ECHO_WAIT | `-->ECHO` (civSendSub 末尾) | 0x403920 检查 ECHO 到达 |
| 3 | ECHO_CHECK / ANSWER_WAIT | `-->ANSWER` (civAnalyze case 3) | civAnalyze 比对 ECHO 后切换 |
| 4 | ANSWER_PROC | (case 4) | 0x403002 处理 ANSWER 数据 |

### 7.2 状态转换（[civAnalyze @ 0x402D44](file:///d:/my/git/RS-BA1/RemoteController/CivCtrl.dll)）

```asm
0x402DA7: mov  al, [esi+0x18]      ; al = status
0x402DAA: sub  al, 1
0x402DAC: jb   0x402DC1            ; status==1 (IDLE) → civRetry
0x402DAE: je   0x402DCD            ; status==2 (ECHO_WAIT) → 检查 ECHO
0x402DB0: dec  al
0x402DB2: je   0x402DE8            ; status==3 (ECHO_CHECK) → 比对 ECHO
0x402DB4: dec  al
0x402DB6: je   0x403002            ; status==4 (ANSWER_PROC) → 处理应答
0x402DBC: jmp  0x4030C7            ; default → 退出
```

状态流：

```
                civSend() 写入 mailslot
                       │
                       ▼
                   ┌────────┐  ECHO 超时(500ms)
        ┌────────▶│  IDLE  │─────────────┐
        │         │ (stat=1)│             │
        │         └────┬───┘              ▼
        │              │ civSendSub   ┌────────┐
        │              │ 写串口       │  JAM   │
        │              ▼             │(civRetry)│
        │         ┌──────────┐       └────────┘
        │         │ECHO_WAIT │
        │         │ (stat=2) │
        │         └────┬─────┘
        │              │ 收到回声数据
        │              ▼
        │         ┌──────────┐
        │         │ECHO_CHECK│ ECHO 不匹配 → NG!!!
        │         │ (stat=3) │              → 重试
        │         └────┬─────┘
        │              │ ECHO 匹配 (memcmp==0)
        │              │ 日志 "ECHO OK!!!"
        │              ▼
        │         ┌──────────────┐  ANSWER 超时(500ms)
        │         │ANSWER_WAIT   │─────────────┐
        │         │(stat=3,      │             │
        │         │ subState变化)│             ▼
        │         └────┬─────────┘        ┌────────┐
        │              │ 收到应答          │  JAM   │
        │              ▼                  └────────┘
        │         ┌──────────────┐
        │         │ANSWER_PROC   │
        │         │ (stat=4)     │
        │         └────┬─────────┘
        │              │ 处理完成, AddRecvData
        └──────────────┘ 切回 IDLE
```

### 7.3 超时机制

- **ECHO 超时**: 500ms (0x1F4)，存于对象 `+0x862` 结构，使用 `timeGetTime()` 时间戳判定
- **ANSWER 超时**: 500ms (0x1F4)，存于对象 `+0x882` 结构
- **CIVTOT 总超时**: 15000 (0x3A98)，存于对象 `+0x16`，可通过 `civSetCivTot` 配置
- 超时触发 `civError @ 0x4038B0`，记录错误码（如 0x1D = WriteFile 失败）

### 7.4 ECHO 比对逻辑（civAnalyze case 3）

```asm
; 比较接收到的回声与发送的命令
0x402DE8: lea  edx, [esi+0x19]     ; edx = &TxBuf (this+0x19)
0x402DEE: lea  edi, [esi+0x439]    ; edi = &RxBuf (this+0x439)
0x402DF8: mov  eax, [edi+0x404]    ; eax = RxBuf.len
0x402E01: cmp  eax, [edx+0x404]    ; 比较 RxBuf.len vs TxBuf.len
0x402E07: jne  0x402E2B            ; 长度不等 → ECHO 不匹配
0x402E1B: call 0x410E8C            ; memcmp(RxBuf.data, TxBuf.data, len)
0x402E23: test eax, eax
0x402E25: jne  0x402E2B            ; 内容不等 → ECHO 不匹配
0x402E27: mov  [ebp-0x31], 1       ; ECHO 匹配标志 = 1

; ECHO 匹配后:
0x402E43: push 0x41C407            ; "ECHO OK!!!"
0x402E8E: mov  [esi+0x18], 3       ; status = 3 (进入 ANSWER_WAIT)
0x402E92: push 0x41C412            ; "-->ANSWER"
```

---

## 8. mailslot 消息格式

### 8.1 civsend mailslot（业务 → DLL）

`civSend @ 0x402190` 构造的消息格式：

```
┌──────────┬──────────────┬───────────────┐
│ flag     │ dataLen      │ data          │
│ (1 byte) │ (4 bytes LE) │ (N bytes)     │
└──────────┴──────────────┴───────────────┘
```

证据：
```asm
0x402216: mov  al, [ebp+0x14]      ; al = flag (civSend 第4参数)
0x402219: mov  [esi], al           ; buf[0] = flag
0x40221B: mov  [esi+1], edi        ; buf[1..4] = dataLen (edi)
0x402227: call 0x410BF4            ; memcpy(buf+5, userData, dataLen)
0x402248: call 0x41BBA2            ; CreateFileA(mailslot, GENERIC_WRITE, ...)
0x402260: call 0x41BD2E            ; WriteFile(hMailslot, buf, len+5, ...)
```

### 8.2 civrecv mailslot（DLL → 业务）

`civRecv @ 0x402624` 解析的消息格式：

```
┌──────────┬──────┬──────────────┬───────────────┐
│ msgId    │ flag │ dataLen      │ data          │
│ (4 bytes)│ (1B) │ (4 bytes LE) │ (N bytes)     │
└──────────┴──────┴──────────────┴───────────────┘
```

返回给调用方：
- `userBuf[0..3]` = msgId（原样透传）
- `userBuf[4..]` = data
- `*flag` = flag
- 返回值 = dataLen

证据：
```asm
0x4026AF: mov  cl, [edi+4]         ; cl = msgBuf[4] = flag
0x4026B2: mov  [edx], cl           ; *userFlag = flag
0x4026B4: mov  eax, [edi+5]        ; eax = msgBuf[5..8] = dataLen
0x4026C2: mov  edx, [edi]          ; edx = msgBuf[0..3] = msgId
0x4026C4: mov  [eax], edx          ; userBuf[0..3] = msgId
0x4026C6: lea  edx, [edi+9]        ; edx = msgBuf+9 = data 起点
0x4026D2: call 0x410BF4            ; memcpy(userBuf+4, msgBuf+9, dataLen)
```

---

## 9. 默认配置（构造函数 0x401580）

```asm
0x401642: mov  [eax+8], 1          ; comPort = 1 (COM1)
0x40164B: mov  [edx+0xC], 0x2580   ; baudRate = 9600
0x401654: mov  byte [ecx+0x10], 0x7F  ; toAddress = 0x7F
0x40165A: mov  byte [eax+0x11], 0     ; fromAddress = 0x00
0x401660: mov  byte [edx+0x12], 0     ; fDtrControl = 0 (DTR_CONTROL_DISABLE)
0x401666: mov  byte [ecx+0x13], 0     ; fRtsControl = 0 (RTS_CONTROL_DISABLE)
0x40166C: mov  word [eax+0x14], 0     ; preambleCount = 0 (实际 2 个 0xFE)
0x401674: mov  word [edx+0x16], 0x3A98 ; civTot = 15000
0x40167C: mov  byte [ecx+0x18], 1     ; status = 1 (IDLE)
0x40168B: mov  [edx+4], 0xFFFFFFFF    ; hCom = INVALID_HANDLE_VALUE
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| COM 端口 | 1 (COM1) | 需 civOpen 参数覆盖 |
| 波特率 | 9600 | 需 civOpen 参数覆盖; Icom 默认 9600, 可设 19200/4800 |
| CI-V to 地址 | 0x7F | 通配地址, 需 civSetAddress 设为电台实际地址 |
| CI-V from 地址 | 0x00 | 需 civSetAddress 设为控制器地址 (通常 0xE0) |
| DTR 模式 | 0 (DISABLE) | — |
| RTS 模式 | 0 (DISABLE) | 若用 RTS 控制 PTT 需改 |
| 前导字节数 | 0 (实际 2) | 标准 CI-V |
| CIVTOT | 15000 | 总超时 |
| 初始状态 | IDLE (1) | — |

---

## 10. 关键函数反汇编摘要

### 10.1 civOpen 导出 thunk（前 50 条已反汇编，节选）

```asm
0x403D1C: push ebp
0x403D1D: mov  ebp, esp
0x403D1F: add  esp, -0x30          ; 48 字节局部栈
0x403D22: mov  eax, 0x41CD08       ; 某全局对象
0x403D27: push ebx / push esi / push edi
0x403D2A: mov  edi, [ebp+8]        ; edi = handle
0x403D2D: call 0x411010            ; (Borland RTL: 异常帧注册)
0x403D34: push 0xAC9               ; alloc size = 0xAC9 (CIVDriver 对象大小~2761字节)
0x403D39: call 0x40C2FC            ; operator new(0xAC9)
0x403D3F: mov  [ebp-4], eax        ; this = new CIVDriver
0x403D46: mov  word [ebp-0x20], 0x18
0x403D4C: push edi                 ; handle
0x403D4D: mov  edx, [ebp-4]
0x403D50: push edx                 ; this
; ... 后续调用构造函数 0x401580, 然后 civOpen_impl 0x401C30
```

### 10.2 civSend mailslot 写入（前 50 条已反汇编）

见 §8.1 与 §3.2，核心是 `CreateFileA(mailslot, GENERIC_WRITE) → WriteFile`。

### 10.3 civSendSub CI-V 帧组装（前 120 条已反汇编）

见 §6.2，核心是 `循环写 0xFE → memcpy 命令体 → 写 0xFD → WriteFile(hCom)`。

### 10.4 civAnalyze 状态机（前 250 条已反汇编）

见 §7.2，核心是 `switch(status) { case 1: civRetry; case 2: checkEcho; case 3: compareEcho; case 4: processAnswer }`。

### 10.5 SendRecvThread 主循环（前 250 条已反汇编）

```asm
0x403968: push ebp / mov ebp,esp / mov eax,[ebp+8] / push eax
0x40396F: call 0x403978           ; 跳转到真正实现
0x403976: ret

; 真正实现 @ 0x403978
0x4039AE: mov byte [ebx+0x88A], 1 ; threadRunning = 1
0x4039B5: jmp 0x403B7A            ; 跳到循环条件
; 循环体:
0x4039BA: push ebx
0x4039BB: call 0x403358           ; jam_idle_handler (推进状态机)
0x4039C0: cmp byte [ebx+0x88B], 0 ; 检查 sendPending
0x4039C8: je  0x403B6C            ; 无发送任务则跳过 mailslot 读取
0x4039D8: mov eax, [ebx+0x88C]    ; hMailslotSend
0x4039DF: call 0x41BC1A           ; GetMailslotInfo
0x4039E4: cmp [ebp-0x30], -1      ; 有消息?
0x4039E8: je  0x403B6C
0x4039F2: call 0x40C2D4           ; alloc(msgSize)
0x403A0C: call 0x41BCBC           ; ReadFile(hMailslotSend, buf, ...)
0x403A11: push 0x41C5E7           ; "ReadFile SendSlot"
; ... 逐字节填充 TxBuf (this+0x19), 含 toAddr/fromAddr
0x403A48: mov al, [ebx+0x11]      ; fromAddress
0x403A75: mov [esi+edx+4], cl     ; TxBuf[len+4] = fromAddress
0x403A88: mov al, [ebx+0x10]      ; toAddress
; ... 继续填充命令体
```

---

## 11. 工程观察

### 11.1 设计亮点

1. **进程隔离** — mailslot 解耦使 DLL 可被 RemoteController 主进程和 CI-V 服务进程共享，避免串口独占冲突。
2. **句柄抽象** — `HandleResolver` 把内部对象指针封装为整数 ID，防止跨进程句柄泄露。
3. **状态机鲁棒** — ECHO/ANSWER 双超时 + JAM 重试，覆盖 CI-V 总线冲突场景（多设备同时发送）。
4. **调试痕迹完整** — 大量 `CIVDriver::xxx()` 日志字符串保留，便于运行时排查（生产构建未剥离）。

### 11.2 潜在问题

1. **超时全 0 的 SetCommTimeouts** — `ReadIntervalTimeout=0, ReadTotalTimeoutConstant=0` 意味着 `ReadFile` 可能阻塞。但实际 mailslot 读取前先 `GetMailslotInfo` 查询消息大小，串口读取则在线程内逐字节循环（`ReadFile %02X` 日志证据），规避了阻塞问题。
2. **默认地址 0x7F/0x00** — 若调用方忘记 `civSetAddress`，CI-V 帧会用 `to=0x7F from=0x00` 发送，0x7F 不是标准广播地址（0x00 才是），可能导致电台无响应。这是"配置陷阱"。
3. **缓冲区大小** — `SendRecvThread` 内 `cmp [esi+0x404], 0x400` 检查缓冲区上限 1024 字节，超出则丢弃。CI-V 帧最长通常 < 32 字节，余量充足。
4. **未剥离的调试字符串** — `Borland C++ - Copyright 2005`、构造/析构日志、状态机日志全部保留，泄露了完整内部结构。

### 11.3 安全视角（防御性）

- **无网络暴露** — 仅本地串口 + 本地 mailslot，无 TCP/UDP 监听。
- **mailslot 路径固定** — `\\.\mailslot\civsend` / `civrecv` 是固定名称，任意本地进程可抢占创建（先到先得）。若恶意进程先创建同名 mailslot，可截获或伪造 CI-V 指令。低风险（需本地代码执行前提）。
- **无认证** — mailslot 消息无校验，任何能写入 mailslot 的进程都能注入 CI-V 命令。在多用户系统上属设计缺陷，但 RS-BA1 应用场景为单用户桌面，可接受。

---

## 12. 复现与方法论

### 12.1 分析脚本

- 反汇编脚本: [civctrl_deep_disasm.py](file:///d:/my/git/scratchpad/tools/civctrl_deep_disasm.py)
- 查询脚本: [civctrl_query.py](file:///d:/my/git/scratchpad/tools/civctrl_query.py)
- IAT 解析脚本: [civctrl_iat_resolve.py](file:///d:/my/git/scratchpad/tools/civctrl_iat_resolve.py)
- 中间 JSON: [CivCtrl_deep_disasm.json](file:///d:/my/git/scratchpad/tools/pe_analysis_output/CivCtrl_deep_disasm.json) (467KB)

### 12.2 方法论

1. **初版 JSON/MD 分析** — 提取 18 个导出函数 + 字符串分类，识别 thunk 模式与关键字符串。
2. **深度反汇编** — capstone 对每个导出函数反汇编 50 条，对 18 个内部方法反汇编 120 条。
3. **字符串 xref 定位** — 用 `CIVDriver::xxx()` 日志字符串反查引用点，从引用点向前找 `55 8B EC` (push ebp; mov ebp,esp) 函数起始，定位 14 个状态机/IO 函数。
4. **IAT thunk 解析** — pefile 解析 import table，把 `jmp [iat]` thunk 地址映射到 API 名。
5. **CI-V 帧扫描** — 全区段扫描 `0xFE 0xFE ... 0xFD` 模式（结果 0，证明帧运行时构造）。
6. **立即数扫描** — 线性扫描 .text 找 `mov/cmp/test/push 0xFE/0xFD`，定位帧构造痕迹（civSendSub 内 3 处确证）。
7. **对象布局还原** — 从 setter 区（0x401A40 起连续小函数）和构造函数的字段写入还原 CIVDriver 类布局。

### 12.3 未覆盖项（动态调试可补）

- HandleResolver (0x404910) 的句柄表数据结构细节
- civAnsBranch (0x4030F0) 的具体应答分发逻辑
- 0x401020 辅助函数（含 `mov ah, 0xFE`，可能是 trace 记录辅助）
- CIVTrace 对象（0x40635C/0x4063EC/0x40641C/0x4064F0）的 trace 链表结构
- EscapeCommFunction 在 PTT 切换中的实际调用路径（需动态断点确认）

---

## 附录 A: 完整导出函数签名推断

```c
// 句柄类型 (DLL 内部对象 ID, 非 Win32 HANDLE)
typedef void* CIV_HANDLE;

// 1. 打开 CI-V 设备: 创建对象、打开串口、启动 SendRecvThread
int  civOpen(CIV_HANDLE hSlot, int comPort, int baudRate, BYTE dtrMode, BYTE rtsMode);

// 2. 设置 CI-V 地址 (to=电台地址, from=控制器地址, 通常 0xE0)
void civSetAddress(CIV_HANDLE h, BYTE toAddr, BYTE fromAddr);

// 3. 设置额外前导字节数 (实际前导 = count + 2)
void civSetAddPreamble(CIV_HANDLE h, WORD count);

// 4. 设置 CIVTOT 总超时 (单位: ms? 默认 15000)
void civSetCivTot(CIV_HANDLE h, WORD tot);

// 5. 关闭: 停线程、关串口、关 mailslot、释放对象
void civClose(CIV_HANDLE h);

// 6. 发送 CI-V 命令 (通过 mailslot 转交 SendRecvThread)
//    data 应为不含前导/结束符的命令体: [toAddr, fromAddr, cmd, ...]
void civSend(CIV_HANDLE h, const void* data, int len, BYTE flag);

// 7. 获取接收缓冲区中待读数据大小
int  civGetRecvSize(CIV_HANDLE h);

// 8. 读取已收到的应答 (从 civrecv mailslot)
//    返回值: 数据长度; *size 输入为 buf 容量, 输出为实际长度
int  civRecv(CIV_HANDLE h, void* buf, int* size, BYTE* flag);

// 9. 是否允许发送 (状态机处于 IDLE)
int  civIsSendEnable(CIV_HANDLE h);

// 10. 设置重试失败标志
void civSetRetryFA(CIV_HANDLE h, BYTE flag);

// 11. 设置等待时间
void civSetWaitTime(CIV_HANDLE h, int ms);

// 12/13. 其他应答计数 (transceive 模式的旁路应答)
void civResetOthAnsCount(CIV_HANDLE h);
int  civGetOthAnsCount(CIV_HANDLE h);

// 14/15. 接收字节计数 (统计量)
void civResetRxByteCount(CIV_HANDLE h);
int  civGetRxByteCount(CIV_HANDLE h);

// 16/17. 连接类型 (本地串口 / 远程? USB?)
void civSetConType(CIV_HANDLE h, BYTE type);
int  civGetConType(CIV_HANDLE h);
```

## 附录 B: CI-V 标准命令参考（DLL 不实现，由调用方构造）

| 命令 | 子命令 | 语义 | 示例帧 (to=0x04 IC-7300, from=0xE0) |
|------|--------|------|--------------------------------------|
| 0x01 | — | 切换频率 (上/下) | `FE FE 04 E0 01 FD` |
| 0x03 | — | 读频率 | `FE FE 04 E0 03 FD` |
| 0x04 | — | 读模式 | `FE FE 04 E0 04 FD` |
| 0x05 | — | 设模式 | `FE FE 04 E0 05 <mode> <filter> FD` |
| 0x06 | — | 设频率 (VFO) | `FE FE 04 E0 06 <5字节BCD> FD` |
| 0x0C | — | 设 VFO (A/B/M) | `FE FE 04 E0 0C <vfo> FD` |
| 0x14 | 0x0C | 读 PTT 状态 | `FE FE 04 E0 14 0C FD` |
| 0x1C | 0x00 | 设 PTT (0=RX, 1=TX) | `FE FE 04 E0 1C 00 <01/00> FD` |
| 0x1A | 0x03 | 读 S-meter | `FE FE 04 E0 1A 03 FD` |
| 0x19 | — | 设 RIT | `FE FE 04 E0 19 ... FD` |

调用方按此规范构造命令体后，通过 `civSend(h, cmdBody, len, flag)` 传入即可，DLL 自动包装 `FE FE ... FD` 并处理 ECHO/ANSWER 状态机。

---

*报告结束*
