# UtyCtrl.dll 静态分析报告

> 文件大小: 204,288 bytes | 机器: x86 | 类型: DLL | 入口: 0xe8e7 | ImageBase: 0x10000000
> 编译时间: 2018-06-19 05:35:08

---

## 区段

| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 熵值 |
|---|---|---|---|---|
| .text | 0x1000 | 123,569 | 123,904 | 6.59 |
| .rdata | 0x20000 | 30,071 | 30,208 | 5.14 |
| .data | 0x28000 | 23,000 | 8,192 | 4.01 |
| .rsrc | 0x2e000 | 13,028 | 13,312 | 4.48 |
| .reloc | 0x32000 | 27,330 | 27,648 | 2.77 |

## 导入表

### KERNEL32.dll (109 函数)

- `GetModuleHandleW`
- `GetCPInfo`
- `GetOEMCP`
- `GetCommandLineA`
- `HeapAlloc`
- `HeapFree`
- `RtlUnwind`
- `ExitProcess`
- `RaiseException`
- `HeapSize`
- `HeapReAlloc`
- `VirtualAlloc`
- `UnhandledExceptionFilter`
- `SetUnhandledExceptionFilter`
- `IsDebuggerPresent`
- `SetHandleCount`
- `GetStdHandle`
- `GetFileType`
- `GetStartupInfoA`
- `FreeEnvironmentStringsA`
- `GetEnvironmentStrings`
- `FreeEnvironmentStringsW`
- `GetEnvironmentStringsW`
- `HeapCreate`
- `HeapDestroy`
- `VirtualFree`
- `QueryPerformanceCounter`
- `GetTickCount`
- `GetSystemTimeAsFileTime`
- `InitializeCriticalSectionAndSpinCount`
- ... 其余 79 个

### SHLWAPI.dll (2 函数)

- `PathFindFileNameA`
- `PathFindExtensionA`

### OLEACC.dll (2 函数)

- `LresultFromObject`
- `CreateStdAccessibleObject`

### USER32.dll (88 函数)

- `DestroyMenu`
- `LoadCursorA`
- `GetSysColorBrush`
- `ShowWindow`
- `RegisterWindowMessageA`
- `LoadIconA`
- `WinHelpA`
- `GetCapture`
- `GetClassLongA`
- `SetPropA`
- `GetPropA`
- `RemovePropA`
- `IsWindow`
- `GetForegroundWindow`
- `GetDlgItem`
- `GetTopWindow`
- `DestroyWindow`
- `GetMessageTime`
- `GetMessagePos`
- `MapWindowPoints`
- `SetMenu`
- `SetForegroundWindow`
- `GetClientRect`
- `CreateWindowExA`
- `GetClassInfoA`
- `RegisterClassA`
- `AdjustWindowRectEx`
- `CopyRect`
- `DefWindowProcA`
- `CallWindowProcA`
- ... 其余 58 个

### GDI32.dll (23 函数)

- `SetTextColor`
- `DeleteDC`
- `GetStockObject`
- `GetDeviceCaps`
- `RestoreDC`
- `SetBkColor`
- `SaveDC`
- `ScaleViewportExtEx`
- `ScaleWindowExtEx`
- `SetWindowExtEx`
- `CreateBitmap`
- `SetViewportExtEx`
- `OffsetViewportOrgEx`
- `SetViewportOrgEx`
- `SelectObject`
- `Escape`
- `ExtTextOutA`
- `TextOutA`
- `RectVisible`
- `PtVisible`
- `DeleteObject`
- `GetClipBox`
- `SetMapMode`

### WINSPOOL.DRV (3 函数)

- `DocumentPropertiesA`
- `OpenPrinterA`
- `ClosePrinter`

### ADVAPI32.dll (9 函数)

- `RegSetValueExA`
- `RegCreateKeyExA`
- `RegQueryValueA`
- `RegOpenKeyA`
- `RegEnumKeyA`
- `RegDeleteKeyA`
- `RegOpenKeyExA`
- `RegQueryValueExA`
- `RegCloseKey`

### OLEAUT32.dll (3 函数)

- `VariantClear`
- `VariantChangeType`
- `VariantInit`

## 导出表

| 名称 | Ordinal | RVA | 虚拟地址 |
|---|---|---|---|
| `ExecCmd` | 1 | 0x16a0 | 0x100016a0 |
| `GetClientTransInfo` | 3 | 0x1240 | 0x10001240 |
| `GetClientTransInfo2` | 2 | 0x12c0 | 0x100012c0 |
| `GetClientTransVol` | 5 | 0x1370 | 0x10001370 |
| `GetClientTransVol3` | 4 | 0x1430 | 0x10001430 |
| `GetCommandProcCount` | 6 | 0x14e0 | 0x100014e0 |
| `GetCountClientTrans` | 7 | 0x11c0 | 0x100011c0 |
| `GetRemoteTransNetworkSet` | 8 | 0x1540 | 0x10001540 |
| `GetRemoteTransState` | 9 | 0x15f0 | 0x100015f0 |

## 导出函数反汇编（前 20 条指令）

### `ExecCmd` (RVA: 0x16a0)

```asm
  0x100016a0:  sub esp, 0x10c  ; 81ec0c010000
  0x100016a6:  mov eax, dword ptr [0x10028c70]  ; a1708c0210
  0x100016ab:  xor eax, esp  ; 33c4
  0x100016ad:  mov dword ptr [esp + 0x108], eax  ; 89842408010000
  0x100016b4:  mov eax, dword ptr [esp + 0x110]  ; 8b842410010000
  0x100016bb:  mov ecx, dword ptr [esp + 0x114]  ; 8b8c2414010000
  0x100016c2:  mov edx, dword ptr [esp + 0x118]  ; 8b942418010000
  0x100016c9:  push ebx  ; 53
  0x100016ca:  mov ebx, dword ptr [esp + 0x12c]  ; 8b9c242c010000
  0x100016d1:  push esi  ; 56
  0x100016d2:  mov esi, dword ptr [esp + 0x124]  ; 8bb42424010000
  0x100016d9:  push edi  ; 57
  0x100016da:  mov edi, dword ptr [esp + 0x130]  ; 8bbc2430010000
  0x100016e1:  push ebx  ; 53
  0x100016e2:  mov dword ptr [esp + 0x1c], ecx  ; 894c241c
  0x100016e6:  mov dword ptr [esp + 0x18], eax  ; 89442418
  0x100016ea:  mov al, byte ptr [esp + 0x130]  ; 8a842430010000
  0x100016f1:  lea ecx, [esp + 0x2c]  ; 8d4c242c
  0x100016f5:  push edi  ; 57
  0x100016f6:  push ecx  ; 51
```

### `GetClientTransInfo` (RVA: 0x1240)

```asm
  0x10001240:  sub esp, 0x108  ; 81ec08010000
  0x10001246:  mov eax, dword ptr [0x10028c70]  ; a1708c0210
  0x1000124b:  xor eax, esp  ; 33c4
  0x1000124d:  mov dword ptr [esp + 0x104], eax  ; 89842404010000
  0x10001254:  cmp dword ptr [0x1002c86c], 0  ; 833d6cc8021000
  0x1000125b:  mov eax, dword ptr [esp + 0x10c]  ; 8b84240c010000
  0x10001262:  push esi  ; 56
  0x10001263:  mov esi, 1  ; be01000000
  0x10001268:  push edi  ; 57
  0x10001269:  mov edi, dword ptr [esp + 0x118]  ; 8bbc2418010000
  0x10001270:  mov dword ptr [esp + 0xc], eax  ; 8944240c
  0x10001274:  mov byte ptr [esp + 8], 1  ; c644240801
  0x10001279:  mov byte ptr [esp + 9], 0x6c  ; c64424096c
  0x1000127e:  mov eax, esi  ; 8bc6
  0x10001280:  je 0x100012a6  ; 7424
  0x10001282:  lea ecx, [esp + 8]  ; 8d4c2408
  0x10001286:  push ecx  ; 51
  0x10001287:  call 0x10001080  ; e8f4fdffff
  0x1000128c:  test eax, eax  ; 85c0
  0x1000128e:  jne 0x100012a4  ; 7514
```

### `GetClientTransInfo2` (RVA: 0x12c0)

```asm
  0x100012c0:  sub esp, 0x108  ; 81ec08010000
  0x100012c6:  mov eax, dword ptr [0x10028c70]  ; a1708c0210
  0x100012cb:  xor eax, esp  ; 33c4
  0x100012cd:  mov dword ptr [esp + 0x104], eax  ; 89842404010000
  0x100012d4:  cmp dword ptr [0x1002c86c], 0  ; 833d6cc8021000
  0x100012db:  mov eax, dword ptr [esp + 0x10c]  ; 8b84240c010000
  0x100012e2:  mov ecx, dword ptr [esp + 0x110]  ; 8b8c2410010000
  0x100012e9:  mov edx, dword ptr [esp + 0x114]  ; 8b942414010000
  0x100012f0:  push ebp  ; 55
  0x100012f1:  push esi  ; 56
  0x100012f2:  mov esi, dword ptr [esp + 0x120]  ; 8bb42420010000
  0x100012f9:  push edi  ; 57
  0x100012fa:  mov edi, dword ptr [esp + 0x128]  ; 8bbc2428010000
  0x10001301:  mov ebp, 1  ; bd01000000
  0x10001306:  mov byte ptr [esp + 0xc], 4  ; c644240c04
  0x1000130b:  mov dword ptr [esp + 0x10], eax  ; 89442410
  0x1000130f:  mov dword ptr [esp + 0x14], ecx  ; 894c2414
  0x10001313:  mov dword ptr [esp + 0x18], edx  ; 89542418
  0x10001317:  mov dword ptr [esp + 0x1c], esi  ; 8974241c
  0x1000131b:  mov byte ptr [esp + 0xd], 0x78  ; c644240d78
```

### `GetClientTransVol` (RVA: 0x1370)

```asm
  0x10001370:  sub esp, 0x108  ; 81ec08010000
  0x10001376:  mov eax, dword ptr [0x10028c70]  ; a1708c0210
  0x1000137b:  xor eax, esp  ; 33c4
  0x1000137d:  mov dword ptr [esp + 0x104], eax  ; 89842404010000
  0x10001384:  cmp dword ptr [0x1002c86c], 0  ; 833d6cc8021000
  0x1000138b:  mov eax, dword ptr [esp + 0x10c]  ; 8b84240c010000
  0x10001392:  mov ecx, dword ptr [esp + 0x110]  ; 8b8c2410010000
  0x10001399:  mov edx, dword ptr [esp + 0x114]  ; 8b942414010000
  0x100013a0:  push ebp  ; 55
  0x100013a1:  push esi  ; 56
  0x100013a2:  mov esi, dword ptr [esp + 0x124]  ; 8bb42424010000
  0x100013a9:  push edi  ; 57
  0x100013aa:  mov edi, dword ptr [esp + 0x124]  ; 8bbc2424010000
  0x100013b1:  mov ebp, 1  ; bd01000000
  0x100013b6:  mov byte ptr [esp + 0xc], 3  ; c644240c03
  0x100013bb:  mov dword ptr [esp + 0x10], eax  ; 89442410
  0x100013bf:  mov dword ptr [esp + 0x14], ecx  ; 894c2414
  0x100013c3:  mov dword ptr [esp + 0x18], edx  ; 89542418
  0x100013c7:  mov dword ptr [esp + 0x1c], edi  ; 897c241c
  0x100013cb:  mov byte ptr [esp + 0xd], 0x24  ; c644240d24
```

### `GetClientTransVol3` (RVA: 0x1430)

```asm
  0x10001430:  sub esp, 0x108  ; 81ec08010000
  0x10001436:  mov eax, dword ptr [0x10028c70]  ; a1708c0210
  0x1000143b:  xor eax, esp  ; 33c4
  0x1000143d:  mov dword ptr [esp + 0x104], eax  ; 89842404010000
  0x10001444:  cmp dword ptr [0x1002c86c], 0  ; 833d6cc8021000
  0x1000144b:  mov eax, dword ptr [esp + 0x10c]  ; 8b84240c010000
  0x10001452:  mov ecx, dword ptr [esp + 0x110]  ; 8b8c2410010000
  0x10001459:  mov edx, dword ptr [esp + 0x114]  ; 8b942414010000
  0x10001460:  push ebp  ; 55
  0x10001461:  push esi  ; 56
  0x10001462:  mov esi, dword ptr [esp + 0x120]  ; 8bb42420010000
  0x10001469:  push edi  ; 57
  0x1000146a:  mov edi, dword ptr [esp + 0x128]  ; 8bbc2428010000
  0x10001471:  mov ebp, 1  ; bd01000000
  0x10001476:  mov byte ptr [esp + 0xc], 5  ; c644240c05
  0x1000147b:  mov dword ptr [esp + 0x10], eax  ; 89442410
  0x1000147f:  mov dword ptr [esp + 0x14], ecx  ; 894c2414
  0x10001483:  mov dword ptr [esp + 0x18], edx  ; 89542418
  0x10001487:  mov dword ptr [esp + 0x1c], esi  ; 8974241c
  0x1000148b:  mov byte ptr [esp + 0xd], 0x3c  ; c644240d3c
```

### `GetCommandProcCount` (RVA: 0x14e0)

```asm
  0x100014e0:  sub esp, 0x108  ; 81ec08010000
  0x100014e6:  mov eax, dword ptr [0x10028c70]  ; a1708c0210
  0x100014eb:  xor eax, esp  ; 33c4
  0x100014ed:  mov dword ptr [esp + 0x104], eax  ; 89842404010000
  0x100014f4:  push esi  ; 56
  0x100014f5:  xor esi, esi  ; 33f6
  0x100014f7:  mov byte ptr [esp + 4], 6  ; c644240406
  0x100014fc:  mov byte ptr [esp + 5], 0  ; c644240500
  0x10001501:  cmp dword ptr [0x1002c86c], esi  ; 39356cc80210
  0x10001507:  je 0x10001525  ; 741c
  0x10001509:  lea eax, [esp + 4]  ; 8d442404
  0x1000150d:  push eax  ; 50
  0x1000150e:  lea eax, [esi + 1]  ; 8d4601
  0x10001511:  call 0x10001080  ; e86afbffff
  0x10001516:  test eax, eax  ; 85c0
  0x10001518:  jne 0x10001525  ; 750b
  0x1000151a:  cmp byte ptr [esp + 4], 6  ; 807c240406
  0x1000151f:  mov eax, dword ptr [esp + 8]  ; 8b442408
  0x10001523:  je 0x10001527  ; 7402
  0x10001525:  mov eax, esi  ; 8bc6
```

### `GetCountClientTrans` (RVA: 0x11c0)

```asm
  0x100011c0:  sub esp, 0x108  ; 81ec08010000
  0x100011c6:  mov eax, dword ptr [0x10028c70]  ; a1708c0210
  0x100011cb:  xor eax, esp  ; 33c4
  0x100011cd:  mov dword ptr [esp + 0x104], eax  ; 89842404010000
  0x100011d4:  push esi  ; 56
  0x100011d5:  xor esi, esi  ; 33f6
  0x100011d7:  mov byte ptr [esp + 4], 0  ; c644240400
  0x100011dc:  mov byte ptr [esp + 5], 0  ; c644240500
  0x100011e1:  cmp dword ptr [0x1002c86c], esi  ; 39356cc80210
  0x100011e7:  je 0x1000121f  ; 7436
  0x100011e9:  lea eax, [esp + 4]  ; 8d442404
  0x100011ed:  push eax  ; 50
  0x100011ee:  lea eax, [esi + 1]  ; 8d4601
  0x100011f1:  call 0x10001080  ; e88afeffff
  0x100011f6:  test eax, eax  ; 85c0
  0x100011f8:  jne 0x1000121f  ; 7525
  0x100011fa:  cmp byte ptr [esp + 4], al  ; 38442404
  0x100011fe:  jne 0x1000121f  ; 751f
  0x10001200:  mov eax, dword ptr [esp + 8]  ; 8b442408
  0x10001204:  mov dword ptr [0x1002c870], eax  ; a370c80210
```

### `GetRemoteTransNetworkSet` (RVA: 0x1540)

```asm
  0x10001540:  sub esp, 0x108  ; 81ec08010000
  0x10001546:  mov eax, dword ptr [0x10028c70]  ; a1708c0210
  0x1000154b:  xor eax, esp  ; 33c4
  0x1000154d:  mov dword ptr [esp + 0x104], eax  ; 89842404010000
  0x10001554:  cmp dword ptr [0x1002c86c], 0  ; 833d6cc8021000
  0x1000155b:  mov eax, dword ptr [esp + 0x10c]  ; 8b84240c010000
  0x10001562:  mov ecx, dword ptr [esp + 0x110]  ; 8b8c2410010000
  0x10001569:  mov edx, dword ptr [esp + 0x114]  ; 8b942414010000
  0x10001570:  push ebp  ; 55
  0x10001571:  push esi  ; 56
  0x10001572:  mov esi, dword ptr [esp + 0x120]  ; 8bb42420010000
  0x10001579:  push edi  ; 57
  0x1000157a:  mov edi, dword ptr [esp + 0x128]  ; 8bbc2428010000
  0x10001581:  mov ebp, 1  ; bd01000000
  0x10001586:  mov byte ptr [esp + 0xc], 7  ; c644240c07
  0x1000158b:  mov dword ptr [esp + 0x10], eax  ; 89442410
  0x1000158f:  mov dword ptr [esp + 0x14], ecx  ; 894c2414
  0x10001593:  mov dword ptr [esp + 0x18], edx  ; 89542418
  0x10001597:  mov dword ptr [esp + 0x1c], esi  ; 8974241c
  0x1000159b:  mov byte ptr [esp + 0xd], 0x40  ; c644240d40
```

### `GetRemoteTransState` (RVA: 0x15f0)

```asm
  0x100015f0:  sub esp, 0x108  ; 81ec08010000
  0x100015f6:  mov eax, dword ptr [0x10028c70]  ; a1708c0210
  0x100015fb:  xor eax, esp  ; 33c4
  0x100015fd:  mov dword ptr [esp + 0x104], eax  ; 89842404010000
  0x10001604:  cmp dword ptr [0x1002c86c], 0  ; 833d6cc8021000
  0x1000160b:  mov eax, dword ptr [esp + 0x10c]  ; 8b84240c010000
  0x10001612:  mov ecx, dword ptr [esp + 0x110]  ; 8b8c2410010000
  0x10001619:  mov edx, dword ptr [esp + 0x114]  ; 8b942414010000
  0x10001620:  push ebp  ; 55
  0x10001621:  push esi  ; 56
  0x10001622:  mov esi, dword ptr [esp + 0x120]  ; 8bb42420010000
  0x10001629:  push edi  ; 57
  0x1000162a:  mov edi, dword ptr [esp + 0x128]  ; 8bbc2428010000
  0x10001631:  mov ebp, 1  ; bd01000000
  0x10001636:  mov byte ptr [esp + 0xc], 8  ; c644240c08
  0x1000163b:  mov dword ptr [esp + 0x10], eax  ; 89442410
  0x1000163f:  mov dword ptr [esp + 0x14], ecx  ; 894c2414
  0x10001643:  mov dword ptr [esp + 0x18], edx  ; 89542418
  0x10001647:  mov dword ptr [esp + 0x1c], esi  ; 8974241c
  0x1000164b:  mov byte ptr [esp + 0xd], 0x1c  ; c644240d1c
```

## 字符串分类

### serial_port (22 条)

- `Software\Microsoft\Windows\CurrentVersion\Policies\Comdlg32`
- `comctl32.dll`
- `comdlg32.dll`
- `InitCommonControls`
- `InitCommonControlsEx`
- `commctrl_DragListMsg`
- `This indicates a bug in your application. It is most likely the result of calling an MSIL-compiled (/clr) function from a native constructor or from DllMain.`
- ` Complete Object Locator'`
- `Icom RemoteUtyCtrl`
- `CompareStringA`
- `GetCommandLineA`
- `GetCommandProcCount`
- `.?AVCComCtlWrapper@@`
- `.?AVCCommDlgWrapper@@`
- `.?AV?$CMFCComObject@VCAccessibleProxy@ATL@@@@`
- `.?AV?$CComObjectRootEx@VCComSingleThreadModel@ATL@@@ATL@@`
- `.?AVCComObjectRootBase@ATL@@`
- `<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">`
- `  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">`
- `CompanyName`
- `Icom Inc.`
- `(C) 2010-2018 Icom Inc.`

### network (12 条)

- `NoNetConnectDisconnect`
- `CNotSupportedException`
- `Please contact the application's support team for more information.`
- `- floating point support not loaded`
- `GetCPInfo`
- `GetConsoleOutputCP`
- `SetViewportOrgEx`
- `OffsetViewportOrgEx`
- `SetViewportExtEx`
- `ScaleViewportExtEx`
- `.PAVCNotSupportedException@@`
- `.?AVCNotSupportedException@@`

### file_paths (98 条)

- `Qh\R`
- `>,r/`
- `Q\_^]`
- `S\_^[]`
- `u/9F`
- `8"u/`
- `j,h(\`
- `t/9U`
- `Software\Microsoft\Windows\CurrentVersion\Policies\Explorer`
- `Software\Microsoft\Windows\CurrentVersion\Policies\Network`
- `f:\dd\vctools\vc7libs\ship\atlmfc\src\mfc\appcore.cpp`
- `Software\Classes\`
- `Software\`
- `f:\dd\vctools\vc7libs\ship\atlmfc\include\afxwin1.inl`
- `f:\dd\vctools\vc7libs\ship\atlmfc\include\afxwin2.inl`
- `f:\dd\vctools\vc7libs\ship\atlmfc\src\mfc\auxdata.cpp`
- `%2\CLSID`
- `%2\Insertable`
- `%2\protocol\StdFileEditing\verb\0`
- `%2\protocol\StdFileEditing\server`
- `CLSID\%1`
- `CLSID\%1\ProgID`
- `CLSID\%1\InprocHandler32`
- `CLSID\%1\LocalServer32`
- `CLSID\%1\Verb\0`
- `CLSID\%1\Verb\1`
- `CLSID\%1\Insertable`
- `CLSID\%1\AuxUserType\2`
- `CLSID\%1\AuxUserType\3`
- `CLSID\%1\DefaultIcon`
- `CLSID\%1\MiscStatus`
- `CLSID\%1\InProcServer32`
- `CLSID\%1\DocObject`
- `%2\DocObject`
- `CLSID\%1\Printable`
- `CLSID\%1\DefaultExtension`
- `- not enough space for _onexit/atexit table`
- ` !"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~`
- ` !"#$%&'()*+,-./0123456789:;<=>?@abcdefghijklmnopqrstuvwxyz[\]^_`abcdefghijklmnopqrstuvwxyz{|}~`
- ` !"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`ABCDEFGHIJKLMNOPQRSTUVWXYZ{|}~`
- `MM/dd/yy`
- `\\.\mailslot\RemoteUtyCtrlCmd`
- `\\.\mailslot\RemoteUtyCtrlRes`
- `C:\Release\dll\UtyCtrl\Release\UtyCtrl.pdb`
- `?/L[`
- `0n0\O`
- `\(un0_0`
- `n0+g>\`
- `        <requestedExecutionLevel level="asInvoker" uiAccess="false"></requestedExecutionLevel>`
- `      </requestedPrivileges>`
- ... 其余 48 条

### error_msgs (14 条)

- `!This program cannot be run in DOS mode.`
- `CInvalidArgException`
- `runtime error `
- `TLOSS error`
- `SING error`
- `DOMAIN error`
- `- unexpected heap error`
- `- unexpected multithread lock error`
- `Runtime Error!`
- `SetLastError`
- `GetLastError`
- `SetErrorMode`
- `.PAVCInvalidArgException@@`
- `.?AVCInvalidArgException@@`

### format_strings (24 条)

- `u%8D$`
- `t%HHt`
- `~%9M`
- `%s%s.dll`
- `%s (%s:%d)`
- `%3,%7`
- `%9, %8`
- `zc%C1`
- `0%0*010f0p0u0`
- `2 2%2i2v2~2`
- `;%<-<q<`
- `2%373Q3`
- `6%6;6k8Y:`
- `0%0B0`
- `2%3-3B3M3]5K6S6Y6b6i6u6{6`
- `5%51575G5M5b5p5{5`
- `6 6%646J6U6Z6e6j6u6z6`
- `6 6%646=6J6U6g6z6`
- `=%>7>`
- `3%4D4`
- `7%737H7R7x7`
- `?%?1?=?I?W?b?i?o?u?y?`
- `%1: %2`
- `: %1`

### interesting (38 条)

- `CreateActCtxA`
- `NoClose`
- `CWinThread`
- `CreateActCtxW`
- `NotifyWinEvent`
- `&Open,0,2`
- `- unable to open console device`
- `- not enough space for thread data`
- ``local static thread guard'`
- `CreateMutexA`
- `ReleaseMutex`
- `CloseHandle`
- `CreateFileA`
- `CreateMailslotA`
- `WriteFile`
- `ReadFile`
- `CreateStdAccessibleObject`
- `GetCurrentThreadId`
- `GetCurrentThread`
- `WritePrivateProfileStringA`
- `IsDebuggerPresent`
- `HeapCreate`
- `WriteConsoleA`
- `WriteConsoleW`
- `SendMessageA`
- `GetWindowThreadProcessId`
- `CreateWindowExA`
- `CreateBitmap`
- `ClosePrinter`
- `OpenPrinterA`
- `RegCloseKey`
- `RegOpenKeyExA`
- `RegOpenKeyA`
- `RegCreateKeyExA`
- `.?AV_AFX_THREAD_STATE@@`
- `.?AVAFX_MODULE_THREAD_STATE@@`
- `.?AUCThreadData@@`
- `.?AVCWinThread@@`

## 资源段 (50 项)

| 类型 | 偏移 | 大小 |
|---|---|---|
| CURSOR/CURSOR/type_1041 | 0x2ea18 | 308 |
| CURSOR/BITMAP/type_1041 | 0x2eb4c | 180 |
| CURSOR/ICON/type_1041 | 0x2ec00 | 308 |
| CURSOR/MENU/type_1041 | 0x2ed34 | 308 |
| CURSOR/DIALOG/type_1041 | 0x2ee68 | 308 |
| CURSOR/STRING/type_1041 | 0x2ef9c | 308 |
| CURSOR/FONTDIR/type_1041 | 0x2f0d0 | 308 |
| CURSOR/FONT/type_1041 | 0x2f204 | 308 |
| CURSOR/ACCELERATOR/type_1041 | 0x2f338 | 308 |
| CURSOR/RCDATA/type_1041 | 0x2f46c | 308 |
| CURSOR/MESSAGETABLE/type_1041 | 0x2f5a0 | 308 |
| CURSOR/GROUP_CURSOR/type_1041 | 0x2f6d4 | 308 |
| CURSOR/type_13/type_1041 | 0x2f808 | 308 |
| CURSOR/GROUP_ICON/type_1041 | 0x2f93c | 308 |
| CURSOR/type_15/type_1041 | 0x2fa70 | 308 |
| CURSOR/VERSION/type_1041 | 0x2fba4 | 308 |
| BITMAP/type_30994/type_1041 | 0x2fcd8 | 184 |
| BITMAP/type_30996/type_1041 | 0x2fd90 | 324 |
| DIALOG/type_30721/type_1041 | 0x2fed4 | 232 |
| DIALOG/type_30734/type_1041 | 0x2ffbc | 52 |
| STRING/type_3841/type_1041 | 0x2fff0 | 98 |
| STRING/type_3842/type_1041 | 0x30054 | 46 |
| STRING/type_3843/type_1041 | 0x30084 | 226 |
| STRING/type_3857/type_1041 | 0x30168 | 850 |
| STRING/type_3858/type_1041 | 0x304bc | 446 |
| STRING/type_3859/type_1041 | 0x3067c | 398 |
| STRING/type_3860/type_1041 | 0x3080c | 104 |
| STRING/type_3865/type_1041 | 0x30874 | 118 |
| STRING/type_3866/type_1041 | 0x308ec | 142 |
| STRING/type_3867/type_1041 | 0x3097c | 740 |

> 其余 20 项

## DLL 依赖

| 导入自 | 函数数 |
|---|---|
| KERNEL32.dll | 109 |
| SHLWAPI.dll | 2 |
| OLEACC.dll | 2 |
| USER32.dll | 88 |
| GDI32.dll | 23 |
| WINSPOOL.DRV | 3 |
| ADVAPI32.dll | 9 |
| OLEAUT32.dll | 3 |

