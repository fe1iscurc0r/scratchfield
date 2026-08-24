# HidCtrl.dll 静态分析报告

> 文件大小: 16,896 bytes | 机器: x86 | 类型: DLL | 入口: 0x1ffb | ImageBase: 0x10000000
> 编译时间: 2012-05-17 12:10:05

---

## 区段

| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 熵值 |
|---|---|---|---|---|
| .text | 0x1000 | 9,106 | 9,216 | 6.32 |
| .rdata | 0x4000 | 2,521 | 2,560 | 5.03 |
| .data | 0x5000 | 1,656 | 1,024 | 5.83 |
| .rsrc | 0x6000 | 1,068 | 1,536 | 4.63 |
| .reloc | 0x7000 | 1,110 | 1,536 | 2.77 |

## 导入表

### KERNEL32.dll (23 函数)

- `CancelIo`
- `CloseHandle`
- `GetLastError`
- `GetCurrentThreadId`
- `GetTickCount`
- `QueryPerformanceCounter`
- `GetOverlappedResult`
- `ReadFile`
- `CreateEventA`
- `WriteFile`
- `WaitForSingleObject`
- `GetCurrentProcessId`
- `CreateFileA`
- `SetUnhandledExceptionFilter`
- `UnhandledExceptionFilter`
- `GetCurrentProcess`
- `TerminateProcess`
- `InterlockedCompareExchange`
- `Sleep`
- `InterlockedExchange`
- `RtlUnwind`
- `OutputDebugStringA`
- `GetSystemTimeAsFileTime`

### SETUPAPI.dll (4 函数)

- `SetupDiGetClassDevsA`
- `SetupDiGetDeviceInterfaceDetailA`
- `SetupDiEnumDeviceInterfaces`
- `SetupDiDestroyDeviceInfoList`

### HID.DLL (6 函数)

- `HidD_GetHidGuid`
- `HidD_GetSerialNumberString`
- `HidD_FreePreparsedData`
- `HidP_GetCaps`
- `HidD_FlushQueue`
- `HidD_GetPreparsedData`

### msvcrt.dll (23 函数)

- `memset`
- `memcpy`
- `_XcptFilter`
- `malloc`
- `_initterm`
- `_amsg_exit`
- `isleadbyte`
- `_iob`
- `_itoa`
- `wctomb`
- `__badioinfo`
- `__pioinfo`
- `_fileno`
- `_lseeki64`
- `_write`
- `_isatty`
- `_errno`
- `??2@YAPAXI@Z`
- `wcstombs`
- `??3@YAXPAX@Z`
- `_mbsstr`
- `_snprintf`
- `free`

## 导出表

| 名称 | Ordinal | RVA | 虚拟地址 |
|---|---|---|---|
| `HidDeviceClose` | 1 | 0x16e0 | 0x100016e0 |
| `HidDeviceConnect` | 2 | 0x1240 | 0x10001240 |
| `HidDeviceDisconnect` | 3 | 0x1660 | 0x10001660 |
| `HidDeviceGetSerialNumberString` | 4 | 0x1340 | 0x10001340 |
| `HidDeviceInitialize` | 5 | 0x1000 | 0x10001000 |
| `HidDeviceOpen` | 6 | 0x1050 | 0x10001050 |
| `HidDeviceReceive` | 7 | 0x13f0 | 0x100013f0 |
| `HidDeviceReceiveDataClear` | 8 | 0x1640 | 0x10001640 |
| `HidDeviceReconnect` | 9 | 0x1690 | 0x10001690 |
| `HidDeviceSend` | 10 | 0x1510 | 0x10001510 |

## 导出函数反汇编（前 20 条指令）

### `HidDeviceClose` (RVA: 0x16e0)

```asm
  0x100016e0:  ret  ; c3
  0x100016e1:  int3  ; cc
  0x100016e2:  int3  ; cc
  0x100016e3:  int3  ; cc
  0x100016e4:  int3  ; cc
  0x100016e5:  int3  ; cc
  0x100016e6:  int3  ; cc
  0x100016e7:  int3  ; cc
  0x100016e8:  int3  ; cc
  0x100016e9:  int3  ; cc
  0x100016ea:  int3  ; cc
  0x100016eb:  int3  ; cc
  0x100016ec:  int3  ; cc
  0x100016ed:  int3  ; cc
  0x100016ee:  int3  ; cc
  0x100016ef:  int3  ; cc
  0x100016f0:  push ebp  ; 55
  0x100016f1:  mov ebp, esp  ; 8bec
  0x100016f3:  mov eax, dword ptr [ebp + 0xc]  ; 8b450c
  0x100016f6:  cmp eax, 3  ; 83f803
```

### `HidDeviceConnect` (RVA: 0x1240)

```asm
  0x10001240:  push ebp  ; 55
  0x10001241:  mov ebp, esp  ; 8bec
  0x10001243:  and esp, 0xfffffff8  ; 83e4f8
  0x10001246:  sub esp, 0x54  ; 83ec54
  0x10001249:  mov eax, dword ptr [0x10005000]  ; a100500010
  0x1000124e:  xor eax, esp  ; 33c4
  0x10001250:  mov dword ptr [esp + 0x50], eax  ; 89442450
  0x10001254:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x10001257:  push ebx  ; 53
  0x10001258:  mov ebx, dword ptr [ebp + 0x14]  ; 8b5d14
  0x1000125b:  push esi  ; 56
  0x1000125c:  mov esi, dword ptr [ebp + 0xc]  ; 8b750c
  0x1000125f:  xor ecx, ecx  ; 33c9
  0x10001261:  push edi  ; 57
  0x10001262:  mov edi, dword ptr [ebp + 0x10]  ; 8b7d10
  0x10001265:  xor edx, edx  ; 33d2
  0x10001267:  mov word ptr [esi], cx  ; 66890e
  0x1000126a:  mov word ptr [edi], dx  ; 668917
  0x1000126d:  mov dword ptr [esp + 0x14], 1  ; c744241401000000
  0x10001275:  test eax, eax  ; 85c0
```

### `HidDeviceDisconnect` (RVA: 0x1660)

```asm
  0x10001660:  push ebp  ; 55
  0x10001661:  mov ebp, esp  ; 8bec
  0x10001663:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x10001666:  push esi  ; 56
  0x10001667:  mov esi, 1  ; be01000000
  0x1000166c:  test eax, eax  ; 85c0
  0x1000166e:  je 0x1000167c  ; 740c
  0x10001670:  push eax  ; 50
  0x10001671:  call dword ptr [0x10004020]  ; ff1520400010
  0x10001677:  mov eax, esi  ; 8bc6
  0x10001679:  pop esi  ; 5e
  0x1000167a:  pop ebp  ; 5d
  0x1000167b:  ret  ; c3
  0x1000167c:  xor eax, eax  ; 33c0
  0x1000167e:  pop esi  ; 5e
  0x1000167f:  pop ebp  ; 5d
  0x10001680:  ret  ; c3
  0x10001681:  int3  ; cc
  0x10001682:  int3  ; cc
  0x10001683:  int3  ; cc
```

### `HidDeviceGetSerialNumberString` (RVA: 0x1340)

```asm
  0x10001340:  push ebp  ; 55
  0x10001341:  mov ebp, esp  ; 8bec
  0x10001343:  sub esp, 0x64  ; 83ec64
  0x10001346:  mov eax, dword ptr [0x10005000]  ; a100500010
  0x1000134b:  xor eax, ebp  ; 33c5
  0x1000134d:  mov dword ptr [ebp - 4], eax  ; 8945fc
  0x10001350:  push ebx  ; 53
  0x10001351:  push esi  ; 56
  0x10001352:  mov esi, dword ptr [ebp + 8]  ; 8b7508
  0x10001355:  push edi  ; 57
  0x10001356:  mov edi, dword ptr [ebp + 0xc]  ; 8b7d0c
  0x10001359:  mov ebx, 1  ; bb01000000
  0x1000135e:  test esi, esi  ; 85f6
  0x10001360:  je 0x100013d1  ; 746f
  0x10001362:  push 0x40  ; 6a40
  0x10001364:  lea eax, [ebp - 0x64]  ; 8d459c
  0x10001367:  push 0  ; 6a00
  0x10001369:  push eax  ; 50
  0x1000136a:  call 0x10002196  ; e8270e0000
  0x1000136f:  add esp, 0xc  ; 83c40c
```

### `HidDeviceInitialize` (RVA: 0x1000)

```asm
  0x10001000:  push ebp  ; 55
  0x10001001:  mov ebp, esp  ; 8bec
  0x10001003:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x10001006:  push esi  ; 56
  0x10001007:  mov esi, 1  ; be01000000
  0x1000100c:  test eax, eax  ; 85c0
  0x1000100e:  je 0x1000104b  ; 743b
  0x10001010:  push 0x10005648  ; 6848560010
  0x10001015:  mov dword ptr [0x10005644], eax  ; a344560010
  0x1000101a:  call dword ptr [0x10004000]  ; ff1500400010
  0x10001020:  mov ecx, dword ptr [0x10005648]  ; 8b0d48560010
  0x10001026:  mov eax, dword ptr [ebp + 0xc]  ; 8b450c
  0x10001029:  mov dword ptr [eax], ecx  ; 8908
  0x1000102b:  mov edx, dword ptr [0x1000564c]  ; 8b154c560010
  0x10001031:  mov dword ptr [eax + 4], edx  ; 895004
  0x10001034:  mov ecx, dword ptr [0x10005650]  ; 8b0d50560010
  0x1000103a:  mov dword ptr [eax + 8], ecx  ; 894808
  0x1000103d:  mov edx, dword ptr [0x10005654]  ; 8b1554560010
  0x10001043:  mov dword ptr [eax + 0xc], edx  ; 89500c
  0x10001046:  mov eax, esi  ; 8bc6
```

### `HidDeviceOpen` (RVA: 0x1050)

```asm
  0x10001050:  push ebp  ; 55
  0x10001051:  mov ebp, esp  ; 8bec
  0x10001053:  sub esp, 0x624  ; 81ec24060000
  0x10001059:  mov eax, dword ptr [0x10005000]  ; a100500010
  0x1000105e:  xor eax, ebp  ; 33c5
  0x10001060:  mov dword ptr [ebp - 4], eax  ; 8945fc
  0x10001063:  mov eax, dword ptr [ebp + 0x10]  ; 8b4510
  0x10001066:  mov edx, dword ptr [ebp + 8]  ; 8b5508
  0x10001069:  push ebx  ; 53
  0x1000106a:  push esi  ; 56
  0x1000106b:  push edi  ; 57
  0x1000106c:  mov edi, dword ptr [ebp + 0xc]  ; 8b7d0c
  0x1000106f:  push edi  ; 57
  0x10001070:  push edx  ; 52
  0x10001071:  mov dword ptr [ebp - 0x620], eax  ; 8985e0f9ffff
  0x10001077:  xor eax, eax  ; 33c0
  0x10001079:  push 0x100041e4  ; 68e4410010
  0x1000107e:  mov dword ptr [ebp - 0x16], eax  ; 8945ea
  0x10001081:  mov dword ptr [ebp - 0x12], eax  ; 8945ee
  0x10001084:  mov dword ptr [ebp - 0xe], eax  ; 8945f2
```

### `HidDeviceReceive` (RVA: 0x13f0)

```asm
  0x100013f0:  push ebp  ; 55
  0x100013f1:  mov ebp, esp  ; 8bec
  0x100013f3:  sub esp, 0x18  ; 83ec18
  0x100013f6:  push ebx  ; 53
  0x100013f7:  mov ebx, dword ptr [ebp + 8]  ; 8b5d08
  0x100013fa:  mov dword ptr [ebp - 4], 0  ; c745fc00000000
  0x10001401:  test ebx, ebx  ; 85db
  0x10001403:  je 0x100014fc  ; 0f84f3000000
  0x10001409:  mov ax, word ptr [ebp + 0xc]  ; 668b450c
  0x1000140d:  xor ecx, ecx  ; 33c9
  0x1000140f:  cmp cx, ax  ; 663bc8
  0x10001412:  jae 0x100014fc  ; 0f83e4000000
  0x10001418:  push esi  ; 56
  0x10001419:  movzx esi, ax  ; 0fb7f0
  0x1000141c:  push edi  ; 57
  0x1000141d:  push esi  ; 56
  0x1000141e:  call dword ptr [0x100040d4]  ; ff15d4400010
  0x10001424:  push esi  ; 56
  0x10001425:  mov edi, eax  ; 8bf8
  0x10001427:  push 0  ; 6a00
```

### `HidDeviceReceiveDataClear` (RVA: 0x1640)

```asm
  0x10001640:  push ebp  ; 55
  0x10001641:  mov ebp, esp  ; 8bec
  0x10001643:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x10001646:  test eax, eax  ; 85c0
  0x10001648:  je 0x10001651  ; 7407
  0x1000164a:  push eax  ; 50
  0x1000164b:  call dword ptr [0x10004010]  ; ff1510400010
  0x10001651:  pop ebp  ; 5d
  0x10001652:  ret  ; c3
  0x10001653:  int3  ; cc
  0x10001654:  int3  ; cc
  0x10001655:  int3  ; cc
  0x10001656:  int3  ; cc
  0x10001657:  int3  ; cc
  0x10001658:  int3  ; cc
  0x10001659:  int3  ; cc
  0x1000165a:  int3  ; cc
  0x1000165b:  int3  ; cc
  0x1000165c:  int3  ; cc
  0x1000165d:  int3  ; cc
```

### `HidDeviceReconnect` (RVA: 0x1690)

```asm
  0x10001690:  push ebp  ; 55
  0x10001691:  mov ebp, esp  ; 8bec
  0x10001693:  push ebx  ; 53
  0x10001694:  push esi  ; 56
  0x10001695:  mov esi, dword ptr [ebp + 0xc]  ; 8b750c
  0x10001698:  mov ebx, 1  ; bb01000000
  0x1000169d:  test esi, esi  ; 85f6
  0x1000169f:  je 0x100016d7  ; 7436
  0x100016a1:  cmp byte ptr [esi], 0  ; 803e00
  0x100016a4:  je 0x100016d7  ; 7431
  0x100016a6:  push edi  ; 57
  0x100016a7:  mov edi, dword ptr [ebp + 8]  ; 8b7d08
  0x100016aa:  mov eax, dword ptr [edi]  ; 8b07
  0x100016ac:  test eax, eax  ; 85c0
  0x100016ae:  je 0x100016d0  ; 7420
  0x100016b0:  push eax  ; 50
  0x100016b1:  call dword ptr [0x10004020]  ; ff1520400010
  0x100016b7:  mov eax, dword ptr [ebp + 0x14]  ; 8b4514
  0x100016ba:  mov ecx, dword ptr [ebp + 0x10]  ; 8b4d10
  0x100016bd:  push edi  ; 57
```

### `HidDeviceSend` (RVA: 0x1510)

```asm
  0x10001510:  push ebp  ; 55
  0x10001511:  mov ebp, esp  ; 8bec
  0x10001513:  sub esp, 0x64  ; 83ec64
  0x10001516:  mov eax, dword ptr [0x10005000]  ; a100500010
  0x1000151b:  xor eax, ebp  ; 33c5
  0x1000151d:  mov dword ptr [ebp - 4], eax  ; 8945fc
  0x10001520:  push esi  ; 56
  0x10001521:  push edi  ; 57
  0x10001522:  mov edi, dword ptr [ebp + 8]  ; 8b7d08
  0x10001525:  mov dword ptr [ebp - 0x4c], 1  ; c745b401000000
  0x1000152c:  test edi, edi  ; 85ff
  0x1000152e:  je 0x10001621  ; 0f84ed000000
  0x10001534:  mov si, word ptr [ebp + 0xc]  ; 668b750c
  0x10001538:  xor eax, eax  ; 33c0
  0x1000153a:  cmp ax, si  ; 663bc6
  0x1000153d:  jae 0x10001621  ; 0f83de000000
  0x10001543:  push ebx  ; 53
  0x10001544:  mov ebx, dword ptr [ebp + 0x10]  ; 8b5d10
  0x10001547:  test ebx, ebx  ; 85db
  0x10001549:  je 0x1000160e  ; 0f84bf000000
```

## 字符串分类

### serial_port (8 条)

- `HidD_GetSerialNumberString`
- `InterlockedCompareExchange`
- `HidDeviceGetSerialNumberString`
- `<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">`
- `  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">`
- `CompanyName`
- `Icom Inc.`
- `(C) 2012 Icom Inc.`

### network (3 条)

- `HidDeviceConnect`
- `HidDeviceDisconnect`
- `HidDeviceReconnect`

### file_paths (10 条)

- `L$\_^[3`
- `C:\Release\dll\HidCtrl\Release\HidCtrl.pdb`
- `?/L[`
- `        <requestedExecutionLevel level="asInvoker" uiAccess="false"></requestedExecutionLevel>`
- `      </requestedPrivileges>`
- `    </security>`
- `  </trustInfo>`
- `</assembly>PAPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADD`
- `0#0)0/050;0B0I0P0W0^0e0l0t0|0`
- `0/141K1n1{1`

### error_msgs (3 条)

- `!This program cannot be run in DOS mode.`
- `Invalid parameter passed to C runtime function.`
- `GetLastError`

### format_strings (5 条)

- `YY}%;`
- `t%HHt`
- `vid_%04x&pid_%04x`
- `zc%C1`
- `=%=5=J=T=o=u=|=`

### interesting (11 条)

- `CreateFileA`
- `WriteFile`
- `CreateEventA`
- `ReadFile`
- `CloseHandle`
- `_write`
- `OutputDebugStringA`
- `GetCurrentThreadId`
- `HidDeviceClose`
- `HidDeviceOpen`
- `HidDeviceSend`

## 资源段 (2 项)

| 类型 | 偏移 | 大小 |
|---|---|---|
| VERSION/CURSOR/type_1041 | 0x60a0 | 560 |
| MANIFEST/BITMAP/type_1033 | 0x62d0 | 346 |

## DLL 依赖

| 导入自 | 函数数 |
|---|---|
| KERNEL32.dll | 23 |
| SETUPAPI.dll | 4 |
| HID.DLL | 6 |
| msvcrt.dll | 23 |

