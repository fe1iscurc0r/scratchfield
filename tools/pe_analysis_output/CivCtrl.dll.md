# CivCtrl.dll 静态分析报告

> 文件大小: 151,040 bytes | 机器: x86 | 类型: DLL | 入口: 0x10f8 | ImageBase: 0x400000
> 编译时间: 2018-06-15 05:58:22

---

## 区段

| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 熵值 |
|---|---|---|---|---|
| .text | 0x1000 | 110,592 | 110,080 | 6.47 |
| .data | 0x1c000 | 40,960 | 24,576 | 4.52 |
| .tls | 0x26000 | 4,096 | 512 | 0.0 |
| .idata | 0x27000 | 4,096 | 2,048 | 4.76 |
| .edata | 0x28000 | 4,096 | 512 | 4.87 |
| .rsrc | 0x29000 | 8,192 | 5,632 | 1.74 |
| .reloc | 0x2b000 | 8,192 | 6,144 | 6.44 |

## 导入表

### KERNEL32.DLL (70 函数)

- `BuildCommDCBA`
- `ClearCommError`
- `CloseHandle`
- `CreateFileA`
- `CreateMailslotA`
- `CreateThread`
- `DeleteCriticalSection`
- `DeleteFileA`
- `EnterCriticalSection`
- `EscapeCommFunction`
- `ExitProcess`
- `ExitThread`
- `FreeEnvironmentStringsA`
- `GetACP`
- `GetCPInfo`
- `GetCurrentProcessId`
- `GetCurrentThreadId`
- `GetEnvironmentStrings`
- `GetFileAttributesA`
- `GetFileType`
- `GetLastError`
- `GetLocalTime`
- `GetLocaleInfoA`
- `GetMailslotInfo`
- `GetModuleFileNameA`
- `GetModuleHandleA`
- `GetOEMCP`
- `GetProcAddress`
- `GetProcessHeap`
- `GetStartupInfoA`
- ... 其余 40 个

### USER32.DLL (3 函数)

- `EnumThreadWindows`
- `MessageBoxA`
- `wsprintfA`

### WINMM.DLL (1 函数)

- `timeGetTime`

## 导出表

| 名称 | Ordinal | RVA | 虚拟地址 |
|---|---|---|---|
| `___CPPdebugHook` | 18 | 0x1c0f8 | 0x41c0f8 |
| `civClose` | 5 | 0x3ec4 | 0x403ec4 |
| `civGetConType` | 17 | 0x4080 | 0x404080 |
| `civGetOthAnsCount` | 13 | 0x3ff8 | 0x403ff8 |
| `civGetRecvSize` | 7 | 0x3f18 | 0x403f18 |
| `civGetRxByteCount` | 15 | 0x4038 | 0x404038 |
| `civIsSendEnable` | 9 | 0x3f70 | 0x403f70 |
| `civOpen` | 1 | 0x3d1c | 0x403d1c |
| `civRecv` | 8 | 0x3f3c | 0x403f3c |
| `civResetOthAnsCount` | 12 | 0x3fdc | 0x403fdc |
| `civResetRxByteCount` | 14 | 0x401c | 0x40401c |
| `civSend` | 6 | 0x3eec | 0x403eec |
| `civSetAddPreamble` | 3 | 0x3e7c | 0x403e7c |
| `civSetAddress` | 2 | 0x3e44 | 0x403e44 |
| `civSetCivTot` | 4 | 0x3ea0 | 0x403ea0 |
| `civSetConType` | 16 | 0x405c | 0x40405c |
| `civSetRetryFA` | 10 | 0x3f94 | 0x403f94 |
| `civSetWaitTime` | 11 | 0x3fb8 | 0x403fb8 |

## 导出函数反汇编（前 20 条指令）

### `___CPPdebugHook` (RVA: 0x1c0f8)

```asm
  0x41c0f8:  add byte ptr [eax], al  ; 0000
  0x41c0fa:  add byte ptr [eax], al  ; 0000
  0x41c0fc:  add byte ptr [eax], al  ; 0000
  0x41c0fe:  add byte ptr [eax], al  ; 0000
  0x41c100:  add byte ptr [eax], al  ; 0000
  0x41c102:  add byte ptr [eax], al  ; 0000
  0x41c104:  add byte ptr [eax], al  ; 0000
  0x41c106:  add byte ptr [eax], al  ; 0000
  0x41c108:  add byte ptr [eax], al  ; 0000
  0x41c10a:  add byte ptr [eax], al  ; 0000
  0x41c10c:  add byte ptr [eax], al  ; 0000
  0x41c10e:  add byte ptr [eax], al  ; 0000
  0x41c110:  movsb byte ptr es:[edi], byte ptr [esi]  ; a4
  0x41c111:  adc al, 0x40  ; 1440
  0x41c113:  add byte ptr [edi], al  ; 0007
  0x41c115:  and byte ptr [eax], al  ; 2000
  0x41c117:  add ah, bh  ; 00fc
```

### `civClose` (RVA: 0x3ec4)

```asm
  0x403ec4:  push ebp  ; 55
  0x403ec5:  mov ebp, esp  ; 8bec
  0x403ec7:  push ebx  ; 53
  0x403ec8:  mov ebx, dword ptr [ebp + 8]  ; 8b5d08
  0x403ecb:  push ebx  ; 53
  0x403ecc:  call 0x404910  ; e83f0a0000
  0x403ed1:  pop ecx  ; 59
  0x403ed2:  test eax, eax  ; 85c0
  0x403ed4:  je 0x403ee4  ; 740e
  0x403ed6:  push eax  ; 50
  0x403ed7:  call 0x401e28  ; e84cdfffff
  0x403edc:  pop ecx  ; 59
  0x403edd:  push ebx  ; 53
  0x403ede:  call 0x40498c  ; e8a90a0000
  0x403ee3:  pop ecx  ; 59
  0x403ee4:  pop ebx  ; 5b
  0x403ee5:  pop ebp  ; 5d
  0x403ee6:  ret 4  ; c20400
  0x403ee9:  nop  ; 90
  0x403eea:  nop  ; 90
```

### `civGetConType` (RVA: 0x4080)

```asm
  0x404080:  push ebp  ; 55
  0x404081:  mov ebp, esp  ; 8bec
  0x404083:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x404086:  push eax  ; 50
  0x404087:  call 0x404910  ; e884080000
  0x40408c:  pop ecx  ; 59
  0x40408d:  test eax, eax  ; 85c0
  0x40408f:  je 0x40409a  ; 7409
  0x404091:  push eax  ; 50
  0x404092:  call 0x401c0c  ; e875dbffff
  0x404097:  pop ecx  ; 59
  0x404098:  jmp 0x40409c  ; eb02
  0x40409a:  xor eax, eax  ; 33c0
  0x40409c:  pop ebp  ; 5d
  0x40409d:  ret 4  ; c20400
  0x4040a0:  push ebp  ; 55
  0x4040a1:  mov ebp, esp  ; 8bec
  0x4040a3:  add esp, 0xffffff74  ; 81c474ffffff
  0x4040a9:  push ebx  ; 53
  0x4040aa:  push esi  ; 56
```

### `civGetOthAnsCount` (RVA: 0x3ff8)

```asm
  0x403ff8:  push ebp  ; 55
  0x403ff9:  mov ebp, esp  ; 8bec
  0x403ffb:  push ebx  ; 53
  0x403ffc:  xor ebx, ebx  ; 33db
  0x403ffe:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x404001:  push eax  ; 50
  0x404002:  call 0x404910  ; e809090000
  0x404007:  pop ecx  ; 59
  0x404008:  test eax, eax  ; 85c0
  0x40400a:  je 0x404015  ; 7409
  0x40400c:  push eax  ; 50
  0x40400d:  call 0x401b50  ; e83edbffff
  0x404012:  pop ecx  ; 59
  0x404013:  mov ebx, eax  ; 8bd8
  0x404015:  mov eax, ebx  ; 8bc3
  0x404017:  pop ebx  ; 5b
  0x404018:  pop ebp  ; 5d
  0x404019:  ret 4  ; c20400
  0x40401c:  push ebp  ; 55
  0x40401d:  mov ebp, esp  ; 8bec
```

### `civGetRecvSize` (RVA: 0x3f18)

```asm
  0x403f18:  push ebp  ; 55
  0x403f19:  mov ebp, esp  ; 8bec
  0x403f1b:  push ebx  ; 53
  0x403f1c:  xor ebx, ebx  ; 33db
  0x403f1e:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x403f21:  push eax  ; 50
  0x403f22:  call 0x404910  ; e8e9090000
  0x403f27:  pop ecx  ; 59
  0x403f28:  test eax, eax  ; 85c0
  0x403f2a:  je 0x403f35  ; 7409
  0x403f2c:  push eax  ; 50
  0x403f2d:  call 0x4025ec  ; e8bae6ffff
  0x403f32:  pop ecx  ; 59
  0x403f33:  mov ebx, eax  ; 8bd8
  0x403f35:  mov eax, ebx  ; 8bc3
  0x403f37:  pop ebx  ; 5b
  0x403f38:  pop ebp  ; 5d
  0x403f39:  ret 4  ; c20400
  0x403f3c:  push ebp  ; 55
  0x403f3d:  mov ebp, esp  ; 8bec
```

### `civGetRxByteCount` (RVA: 0x4038)

```asm
  0x404038:  push ebp  ; 55
  0x404039:  mov ebp, esp  ; 8bec
  0x40403b:  push ebx  ; 53
  0x40403c:  xor ebx, ebx  ; 33db
  0x40403e:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x404041:  push eax  ; 50
  0x404042:  call 0x404910  ; e8c9080000
  0x404047:  pop ecx  ; 59
  0x404048:  test eax, eax  ; 85c0
  0x40404a:  je 0x404055  ; 7409
  0x40404c:  push eax  ; 50
  0x40404d:  call 0x401bc4  ; e872dbffff
  0x404052:  pop ecx  ; 59
  0x404053:  mov ebx, eax  ; 8bd8
  0x404055:  mov eax, ebx  ; 8bc3
  0x404057:  pop ebx  ; 5b
  0x404058:  pop ebp  ; 5d
  0x404059:  ret 4  ; c20400
  0x40405c:  push ebp  ; 55
  0x40405d:  mov ebp, esp  ; 8bec
```

### `civIsSendEnable` (RVA: 0x3f70)

```asm
  0x403f70:  push ebp  ; 55
  0x403f71:  mov ebp, esp  ; 8bec
  0x403f73:  push ebx  ; 53
  0x403f74:  xor ebx, ebx  ; 33db
  0x403f76:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x403f79:  push eax  ; 50
  0x403f7a:  call 0x404910  ; e891090000
  0x403f7f:  pop ecx  ; 59
  0x403f80:  test eax, eax  ; 85c0
  0x403f82:  je 0x403f8d  ; 7409
  0x403f84:  push eax  ; 50
  0x403f85:  call 0x401aa0  ; e816dbffff
  0x403f8a:  pop ecx  ; 59
  0x403f8b:  mov ebx, eax  ; 8bd8
  0x403f8d:  mov eax, ebx  ; 8bc3
  0x403f8f:  pop ebx  ; 5b
  0x403f90:  pop ebp  ; 5d
  0x403f91:  ret 4  ; c20400
  0x403f94:  push ebp  ; 55
  0x403f95:  mov ebp, esp  ; 8bec
```

### `civOpen` (RVA: 0x3d1c)

```asm
  0x403d1c:  push ebp  ; 55
  0x403d1d:  mov ebp, esp  ; 8bec
  0x403d1f:  add esp, -0x30  ; 83c4d0
  0x403d22:  mov eax, 0x41cd08  ; b808cd4100
  0x403d27:  push ebx  ; 53
  0x403d28:  push esi  ; 56
  0x403d29:  push edi  ; 57
  0x403d2a:  mov edi, dword ptr [ebp + 8]  ; 8b7d08
  0x403d2d:  call 0x411010  ; e8ded20000
  0x403d32:  xor esi, esi  ; 33f6
  0x403d34:  push 0xac9  ; 68c90a0000
  0x403d39:  call 0x40c2fc  ; e8be850000
  0x403d3e:  pop ecx  ; 59
  0x403d3f:  mov dword ptr [ebp - 4], eax  ; 8945fc
  0x403d42:  test eax, eax  ; 85c0
  0x403d44:  je 0x403d64  ; 741e
  0x403d46:  mov word ptr [ebp - 0x20], 0x18  ; 66c745e01800
  0x403d4c:  push edi  ; 57
  0x403d4d:  mov edx, dword ptr [ebp - 4]  ; 8b55fc
  0x403d50:  push edx  ; 52
```

### `civRecv` (RVA: 0x3f3c)

```asm
  0x403f3c:  push ebp  ; 55
  0x403f3d:  mov ebp, esp  ; 8bec
  0x403f3f:  push ebx  ; 53
  0x403f40:  xor ebx, ebx  ; 33db
  0x403f42:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x403f45:  push eax  ; 50
  0x403f46:  call 0x404910  ; e8c5090000
  0x403f4b:  pop ecx  ; 59
  0x403f4c:  test eax, eax  ; 85c0
  0x403f4e:  je 0x403f67  ; 7417
  0x403f50:  mov edx, dword ptr [ebp + 0x14]  ; 8b5514
  0x403f53:  push edx  ; 52
  0x403f54:  mov ecx, dword ptr [ebp + 0x10]  ; 8b4d10
  0x403f57:  push ecx  ; 51
  0x403f58:  mov edx, dword ptr [ebp + 0xc]  ; 8b550c
  0x403f5b:  push edx  ; 52
  0x403f5c:  push eax  ; 50
  0x403f5d:  call 0x402624  ; e8c2e6ffff
  0x403f62:  add esp, 0x10  ; 83c410
  0x403f65:  mov ebx, eax  ; 8bd8
```

### `civResetOthAnsCount` (RVA: 0x3fdc)

```asm
  0x403fdc:  push ebp  ; 55
  0x403fdd:  mov ebp, esp  ; 8bec
  0x403fdf:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x403fe2:  push eax  ; 50
  0x403fe3:  call 0x404910  ; e828090000
  0x403fe8:  pop ecx  ; 59
  0x403fe9:  test eax, eax  ; 85c0
  0x403feb:  je 0x403ff4  ; 7407
  0x403fed:  push eax  ; 50
  0x403fee:  call 0x401b40  ; e84ddbffff
  0x403ff3:  pop ecx  ; 59
  0x403ff4:  pop ebp  ; 5d
  0x403ff5:  ret 4  ; c20400
  0x403ff8:  push ebp  ; 55
  0x403ff9:  mov ebp, esp  ; 8bec
  0x403ffb:  push ebx  ; 53
  0x403ffc:  xor ebx, ebx  ; 33db
  0x403ffe:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x404001:  push eax  ; 50
  0x404002:  call 0x404910  ; e809090000
```


> 其余 8 个函数的反汇编见 JSON 输出

## 字符串分类

### ci_v_commands (57 条)

- `CIVTrace *`
- `CIVTrace *[2]`
- `CIVTrace`
- `CIVDriver *`
- `CIVTxRx *[2]`
- `CIVTxRx *`
- `CIVTxRx`
- `CIVDriver`
- `CIVDriver *[2]`
- `CIVDriver::CIVDriver()`
- `\\.\mailslot\civsend`
- `\\.\mailslot\civrecv`
- `CIVDriver::~CIVDriver()`
- `CIVDriver::civOpen()`
- `CIVDriver::civClose()`
- `CIVDriver::civReset()`
- `CIVDriver::civSend()`
- `CIVDriver::civSendRetry()`
- `CIVDriver::civSendSub()`
- `CIVDriver::civRecv`
- `CIVDriver::civCtrlBranch()`
- `recv transceive`
- `CIVDriver::civAnalyze()`
- `civAnalyze status = %d, LenTx = %d, LenRx = %d`
- `  ANSWER CIV -> error`
- `CIVDriver::civAnsBranch()`
- `civAnsBranch`
- `CIVDriver::AddRecvData`
- `  Status = JAM CIVTOT -> error`
- `  Status = JAM CIVJAM.timeout`
- `  ECHO CIVTOT Timeout -> error`
- `  ANSWER CIVTOT Timeout -> error`
- `CIVDriver::civRetry()`
- `CIVDriver::civRetryImmediately()`
- `CIVDriver::civError()`
- `CIVDriver::SendRecvThread`
- `Broken pipe`
- `CivCtrl.dll`
- `civClose`
- `civGetConType`
- `civGetOthAnsCount`
- `civGetRecvSize`
- `civGetRxByteCount`
- `civIsSendEnable`
- `civOpen`
- `civRecv`
- `civResetOthAnsCount`
- `civResetRxByteCount`
- `civSend`
- `civSetAddPreamble`
- ... 其余 7 条

### serial_port (15 条)

- `CComBuf *`
- `CComBuf`
- `\\.\COM%d`
- `baud=%d parity=N data=8 stop=1`
- `No space for copy of command line`
- `dtrCount <= vdtCount`
- `BuildCommDCBA`
- `ClearCommError`
- `EscapeCommFunction`
- `SetCommState`
- `SetCommTimeouts`
- `CompanyName`
- `Icom Inc.`
- `(C) 2010-2018 Icom Inc.`
- `Comments`

### network (1 条)

- `GetCPInfo`

### file_paths (47 条)

- `;K\w`
- `;S\v`
- `C\[]`
- `Nt/NtB`
- `Nt/Nt?`
- `u/j_V`
- `K@Qj/W`
- `C\Pj6W`
- `9\u.f`
- `%\rB`
- `Inappropriate I/O control operation`
- `Input/output error`
- ` !"#$%&'()*+,-./0123456789:;<=>?@abcdefghijklmnopqrstuvwxyz[\]^_`abcdefghijklmnopqrstuvwxyz{|}~`
- ` !"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`ABCDEFGHIJKLMNOPQRSTUVWXYZ{|}~`
- `%m/%d/%y`
- `%02d/%02d/%04d %02d:%02d:%02d.%03d `
- `=/>E>`
- `0 0&0,02080>0D0J0P0V0\0b0h0n0t0z0`
- `>/>?>`>`
- `;/;o;`
- `4/5<5o5z5`
- `1W2\2}2`
- `165F5K5\5d5s5`
- `?3?>?R?\?`
- `8S9\9`
- `5\6u6z6`
- `7\8a8`
- `9#9'9+9/939o9z9<:`
- `6@6L6X6\6h6x6`
- `7(7L7X7\7l7`
- `8$8(888\8h8l8|8`
- `>(>,>8><>@>D>H>L>P>T>X>\>h>l>p>|>`
- `? ?$?(?,?0?4?8?<?@?D?\8t8`
- `9$90949X9\9`
- `6 6,60646@6D6H6T6\6h6t6`
- `101<1H1L1P1\1`1d1p1t1|1`
- `1$2(24282D2L2\2h2l2p2`
- `>$>0>8>\>`>`
- `; ;,;D;\;t;`
- `=(=L=X=\=l=|=`
- `9,9P9\9`9`
- `3 3<3H3L3P3\3d3x3`
- `0$0(0,0004080<0@0D0H0L0P0T0X0\0`0l0x0|0`
- `1<1H1L1\1`
- `> >$>(>,>0>D>H>L>P>T>X>\>`>d>h>l>p>t>x>|>`
- `3 3$3(3,3034383<3@3D3H3L3P3T3X3\3`3d3h3l3p3t3(:,:0:4:8:<:@:D:H:L:`
- `,0004080<0@0D0H0L0P0T0X0\0`0d0h0x1|1`

### audio (6 条)

- `std::codecvt<char,char,int> *`
- `std::codecvt_base *`
- `std::codecvt_base`
- `std::codecvt<char,char,int>`
- `std::codecvt<wchar_t,char,int> *`
- `std::codecvt<wchar_t,char,int>`

### error_msgs (28 条)

- `std::length_error`
- `std::length_error *`
- `std::logic_error *`
- `std::logic_error`
- `std::ios_base::failure`
- `std::ios_base::failure *`
- `std::runtime_error *`
- `std::runtime_error`
- `Cannot run multiple instances of a DLL under WIN32s`
- `ios_base::failbit set`
- `invalid string position`
- `hrdir_b.c: LoadLibrary != mmdll borlndmm failed`
- `Error 0`
- `Invalid function number`
- `Path not found`
- `Invalid memory block address`
- `Invalid environment`
- `Invalid format`
- `Invalid access code`
- `Invalid data`
- `Invalid argument`
- `Exec format error`
- `Unknown error`
- `Error: system code page access failure; MBCS table not initialized`
- `Assertion failed: `
- `Semaphore error `
- `GetLastError`
- `SetLastError`

### format_strings (50 条)

- `%u8F3`
- `C$Pj%W`
- `D<"u%`
- `:"u%`
- `%lqB`
- `%pqB`
- `%tqB`
- `%xqB`
- `%|qB`
- `% rB`
- `%$rB`
- `%(rB`
- `%,rB`
- `%0rB`
- `%4rB`
- `%8rB`
- `%<rB`
- `%@rB`
- `%DrB`
- `%HrB`
- `%LrB`
- `%PrB`
- `%TrB`
- `%XrB`
- `%`rB`
- `%drB`
- `%hrB`
- `%lrB`
- `%prB`
- `%trB`
- `%xrB`
- `%|rB`
- `%s%d`
- ` size=%d`
- `ReadFile %02X`
- `< +++ Callback answer ret = %d`
- `%d:%02d:%02d.%03d`
- `%02X `
- `%+0I`
- `%+0M`
- `%+0S`
- `%+0H`
- `%+0d`
- `%+0m`
- `%+0y`
- `%H:%M:%S`
- `%A, %B %d, %Y`
- `An exception (%08X) occurred during DllEntryPoint or DllMain in module:`
- `5%6:6R6j6x6`
- `2(2%8>8`

### interesting (22 条)

- `send data...`
- `WriteFile SendSlot`
- `WriteFile--`
- `ReadFile RecvSlot`
- `WriteFile RecvSlot`
- `  Status = IDLE SendRetry!!`
- `ReadFile SendSlot`
- `___CPPdebugHook`
- `Too many open files`
- `Read-only file system`
- `File already exists`
- `creating thread data lock`
- `CloseHandle`
- `CreateFileA`
- `CreateMailslotA`
- `CreateThread`
- `ExitThread`
- `GetCurrentThreadId`
- `ReadFile`
- `SetThreadLocale`
- `WriteFile`
- `EnumThreadWindows`

## 资源段 (4 项)

| 类型 | 偏移 | 大小 |
|---|---|---|
| ICON/CURSOR/type_1041 | 0x29150 | 4264 |
| RCDATA/DVCLAL/type_0 | 0x2a1f8 | 16 |
| GROUP_ICON/MAINICON/type_1041 | 0x2a208 | 20 |
| VERSION/CURSOR/type_1033 | 0x2a21c | 712 |

## DLL 依赖

| 导入自 | 函数数 |
|---|---|
| KERNEL32.DLL | 70 |
| USER32.DLL | 3 |
| WINMM.DLL | 1 |

