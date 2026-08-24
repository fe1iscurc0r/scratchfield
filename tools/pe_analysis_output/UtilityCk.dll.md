# UtilityCk.dll 静态分析报告

> 文件大小: 201,728 bytes | 机器: x86 | 类型: DLL | 入口: 0xe1fa | ImageBase: 0x10000000
> 编译时间: 2017-07-19 11:34:25

---

## 区段

| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 熵值 |
|---|---|---|---|---|
| .text | 0x1000 | 121,771 | 121,856 | 6.61 |
| .rdata | 0x1f000 | 29,666 | 29,696 | 5.16 |
| .data | 0x27000 | 23,000 | 8,192 | 4.01 |
| .rsrc | 0x2d000 | 13,028 | 13,312 | 4.48 |
| .reloc | 0x31000 | 27,228 | 27,648 | 2.74 |

## 导入表

### SHLWAPI.dll (2 函数)

- `PathFindExtensionA`
- `PathFindFileNameA`

### OLEACC.dll (2 函数)

- `CreateStdAccessibleObject`
- `LresultFromObject`

### KERNEL32.dll (104 函数)

- `GetCPInfo`
- `GetOEMCP`
- `GetCommandLineA`
- `HeapAlloc`
- `HeapFree`
- `RtlUnwind`
- `Sleep`
- `ExitProcess`
- `RaiseException`
- `HeapSize`
- `HeapReAlloc`
- `VirtualAlloc`
- `TerminateProcess`
- `UnhandledExceptionFilter`
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
- ... 其余 74 个

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
- `GetClassInfoExA`
- `GetClassInfoA`
- `RegisterClassA`
- `AdjustWindowRectEx`
- `CopyRect`
- `DefWindowProcA`
- `CallWindowProcA`
- ... 其余 58 个

### GDI32.dll (23 函数)

- `DeleteDC`
- `GetDeviceCaps`
- `GetStockObject`
- `SetTextColor`
- `SetBkColor`
- `RestoreDC`
- `SaveDC`
- `CreateBitmap`
- `ScaleWindowExtEx`
- `SetWindowExtEx`
- `ScaleViewportExtEx`
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
| `Utility_GetKeyNum` | 1 | 0x1040 | 0x10001040 |

## 导出函数反汇编（前 20 条指令）

### `Utility_GetKeyNum` (RVA: 0x1040)

```asm
  0x10001040:  mov eax, dword ptr [esp + 4]  ; 8b442404
  0x10001044:  imul eax, eax  ; 0fafc0
  0x10001047:  add eax, 0x19f8  ; 05f8190000
  0x1000104c:  ret 4  ; c20400
  0x1000104f:  int3  ; cc
  0x10001050:  ret 4  ; c20400
  0x10001053:  int3  ; cc
  0x10001054:  int3  ; cc
  0x10001055:  int3  ; cc
  0x10001056:  int3  ; cc
  0x10001057:  int3  ; cc
  0x10001058:  int3  ; cc
  0x10001059:  int3  ; cc
  0x1000105a:  int3  ; cc
  0x1000105b:  int3  ; cc
  0x1000105c:  int3  ; cc
  0x1000105d:  int3  ; cc
  0x1000105e:  int3  ; cc
  0x1000105f:  int3  ; cc
  0x10001060:  mov eax, dword ptr [esp + 4]  ; 8b442404
```

## 字符串分类

### serial_port (20 条)

- `Software\Microsoft\Windows\CurrentVersion\Policies\Comdlg32`
- `comctl32.dll`
- `comdlg32.dll`
- `InitCommonControls`
- `InitCommonControlsEx`
- `commctrl_DragListMsg`
- `This indicates a bug in your application. It is most likely the result of calling an MSIL-compiled (/clr) function from a native constructor or from DllMain.`
- ` Complete Object Locator'`
- `CompareStringA`
- `GetCommandLineA`
- `.?AVCComCtlWrapper@@`
- `.?AVCCommDlgWrapper@@`
- `.?AV?$CMFCComObject@VCAccessibleProxy@ATL@@@@`
- `.?AV?$CComObjectRootEx@VCComSingleThreadModel@ATL@@@ATL@@`
- `.?AVCComObjectRootBase@ATL@@`
- `<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">`
- `  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">`
- `CompanyName`
- `Icom Inc.`
- `(C) 2017 Icom Inc.`

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

### file_paths (88 条)

- `>,r/`
- `Q\_^]`
- `S\_^[]`
- `u/9F`
- `8"u/`
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
- `C:\Release\UtilityCk\Release\UtilityCk.pdb`
- `?/L[`
- `0n0\O`
- `\(un0_0`
- `n0+g>\`
- `        <requestedExecutionLevel level="asInvoker" uiAccess="false"></requestedExecutionLevel>`
- `      </requestedPrivileges>`
- `    </security>`
- `  </trustInfo>`
- `</assembly>PAPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPADDINGPADDINGXXPAD`
- `=/=E=a=`
- ... 其余 38 条

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

### format_strings (11 条)

- `t%HHt`
- `~%9M`
- `%s%s.dll`
- `%s (%s:%d)`
- `%3,%7`
- `%9, %8`
- `zc%C1`
- `8%8@8`
- `: :%:5:d:r:`
- `%1: %2`
- `: %1`

### interesting (34 条)

- `CreateActCtxA`
- `NoClose`
- `CWinThread`
- `CreateActCtxW`
- `NotifyWinEvent`
- `&Open,0,2`
- `- unable to open console device`
- `- not enough space for thread data`
- ``local static thread guard'`
- `CreateStdAccessibleObject`
- `GetCurrentThreadId`
- `GetCurrentThread`
- `CloseHandle`
- `WritePrivateProfileStringA`
- `WriteFile`
- `CreateFileA`
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
| CURSOR/CURSOR/type_1041 | 0x2da18 | 308 |
| CURSOR/BITMAP/type_1041 | 0x2db4c | 180 |
| CURSOR/ICON/type_1041 | 0x2dc00 | 308 |
| CURSOR/MENU/type_1041 | 0x2dd34 | 308 |
| CURSOR/DIALOG/type_1041 | 0x2de68 | 308 |
| CURSOR/STRING/type_1041 | 0x2df9c | 308 |
| CURSOR/FONTDIR/type_1041 | 0x2e0d0 | 308 |
| CURSOR/FONT/type_1041 | 0x2e204 | 308 |
| CURSOR/ACCELERATOR/type_1041 | 0x2e338 | 308 |
| CURSOR/RCDATA/type_1041 | 0x2e46c | 308 |
| CURSOR/MESSAGETABLE/type_1041 | 0x2e5a0 | 308 |
| CURSOR/GROUP_CURSOR/type_1041 | 0x2e6d4 | 308 |
| CURSOR/type_13/type_1041 | 0x2e808 | 308 |
| CURSOR/GROUP_ICON/type_1041 | 0x2e93c | 308 |
| CURSOR/type_15/type_1041 | 0x2ea70 | 308 |
| CURSOR/VERSION/type_1041 | 0x2eba4 | 308 |
| BITMAP/type_30994/type_1041 | 0x2ecd8 | 184 |
| BITMAP/type_30996/type_1041 | 0x2ed90 | 324 |
| DIALOG/type_30721/type_1041 | 0x2eed4 | 232 |
| DIALOG/type_30734/type_1041 | 0x2efbc | 52 |
| STRING/type_3841/type_1041 | 0x2eff0 | 98 |
| STRING/type_3842/type_1041 | 0x2f054 | 46 |
| STRING/type_3843/type_1041 | 0x2f084 | 226 |
| STRING/type_3857/type_1041 | 0x2f168 | 850 |
| STRING/type_3858/type_1041 | 0x2f4bc | 446 |
| STRING/type_3859/type_1041 | 0x2f67c | 398 |
| STRING/type_3860/type_1041 | 0x2f80c | 104 |
| STRING/type_3865/type_1041 | 0x2f874 | 118 |
| STRING/type_3866/type_1041 | 0x2f8ec | 142 |
| STRING/type_3867/type_1041 | 0x2f97c | 740 |

> 其余 20 项

## DLL 依赖

| 导入自 | 函数数 |
|---|---|
| SHLWAPI.dll | 2 |
| OLEACC.dll | 2 |
| KERNEL32.dll | 104 |
| USER32.dll | 88 |
| GDI32.dll | 23 |
| WINSPOOL.DRV | 3 |
| ADVAPI32.dll | 9 |
| OLEAUT32.dll | 3 |

