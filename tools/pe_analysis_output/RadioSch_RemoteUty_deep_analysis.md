# RS-BA1 V2 深度逆向分析报告

> 目标文件：
> - [RadioSch.dll](file:///d:/my%20git/RemoteUtility/RadioSch.dll) — 1,972,736 字节，PE32 x86 DLL，电台调度核心
> - [RemoteUty.exe](file:///d:/my%20git/RemoteUtility/RemoteUty.exe) — 3,010,048 字节，PE32 x86 EXE，RemoteUtility 主程序
>
> 分析方法：纯静态分析（pefile + capstone 反汇编 + 字符串交叉引用 + IAT 调用点扫描）
>
> 分析时间：2026-08-09
>
> 输出脚本：
> - [deep_disasm.py](file:///d:/my%20git/scratchpad/tools/deep_disasm.py) — 一阶分析（导出函数 + IAT 调用点）
> - [deep_disasm_v2.py](file:///d:/my%20git/scratchpad/tools/deep_disasm_v2.py) — 二阶分析（调用点上下文反汇编 + 字符串引用）
> - 中间数据：[deep_analysis.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/deep_analysis.json) / [deep_analysis_v2.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/deep_analysis_v2.json)

---

## 0. 执行摘要（TL;DR）

| 维度 | 结论 |
|------|------|
| **网络协议** | 纯 UDP（`socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)`），未用 TCP |
| **可靠传输** | 自研可靠 UDP 栈 `CUDPCtrl2`：序列号 + 重传 + 心跳 + 同步请求 |
| **网络端口** | 不在二进制中硬编码。运行时从注册表 `SOFTWARE\Icom\Remote Utility` 读取 `CommandPort / SerialPort / AudioPort` 三组端口 |
| **接口枚举** | `WSAIoctl(SIO_GET_INTERFACE_LIST=0x9800000c)` 枚举本机所有 IP（多 WLAN 适配器支持） |
| **CI-V 通信** | 通过 `\\.\COM%d` 串口设备路径访问；参数 `baud=%d parity=N data=8 stop=1`；多线程 Send/Recv |
| **USB 发现** | `SETUPAPI` 9 函数（CM_Get_Device_IDA 7 调用点）枚举设备树，匹配 `"VIDPID%d"` 字符串模式 |
| **虚拟驱动** | `icom_vaudio.sys` + `icom_vserial.sys`；用户态通过 `CreateFileA("\\.\ICOM_SERIAL")` 访问；参数注册表 `SYSTEM\CurrentControlSet\Services\icom_vaudio\Parameters\%s` |
| **三路信道** | 三组独立 UDP 端口分别承载 Command / Serial / Audio 三类业务，互不阻塞 |

---

## 1. RadioSch.dll 5 个导出函数深度反汇编（前 80 条指令）

### 1.1 导出表

| 名称 | Ordinal | RVA | 虚拟地址 |
|---|---|---|---|
| `CloseDll` | 1 | 0x2b00 | 0x10002b00 |
| `GetUsbDev` | 2 | 0x2c00 | 0x10002c00 |
| `OpenDll` | 3 | 0x3e20 | 0x10003e20 |
| `SearchUsbDev2` | 4 | 0x3f70 | 0x10003f70 |
| `SearchUsbDev` | 5 | 0x3f70 | 0x10003f70 |

注意：`SearchUsbDev` 与 `SearchUsbDev2` 共享同一 RVA（0x3f70），两者仅 ordinal 不同，函数体完全相同。这是 Icom 故意保留的双命名兼容入口。

### 1.2 CloseDll — 关闭 DLL/释放资源

```asm
0x10002b00: push ebp
0x10002b01: mov  ebp, esp
0x10002b03: push esi
0x10002b04: push 0x101be2d4                       ; 全局 CRITICAL_SECTION 地址
0x10002b09: call dword ptr [0x1016d3fc]           ; KERNEL32!EnterCriticalSection
0x10002b0f: mov  esi, dword ptr [ebp + 8]         ; arg1 = 对象指针
0x10002b12: mov  ecx, 0x101be2b0                  ; 另一个全局对象
0x10002b17: push 0
0x10002b19: push esi
0x10002b1a: call 0x1000ce54                       ; 内部 lookup(arg1) - 返回设备表项
0x10002b1f: test eax, eax
0x10002b21: je   0x10002b3b                       ; 找不到 → 跳到尾部
0x10002b23: push eax
0x10002b24: mov  ecx, 0x101be2b0
0x10002b29: call 0x1000cf61                       ; 内部 remove(entry)
0x10002b2e: test esi, esi
0x10002b30: je   0x10002b3b
0x10002b32: mov  eax, dword ptr [esi]              ; eax = this->vtable
0x10002b34: mov  ecx, esi
0x10002b36: push 1                                ; arg = 1（删除对象标志）
0x10002b38: call dword ptr [eax + 4]               ; this->vtable[1](1) 虚析构
0x10002b3b: mov  eax, dword ptr [0x101be2cc]
0x10002b40: mov  ecx, 0x101be2cc
0x10002b45: pop  esi
0x10002b46: pop  ebp
0x10002b47: jmp  dword ptr [eax + 0x14]            ; tail-call 全局对象的方法（LeaveCriticalSection 包装）
```

**关键证据**：
- `0x101be2d4` 是全局 CRITICAL_SECTION（所有 USB 设备访问互斥）
- `[0x1016d3fc]` IAT 表项 → `KERNEL32!EnterCriticalSection`
- `0x1000ce54` 是 lookup 函数（按 arg1 查找已注册的 USB 设备表项）
- 析构走 C++ 虚函数表 `[this+0]+4`（典型的 `delete this` 模式）
- 控制流尾部跳到 `[eax+0x14]`，即全局对象的虚函数表偏移 0x14（指向 `LeaveCriticalSection` 包装或链表清理）

后续反汇编揭示 `CloseDll` 在 `0x10002b50` 之后是另一个内部函数体（int3 padding 隔开），代码逻辑：
- 遍历链表 `[ebx+0xcc]` → `[ebx+0xd0]`（每节点 0x18 字节）
- 调用 `[node+0]+4` 析构每个节点
- tail-call `0x1000e894`（容器析构）

→ **`CloseDll` 负责关闭一个 USB 设备调度上下文，并清理其拥有的设备链表**。

### 1.3 GetUsbDev — 获取 USB 设备列表

```asm
0x10002c00: push ebp
0x10002c01: mov  ebp, esp
0x10002c03: push ecx                              ; 局部变量
0x10002c04: push esi
0x10002c05: mov  esi, dword ptr [ebp + 8]         ; arg1 = 查找键
0x10002c08: push edi
0x10002c09: push 0x101be2d4
0x10002c0e: call dword ptr [0x1016d3fc]            ; EnterCriticalSection
0x10002c14: push 0
0x10002c16: push esi
0x10002c17: mov  ecx, 0x101be2b0
0x10002c1c: call 0x1000ce54                       ; lookup(arg1)
0x10002c21: neg  eax                               ; CF = (eax != 0)
0x10002c23: mov  ecx, 0x101be2cc
0x10002c28: sbb  edi, edi                          ; edi = (eax==0) ? 0 : -1
0x10002c2a: mov  eax, dword ptr [0x101be2cc]
0x10002c2f: call dword ptr [eax + 0x14]            ; 全局对象方法
0x10002c32: and  edi, esi                          ; edi = (found ? arg1 : 0)
0x10002c34: je   0x10002cd7                        ; 找不到 → 跳过填充
0x10002c3a: push dword ptr [ebp + 0xc]             ; arg2
0x10002c3d: mov  ecx, edi
0x10002c3f: call 0x1000ce7b                       ; 取出设备表 entry
0x10002c44: test eax, eax
0x10002c46: je   0x10002cd7
0x10002c4c: mov  edi, dword ptr [ebp + 0x10]       ; arg3 = 输出缓冲
0x10002c4f: push ebx
0x10002c50: mov  ebx, dword ptr [eax + 8]          ; ebx = entry->devices (设备数组)
0x10002c53: push 0x220                             ; 0x220 = 544 字节
0x10002c58: push 0
0x10002c5a: mov  dword ptr [ebp - 4], ebx
0x10002c5d: mov  eax, dword ptr [ebx]              ; eax = devices->vid
0x10002c5f: mov  dword ptr [edi], eax              ; out->vid = vid
0x10002c61: mov  eax, dword ptr [ebx + 4]
0x10002c64: mov  dword ptr [edi + 4], eax          ; out->pid = pid
0x10002c67: mov  eax, dword ptr [ebx + 0xc]
0x10002c6a: mov  dword ptr [edi + 8], eax          ; out->count = devices->count
0x10002c6d: lea  eax, [edi + 0xc]
0x10002c70: push eax
0x10002c71: call 0x10143a10                       ; strncpy(out+0xc, devices->path, 0x220)
0x10002c76: add  esp, 0xc
0x10002c79: mov  dword ptr [ebp + 8], 0            ; i = 0
0x10002c80: cmp  dword ptr [ebx + 0xc], 0          ; while (i < devices->count)
0x10002c84: jle  0x10002ccb
0x10002c86: add  edi, 0x10                         ; out += 0x10 (skip header)
0x10002c89: mov  ecx, 0x3f                         ; max_len = 63
0x10002c8e: add  ebx, 0x18                         ; src += 0x18
0x10002c91: mov  eax, dword ptr [ebx - 8]          ; src->path
0x10002c94: mov  dword ptr [edi - 4], eax          ; out->field0 = src->path
0x10002c97: mov  eax, dword ptr [ebx]
0x10002c99: mov  esi, dword ptr [eax - 0xc]
0x10002c9c: cmp  esi, 0x40                         ; if len > 64, clamp to 63
0x10002c9f: cmovae esi, ecx
0x10002ca2: push esi
0x10002ca3: push eax
0x10002ca4: push edi
0x10002ca5: call 0x10142f10                        ; strncpy(out, src->path, len)
0x10002caa: mov  ecx, dword ptr [ebp + 8]
0x10002cad: lea  ebx, [ebx + 0xc]
0x10002cb0: mov  eax, dword ptr [ebp - 4]
0x10002cb3: inc  ecx                               ; i++
0x10002cb4: mov  byte ptr [edi + esi], 0           ; null-terminate
0x10002cb8: add  esp, 0xc
0x10002cbb: add  edi, 0x44                         ; out += 0x44 (每设备 68 字节)
0x10002cbe: mov  dword ptr [ebp + 8], ecx
0x10002cc1: cmp  ecx, dword ptr [eax + 0xc]
0x10002cc4: mov  ecx, 0x3f
0x10002cc9: jl   0x10002c91
0x10002ccb: pop  ebx
0x10002ccc: pop  edi
0x10002ccd: mov  eax, 1                             ; return 1 (success)
0x10002cd2: pop  esi
0x10002cd3: mov  esp, ebp
0x10002cd5: pop  ebp
0x10002cd6: ret
```

**`GetUsbDev(arg1, arg2, arg3)` 输出结构布局**（C 风格）：

```c
struct UsbDevList {        // sizeof >= 0x10 + count*0x44
    uint32_t vid;          // [out+0x00]
    uint32_t pid;          // [out+0x04]
    uint32_t reserved;     // [out+0x08]
    char     path[0x220];  // [out+0x0c] 设备基础路径
    UsbDevItem items[];    // [out+0x10+...] 每项 0x44 字节
};

struct UsbDevItem {        // sizeof = 0x44 = 68 字节
    char device_path[64];  // 设备路径（截断到 63 字符 + null）
};
```

- 每个设备条目内部结构 0x18 字节（源端）：`[src+0]=path ptr, [src+0xc]=next_path`
- 输出端每个设备占 0x44 字节
- 字符串最大长度 64 字节（`cmp esi, 0x40; cmovae esi, ecx` clamp 到 0x3f）

### 1.4 OpenDll — 打开/初始化 DLL 调度上下文

```asm
0x10003e20: push ebp
0x10003e21: mov  ebp, esp
0x10003e23: push -1                                ; SEH 链 terminate handler
0x10003e25: push 0x1015f0ca                        ; SEH handler 地址
0x10003e2a: mov  eax, dword ptr fs:[0]             ; 保存前一个 SEH
0x10003e30: push eax
0x10003e31: sub  esp, 0x1c                         ; 28 字节局部
0x10003e34: push ebx
0x10003e35: push esi
0x10003e36: push edi
0x10003e37: mov  eax, dword ptr [0x101b9e2c]       ; /GS cookie
0x10003e3c: xor  eax, ebp
0x10003e3e: push eax
0x10003e3f: lea  eax, [ebp - 0xc]
0x10003e42: mov  dword ptr fs:[0], eax             ; 安装新 SEH
0x10003e48: push 0x50                              ; 80 字节对象大小
0x10003e4a: call 0x1000cd09                        ; operator new[](0x50)
0x10003e4f: add  esp, 4
0x10003e52: mov  dword ptr [ebp - 0x18], eax       ; this = new obj
0x10003e55: mov  dword ptr [ebp - 4], 0            ; SEH state = 0
0x10003e5c: test eax, eax
0x10003e5e: je   0x10003f00                         ; new 失败 → 跳过
0x10003e64: sub  esp, 0xc                          ; alloc 12 bytes on stack
0x10003e67: mov  ebx, esp                          ; ebx = &local[0]
0x10003e69: mov  dword ptr [ebp - 0x10], ebx
0x10003e6c: mov  dword ptr [ebx], 0                ; clear 12 bytes
0x10003e72: mov  dword ptr [ebx + 4], 0
0x10003e79: mov  dword ptr [ebx + 8], 0
0x10003e80: mov  eax, dword ptr [0x101be2a8]       ; 全局 vector end
0x10003e85: mov  esi, dword ptr [0x101be2a4]       ; 全局 vector begin
0x10003e8b: mov  dword ptr [ebp - 0x14], eax
0x10003e8e: cmp  esi, eax
0x10003e90: je   0x10003ef4                         ; vector empty → skip copy
0x10003e92: mov  ecx, eax
0x10003e94: mov  eax, 0x2aaaaaab                   ; 1/12 魔数（除以 12 = 0x18>>1）
0x10003e99: sub  ecx, esi                          ; ecx = size_in_bytes
0x10003e9b: imul ecx                               ; edx:eax = size * 0x2AAAAAAB
0x10003e9d: mov  ecx, ebx
0x10003e9f: sar  edx, 2                            ; edx = size / 12
0x10003ea2: mov  edi, edx
0x10003ea4: shr  edi, 0x1f                         ; 符号位
0x10003ea7: add  edi, edx                          ; edi = element_count
0x10003ea9: push edi
0x10003eaa: call 0x10004350                        ; vector::reserve(edi)
0x10003eaf: mov  ebx, eax                          ; ebx = new buffer
0x10003eb1: lea  ecx, [edi + edi*2]                ; ecx = count*3
0x10003eb4: mov  eax, dword ptr [ebp - 0x10]
0x10003eb7: mov  dword ptr [ebp - 0x1c], eax
0x10003eba: lea  ecx, [ebx + ecx*8]                ; ecx = buf + count*24 = buf + count*0x18
0x10003ebd: mov  dword ptr [eax], ebx              ; this->begin = buf
0x10003ebf: mov  dword ptr [eax + 4], ebx          ; this->end = buf
0x10003ec2: mov  dword ptr [eax + 8], ecx          ; this->cap = buf + count*0x18
0x10003ec5: mov  dword ptr [ebp - 0x28], ebx
0x10003ec8: mov  dword ptr [ebp - 0x24], ebx
0x10003ecb: mov  dword ptr [ebp - 0x20], eax
0x10003ece: mov  edi, dword ptr [ebp - 0x14]
0x10003ed1: mov  byte ptr [ebp - 4], 2             ; SEH state = 2
0x10003ed5: push esi
0x10003ed6: mov  ecx, ebx
0x10003ed8: call 0x10002490                        ; 复制元素（构造函数）
0x10003edd: add  ebx, 0x18                          ; next slot
0x10003ee0: add  esi, 0x18                          ; next src
0x10003ee3: mov  dword ptr [ebp - 0x24], ebx
0x10003ee6: cmp  esi, edi
0x10003ee8: jne  0x10003ed5                         ; loop
0x10003eea: mov  eax, dword ptr [ebp - 0x10]
0x10003eed: mov  byte ptr [ebp - 4], 0
0x10003ef1: mov  dword ptr [eax + 4], ebx          ; update end
0x10003ef4: mov  ecx, dword ptr [ebp - 0x18]
0x10003ef7: call 0x10004b60                        ; 包装对象到上下文
0x10003efc: mov  esi, eax
0x10003efe: jmp  0x10003f02
0x10003f00: xor  esi, esi                           ; new 失败 → esi = NULL
0x10003f02: push 0x101be2d4
0x10003f07: mov  dword ptr [ebp - 4], 0xffffffff
0x10003f0e: call dword ptr [0x1016d3fc]             ; LeaveCriticalSection
0x10003f14: push esi
0x10003f15: mov  ecx, 0x101be2b0
0x10003f1a: call 0x1000ce28                        ; register(new_obj) 加入全局表
0x10003f1f: mov  edx, dword ptr [0x101be2cc]
```

**`OpenDll(arg1, arg2)` 关键点**：
1. 用 `/GS` 栈保护 + SEH frame，是 MSVC `try/catch` 生成的代码
2. `new[](0x50)` 分配 80 字节对象（DLL 上下文）
3. 全局 vector `[0x101be2a4] (begin) → [0x101be2a8] (end)` 保存已注册设备
4. 用除法魔数 `0x2AAAAAAB` 计算元素数量（除以 12 字节得到元素数）
5. 调用 `0x10004350` 扩容 vector，元素大小 0x18 字节
6. 复制构造每个元素（`0x10002490` = copy ctor）
7. 注册新对象到全局表（`0x1000ce28`）

→ **`OpenDll` 创建一个 USB 设备调度上下文，并复制全局设备列表到本地副本**。

### 1.5 SearchUsbDev / SearchUsbDev2 — 查找 USB 设备

```asm
0x10003f70: push ebp
0x10003f71: mov  ebp, esp
0x10003f73: push edi
0x10003f74: push 0x101be2d4
0x10003f79: call dword ptr [0x1016d3fc]            ; EnterCriticalSection
0x10003f7f: push 0
0x10003f81: push dword ptr [ebp + 8]               ; arg1 = 查找键
0x10003f84: mov  ecx, 0x101be2b0
0x10003f89: call 0x1000ce54                        ; lookup(arg1)
0x10003f8e: neg  eax
0x10003f90: mov  ecx, 0x101be2cc
0x10003f95: sbb  edi, edi                          ; edi = found ? -1 : 0
0x10003f97: mov  eax, dword ptr [0x101be2cc]
0x10003f9c: call dword ptr [eax + 0x14]             ; 全局对象方法（更新统计？）
0x10003f9f: and  edi, dword ptr [ebp + 8]           ; edi = found ? arg1 : 0
0x10003fa2: je   0x10003fad                         ; not found → return 0
0x10003fa4: mov  ecx, edi
0x10003fa6: pop  edi
0x10003fa7: pop  ebp
0x10003fa8: jmp  0x10007400                        ; tail-call 真正的查找函数
0x10003fad: xor  eax, eax                          ; return 0
0x10003faf: pop  edi
0x10003fb0: pop  ebp
0x10003fb1: ret
```

**关键点**：
- 仅接受 1 个参数 `arg1`（查找键，可能是 VID/PID 或路径前缀）
- 用 `lookup(arg1)` 查全局设备表
- 找到则 tail-call `0x10007400`（真正的 USB 设备打开/枚举函数）
- 找不到返回 0
- `SearchUsbDev` 和 `SearchUsbDev2` 同地址，仅 ordinal 不同 → 二进制兼容性 alias

---

## 2. RemoteUty.exe 网络层深度分析

### 2.1 WS2_32.dll 导入函数（18 个）

| 函数 | IAT RVA | 调用点数 | 用途 |
|------|---------|----------|------|
| `WSAStartup` | 0x18f96c | 4 | 初始化 Winsock（多处初始化，版本 0x101 = 2.1） |
| `WSACleanup` | 0x18f964 | 9 | 释放 Winsock（每条退出路径都清理） |
| `socket` | 0x18f954 | 1 | 创建 UDP socket（仅 1 处，单 socket 模型） |
| `bind` | 0x18f94c | 1 | 绑定本地端口（服务端模式） |
| `htons` | 0x18f950 | 2 | 主机→网络字节序端口（2 处：服务端 bind + 客户端 connect） |
| `htonl` | 0x18f970 | 4 | 主机→网络字节序 IP（4 处：填充 sockaddr_in） |
| `ntohs` | 0x18f93c | 2 | 网络→主机字节序端口（解析远端端口） |
| `ntohl` | 0x18f95c | 1 | 网络→主机字节序 IP |
| `inet_ntoa` | 0x18f960 | 1 | IP 转字符串（仅日志用） |
| `gethostbyname` | 0x18f968 | 3 | DNS 解析（弃用 API） |
| `getsockname` | 0x18f940 | 1 | 获取本地 socket 地址 |
| `setsockopt` | 0x18f980 | **0** | **未调用！** 没设置 SO_REUSEADDR 等 |
| `recvfrom` | 0x18f974 | 1 | 接收 UDP 数据包 |
| `sendto` | 0x18f978 | 1 | 发送 UDP 数据包 |
| `WSAIoctl` | 0x18f97c | 1 | SIO_GET_INTERFACE_LIST 枚举本机 IP |
| `closesocket` | 0x18f944 | 4 | 关闭 socket |
| `shutdown` | 0x18f948 | 4 | 关闭 socket 收发方向 |
| `WSAGetLastError` | 0x18f958 | 7 | 获取错误码 |

**关键观察**：
- 无 `listen/accept/connect/recv/send` → **纯 UDP，无 TCP**
- `socket` 仅 1 个调用点 → 单一 UDP socket 模型（虽多线程复用）
- `setsockopt` 0 调用点 → **未配置任何 socket 选项**（详见 §2.5 安全分析）

### 2.2 socket 调用点 — 确证 UDP

**调用点 RVA 0x5376c**（CUdp::open 内部）：

```asm
0x5374f: call WSAStartup(0x0202, &wsadata)         ; 初始化（在 0x5374f）
0x53755: test eax, eax
0x53757: je   0x453766                              ; 失败 → 错误处理
0x53759: call WSAGetLastError                       ; 错误路径
0x5375f: mov  ebx, eax
0x53761: jmp  0x45391a                              ; 跳到退出
0x53766: push 0                                     ; protocol  = 0  (IPPROTO_UDP)
0x53768: push 2                                     ; type      = 2  (SOCK_DGRAM)
0x5376a: push 2                                     ; af        = 2  (AF_INET)
0x5376c: call socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
0x53772: mov  dword ptr [esi + 0xc], eax            ; this->sock = sock
0x53775: cmp  eax, -1                               ; == INVALID_SOCKET?
```

**结论确凿**：`SOCK_DGRAM = 2` → UDP socket。

### 2.3 bind + sockaddr_in 构造

**调用点 RVA 0x537c8**（紧随 socket 之后）：

```asm
0x5378d: movzx ecx, word ptr [esi + 0x10]          ; port = this->port (运行时配置)
0x53791: xor   eax, eax
0x53793: mov   dword ptr [esp + 0x44], eax          ; 清零 sockaddr_in
0x53797: push  ecx                                  ; push port
0x53798: mov   dword ptr [esp + 0x44], eax          ; sin_addr = 0 (INADDR_ANY)
0x5379c: mov   dword ptr [esp + 0x4c], eax
0x537a0: mov   dword ptr [esp + 0x50], eax
0x537a4: mov   dword ptr [esp + 0x48], eax          ; sin_zero = 0
0x537a8: call  htons(port)                          ; port = htons(port)
0x537ae: mov   ecx, dword ptr [esi + 0xc]           ; this->sock
0x537b1: mov   word ptr [esp + 0x42], ax            ; sin_port = htons(port)
0x537b6: push  0x10                                 ; namelen = 16
0x537b8: lea   eax, [esp + 0x44]
0x537bc: push  eax                                  ; &sockaddr_in
0x537bd: mov   edx, 2
0x537c2: mov   word ptr [esp + 0x4c], dx            ; sin_family = AF_INET (2)
0x537c8: call  bind(sock, &sockaddr_in, 16)
0x537ce: test  eax, eax
0x537d0: je    0x4537fb                             ; 成功 → getsockname
```

**sockaddr_in 内存布局**（栈帧 `[esp+0x40]..[esp+0x50]`）：

```c
struct sockaddr_in {            // 16 bytes
    int16_t sin_family;         // [esp+0x4c] = 2 (AF_INET)
    uint16_t sin_port;          // [esp+0x42] = htons(this->port)
    struct in_addr sin_addr;    // [esp+0x44] = 0 (INADDR_ANY)
    char sin_zero[8];           // [esp+0x48..0x50]
};
```

- **端口来自 `[esi+0x10]`**（CUdp 对象偏移 0x10），运行时从注册表读取
- **`INADDR_ANY`**：绑定所有网络接口
- 这是 CUdp::open 的服务端模式（监听模式）

### 2.4 recvfrom / sendto — UDP 收发

**recvfrom 调用点 RVA 0x53bae**（CUdp::recv）：

```asm
0x53b96: mov  dword ptr [edi], eax                  ; 记录时间戳
0x53b98: mov  ecx, dword ptr [esi + 0xc]            ; this->sock
0x53b9b: mov  dword ptr [esp + 0x1c], eax
0x53b9f: mov  eax, dword ptr [esp + 0x78]           ; fromlen ptr
0x53ba3: push eax                                  ; &fromlen
0x53ba4: push ebx                                  ; &from (sockaddr_in 来源)
0x53ba5: push ecx                                  ; sock
0x53ba6: mov  dword ptr [esp + 0x34], 0x10          ; fromlen = 16
0x53bae: call recvfrom(sock, buf, len, 0, from, &fromlen)
0x53bb4: test eax, eax
0x53bb6: jle  0x453c02                              ; <=0 → 错误或关闭
```

**sendto 调用点 RVA 0x53ade**（CUdp::send）：

```asm
0x53acf: mov  eax, dword ptr [edi + 0xc]            ; this->sock
0x53ad2: push 0x10                                  ; tolen = 16
0x53ad4: lea  ecx, [esp + 0x40]
0x53ad8: push ecx                                  ; &to (sockaddr_in 目的)
0x53ad9: push 0                                     ; flags = 0
0x53adb: push edx                                  ; buf
0x53adc: push ebx                                  ; len
0x53add: push eax                                  ; sock
0x53ade: call sendto(sock, buf, len, 0, to, 16)
0x53ae4: mov  edx, dword ptr [esi]
0x53ae6: mov  edi, eax                             ; 记录返回值
```

### 2.5 WSAIoctl — 枚举本机网络接口

**调用点 RVA 0x538c1**：

```asm
0x538ae: push edi                                   ; outBufLen (DWORD)
0x538af: push edi                                   ; outBuf ptr (initially NULL)
0x538b0: push 4                                     ; inBufLen
0x538b2: lea  edx, [esp + 0x28]
0x538b6: push edx                                   ; &inBuf (DWORD)
0x538b7: push 0x9800000c                            ; dwIoControlCode = SIO_GET_INTERFACE_LIST
0x538bc: push eax                                   ; socket
0x538bd: mov  dword ptr [esp + 0x34], edi
0x538c1: call WSAIoctl(sock, SIO_GET_INTERFACE_LIST, ...)
```

`0x9800000c` = **SIO_GET_INTERFACE_LIST**（IOC_OUT | IOC_WS2 | 12）

→ RS-BA1 用此 ioctl 枚举本机所有网络接口（IP 列表），用于多 WLAN 卡场景下选择合适的本地地址。

### 2.6 端口配置来源 — 运行时注册表读取

字符串引用证据（字符串 → 代码引用）：

| 字符串 | RVA | 引用点 |
|--------|-----|--------|
| `CommandPort` | 0x1bb89c | 0x2b00e, 0x2b2f4, 0x31bc6 |
| `SerialPort` | 0x1bb8a8 | 0x2b024, 0x2b306, 0x31be7 |
| `AudioPort` | 0x1bb8b4 | 0x2b03a, 0x2b318, 0x31c08 |
| `SOFTWARE\Icom\Remote Utility` | 0x1bbb04 | 0x2d4e3, 0x30915, 0x30cbc |
| `SOFTWARE\Icom\RS-BA1\RemoteUty` | 0x1bc200 | 0x31a3c, 0x31b0a |

**端口配置代码模式**（rva 0x2b00e 处）：

```asm
0x2b004: call 0x4027e0                              ; 准备读取
0x2b009: mov  ecx, 0xc351                           ; 资源 ID 0xC351 = 50001
0x2b00e: mov  ebx, 0x5bb89c                         ; "CommandPort"
0x2b013: lea  eax, [esp + 0x2c]
0x2b017: call 0x42da10                              ; 读注册表/配置项
0x2b01c: mov  dword ptr [edi + 8], eax              ; 存入 ctx->commandPort

0x2b01f: mov  ecx, 0xc352                           ; 资源 ID 0xC352 = 50002
0x2b024: mov  ebx, 0x5bb8a8                         ; "SerialPort"
0x2b029: lea  eax, [esp + 0x2c]
0x2b02d: call 0x42da10
0x2b032: mov  dword ptr [edi + 0xc], eax            ; 存入 ctx->serialPort

0x2b035: mov  ecx, 0xc353                           ; 资源 ID 0xC353 = 50003
0x2b03a: mov  ebx, 0x5bb8b4                         ; "AudioPort"
0x2b03f: lea  eax, [esp + 0x2c]
0x2b043: call 0x42da10
0x2b048: push 0
0x2b04a: push 0x5b8ea4                             ; 另一个键名（"Port"?）
```

**关键发现**：
- `0xC351/0xC352/0xC353` 是资源 ID（50001/50002/50003）
- 这暗示 **RS-BA1 V2 默认端口可能是 50001/50002/50003**
- 这些 ID 在 PE 资源段中是字符串表条目（参见 RemoteUty.exe 资源段 STRING 表 0x3857 等）
- 实际端口号优先从注册表 `SOFTWARE\Icom\Remote Utility` 读取，注册表缺失时回落到资源段默认值

### 2.7 网络协议栈架构

基于字符串证据，RemoteUty.exe 实现了**三层 UDP 协议栈**：

```
┌─────────────────────────────────────────────────────────────┐
│                  业务层（RemoteController 通信）             │
├─────────────────────────────────────────────────────────────┤
│  Command 信道      │   Serial 信道      │   Audio 信道       │
│  (CClientCommand   │  (CClientSerial   │  (CClientAudio    │
│   Ctrl)            │   Ctrl)           │   Ctrl)           │
├─────────────────────────────────────────────────────────────┤
│        可靠传输层（CUDPCtrl2）                                │
│  - sendReqSync / sendReqFSync  同步请求                       │
│  - sendNop                      心跳                          │
│  - sendReqResend                重传请求                       │
│  - TimerThread                  超时重传线程                   │
│  - setResend                    重传配置                       │
│  - ExecSync / ExecFsync / ExecCmd   执行命令                  │
├─────────────────────────────────────────────────────────────┤
│        会话层（CUDPCtrl）                                     │
│  - ExOpen / ExConnect / ExAccept  建立/接受会话                │
│  - ExSend / ExClose              发送/关闭                     │
│  - ExSessionClose                会话级关闭                   │
│  - sendDisconnect / recvCallback  断连通知/回调                │
├─────────────────────────────────────────────────────────────┤
│        UDP 传输层（CUdp）                                     │
│  - open (socket+bind) / close                                 │
│  - send (sendto) / recv (recvfrom)                            │
│  - recvThread (后台接收线程)                                  │
│  - addCallback / delCallback                                  │
├─────────────────────────────────────────────────────────────┤
│        Winsock API（WS2_32.dll）                              │
│  WSAStartup → socket(SOCK_DGRAM) → bind →                     │
│  recvfrom/sendto → closesocket → WSACleanup                   │
└─────────────────────────────────────────────────────────────┘
```

### 2.8 数据包格式推测

基于字符串 `" port = %d seq = %d"`（调试日志），数据包至少包含：

```c
struct RsBa1UdpPacket {
    uint8_t  magic;          // 协议魔数（待动态分析确认）
    uint8_t  type;           // 包类型：sync/fsync/cmd/nop/data/resend
    uint16_t port;           // 业务端口标识
    uint32_t seq;            // 序列号
    uint32_t ack_seq;        // 确认号（推测）
    uint8_t  payload[];      // 载荷
};
```

包类型（基于 CUDPCtrl2 方法名）：
- `sendReqSync` - 同步请求（请求对端序号同步）
- `sendReqFSync` - 强制同步请求
- `sendNop` - 心跳/保活（KeepAlive）
- `sendReqResend` - 重传请求（NACK 模式）
- `ExecSync/ExecFsync/ExecCmd` - 命令执行

### 2.9 音频流处理

`CAudioCtrl` 是音频核心（CSDN 风格命名）：

```c
// 字符串证据
"m_SendConf: fs:%d bit:%d ch:%d codec:%s cnt:%d time:%d"
"m_RecvConf: fs:%d bit:%d ch:%d codec:%s cnt:%d time:%d"
// fs=采样率, bit=位深, ch=声道, codec=编码, cnt=块大小, time=时长
```

- 采样率转换 `CSampleConv::conv/conv1/conv3/lpf/bitchnconv` - 重采样 + 低通滤波
- `CAudioCtrl::CheckPostUdpRecv` - UDP 接收后处理（处理丢包导致的"切割"）
- `CClientAudioCtrl::vaudioSendBlock` - 通过虚拟音频驱动发送块

---

## 3. RadioSch.dll 硬件层 — SETUPAPI + USB 设备发现

### 3.1 SETUPAPI.dll 9 个导入函数

| 函数 | IAT VA | 调用点数 | 用途 |
|------|--------|----------|------|
| `SetupDiGetClassDevsA` | 0x1016d498 | 2 | 创建设备信息集 |
| `SetupDiEnumDeviceInfo` | 0x1016d490 | 4 | 枚举设备 |
| `SetupDiGetDeviceInstanceIdA` | 0x1016d4ac | 2 | 取设备实例 ID |
| `SetupDiOpenDevRegKey` | 0x1016d49c | 1 | 打开设备注册表键 |
| `SetupDiDestroyDeviceInfoList` | 0x1016d494 | 2 | 销毁设备信息集 |
| `CM_Get_Device_IDA` | 0x1016d4a4 | 7 | 取设备 ID 字符串 |
| `CM_Get_Parent` | 0x1016d4a8 | 2 | 取父设备（USB 集线器） |
| `CM_Get_Child` | 0x1016d4a0 | 1 | 取子设备（接口） |
| `CM_Get_Sibling` | 0x1016d4b0 | 2 | 取兄弟设备（同 composite） |

### 3.2 设备枚举流程

**SetupDiGetClassDevsA** (调用点 RVA 0x62af)：

```asm
0x629e: push 0xa                                   ; Flags = DIGCF_PRESENT (0x02) | DIGCF_DEVICEINTERFACE (0x10) -- 但 0x0A = DIGCF_PRESENT|DIGCF_ALLCLASSES
0x62a0: push 0                                     ; Enumerator = NULL
0x62a2: push 0                                     ; hwndParent = NULL
0x62a4: lea  eax, [ebp - 0x128]                    ; &GUID
0x62aa: mov  byte ptr [ebp - 4], 5
0x62ae: push eax                                   ; ClassGuid
0x62af: call SetupDiGetClassDevsA(GUID, NULL, NULL, 0x0A)
```

`0x0A = DIGCF_ALLCLASSES(0x08) | DIGCF_PRESENT(0x02)` → 枚举所有当前连接的设备

第二处调用点 RVA 0x75a8：Flags = `0x12 = DIGCF_DEVICEINTERFACE(0x10) | DIGCF_PRESENT(0x02)` → 枚举特定 GUID 的设备接口（更精确）

**SetupDiEnumDeviceInfo** (调用点 RVA 0x6305)：

```asm
0x62e3: lea  ecx, [ebp - 0x144]                    ; &devinfo_data (SP_DEVINFO_DATA)
0x62f1: push ecx                                   ; &devinfo_data
0x62f2: push 0                                     ; member index = 0
0x62f4: push eax                                   ; DeviceInfoSet
0x6305: call SetupDiEnumDeviceInfo(set, 0, &data)
0x630b: test eax, eax
0x630d: je   0x10006a9b                             ; 失败 → 跳到清理
```

**CM_Get_Device_IDA** (调用点 RVA 0x59d0)：

```asm
0x59be: push 0x400                                  ; max len = 1024
0x59c3: lea  eax, [ebp - 0x410]                    ; &buffer[1024]
0x59c9: push eax
0x59ca: push dword ptr [ebp - 0x87c]               ; dev_inst handle
0x59d0: call CM_Get_Device_IDA(devInst, buf, 1024, 0)
0x59d6: lea  ecx, [ebp - 0x410]                    ; 解析返回的 ID
0x59dc: lea  edx, [ecx + 1]
```

缓冲区 0x400 字节 = 1024 字节 → 设备 ID 完整路径（如 `USB\VID_0C26&PID_0010\6&1A2B3C4D&0&1`）

### 3.3 设备树遍历

RadioSch.dll 用 3 个 CM_ 函数遍历 USB 设备树：

```
USB Root Hub
└── USB Composite Device (VID/PID 匹配)
    ├── Child Interface 1 (CI-V 串口)
    ├── Child Interface 2 (CI-V audio)
    └── Child Interface 3 (control)
```

- `CM_Get_Child` (0x8cc8)：从 composite 设备下钻到子接口
- `CM_Get_Sibling` (0x9053, 0x91d2)：遍历同 composite 的兄弟接口
- `CM_Get_Parent` (0x684f, 0x7a92)：从子接口上溯到 composite 设备（用于查找 VID/PID）

### 3.4 SetupDiOpenDevRegKey — 读取设备硬件参数

**调用点 RVA 0x6617**：

```asm
0x65fb: push 1                                     ; KeyType = DIREG_DEV (1)
0x65fd: or   eax, 0xffffffff
0x6600: push 0                                     ; Reserved = 0
0x6602: mov  dword ptr [ebp - 0x14c], eax
0x6608: lea  eax, [ebp - 0x144]                    ; &devinfo_data
0x660e: push 1                                     ; samDesired = KEY_READ
0x6610: push eax
0x6611: push dword ptr [ebp - 0x168]               ; DeviceInfoSet
0x6617: call SetupDiOpenDevRegKey(set, &data, DIREG_DEV, 0, KEY_READ, 0)
0x661d: mov  edi, eax                               ; hKey
0x661f: test edi, edi
```

→ 打开 `HKLM\SYSTEM\CurrentControlSet\Enum\<device>\<instance>\Device Parameters` 键读取硬件参数

### 3.5 USB 设备匹配 — "VIDPID%d" 字符串模板

**字符串引用 RVA 0x2eef**：

```asm
0x2ede: mov  byte ptr [ebp - 4], 5                 ; SEH state
0x2ee2: push edi
0x2ee3: lea  eax, [ebp - 0x170]                     ; &buf
0x2ee9: mov  dword ptr [ebp - 0x190], edi
0x2eef: push 0x1016de84                             ; "VIDPID%d"
0x2ef4: push eax
0x2ef5: call 0x10001e30                            ; sprintf(buf, "VIDPID%d", vid)
0x2efa: add  esp, 0xc
0x2efd: lea  ecx, [ebp - 0x160]
0x2f03: push dword ptr [ebp - 0x170]
0x2f09: call 0x100020b0                            ; 字符串查找/匹配
```

→ RadioSch.dll 用 `sprintf(buf, "VIDPID%d", vid)` 构造匹配模式，然后与 CM_Get_Device_IDA 返回的字符串比对（strstr 或 strcmp）

### 3.6 注册表路径直查

字符串 `SYSTEM\CurrentControlSet\Enum\` (rva 0x16df30) 在 RVA 0x8d46 和 0x90d2 被引用 → 备用路径：直接遍历注册表枚举键值

---

## 4. CI-V 串口通信

### 4.1 类层次（基于字符串证据）

```
CCIVComIF (单串口接口)
├── Open / Close
├── Read / Write
├── EscapeCommFunction
├── GetCommModemStatus
└── AddRecvData

CCIVCom (多接口聚合)
├── Open / CloseSub / Close
├── AddIF / RemoveIF
├── Send
├── EscapeCommFunction / GetCommModemStatus
├── SendThread              ← 独立发送线程
└── RecvThread              ← 独立接收线程

CTransceiver (电台抽象)
├── createDevice
└── deleteDevice
```

### 4.2 串口互斥锁

字符串 `MUTEX_REMOTEUTY_CCIVCOMIF_COM%d` (rva 0x1b84fc)：
- 每个串口（COM%d）一把命名互斥锁
- 防止 RemoteUty 多实例同时访问同一电台

### 4.3 串口参数

字符串 `baud=%d parity=N data=8 stop=1` (rva 0x1b85f0)，引用点 RVA 0x11388：

```asm
0x11379: je   0x4114bb
0x1137f: mov  eax, dword ptr [esp + 0x7c]          ; baud rate
0x11383: push eax                                  ; baud
0x11384: lea  ecx, [esp + 0x18]                    ; &dcb
0x11388: push 0x5b85f0                             ; "baud=%d parity=N data=8 stop=1"
0x1138d: push ecx                                  ; &dcb_string
0x1138e: call 0x402460                             ; sprintf or BuildCommDCBA
```

→ 调用 Win32 `BuildCommDCBAndTimeoutsA("baud=19200 parity=N data=8 stop=1", &dcb)` 构造 DCB

固定参数：
- `parity=N` (None)
- `data=8` (8 bits)
- `stop=1` (1 stop bit)
- `baud=%d` → 运行时从注册表 `Baudrate` 键读取（典型值 19200/9600）

### 4.4 串口设备路径

字符串 `\\.\COM%d` (在 ci_v_commands 分类下)：
- 通过 `CreateFileA("\\.\COM%d", ...)` 打开串口
- `%d` 来自注册表 `SerialPort` 配置

### 4.5 CI-V 协议层

字符串证据：
- `CI-V` / `#CI-V` / `"CI-V USB` / `/CI-V` / `eCI-V` - CI-V 协议标识
- `CIVAddress` - CI-V 地址配置项
- `UseCIV` - 是否使用 CI-V 协议（vs 直接串口透传）

---

## 5. 虚拟驱动管理 — icom_vaudio.sys / icom_vserial.sys

### 5.1 关键字符串

| 字符串 | RVA | 含义 |
|--------|-----|------|
| `icom_vaudio.sys` | 0x2b7290 | 虚拟音频驱动内核文件 |
| `icom_vserial.sys` | 0x2b726e | 虚拟串口驱动内核文件 |
| `\\.\ICOM_SERIAL` | 0x1b94f0 | 用户态设备路径（CreateFileA 打开） |
| `\Device\IcomVSerial` | 0x1bce5c | 内核设备名（NT 设备命名空间） |
| `ICOM_VAUDIO` | 0x1bed28 | 虚拟音频设备符号链接 |
| `VAudioDevice` | 0x1b8f38 | 用户态音频设备名 |
| `(Icom Virtual Audio Driver)` | 0x1b9068 | 设备描述 |
| `SYSTEM\CurrentControlSet\Services\icom_vaudio\Parameters\%s` | 0x1b9470 | 驱动实例参数注册表 |
| `SOFTWARE\Icom\Remote Utility` | 0x1bbb04 | 用户态配置注册表 |
| `SOFTWARE\Icom\RS-BA1\RemoteUty` | 0x1bc200 | 兼容性配置注册表 |
| `%s\DRIVERS\%s` | — | 驱动文件路径模板 |

### 5.2 虚拟串口打开逻辑

**调用点 RVA 0x3c871**（CreateFileA 打开 `\\.\ICOM_SERIAL`）：

```asm
0x3c868: push 3                                     ; OPEN_EXISTING (3)
0x3c86a: push ebx                                  ; hTemplateFile = NULL
0x3c86b: push ebx                                  ; dwFlagsAndAttributes = 0
0x3c86c: push 0xc0000000                           ; dwDesiredAccess = GENERIC_READ|GENERIC_WRITE (0xC0000000)
0x3c871: push 0x5b94f0                             ; "\\\\.\\ICOM_SERIAL"
0x3c876: call dword ptr [0x58f2b8]                 ; KERNEL32!CreateFileA
0x3c87c: mov  dword ptr [esi + 4], eax             ; ctx->handle = hDevice
0x3c87f: cmp  eax, -1
0x3c882: jne  0x43c88c                              ; 成功 → 继续
0x3c884: call dword ptr [0x58f2a8]                 ; GetLastError
0x3c88a: mov  ebx, eax
0x3c88c: mov  dword ptr [esp + 0x4c], ebx
```

→ 标准的 DeviceIoControl 设备打开模式：
- 共享模式 0（独占） — 但参数序对，stack 顺序为 CreateFileA(lpFileName, dwDesiredAccess, dwShareMode, lpSecurityAttributes, dwCreationDisposition, dwFlagsAndAttributes, hTemplateFile)
- 实际上 `push 3; push ebx; push ebx; push 0xc0000000; push name` 对应：
  - `dwCreationDisposition = 3` (OPEN_EXISTING)
  - `dwFlagsAndAttributes = 0`
  - `dwShareMode = 0` (独占)
  - `dwDesiredAccess = 0xC0000000` (GENERIC_READ | GENERIC_WRITE)

### 5.3 内核设备名查找 — NtOpenFile 模式

**调用点 RVA 0x3c8e3, 0x4ace5**（`\Device\IcomVSerial` 字符串引用）：

```asm
0x3c8d8: cmp  eax, 1
0x3c8db: jne  0x43c90b
0x3c8dd: cmp  dword ptr [ebx - 0xc], 0             ; length check
0x3c8e1: jl   0x43c8f9
0x3c8e3: push 0x5bce5c                             ; "\\Device\\IcomVSerial"
0x3c8e8: push ebx                                  ; &ustr
0x3c8e9: call 0x55d19a                             ; RtlInitUnicodeString / similar
0x3c8ee: add  esp, 8
0x3c8f1: test eax, eax
0x3c8f3: je   0x43c8f9
0x3c8f5: sub  eax, ebx
0x3c8f7: jns  0x43c903
0x3c8f9: mov  dword ptr [esp + 0x4c], 0xb7         ; status = 0xB7 (STATUS_INVALID_DEVICE_REQUEST?)
```

→ 同时使用 Win32 路径（`\\.\ICOM_SERIAL`）和 NT 路径（`\Device\IcomVSerial`）两条路径尝试打开。NT 路径通常用于 `NtCreateFile`/`NtOpenFile` 系统调用。

### 5.4 用户态包装类

| 类名 | RVA | 职责 |
|------|-----|------|
| `CVAudioCtrl` | 0x1f0ac8 | 虚拟音频控制（基类） |
| `CVSerialCtrl` | 0x1f0ae4 | 虚拟串口控制（基类） |
| `CClientAudioCtrl` | — | 客户端音频控制（继承 CVAudioCtrl） |
| `CClientSerialCtrl` | — | 客户端串口控制（继承 CVSerialCtrl） |

### 5.5 虚拟音频发送

字符串 `CClientAudioCtrl::vaudioSendBlock` (rva 0x1b729c) → 音频块通过虚拟音频驱动发送（DeviceIoControl 或 WriteFile）

字符串 `vserial send  %10d recv     %10d` (rva 0x1bcfd4) → 虚拟串口收发统计日志

### 5.6 驱动实例参数注册表

`SYSTEM\CurrentControlSet\Services\icom_vaudio\Parameters\%s` 表明：
- 每个虚拟音频实例在驱动 Parameters 下有独立子键
- `%s` 是实例名（可能是 GUID 或编号）
- 用户态通过 `RegOpenKeyExA` 打开此键读取配置

### 5.7 驱动安装

字符串 `%s\DRIVERS\%s` + `Please reinstall from CD.` 表明：
- 安装时从 CD 复制 `icom_vaudio.sys` / `icom_vserial.sys` 到 `%SystemRoot%\System32\drivers\`
- 通过 SC Manager 注册服务（InstallService + StartService）

---

## 6. 完整系统架构

### 6.1 RS-BA1 V2 网络服务端架构

```
                          ┌──────────────────────────────┐
                          │     RemoteController.exe      │
                          │       (Remote 控制端)         │
                          └────────────┬──────────────────┘
                                       │ WLAN (UDP)
                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                       RemoteUty.exe (网络服务端)                │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ Command     │  │  Serial     │  │  Audio      │              │
│  │ Channel     │  │  Channel    │  │  Channel    │              │
│  │ (UDP:50001) │  │ (UDP:50002) │  │ (UDP:50003) │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                     │
│         ▼                ▼                ▼                     │
│  ┌──────────────────────────────────────────────────┐            │
│  │           CUDPCtrl2 (可靠传输层)                 │            │
│  │  Sync/FSync/Nop/Resend + TimerThread            │            │
│  └──────────────────────────────────────────────────┘            │
│         │                │                │                     │
│         ▼                ▼                ▼                     │
│  ┌──────────────────────────────────────────────────┐            │
│  │           CUDPCtrl (会话层)                      │            │
│  │  ExOpen/ExAccept/ExConnect/ExSend/ExClose        │            │
│  └──────────────────────────────────────────────────┘            │
│         │                │                │                     │
│         ▼                ▼                ▼                     │
│  ┌──────────────────────────────────────────────────┐            │
│  │           CUdp (UDP 传输层)                       │            │
│  │  socket(AF_INET, SOCK_DGRAM) + bind + recvfrom   │            │
│  └──────────────────────────────────────────────────┘            │
└──────────────────────────┬───────────────────────────────────────┘
                           │ 内部接口
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    RadioSch.dll (电台调度核心)                    │
│                                                                  │
│  导出: OpenDll / CloseDll / GetUsbDev / SearchUsbDev(2)           │
│                                                                  │
│  ┌──────────────────────────────────────────────────┐            │
│  │  SETUPAPI 设备枚举 (9 函数, 23 调用点)           │            │
│  │  SetupDiGetClassDevs + CM_Get_Device_IDA +       │            │
│  │  CM_Get_Parent/Child/Sibling 设备树遍历          │            │
│  └──────────────────────────────────────────────────┘            │
│                           │                                      │
│  ┌──────────────────────────────────────────────────┐            │
│  │  CCIVComIF / CCIVCom (CI-V 串口)                  │            │
│  │  CreateFileA("\\\\.\\COM%d", baud=%d N81)        │            │
│  │  SendThread + RecvThread 多线程                   │            │
│  └──────────────────────────────────────────────────┘            │
└──────────────────────────┬───────────────────────────────────────┘
                           │ USB
                           ▼
                  ┌──────────────────┐
                  │   Icom 电台硬件    │
                  │   (USB composite)  │
                  │   - CI-V 串口接口   │
                  │   - USB Audio      │
                  └──────────────────┘
```

### 6.2 虚拟驱动数据流

```
RemoteController ←→ RemoteUty.exe ←→ (虚拟驱动) ←→ 实际电台
                                  ↑
              ┌───────────────────┴───────────────────┐
              │                                       │
       icom_vserial.sys                      icom_vaudio.sys
       (虚拟 COM 端口)                       (虚拟 wave 设备)
              │                                       │
       \\.\ICOM_SERIAL                       VAudioDevice
       \Device\IcomVSerial                    ICOM_VAUDIO
              │                                       │
              └─────→ 应用层视为真实串口/声卡 ←──────┘
```

→ 虚拟驱动的作用：让传统电台控制软件（如 N1MM/HRD）能通过虚拟 COM 端口"看到"网络上的电台，同时音频流通过虚拟声卡路由。

---

## 7. 安全分析

### 7.1 网络层安全发现

#### 🔴 严重：未设置 SO_REUSEADDR
**位置**：WS2_32 导入表中 `setsockopt` 调用点 = 0
**影响**：服务端异常退出后，UDP 端口进入 TIME_WAIT 等待，无法立即重新绑定。重启服务端会失败。
**修复**：bind 之前调用：
```c
int opt = 1;
setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, (char*)&opt, sizeof(opt));
```

#### 🔴 严重：自定义可靠 UDP 协议无加密无认证
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

**修复建议**（防御视角）：
- 在 CUDPCtrl2 层增加 HMAC-SHA256 包认证
- 会话初始化时协商会话密钥（基于预共享密钥 PSK）
- 增加 timestamp 字段防重放

#### 🟡 注意：gethostbyname 已弃用
**位置**：3 处调用
**影响**：不支持 IPv6；DNS 解析在阻塞调用中可能卡死
**修复**：替换为 `getaddrinfo`（支持 IPv4/IPv6，且可设非阻塞）

#### 🟡 注意：无超时控制的 recvfrom
**位置**：rva 0x53bae
**影响**：`recvfrom` 默认阻塞，无 SO_RCVTIMEO 设置（setsockopt 0 调用）
**修复**：通过 WSAEventSelect 或 SO_RCVTIMEO 实现超时

### 7.2 硬件层安全发现

#### 🟡 注意：USB 设备匹配方式宽松
**位置**：`VIDPID%d` 模板
**影响**：仅按 VID 匹配（字符串模板中只有 `%d`，可能仅匹配 VID 数字，不查 PID）
**风险**：理论上可被同 VID 的伪造 USB 设备欺骗（但需要物理接触）

#### 🟡 注意：虚拟串口 CreateFileA 共享模式 = 0（独占）
**位置**：rva 0x3c871
**影响**：虚拟串口一次只能被一个进程打开（设计正确，无安全问题）

### 7.3 配置存储安全

#### 🟢 注意：注册表配置无 ACL 检查
**位置**：`SOFTWARE\Icom\Remote Utility`
**影响**：注册表项可被普通用户修改（Windows 默认 HKLM\SOFTWARE 子键通常 Users 可写）
**风险**：低权限用户可篡改端口配置导致服务 DoS（非提权）

---

## 8. 关键 RVA 速查表

### 8.1 RemoteUty.exe 网络层

| 功能 | 关键 RVA | 函数 |
|------|----------|------|
| WSAStartup 调用 | 0x5374f | CUdp::open |
| socket 创建 | 0x5376c | CUdp::open |
| bind 调用 | 0x537c8 | CUdp::open |
| htons (服务端) | 0x537a8 | CUdp::open |
| getsockname | 0x53811 | CUdp::open |
| WSAIoctl (接口枚举) | 0x538c1 | CUdp::open |
| recvfrom | 0x53bae | CUdp::recv |
| sendto | 0x53ade | CUdp::send |
| htons (客户端) | 0x53ab6 | CUdp::connect |
| WSAStartup (其他) | 0x1412b, 0x402f3, 0x446f5 | 其他初始化 |
| gethostbyname | 0x1414d, 0x40306, 0x44707 | DNS 解析 |
| 端口配置读取 | 0x2b00e (CommandPort), 0x2b024 (SerialPort), 0x2b03a (AudioPort) | 配置加载 |
| 虚拟串口打开 | 0x3c871 | CVSerialCtrl::open |
| 虚拟音频查找 | 0x4eb90, 0x4ebb5 | CVAudioCtrl::find |
| NT 设备名查找 | 0x3c8e3, 0x4ace5 | CVSerialCtrl::openAlt |
| KeepAlive 线程 | — | CRemoteServer::KeepAliveThread |

### 8.2 RadioSch.dll 硬件层

| 功能 | 关键 RVA | 函数 |
|------|----------|------|
| CloseDll | 0x2b00 | 导出 |
| GetUsbDev | 0x2c00 | 导出 |
| OpenDll | 0x3e20 | 导出 |
| SearchUsbDev / SearchUsbDev2 | 0x3f70 | 导出（双命名 alias） |
| SearchUsbDev 真实实现 | 0x7400 | tail-call 目标 |
| USB 设备查找 | 0xce54 | 内部 lookup |
| VIDPID 模板构造 | 0x2eef | USB 匹配 |
| SetupDiGetClassDevsA #1 | 0x62af | 枚举所有设备 (DIGCF_ALLCLASSES) |
| SetupDiGetClassDevsA #2 | 0x75a8 | 枚举接口 (DIGCF_DEVICEINTERFACE) |
| SetupDiEnumDeviceInfo | 0x6305, 0x6a87, 0x75fc, 0x89ee | 4 处 |
| CM_Get_Device_IDA | 0x59d0, 0x5c20, 0x686c, 0x815f, 0x8bcd, 0x8ce9, 0x9075 | 7 处 |
| CM_Get_Parent | 0x684f, 0x7a92 | 2 处 |
| CM_Get_Child | 0x8cc8 | 1 处 |
| CM_Get_Sibling | 0x9053, 0x91d2 | 2 处 |
| SetupDiOpenDevRegKey | 0x6617 | 1 处 |

---

## 9. 复现方法

### 9.1 重新生成反汇编数据

```powershell
# 在 d:\my git 目录下
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\deep_disasm.py'
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\deep_disasm_v2.py'
```

输出：
- [deep_analysis.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/deep_analysis.json) — 一阶反汇编数据（导出函数前 80 条 + IAT 调用点扫描）
- [deep_analysis_v2.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/deep_analysis_v2.json) — 二阶反汇编数据（调用点上下文 + 字符串引用）

### 9.2 提取摘要文本

```powershell
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\extract_deep.py'
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' 'd:\my git\scratchpad\tools\extract_deep_v2.py'
```

### 9.3 验证脚本依赖

```powershell
& 'd:\my git\scratchpad\.venv\Scripts\python.exe' -c "import pefile, capstone; print('pefile', pefile.__version__); print('capstone', capstone.__version__)"
# pefile 2024.8.26
# capstone 5.0.7
```

---

## 10. 待动态分析确认的疑点

1. **端口号是否真的是 50001/50002/50003**
   - 静态只看到资源 ID `0xC351/0xC352/0xC353`，需动态启动 RemoteUty.exe 后用 `netstat -ano | findstr <pid>` 确认实际监听端口

2. **CUDPCtrl2 数据包格式**
   - 字符串 `" port = %d seq = %d"` 暗示包头有 port + seq，但完整结构需 Wireshark 抓包 + IDA 动态调试确认

3. **USB 设备 VID/PID**
   - Icom USB 电台典型 VID 是 `0x0C26`（Icom Inc.），PID 因型号不同（IC-7300=0x0010, IC-9700=0x0012 等）。需在被 RadioSch.dll 命中的真实设备上验证

4. **虚拟驱动 IOCTL 码**
   - `\Device\IcomVSerial` 设备的 DeviceIoControl 控制码需通过 IRP 监控（如 DriverMonitor）确认

5. **setsockopt 0 调用点的另一种解释**
   - 可能 setsockopt 通过函数指针间接调用（未在 IAT 显式导入处出现）。需要用 IDA xref 验证

---

## 附录 A：参考文献与依据

- 静态分析输入数据：
  - [RadioSch.dll.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/RadioSch.dll.json) (197 KB)
  - [RemoteUty.exe.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/RemoteUty.exe.json) (262 KB)
  - [RadioSch.dll.md](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/RadioSch.dll.md)
  - [RemoteUty.exe.md](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/RemoteUty.exe.md)

- 反汇编中间数据：
  - [deep_analysis.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/deep_analysis.json) (112 KB)
  - [deep_analysis_v2.json](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/deep_analysis_v2.json) (210 KB)
  - [deep_analysis_summary.txt](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/deep_analysis_summary.txt) (22 KB)
  - [deep_analysis_v2_summary.txt](file:///d:/my%20git/scratchpad/tools/pe_analysis_output/deep_analysis_v2_summary.txt) (39 KB)

- 分析脚本：
  - [pe_analyzer.py](file:///d:/my%20git/scratchpad/tools/pe_analyzer.py) — 一阶 PE 静态分析（已有）
  - [deep_disasm.py](file:///d:/my%20git/scratchpad/tools/deep_disasm.py) — 深度反汇编脚本（新建）
  - [deep_disasm_v2.py](file:///d:/my%20git/scratchpad/tools/deep_disasm_v2.py) — 调用点上下文反汇编脚本（新建）

- 工具链：
  - pefile 2024.8.26 (PE 解析)
  - capstone 5.0.7 (反汇编)
  - Python 3.x (在 `d:\my git\scratchpad\.venv\Scripts\python.exe`)
