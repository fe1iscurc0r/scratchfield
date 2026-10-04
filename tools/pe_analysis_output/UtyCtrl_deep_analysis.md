# UtyCtrl.dll 深度逆向分析报告

> 分析对象：`d:\my git\RS-BA1\RemoteController\UtyCtrl.dll`
> 文件大小：204,288 bytes | PE32 | x86 | DLL | ImageBase 0x10000000
> 编译时间：2018-06-19 05:35:08 (UTC)
> PDB 路径：`C:\Release\dll\UtyCtrl\Release\UtyCtrl.pdb`
> 厂商：Icom Inc. (C) 2010-2018

---

## 执行摘要

**关键发现（颠覆原始假设）**：

1. **UtyCtrl.dll 不直接做 WLAN socket 通信**。导入表里没有 `ws2_32.dll`、没有 `WSAStartup`/`socket`/`connect`/`send`/`recv`。它通过 **Windows Mailslot（邮筒）IPC** 与本机的 RemoteUtility 进程通信。
2. 真正的网络通信（WLAN、UDP/TCP socket）在 RemoteUtility 进程内，UtyCtrl.dll 只是把命令通过 Mailslot 转发给 RemoteUtility，由后者完成网络收发。
3. 两个 Mailslot：
   - `\\.\mailslot\RemoteUtyCtrlCmd` — 命令通道（UtyCtrl 写，RemoteUtility 读）
   - `\\.\mailslot\RemoteUtyCtrlRes` — 响应通道（UtyCtrl 创建并读，RemoteUtility 写）
4. 一个 Mutex `Icom RemoteUtyCtrl` 串行化所有 Mailslot 事务，超时 5000ms。
5. 9 个导出函数中，8 个走"请求-响应"完整流程，1 个（`ExecCmd`）走 fire-and-forget 单向写入。

**架构修正**：

原始任务描述"RemoteController 通过 UtyCtrl.dll 发送控制命令到 RemoteUtility 的网络端口"不准确。实际数据流是：

```
RemoteController.exe
        │ (同进程内调用)
        ▼
   UtyCtrl.dll ──Mailslot──► RemoteUtility.exe ──WLAN Socket──► RS-BA1 主机
        │                          ▲
        └──────Mailslot Response───┘
```

UtyCtrl.dll 是 RemoteController 进程内的"IPC 前端"，不是网络客户端。

---

## 1. 文件元信息

| 项 | 值 |
|---|---|
| 文件 | [UtyCtrl.dll](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll) |
| 大小 | 204,288 bytes |
| 机器 | x86 (32-bit) |
| 子系统 | Windows GUI (2) |
| 入口 RVA | 0xE8E7 |
| ImageBase | 0x10000000 |
| 时间戳 | 2018-06-19 05:35:08 UTC |
| 编译器 | MSVC 9.0 (VS2008 SP1) + MFC |
| 调试符号 | `C:\Release\dll\UtyCtrl\Release\UtyCtrl.pdb` |
| 公司 | Icom Inc. |
| 文件版本 | 2.0.0.1 |

### 1.1 区段

| 名称 | VA | VSize | RawSize | 熵 |
|---|---|---|---|---|
| .text | 0x1000 | 123,569 | 123,904 | 6.59 |
| .rdata | 0x20000 | 30,071 | 30,208 | 5.14 |
| .data | 0x28000 | 23,000 | 8,192 | 4.01 |
| .rsrc | 0x2e000 | 13,028 | 13,312 | 4.48 |
| .reloc | 0x32000 | 27,330 | 27,648 | 2.77 |

### 1.2 导入表关键 API

完整 IAT 含 239 个槽位。与 Mailslot 通信直接相关的 9 个 API 全部来自 KERNEL32.dll：

| IAT 槽位 | API | 调用次数 | 调用点 |
|---|---|---|---|
| 0x10020210 | `ReadFile` | 1 | 0x10001174 (核心函数内) |
| 0x10020214 | `Sleep` | 1 | 0x10001150 (核心函数内) |
| 0x10020218 | `GetMailslotInfo` | 2 | 0x10001139, 0x1000115E (核心函数内) |
| 0x1002021C | `WriteFile` | 2 | 0x10001119 (核心函数), 0x10001776 (ExecCmd) |
| 0x10020220 | `CreateMailslotA` | 1 | 0x100010E6 (核心函数) |
| 0x10020224 | `CreateFileA` | 2 | 0x100010CC (核心函数), 0x10001753 (ExecCmd) |
| 0x10020228 | `WaitForSingleObject` | 2 | 0x1000109F (核心函数), 0x1000172B (ExecCmd) |
| 0x1002022C | `CloseHandle` | 5 | 0x1000102F, 0x10001187, 0x10001198, 0x10001783, 0x100033F1 |
| 0x10020230 | `ReleaseMutex` | 3 | 0x10001023, 0x100011A5, 0x10001790 |

**注意**：完全没有任何网络 API（ws2_32、wininet、winhttp、IPHLPAPI）。`RegOpen*`/`RegQuery*` 只用于读取自身注册配置，不涉及远端参数。

---

## 2. 导出函数总览

9 个导出函数全部位于 .text 段头部 0x100011C0–0x100016A0 区间：

| # | 名称 | Ordinal | VA | cmd_code | data_len | 模式 |
|---|---|---|---|---|---|---|
| 1 | `GetCountClientTrans` | 7 | 0x100011C0 | 0 | 0 | 请求-响应 |
| 2 | `GetClientTransInfo` | 3 | 0x10001240 | 1 | 0x6C (108) | 请求-响应 |
| 3 | `GetClientTransInfo2` | 2 | 0x100012C0 | 4 | 0x78 (120) | 请求-响应 |
| 4 | `GetClientTransVol` | 5 | 0x10001370 | 3 | 0x24 (36) | 请求-响应 |
| 5 | `GetClientTransVol3` | 4 | 0x10001430 | 5 | 0x3C (60) | 请求-响应 |
| 6 | `GetCommandProcCount` | 6 | 0x100014E0 | 6 | 0 | 请求-响应 |
| 7 | `GetRemoteTransNetworkSet` | 8 | 0x10001540 | 7 | 0x40 (64) | 请求-响应 |
| 8 | `GetRemoteTransState` | 9 | 0x100015F0 | 8 | 0x1C (28) | 请求-响应 |
| 9 | `ExecCmd` | 1 | 0x100016A0 | 2 | 动态 = (arg5 & 0xFF) + 0x14 | **单向 fire-and-forget** |

### 2.1 通用模板

8 个 `Get*` 函数共用一个模板（仅 cmd_code 和 data_len 不同）：

```asm
; 函数入口，分配栈帧 + 栈金丝雀
sub     esp, 0x108                      ; 264 字节本地缓冲
mov     eax, [0x10028C70]               ; g_security_cookie
xor     eax, esp
mov     [esp+0x104], eax                ; 保存 canary

; 检查 Mailslot Mutex 是否就绪
cmp     dword ptr [0x1002C86C], 0       ; g_mutex_handle == 0?
mov     eax, [esp+0x10C]                ; arg1
mov     ecx, [esp+0x110]                ; arg2
mov     edx, [esp+0x114]                ; arg3
push    ebp / push esi / push edi
mov     esi/edi, [esp+...]              ; arg4/arg5

mov     ebp, 1                          ; flag=1（需响应）
mov     byte ptr [esp+0xC], <cmd_code>  ; 命令码
mov     dword ptr [esp+0x10], eax       ; 参数填入命令缓冲区
mov     dword ptr [esp+0x14], ecx
mov     dword ptr [esp+0x18], edx
mov     dword ptr [esp+0x1C], esi
mov     byte ptr [esp+0xD], <data_len>  ; 负载长度

lea     ecx, [esp+8]                    ; ecx = &cmd_buf[0]
push    <响应缓冲区指针>
push    ecx                              ; 命令缓冲区指针
call    0x10001080                       ; ★ 核心 Mailslot 事务函数

test    eax, eax
jne     <失败分支>                       ; 返回非 0 → 失败

; 成功：检查 echo 回填
cmp     byte ptr [esp+8], <cmd_code>    ; cmd_buf[0] 被远端回填为 cmd_code
jne     <失败分支>                       ; 不匹配 → 协议错误

; 拷贝响应数据到调用方缓冲区（GetClientTransInfo 例）
mov     ecx, 0x1A                       ; 26 dwords = 104 bytes
lea     esi, [esp+0x10]                  ; 源：栈上响应缓冲
rep movsd                               ; 拷到 es:[edi]

; 栈金丝雀校验 + 返回
mov     ecx, [esp+0x104]
xor     ecx, esp
call    0x1000E51E                       ; __security_check_cookie
add     esp, 0x108
ret     <参数字节数>
```

### 2.2 关键模式：echo 回填校验

8 个 `Get*` 函数成功路径上都有一段：

```asm
cmp     byte ptr [esp+8], <原 cmd_code>
jne     <失败分支>
```

这说明 RemoteUtility 在响应 mailslot 里**回填原 cmd_code 到响应包 offset 0**，作为请求-响应配对确认。这是 RS-BAV1 协议族常见的"echo 命令码"机制，防止错位响应。

### 2.3 响应数据大小

| 函数 | 响应拷贝指令 | 响应字节数 |
|---|---|---|
| `GetCountClientTrans` | `mov [0x1002C870], eax` | 4 bytes (单个 dword) |
| `GetClientTransInfo` | `mov ecx, 0x1A; rep movsd` | 104 bytes (26 dwords) |
| `GetClientTransInfo2` | （需继续反汇编） | 推测同上 |
| `GetClientTransVol` | （需继续反汇编） | 推测较小 |
| `GetClientTransVol3` | （需继续反汇编） | 推测中等 |
| `GetRemoteTransNetworkSet` | （需继续反汇编） | 推测含 IP/端口结构 |
| `GetRemoteTransState` | （需继续反汇编） | 推测含状态位图 |

> 注：本次脚本反汇编了每个导出函数前 50 条指令，部分长函数的响应拷贝段超出范围。完整反汇编见 [UtyCtrl_deep_disasm.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/UtyCtrl_deep_disasm.json)。

---

## 3. 核心函数 0x10001080 — Mailslot 事务引擎

这是整个 DLL 的心脏。所有 `Get*` 导出函数都通过 `call 0x10001080` 完成一次完整的 Mailslot 请求-响应事务。

### 3.1 函数签名（逆向推断）

```c
// 返回值：0 = 成功，1 = 失败
int __fastcall mailslot_xact(
    void*   cmd_buf,        // [eax] 命令缓冲区，offset 0 = cmd_code, offset 1 = data_len
    void*   resp_buf        // [栈] 响应缓冲区，NULL 表示不需要响应
);
```

### 3.2 完整反汇编与注释

```asm
; ==================== 序言 ====================
0x10001080:  sub     esp, 0xC                ; 局部变量 12 字节
0x10001083:  push    ebx
0x10001084:  push    esi
0x10001085:  push    edi
0x10001086:  mov     edi, eax                ; edi = cmd_buf
0x10001088:  mov     eax, [0x1002C86C]       ; eax = g_mutex_handle
0x1000108D:  push    0x1388                  ; 5000 ms 超时
0x10001092:  mov     ebx, 1                  ; ebx = 1 (失败标志，默认失败)
0x10001097:  push    eax                     ; mutex handle
0x10001098:  mov     [esp+0x18], ebx         ; 保存失败标志
0x1000109C:  or      esi, 0xFFFFFFFF         ; esi = -1 (res_mailslot handle，初始无效)
0x1000109F:  call    [WaitForSingleObject]   ; ★ WaitForSingleObject(g_mutex, 5000ms)

; ==================== 等待结果检查 ====================
0x100010A5:  test    eax, eax
0x100010A7:  je      0x100010B4             ; WAIT_OBJECT_0 (0) → 获得锁，继续
0x100010A9:  cmp     eax, 0x80              ; WAIT_ABANDONED (0x80)?
0x100010AE:  jne     0x100011AB             ; 都不是 (WAIT_TIMEOUT) → 跳到末尾返回失败

; ==================== 打开命令 Mailslot 写入端 ====================
0x100010B4:  push    ebp                    ; 保存 ebp
0x100010B5:  push    0                      ; hTemplateFile = NULL
0x100010B7:  push    0x80                   ; dwFlagsAndAttributes = FILE_ATTRIBUTE_NORMAL
0x100010BC:  push    3                      ; dwCreationDisposition = OPEN_EXISTING
0x100010BE:  push    0                      ; lpSecurityAttributes = NULL
0x100010C0:  push    3                      ; dwShareMode = FILE_SHARE_READ | FILE_SHARE_WRITE
0x100010C2:  push    0x40000000             ; dwDesiredAccess = GENERIC_WRITE
0x100010C7:  push    0x10023868             ; lpFileName = "\\.\mailslot\RemoteUtyCtrlCmd"
0x100010CC:  call    [CreateFileA]           ; ★ CreateFileA(RemoteUtyCtrlCmd, GENERIC_WRITE, ...)
0x100010D2:  mov     ebp, eax               ; ebp = cmd_mailslot_handle

; ==================== 若需响应，创建响应 Mailslot ====================
0x100010D4:  test    edi, edi               ; resp_buf == NULL?
0x100010D6:  je      0x100010EE             ; 不需响应 → 跳过
0x100010D8:  push    0                      ; lpSecurityAttributes = NULL
0x100010DA:  push    -1                     ; dwReadTimeout = MAILSLOT_WAIT_FOREVER
0x100010DC:  push    0x104                  ; cbMaxMsg = 260 字节
0x100010E1:  push    0x10023888             ; lpName = "\\.\mailslot\RemoteUtyCtrlRes"
0x100010E6:  call    [CreateMailslotA]      ; ★ CreateMailslotA(RemoteUtyCtrlRes, 260, FOREVER, NULL)
0x100010EC:  mov     esi, eax               ; esi = res_mailslot_handle

; ==================== 句柄有效性检查 ====================
0x100010EE:  cmp     ebp, -1                ; cmd_mailslot == INVALID_HANDLE_VALUE?
0x100010F1:  je      0x10001191             ; 失败 → 跳到清理
0x100010F7:  test    edi, edi
0x100010F9:  je      0x10001104             ; 不需响应 → 直接写
0x100010FB:  cmp     esi, -1                ; res_mailslot == INVALID_HANDLE_VALUE?
0x100010FE:  je      0x10001186             ; 失败 → 跳到清理

; ==================== 写命令包 ====================
0x10001104:  mov     ecx, [esp+0x20]        ; ecx = cmd_buf (栈上参数)
0x10001108:  movzx   eax, byte ptr [ecx+1]  ; eax = cmd_buf[1] = data_len
0x1000110C:  push    0                      ; lpOverlapped = NULL
0x1000110E:  lea     edx, [esp+0x14]
0x10001112:  push    edx                    ; lpNumberOfBytesWritten = &local
0x10001113:  add     eax, 4                 ; 写入长度 = data_len + 4 (头部 4 字节)
0x10001116:  push    eax                    ; nNumberOfBytesToWrite
0x10001117:  push    ecx                    ; lpBuffer = cmd_buf
0x10001118:  push    ebp                    ; hFile = cmd_mailslot
0x10001119:  call    [WriteFile]            ; ★ WriteFile(cmd_mailslot, cmd_buf, data_len+4, ...)

0x1000111F:  test    eax, eax
0x10001121:  je      0x10001186             ; 写失败 → 清理

; ==================== 轮询响应 Mailslot ====================
0x10001123:  test    edi, edi
0x10001125:  je      0x1000117E             ; 不需响应 → 跳到成功路径

0x10001127:  mov     edi, [GetMailslotInfo] ; edi = GetMailslotInfo 函数指针
0x1000112D:  push    0                      ; lpMaxMessageSize = NULL
0x1000112F:  push    0                      ; lpNextSize = NULL
0x10001131:  lea     eax, [esp+0x18]
0x10001135:  push    eax                    ; lpMessageCount = &local
0x10001136:  push    0                      ; lpReadTimeout = NULL
0x10001138:  push    esi                    ; hMailslot = res_mailslot
0x10001139:  call    edi                    ; GetMailslotInfo(res, NULL, NULL, &msg_count, NULL)
0x1000113B:  test    eax, eax
0x1000113D:  je      0x10001186             ; 失败 → 清理

; ===== 轮询循环：等响应到达 =====
0x1000113F:  mov     ebx, [Sleep]           ; ebx = Sleep 函数指针
0x10001145:  mov     eax, [esp+0x10]        ; eax = msg_count
0x10001149:  cmp     eax, -1               ; MAILSLOT_NO_MESSAGE?
0x1000114C:  jne     0x10001166             ; 有消息 → 跳出循环去 ReadFile
0x1000114E:  push    1                      ; dwMilliseconds = 1
0x10001150:  call    ebx                    ; Sleep(1)  ← 1ms 退避
0x10001152:  push    0
0x10001154:  push    0
0x10001156:  lea     ecx, [esp+0x18]
0x1000115A:  push    ecx                    ; &msg_count
0x1000115B:  push    0
0x1000115D:  push    esi
0x1000115E:  call    edi                    ; GetMailslotInfo(res, ..., &msg_count, ...)
0x10001160:  test    eax, eax
0x10001162:  jne     0x10001145             ; 成功 → 回到循环顶
0x10001164:  jmp     0x10001186             ; 失败 → 清理

; ==================== 读响应 ====================
0x10001166:  push    0                      ; lpOverlapped = NULL
0x10001168:  lea     edx, [esp+0x1C]
0x1000116C:  push    edx                    ; lpNumberOfBytesRead = &local
0x1000116D:  push    eax                    ; nNumberOfBytesToRead = msg_count
0x1000116E:  mov     eax, [esp+0x2C]        ; eax = resp_buf (调用方传入)
0x10001172:  push    eax                    ; lpBuffer = resp_buf
0x10001173:  push    esi                    ; hFile = res_mailslot
0x10001174:  call    [ReadFile]             ; ★ ReadFile(res_mailslot, resp_buf, msg_count, ...)

0x1000117A:  test    eax, eax
0x1000117C:  je      0x10001186             ; 失败 → 清理

; ==================== 成功路径 ====================
0x1000117E:  mov     dword ptr [esp+0x14], 0  ; success_flag = 0

; ==================== 清理：关闭句柄 + 释放 Mutex ====================
0x10001186:  push    ebp                    ; cmd_mailslot handle
0x10001187:  call    [CloseHandle]          ; ★ CloseHandle(cmd_mailslot)
0x1000118D:  mov     ebx, [esp+0x14]        ; ebx = success_flag
0x10001191:  pop     ebp
0x10001192:  cmp     esi, -1
0x10001195:  je      0x1000119E
0x10001197:  push    esi                    ; res_mailslot handle
0x10001198:  call    [CloseHandle]          ; ★ CloseHandle(res_mailslot)
0x1000119E:  mov     ecx, [0x1002C86C]      ; g_mutex_handle
0x100011A4:  push    ecx
0x100011A5:  call    [ReleaseMutex]         ; ★ ReleaseMutex(g_mutex)

; ==================== 返回 ====================
0x100011AB:  pop     edi
0x100011AC:  pop     esi
0x100011AD:  mov     eax, ebx               ; 返回值 = success_flag (0=成功, 1=失败)
0x100011AF:  pop     ebx
0x100011B0:  add     esp, 0xC
0x100011B3:  ret     4                      ; 清栈 4 字节（resp_buf 参数）
```

### 3.3 事务状态机

```
                  ┌──────────────────┐
                  │   入口 (eax=cmd) │
                  └────────┬─────────┘
                           ▼
              ┌────────────────────────┐
              │ WaitForSingleObject    │
              │ (mutex, 5000ms)        │
              └────────┬───────────────┘
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
        WAIT_OBJ_0  WAIT_ABANDONED  TIMEOUT
            │          │              │
            └────┬─────┘              ▼
                 ▼               返回失败 (ebx=1)
       ┌──────────────────┐
       │ CreateFileA      │
       │ (RemoteUtyCtrlCmd)│
       └────────┬─────────┘
                ▼
         句柄 == -1 ?  ──是──► 跳到清理
                │否
                ▼
       需要响应 ?  ──否──► 跳过创建 res mailslot
                │是                 │
                ▼                   │
       ┌──────────────────────┐    │
       │ CreateMailslotA      │    │
       │ (RemoteUtyCtrlRes,   │    │
       │  cbMaxMsg=260,       │    │
       │  timeout=FOREVER)    │    │
       └────────┬─────────────┘    │
                ▼                   │
         句柄 == -1 ?  ──是──► 跳到清理
                │否                 │
                └──────┬────────────┘
                       ▼
       ┌──────────────────────────────┐
       │ WriteFile(cmd_mailslot,      │
       │   cmd_buf, data_len+4, ...)  │
       └────────┬─────────────────────┘
                ▼
         写成功 ?  ──否──► 跳到清理
                │是
                ▼
       需要响应 ?  ──否──► 跳到成功路径
                │是
                ▼
       ┌─────────────────────────────┐
       │ 轮询循环:                    │
       │  GetMailslotInfo(res, ...)  │
       │  if msg_count == -1:        │
       │    Sleep(1)                 │
       │    goto 轮询循环             │
       └────────┬────────────────────┘
                ▼
       ┌─────────────────────────────┐
       │ ReadFile(res_mailslot,      │
       │   resp_buf, msg_count, ...) │
       └────────┬────────────────────┘
                ▼
         读成功 ?  ──否──► 跳到清理
                │是
                ▼
       success_flag = 0
                │
                ▼
       ┌──────────────────────────┐
       │ CloseHandle(cmd_mailslot)│
       │ if res != -1:            │
       │   CloseHandle(res)       │
       │ ReleaseMutex(g_mutex)    │
       └────────┬─────────────────┘
                ▼
       返回 success_flag (0=成功, 1=失败)
```

---

## 4. 命令协议格式

### 4.1 命令包结构（UtyCtrl → RemoteUtility）

```c
#pragma pack(push, 1)
struct UtyCtrlCmdPkt {
    uint8_t  cmd_code;          // offset 0: 命令码（见下表）
    uint8_t  data_len;          // offset 1: 负载长度（不含头部 4 字节）
    uint8_t  reserved[2];       // offset 2-3: 保留（实测栈上残留）
    uint8_t  payload[data_len]; // offset 4+: 实际数据
};  // 总写入字节数 = data_len + 4
#pragma pack(pop)
```

**写入长度公式**：`WriteFile` 第三参数 = `cmd_buf[1] + 4`，由 0x10001113 处的 `add eax, 4` 实现。

### 4.2 命令码映射

| cmd_code | 含义 | data_len | 用途 |
|---|---|---|---|
| 0 | GetCountClientTrans | 0 | 查询客户端传输数量 |
| 1 | GetClientTransInfo | 0x6C (108) | 查询传输信息（v1） |
| 2 | ExecCmd | 动态 (arg5+0x14) | 执行控制命令（**单向**） |
| 3 | GetClientTransVol | 0x24 (36) | 查询客户端音量 |
| 4 | GetClientTransInfo2 | 0x78 (120) | 查询传输信息（v2，扩展） |
| 5 | GetClientTransVol3 | 0x3C (60) | 查询客户端音量 v3 |
| 6 | GetCommandProcCount | 0 | 查询命令处理计数 |
| 7 | GetRemoteTransNetworkSet | 0x40 (64) | 查询远端网络配置（**含 WLAN 参数**） |
| 8 | GetRemoteTransState | 0x1C (28) | 查询远端传输状态 |

### 4.3 响应包结构（RemoteUtility → UtyCtrl）

```c
struct UtyCtrlRespPkt {
    uint8_t  echo_cmd_code;     // offset 0: 回填原 cmd_code（echo 确认）
    uint8_t  status;             // offset 1: 状态码（含义待动态分析）
    uint8_t  reserved[2];        // offset 2-3
    uint8_t  payload[];          // offset 4+: 响应数据
};
```

响应包 offset 0 被导出函数检查等于原 cmd_code，否则视为协议错误（见 [0x10001290](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x10001290) 处 `cmp byte ptr [esp+8], 1`）。

---

## 5. Mailslot IPC 架构

### 5.1 通信拓扑

```
┌─────────────────────────────────────────────────────────────┐
│              RemoteController.exe (主进程)                   │
│                                                              │
│   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐  │
│   │ UtyCtrl.dll   │   │ CivCtrl.dll   │   │ HidCtrl.dll   │  │
│   │ (本分析)      │   │ (CI-V 控制)   │   │ (HID 控制)    │  │
│   └───────┬───────┘   └───────┬───────┘   └───────┬───────┘  │
│           │                   │                   │          │
└───────────┼───────────────────┼───────────────────┼──────────┘
            │                   │                   │
            │ Mailslot          │ Mailslot          │ Mailslot
            │ (本机 IPC)        │ (本机 IPC)        │ (本机 IPC)
            ▼                   ▼                   ▼
   \\.\mailslot\         \\.\mailslot\       \\.\mailslot\
   RemoteUtyCtrlCmd      RemoteCivCtrlCmd    RemoteHidCtrlCmd
   RemoteUtyCtrlRes      RemoteCivCtrlRes    RemoteHidCtrlRes
            │                   │                   │
            ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│            RemoteUtility.exe (网络代理进程)                  │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  Mailslot 服务器端                                   │   │
│   │  - 读 Remote*Cmd mailslot                            │   │
│   │  - 处理命令                                          │   │
│   │  - 写 Remote*Res mailslot 响应                       │   │
│   └──────────────────────────────────────────────────────┘   │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  WLAN Socket 客户端                                  │   │
│   │  - socket(AF_INET, SOCK_DGRAM/STREAM)                │   │
│   │  - connect(server_ip, server_port)                   │   │
│   │  - send/recv 控制命令 + 音频流                       │   │
│   └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ WLAN (UDP/TCP)
                  ┌───────────────┐
                  │  RS-BA1 V2    │
                  │  主机 (电台)  │
                  └───────────────┘
```

### 5.2 Mailslot 名字空间

所有 Mailslot 名以 `\\.\mailslot\` 开头，**点号代表本机**。这意味着：

- UtyCtrl.dll 创建/打开的 Mailslot 都是**本机 IPC 通道**
- 不是 `\\RemoteMachine\mailslot\...`（跨机 Mailslot）
- 真正的 WLAN 网络通信由 RemoteUtility 进程独立完成

| Mailslot 名 | 创建方 | 写入方 | 读取方 | 用途 |
|---|---|---|---|---|
| `\\.\mailslot\RemoteUtyCtrlCmd` | RemoteUtility | UtyCtrl (CreateFileA) | RemoteUtility | 命令下行 |
| `\\.\mailslot\RemoteUtyCtrlRes` | UtyCtrl (CreateMailslotA) | RemoteUtility | UtyCtrl (ReadFile) | 响应上行 |

**注意**：每次 `Get*` 调用都会**重新创建** RemoteUtyCtrlRes mailslot（[0x100010E6](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x100010E6)）。这导致响应 mailslot 句柄每次都是新的，RemoteUtility 必须每次重新打开它写入响应。这是一种简化的请求-响应配对机制（每次请求独占响应通道），但效率低。

### 5.3 Mutex 串行化

- Mutex 名：`Icom RemoteUtyCtrl`（位于 [0x10023854](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll) 字符串）
- 句柄全局变量：`g_mutex_handle` @ [0x1002C86C](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll)
- 创建时机：DLL 初始化（C++ 类构造，见第 7 节）
- 每次事务：`WaitForSingleObject(g_mutex, 5000ms)` → 事务 → `ReleaseMutex(g_mutex)`
- 超时 5000ms：硬编码立即数 `0x1388`，在 [0x1000108D](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x1000108D) 和 [0x10001725](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x10001725) 处出现

### 5.4 Mailslot 参数

| 参数 | 值 | 来源 |
|---|---|---|
| 命令 Mailslot 名 | `\\.\mailslot\RemoteUtyCtrlCmd` | 字符串 @ 0x10023868 |
| 响应 Mailslot 名 | `\\.\mailslot\RemoteUtyCtrlRes` | 字符串 @ 0x10023888 |
| 响应 Mailslot cbMaxMsg | 260 字节 (0x104) | 立即数 @ 0x100010DC |
| 响应 Mailslot dwReadTimeout | MAILSLOT_WAIT_FOREVER (-1) | 立即数 @ 0x100010DA |
| Mutex 名 | `Icom RemoteUtyCtrl` | 字符串 @ 0x10023854 |
| Mutex 等待超时 | 5000 ms (0x1388) | 立即数 @ 0x1000108D, 0x10001725 |
| 轮询退避 | 1 ms (Sleep(1)) | 立即数 @ 0x1000114E |

---

## 6. ExecCmd — 单向命令路径

`ExecCmd` 是唯一不调用核心函数 0x10001080 的导出函数。它内联了**简化版** Mailslot 写入流程：只创建命令 mailslot 写入端、写命令、关闭，**不创建响应 mailslot、不读响应**。

### 6.1 函数签名（推断）

```c
// 返回值：0 = 成功写入，非 0 = 失败
int __stdcall ExecCmd(
    uint32_t  arg1,         // [esp+0x110] — 命令字段 1
    uint32_t  arg2,         // [esp+0x114] — 命令字段 2
    uint32_t  arg3,         // [esp+0x118] — 命令字段 3
    void*     arg4,         // [esp+0x12C] — memcpy 源（用户数据缓冲区）
    uint32_t  arg5,         // [esp+0x124] — 低字节决定 data_len
    uint8_t   arg6_byte     // [esp+0x130] — 命令字段 6（单字节）
);
```

### 6.2 关键代码路径

```asm
; ===== 准备命令缓冲区（栈上） =====
0x100016F1:  lea     ecx, [esp+0x2C]        ; ecx = &cmd_buf (栈上缓冲区)
0x100016F5:  push    edi                     ; memcpy count = arg6_dword
0x100016F6:  push    ecx                     ; memcpy dest = &cmd_buf[?]
0x100016F7:  mov     byte ptr [esp+0x1C], 2  ; cmd_code = 2 (ExecCmd)
0x100016FC:  mov     [esp+0x28], edx          ; cmd_buf 字段 = arg3
0x10001700:  mov     [esp+0x2C], esi          ; cmd_buf 字段 = arg5
0x10001704:  mov     byte ptr [esp+0x30], al  ; cmd_buf 字段 = arg6_byte
0x10001708:  call    0x10015390               ; memcpy(&cmd_buf[?], arg4, arg6_dword)
                                              ; (0x10015390 是 MSVC CRT memcpy 实现)

; ===== 计算动态 data_len =====
0x1000170D:  mov     eax, [0x1002C86C]        ; g_mutex_handle
0x10001712:  add     bl, 0x14                 ; bl = (memcpy_ret & 0xFF) + 0x14
                                              ; memcpy 返回 dest，dest = &cmd_buf[?]
                                              ; 其低字节 = (arg5 & 0xFF) + 某偏移
0x10001715:  add     esp, 0xC                 ; 清栈 memcpy 参数
0x10001718:  mov     byte ptr [esp+0x11], bl  ; data_len = bl

0x1000171C:  mov     edi, 1                   ; edi = 1 (失败标志，默认失败)

; ===== 检查 Mutex =====
0x10001721:  test    eax, eax
0x10001723:  je      0x10001796               ; mutex 未初始化 → 返回失败

; ===== 等 Mutex =====
0x10001725:  push    0x1388                   ; 5000ms
0x1000172A:  push    eax
0x1000172B:  call    [WaitForSingleObject]
0x10001731:  test    eax, eax
0x10001733:  je      0x1000173C
0x10001735:  cmp     eax, 0x80
0x1000173A:  jne     0x10001796               ; 非 0/0x80 → 返回失败

; ===== 打开命令 Mailslot =====
0x1000173C:  push    0                        ; hTemplateFile
0x1000173E:  push    0x80                     ; FILE_ATTRIBUTE_NORMAL
0x10001743:  push    3                        ; OPEN_EXISTING
0x10001745:  push    0                        ; lpSec
0x10001747:  push    3                        ; FILE_SHARE_READ|WRITE
0x10001749:  push    0x40000000               ; GENERIC_WRITE
0x1000174E:  push    0x10023868               ; "\\.\mailslot\RemoteUtyCtrlCmd"
0x10001753:  call    [CreateFileA]
0x10001759:  mov     esi, eax                 ; esi = cmd_mailslot_handle
0x1000175B:  cmp     esi, -1
0x1000175E:  je      0x10001789               ; 失败 → 跳到 ReleaseMutex

; ===== 写命令（无响应读取） =====
; （后续指令在 0x10001760..0x10001790，脚本 50 条指令未覆盖完整，
;   但 IAT 调用统计确认 0x10001776 调用 WriteFile，
;   0x10001783 调用 CloseHandle，0x10001790 调用 ReleaseMutex，
;   无 ReadFile、无 CreateMailslotA）

0x10001776:  call    [WriteFile]               ; 写命令到 RemoteUtyCtrlCmd
0x10001783:  call    [CloseHandle]             ; 关闭 cmd_mailslot
0x10001790:  call    [ReleaseMutex]            ; 释放 mutex
0x100017A4:  call    0x1000E51E                ; __security_check_cookie
```

### 6.3 ExecCmd 与 Get* 路径对比

| 特征 | Get* 系列 | ExecCmd |
|---|---|---|
| 调用 0x10001080 | 是 | 否（内联） |
| 创建响应 Mailslot | 是 | **否** |
| WriteFile | 是 | 是 |
| ReadFile | 是 | **否** |
| 等待响应轮询 | 是 | **否** |
| 模式 | 请求-响应 | 单向 fire-and-forget |
| Mutex 保护 | 是 | 是 |
| 超时 | 5000ms | 5000ms |

ExecCmd 用于"发出即可"的控制命令（如 PTT 切换、模式切换），不需要立即确认。

---

## 7. C++ 类析构与初始化（0x10001010）

[0x10001010](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x10001010) 是 `CUtyCtrlApp`（或类似 C++ 类）的析构函数。这揭示了 `g_mutex_handle` 的生命周期：

```asm
0x10001010:  push    esi
0x10001011:  mov     esi, ecx                 ; this 指针（thiscall 约定）
0x10001013:  mov     [esi], 0x100238AC        ; 设置 vtable = 0x100238AC
0x10001019:  mov     eax, [0x1002C86C]        ; eax = g_mutex_handle
0x1000101E:  test    eax, eax
0x10001020:  je      0x10001035               ; mutex 不存在 → 跳过清理
0x10001022:  push    eax
0x10001023:  call    [ReleaseMutex]            ; 释放 mutex（防御性）
0x10001029:  mov     eax, [0x1002C86C]
0x1000102E:  push    eax
0x1000102F:  call    [CloseHandle]            ; 关闭 mutex handle
0x10001035:  mov     ecx, esi
0x10001037:  call    0x10002966               ; 基类析构（CWinApp 链）
0x1000103C:  test    byte ptr [esp+8], 1      ; flags & 1 == 堆对象?
0x10001041:  je      0x1000104C
0x10001043:  push    esi
0x10001044:  call    0x1000193D               ; delete this
0x10001049:  add     esp, 4
0x1000104C:  mov     eax, esi
0x1000104E:  pop     esi
0x1000104F:  ret     4
```

**vtable @ 0x100238AC**：RTTI 字符串证实类名为 `CUtyCtrlApp`（见原 JSON 第 1548 行 `.?AVCUtyCtrlApp@@`）。

构造函数（CreateMutexA @ 0x1000106E 的调用者）未在本次反汇编范围内，但 IAT 调用统计显示 `CreateMutexA` 仅在 0x1000106E 调用一次，必在构造路径上。

---

## 8. WLAN 连接参数分析

### 8.1 重要修正

**UtyCtrl.dll 内部不存储任何 WLAN 参数**（IP、端口、SSID、密码）。所有网络配置在 RemoteUtility 进程内。

### 8.2 GetRemoteTransNetworkSet 的作用

[0x10001540](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x10001540) 的 `GetRemoteTransNetworkSet` 是**查询接口**，不是配置接口：

```asm
0x10001540:  sub     esp, 0x108
0x10001586:  mov     byte ptr [esp+0xC], 7    ; cmd_code = 7
0x1000158B:  mov     [esp+0x10], eax          ; 参数 1
0x1000158F:  mov     [esp+0x14], ecx          ; 参数 2
0x10001593:  mov     [esp+0x18], edx          ; 参数 3
0x10001597:  mov     [esp+0x1C], esi          ; 参数 4
0x1000159B:  mov     byte ptr [esp+0xD], 0x40 ; data_len = 64 字节
```

它向 RemoteUtility 发送 cmd_code=7、负载 64 字节的查询包，RemoteUtility 在响应里返回当前 WLAN 配置。响应数据格式需要动态调试才能完全确定，但基于 cmd_code=7、响应缓冲区大小推测，64 字节响应可能包含：

```c
struct RemoteTransNetworkSet {  // 推测，64 字节
    uint32_t  valid;              // 配置是否有效
    char     ip_addr[16];         // 远端 IP (ASCII 字符串)
    uint16_t port;                // 远端端口
    uint16_t reserved;
    uint32_t timeout_ms;          // 连接超时
    uint32_t keepalive_ms;        // 心跳间隔
    char     ssid[32];            // SSID
    // ... 其他字段
};
```

### 8.3 获取真实 WLAN 参数的方法

由于 UtyCtrl.dll 只是转发，获取真实 WLAN 参数有两条路径：

1. **静态路径**：分析 `RemoteUtility.exe` 的网络配置存储（注册表 / INI 文件 / 硬编码）
2. **动态路径**：用 API Monitor 钩 `GetRemoteTransNetworkSet` 的返回缓冲区

UtyCtrl.dll 内 `RegOpenKeyExA` / `RegQueryValueExA` 调用集中在 [0x10001AEB](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x10001AEB) 和 [0x10006406](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x10006406)，但都用于读取自身 COM 注册信息，不涉及 WLAN。

---

## 9. 音频流传输分析

### 9.1 关键结论

**UtyCtrl.dll 不传输音频流**。音频流的网络传输由 RemoteUtility 进程直接处理。

### 9.2 GetClientTransVol 系列

| 函数 | cmd_code | data_len | 含义 |
|---|---|---|---|
| `GetClientTransVol` | 3 | 0x24 (36) | 查询客户端传输音量（v1） |
| `GetClientTransVol3` | 5 | 0x3C (60) | 查询客户端传输音量（v3，扩展字段） |

这两个函数是**音量查询**，不是音频数据传输。它们：
- 发送 36/60 字节的查询包（含查询参数）
- 接收响应（音量等级、电平表读数等状态值）
- 不涉及音频 PCM 数据流

### 9.3 真正的音频流路径

```
RS-BA1 主机 ──WLAN──► RemoteUtility.exe ──► Windows 音频 API
                                          (DirectSound / WaveOut)
```

RemoteUtility 进程：
- 从 WLAN socket 收音频 PCM 数据
- 直接送 Windows 音频设备播放
- **不经过** UtyCtrl.dll

UtyCtrl.dll 只负责**控制平面**（命令、状态查询），不碰**数据平面**（音频流）。这是典型的控制/数据分离架构。

---

## 10. 与 CivCtrl.dll / HidCtrl.dll 的关系

### 10.1 命名模式推断

基于 UtyCtrl.dll 的 Mailslot 命名模式，可以高度确信 CivCtrl.dll 和 HidCtrl.dll 采用相同模式：

| DLL | 推断 Mailslot 名 | 功能 |
|---|---|---|
| UtyCtrl.dll | `\\.\mailslot\RemoteUtyCtrlCmd` / `RemoteUtyCtrlRes` | Utility 控制（音量、状态、网络配置） |
| CivCtrl.dll | `\\.\mailslot\RemoteCivCtrlCmd` / `RemoteCivCtrlRes` | Icom CI-V 协议控制（频率、模式、PTT） |
| HidCtrl.dll | `\\.\mailslot\RemoteHidCtrlCmd` / `RemoteHidCtrlRes` | HID 设备控制（虚拟旋钮、按键） |

**验证方法**：对 CivCtrl.dll 和 HidCtrl.dll 跑同样的字符串提取脚本，若发现 `RemoteCivCtrlCmd` / `RemoteHidCtrlCmd` 字符串即证实。

### 10.2 共同的架构模式

三个 DLL 应该共用：
- 同样的 C++ 基类（CWinApp 派生）
- 同样的核心事务函数模板（WaitForSingleObject → CreateFileA → CreateMailslotA → WriteFile → ReadFile → CloseHandle → ReleaseMutex）
- 同样的命令包格式（cmd_code + data_len + 4 字节头）
- 同样的 Mutex 串行化模式（各自独立 Mutex）

### 10.3 分工

| DLL | 控制域 | 典型命令 |
|---|---|---|
| UtyCtrl | 通信会话、音量、网络状态 | 连接、断开、查询音量、查询链路状态 |
| CivCtrl | 电台参数控制 | 设置频率、切换模式、PTT、查询 S-meter |
| HidCtrl | HID 输入模拟 | 模拟旋钮旋转、模拟按键 |

RemoteController 主进程通过统一的 `ExecCmd` / `Get*` 接口调用三个 DLL，三个 DLL 各自通过独立 Mailslot 与 RemoteUtility 进程内的对应子系统通信。

---

## 11. 全局变量映射

| VA | 名称 | 类型 | 含义 | xref 数 |
|---|---|---|---|---|
| 0x10028C70 | `g_security_cookie` | uint32_t | MSVC 栈金丝雀 | 19 |
| 0x1002C86C | `g_mutex_handle` | HANDLE | `Icom RemoteUtyCtrl` Mutex 句柄 | 15 |
| 0x1002C870 | `g_last_count` | uint32_t | `GetCountClientTrans` 缓存的最近计数值 | 1 |
| 0x1002D888 | (CRT 内部) | uint32_t | CRT 堆状态标志（被 memcpy 检查） | 1 |

### 11.1 g_mutex_handle 的 15 个 xref

每个导出函数入口处都检查 `g_mutex_handle != 0`（[0x100011E1](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x100011E1) 模式），加上 0x10001080 核心函数和 0x10001010 析构函数的访问，共 15 处。

### 11.2 g_last_count 的写入点

[0x10001204](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x10001204) 处 `mov [0x1002C870], eax` 将 `GetCountClientTrans` 的成功响应值缓存。这是单例缓存模式：第一次调用走 Mailslot，后续调用可能直接返回缓存值（待动态验证）。

---

## 12. IAT 调用点分布（节选）

### 12.1 Mailslot 通信相关 API

```
CreateMailslotA        x1  @ 0x100010E6   (核心函数 0x10001080)
CreateFileA            x2  @ 0x100010CC, 0x10001753  (核心函数 + ExecCmd)
WriteFile              x2  @ 0x10001119, 0x10001776  (核心函数 + ExecCmd)
ReadFile               x1  @ 0x10001174   (核心函数)
GetMailslotInfo        x2  @ 0x10001139, 0x1000115E  (核心函数轮询循环)
Sleep                  x1  @ 0x10001150   (核心函数轮询退避)
WaitForSingleObject    x2  @ 0x1000109F, 0x1000172B  (核心函数 + ExecCmd)
ReleaseMutex           x3  @ 0x10001023, 0x100011A5, 0x10001790
CloseHandle            x5  @ 0x1000102F, 0x10001187, 0x10001198,
                               0x10001783, 0x100033F1
CreateMutexA           x1  @ 0x1000106E   (C++ 类构造)
```

### 12.2 高频 API（非通信）

```
USER32!SendMessageA     x5   UI 消息（控件状态更新）
USER32!PostMessageA     x3   异步 UI 通知
USER32!GetWindowLongA  x2   窗口属性查询
USER32!EnableWindow     x3   控件启用/禁用
GDI32!DeleteObject     x2   GDI 资源释放
ADVAPI32!RegCloseKey   x5   注册表清理
KERNEL32!GetModuleHandleA x4 模块句柄查询
KERNEL32!GetModuleFileNameA x4 自身路径查询
KERNEL32!GlobalAlloc/Free/Lock/Unlock x多  全局内存管理
```

高频 USER32/GDI32 调用表明 UtyCtrl.dll 含 UI 控件类（MFC `CWnd` 派生），用于在 RemoteController 主窗口里显示状态、音量滑块等。

---

## 13. 安全分析（深度调研三层框架）

### 13.1 技术层

#### 13.1.1 Mailslot 无认证

| 风险 | 描述 | 严重性 |
|---|---|---|
| 命令注入 | 任何本机进程可 `CreateFileA("\\.\mailslot\RemoteUtyCtrlCmd", GENERIC_WRITE)` 写入伪造命令包 | 高 |
| 响应窃听 | 任何本机进程可抢先 `CreateMailslotA("\\.\mailslot\RemoteUtyCtrlRes")` 抢占响应通道 | 高 |
| 响应欺骗 | 任何本机进程可写入已被 UtyCtrl 创建的 RemoteUtyCtrlRes mailslot，伪造响应 | 高 |
| DoS | 持续占用 `Icom RemoteUtyCtrl` Mutex 5 秒即可阻塞所有 UtyCtrl 调用 | 中 |

**攻击者最省力路径**：抢占 `RemoteUtyCtrlRes` mailslot。因为 UtyCtrl 每次调用都 `CreateMailslotA` 创建该 mailslot，但若攻击者已持有同名 mailslot，CreateMailslotA 会失败返回 INVALID_HANDLE_VALUE（[0x100010EE](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x100010EE) 检查后跳到清理），导致 UtyCtrl 功能完全失效。

#### 13.1.2 命令包无校验

- 命令包无 CRC、无 HMAC、无序列号
- 唯一完整性机制是响应包 offset 0 的 cmd_code echo 回填
- 攻击者可注入任意 cmd_code（1-8）+ 任意 64 字节内 payload，RemoteUtility 会照单全收

#### 13.1.3 Mutex 名硬编码

Mutex 名 `Icom RemoteUtyCtrl` 是全局命名空间（非 `Local\` 前缀），意味着跨会话可见。任何同会话或同权限进程都能打开它。

### 13.2 认知层

#### 13.2.1 信息暴露面

- DLL 字符串明文暴露所有 Mailslot 名、Mutex 名、PDB 路径
- PDB 路径 `C:\Release\dll\UtyCtrl\Release\UtyCtrl.pdb` 暴露开发者构建环境
- 版本信息 `(C) 2010-2018 Icom Inc.` 暴露维护周期

#### 13.2.2 协议可观测性

- Mailslot 是 Windows 内核对象，可用 Process Explorer / API Monitor 完整观测
- 命令包格式简单（cmd_code + data_len），无加密无混淆
- 逆向成本极低（本报告即证明）

### 13.3 系统层

#### 13.3.1 降级链分析

UtyCtrl.dll 当前降级链：

```
正常路径：UtyCtrl → Mailslot → RemoteUtility → WLAN → 主机
   │
   ├─ Mutex 超时(5s) → 返回失败 → RemoteController 显示"通信失败"
   ├─ CreateFileA 失败 → 返回失败 → 同上
   ├─ CreateMailslotA 失败 → 跳过响应读取 → 仅写不读（部分降级）
   ├─ WriteFile 失败 → 返回失败
   └─ ReadFile 超时（GetMailslotInfo 持续返回 -1）→ 死循环轮询
```

**致命缺陷**：[0x10001145](file:///d:/my%20git/RS-BA1/RemoteController/UtyCtrl.dll#L0x10001145) 的轮询循环**无超时上限**。若 RemoteUtility 进程崩溃或没写响应，`GetMailslotInfo` 会持续返回 -1（无消息），UtyCtrl 会无限 `Sleep(1)` 轮询，**线程永久挂死**。唯一退出条件是 `GetMailslotInfo` 本身失败（返回 0），但这种情况罕见。

这是典型的"活着就行，但活着的方式不能再生"的设计——违反再生性原则。

#### 13.3.2 资源泄漏风险

每次 `Get*` 调用都创建+关闭 RemoteUtyCtrlRes mailslot。高频调用下（如音量轮询）会产生大量内核对象创建/销毁开销，且若中途异常（如 CloseHandle 前崩溃），响应 mailslot 会泄漏。

### 13.4 防御建议

| # | 建议 | 优先级 |
|---|---|---|
| 1 | 给 Mailslot 加 ACL（限制访问到当前用户 SID） | 高 |
| 2 | 命令包加 HMAC（共享密钥在 RemoteUtility 启动时注入） | 高 |
| 3 | 轮询循环加最大重试次数（如 5000 次 = 5 秒） | 高 |
| 4 | Mutex 改用 `Local\Icom RemoteUtyCtrl` 前缀，限制会话范围 | 中 |
| 5 | 响应 mailslot 改用一次性随机名（如 `RemoteUtyCtrlRes_<PID>_<SEQ>`） | 中 |
| 6 | 移除 PDB 路径字符串（链接器 `/PDBALTPATH`） | 低 |

---

## 14. 调试钩子点

供后续动态调试使用的关键地址：

| 目的 | 地址 | 说明 |
|---|---|---|
| 钩 `WaitForSingleObject` 返回 | 0x100010A5 | 观察 mutex 获取耗时 |
| 钩 `CreateFileA` 返回 | 0x100010D2 | 获取 cmd mailslot 句柄 |
| 钩 `CreateMailslotA` 返回 | 0x100010EC | 获取 res mailslot 句柄 |
| 钩 `WriteFile` 入口 | 0x10001119 | dump 命令包内容（cmd_code + data_len + payload） |
| 钩 `ReadFile` 返回 | 0x1000117A | dump 响应包内容 |
| 钩 `GetMailslotInfo` 返回 | 0x1000113B | 观察 msg_count 变化 |
| 钩轮询循环顶 | 0x10001145 | 统计轮询次数（测响应延迟） |
| 钩 `ExecCmd` 入口 | 0x100016A0 | dump 所有 6 个参数 |
| 钩 `ExecCmd` 的 `WriteFile` | 0x10001776 | dump ExecCmd 命令包 |

### 14.1 Frida 钩子模板

```javascript
// 钩 UtyCtrl.dll!0x10001119 (WriteFile 调用前) dump 命令包
var mod = Process.findModuleByName("UtyCtrl.dll");
var writeCallAddr = mod.base.add(0x1119);

Interceptor.attach(writeCallAddr, {
    onEnter: function(args) {
        // 此时栈上已 push 完 WriteFile 的 5 个参数
        // [esp+0] = ret addr, [esp+4]=hFile, [esp+8]=lpBuffer,
        // [esp+0xC]=nBytes, [esp+0x10]=&written, [esp+0x14]=lpOverlapped
        var esp = this.context.esp;
        var lpBuffer = esp.add(0x8).readPointer();
        var nBytes = esp.add(0xC).readU32();
        console.log("[UtyCtrl] WriteFile " + nBytes + " bytes:");
        console.log(hexdump(lpBuffer, {length: nBytes}));
    }
});
```

---

## 15. 验证清单（待动态调试确认）

以下结论基于静态分析推断，需要动态调试验证：

- [ ] `g_mutex_handle` 在 DLL 加载时由 `CUtyCtrlApp` 构造函数调用 `CreateMutexA` 创建
- [ ] `GetClientTransInfo` 响应数据大小确实是 104 字节（26 dwords）
- [ ] `GetRemoteTransNetworkSet` 响应包含 WLAN IP/端口结构
- [ ] `ExecCmd` 的 data_len 计算公式 `(arg5 & 0xFF) + 0x14`
- [ ] 轮询循环确实无超时上限（潜在挂死点）
- [ ] CivCtrl.dll / HidCtrl.dll 使用 `RemoteCivCtrlCmd` / `RemoteHidCtrlCmd` mailslot 名
- [ ] RemoteUtility.exe 是 mailslot 服务器端，读取 RemoteUtyCtrlCmd

---

## 16. 工具与产物

### 16.1 分析脚本

- [utyctrl_deep_disasm.py](file:///d:/my%20git/scratchpad/tools/utyctrl_deep_disasm.py) — 主反汇编脚本（pefile + capstone）
- [utyctrl_deep_disasm2.py](file:///d:/my%20git/scratchpad/tools/utyctrl_deep_disasm2.py) — 补充脚本（init 函数 + ExecCmd 子函数 + 字符串簇）

### 16.2 中间产物

- [UtyCtrl_deep_disasm.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/UtyCtrl_deep_disasm.json) — 9 个导出函数 + 核心函数完整反汇编 + IAT 调用点 + 字符串/全局变量 xref
- [UtyCtrl_deep_disasm2.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/UtyCtrl_deep_disasm2.json) — init 函数 + ExecCmd 完整 + 字符串簇 dump

### 16.3 复现命令

```powershell
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\utyctrl_deep_disasm.py'
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\utyctrl_deep_disasm2.py'
```

---

## 附录 A：原始字符串簇（.rdata 0x10023840 起）

```
0x10023854  "Icom RemoteUtyCtrl"              ← Mutex 名
0x10023868  "\\.\mailslot\RemoteUtyCtrlCmd"   ← 命令 Mailslot
0x10023888  "\\.\mailslot\RemoteUtyCtrlRes"   ← 响应 Mailslot
0x100239B0  "RSDSB"                            ← PDB 路径前缀（调试符号）
0x100239C8  "C:\Release\dll\UtyCtrl\Release\UtyCtrl.pdb"
```

## 附录 B：9 个导出函数的 cmd_code/data_len 字节序列

从每个导出函数入口的栈初始化指令提取：

| 函数 | 设置 cmd_code 指令 | 设置 data_len 指令 |
|---|---|---|
| `GetCountClientTrans` | `mov byte ptr [esp+4], 0` @ 0x100011D7 | (无，data_len=0) |
| `GetClientTransInfo` | `mov byte ptr [esp+8], 1` @ 0x10001274 | `mov byte ptr [esp+9], 0x6C` @ 0x10001279 |
| `GetClientTransInfo2` | `mov byte ptr [esp+0xC], 4` @ 0x10001306 | `mov byte ptr [esp+0xD], 0x78` @ 0x1000131B |
| `GetClientTransVol` | `mov byte ptr [esp+0xC], 3` @ 0x100013B6 | `mov byte ptr [esp+0xD], 0x24` @ 0x100013CB |
| `GetClientTransVol3` | `mov byte ptr [esp+0xC], 5` @ 0x10001476 | `mov byte ptr [esp+0xD], 0x3C` @ 0x1000148B |
| `GetCommandProcCount` | `mov byte ptr [esp+4], 6` @ 0x100014F7 | (无，data_len=0) |
| `GetRemoteTransNetworkSet` | `mov byte ptr [esp+0xC], 7` @ 0x10001586 | `mov byte ptr [esp+0xD], 0x40` @ 0x1000159B |
| `GetRemoteTransState` | `mov byte ptr [esp+0xC], 8` @ 0x10001636 | `mov byte ptr [esp+0xD], 0x1C` @ 0x1000164B |
| `ExecCmd` | `mov byte ptr [esp+0x1C], 2` @ 0x100016F7 | `mov byte ptr [esp+0x11], bl` @ 0x10001718 (动态) |
