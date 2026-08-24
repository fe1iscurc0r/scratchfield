# RadioSch.dll 静态分析报告

> 文件大小: 1,972,736 bytes | 机器: x86 | 类型: DLL | 入口: 0x141d08 | ImageBase: 0x10000000
> 编译时间: 2019-12-13 06:03:32

---

## 区段

| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 熵值 |
|---|---|---|---|---|
| .text | 0x1000 | 1,489,514 | 1,489,920 | 6.57 |
| .rdata | 0x16d000 | 307,886 | 308,224 | 5.42 |
| .data | 0x1b9000 | 38,540 | 20,992 | 4.92 |
| .rsrc | 0x1c3000 | 16,632 | 16,896 | 3.61 |
| .reloc | 0x1c8000 | 135,416 | 135,680 | 6.56 |

## 导入表

### KERNEL32.dll (156 函数)

- `GetStdHandle`
- `ExitProcess`
- `GetFileType`
- `SetStdHandle`
- `QueryPerformanceFrequency`
- `HeapQueryInformation`
- `GetCommandLineW`
- `GetCommandLineA`
- `LCMapStringW`
- `FreeLibraryAndExitThread`
- `ExitThread`
- `CreateThread`
- `VirtualQuery`
- `VirtualAlloc`
- `GetSystemInfo`
- `InterlockedFlushSList`
- `RtlUnwind`
- `OutputDebugStringW`
- `CompareStringW`
- `GetStringTypeW`
- `GetConsoleCP`
- `GetConsoleMode`
- `SetFilePointerEx`
- `FindFirstFileExW`
- `FindNextFileW`
- `IsValidCodePage`
- `GetEnvironmentStringsW`
- `FreeEnvironmentStringsW`
- `SetEnvironmentVariableW`
- `CreateFileW`
- ... 其余 126 个

### USER32.dll (224 函数)

- `ReleaseCapture`
- `SetCapture`
- `GetNextDlgGroupItem`
- `LoadImageW`
- `TrackMouseEvent`
- `IntersectRect`
- `MapDialogRect`
- `GetAsyncKeyState`
- `GetNextDlgTabItem`
- `EndDialog`
- `CreateDialogIndirectParamA`
- `OffsetRect`
- `SetRectEmpty`
- `InflateRect`
- `GetMenuItemInfoA`
- `DestroyMenu`
- `CharUpperA`
- `DestroyIcon`
- `FillRect`
- `GetWindowDC`
- `TabbedTextOutA`
- `GrayStringA`
- `DrawTextExA`
- `DrawTextA`
- `InvalidateRect`
- `KillTimer`
- `SetTimer`
- `DeleteMenu`
- `SystemParametersInfoA`
- `CopyImage`
- ... 其余 194 个

### GDI32.dll (97 函数)

- `Escape`
- `ExcludeClipRect`
- `GetClipBox`
- `GetObjectType`
- `GetPixel`
- `GetStockObject`
- `GetViewportExtEx`
- `GetWindowExtEx`
- `IntersectClipRect`
- `LineTo`
- `PtVisible`
- `RectVisible`
- `RestoreDC`
- `SaveDC`
- `SelectClipRgn`
- `ExtSelectClipRgn`
- `SelectObject`
- `SelectPalette`
- `SetBkMode`
- `SetMapMode`
- `SetLayout`
- `GetLayout`
- `SetPolyFillMode`
- `SetROP2`
- `SetTextAlign`
- `MoveToEx`
- `TextOutA`
- `ExtTextOutA`
- `SetViewportExtEx`
- `SetViewportOrgEx`
- ... 其余 67 个

### MSIMG32.dll (2 函数)

- `TransparentBlt`
- `AlphaBlend`

### WINSPOOL.DRV (3 函数)

- `DocumentPropertiesA`
- `OpenPrinterA`
- `ClosePrinter`

### ADVAPI32.dll (11 函数)

- `RegEnumKeyExA`
- `RegEnumValueA`
- `RegQueryValueA`
- `RegEnumKeyA`
- `RegSetValueExA`
- `RegDeleteValueA`
- `RegDeleteKeyA`
- `RegCreateKeyExA`
- `RegQueryValueExA`
- `RegOpenKeyExA`
- `RegCloseKey`

### SHELL32.dll (9 函数)

- `SHGetFileInfoA`
- `ShellExecuteA`
- `SHGetPathFromIDListA`
- `SHAppBarMessage`
- `SHBrowseForFolderA`
- `DragFinish`
- `DragQueryFileA`
- `SHGetDesktopFolder`
- `SHGetSpecialFolderLocation`

### SHLWAPI.dll (6 函数)

- `PathIsUNCA`
- `PathStripToRootA`
- `PathRemoveFileSpecW`
- `StrFormatKBSizeA`
- `PathFindFileNameA`
- `PathFindExtensionA`

### UxTheme.dll (12 函数)

- `GetThemePartSize`
- `GetThemeSysColor`
- `DrawThemeText`
- `DrawThemeParentBackground`
- `OpenThemeData`
- `CloseThemeData`
- `DrawThemeBackground`
- `GetThemeColor`
- `GetCurrentThemeName`
- `GetWindowTheme`
- `IsAppThemed`
- `IsThemeBackgroundPartiallyTransparent`

### ole32.dll (21 函数)

- `OleLockRunning`
- `OleCreateMenuDescriptor`
- `OleDestroyMenuDescriptor`
- `OleTranslateAccelerator`
- `IsAccelerator`
- `CoLockObjectExternal`
- `RevokeDragDrop`
- `RegisterDragDrop`
- `OleGetClipboard`
- `DoDragDrop`
- `CreateStreamOnHGlobal`
- `CoInitializeEx`
- `CoDisconnectObject`
- `CoInitialize`
- `CoCreateInstance`
- `CoCreateGuid`
- `CoUninitialize`
- `ReleaseStgMedium`
- `OleDuplicateData`
- `CoTaskMemFree`
- `CoTaskMemAlloc`

### OLEAUT32.dll (13 函数)

- `SysAllocStringByteLen`
- `SysAllocStringLen`
- `LoadTypeLib`
- `SysStringLen`
- `SystemTimeToVariantTime`
- `SysAllocString`
- `VariantInit`
- `VarBstrFromDate`
- `SysFreeString`
- `VariantChangeType`
- `VariantCopy`
- `VariantClear`
- `VariantTimeToSystemTime`

### SETUPAPI.dll (9 函数)

- `SetupDiEnumDeviceInfo`
- `SetupDiDestroyDeviceInfoList`
- `SetupDiGetClassDevsA`
- `SetupDiOpenDevRegKey`
- `CM_Get_Child`
- `CM_Get_Device_IDA`
- `CM_Get_Parent`
- `SetupDiGetDeviceInstanceIdA`
- `CM_Get_Sibling`

### WINMM.dll (7 函数)

- `PlaySoundA`
- `waveOutGetDevCapsA`
- `waveOutGetNumDevs`
- `waveOutMessage`
- `waveInGetNumDevs`
- `waveInGetDevCapsA`
- `waveInMessage`

### gdiplus.dll (22 函数)

- `GdipCreateBitmapFromStream`
- `GdipGetImagePaletteSize`
- `GdipGetImagePalette`
- `GdipGetImagePixelFormat`
- `GdipGetImageHeight`
- `GdipGetImageGraphicsContext`
- `GdipDisposeImage`
- `GdipCloneImage`
- `GdiplusStartup`
- `GdipBitmapLockBits`
- `GdipBitmapUnlockBits`
- `GdipFree`
- `GdipAlloc`
- `GdiplusShutdown`
- `GdipDeleteGraphics`
- `GdipDrawImageI`
- `GdipCreateBitmapFromHBITMAP`
- `GdipCreateFromHDC`
- `GdipSetInterpolationMode`
- `GdipDrawImageRectI`
- `GdipCreateBitmapFromScan0`
- `GdipGetImageWidth`

### OLEACC.dll (3 函数)

- `CreateStdAccessibleObject`
- `LresultFromObject`
- `AccessibleObjectFromWindow`

### IMM32.dll (3 函数)

- `ImmReleaseContext`
- `ImmGetOpenStatus`
- `ImmGetContext`

## 导出表

| 名称 | Ordinal | RVA | 虚拟地址 |
|---|---|---|---|
| `CloseDll` | 1 | 0x2b00 | 0x10002b00 |
| `GetUsbDev` | 2 | 0x2c00 | 0x10002c00 |
| `OpenDll` | 3 | 0x3e20 | 0x10003e20 |
| `SearchUsbDev` | 5 | 0x3f70 | 0x10003f70 |
| `SearchUsbDev2` | 4 | 0x3f70 | 0x10003f70 |

## 导出函数反汇编（前 20 条指令）

### `CloseDll` (RVA: 0x2b00)

```asm
  0x10002b00:  push ebp  ; 55
  0x10002b01:  mov ebp, esp  ; 8bec
  0x10002b03:  push esi  ; 56
  0x10002b04:  push 0x101be2d4  ; 68d4e21b10
  0x10002b09:  call dword ptr [0x1016d3fc]  ; ff15fcd31610
  0x10002b0f:  mov esi, dword ptr [ebp + 8]  ; 8b7508
  0x10002b12:  mov ecx, 0x101be2b0  ; b9b0e21b10
  0x10002b17:  push 0  ; 6a00
  0x10002b19:  push esi  ; 56
  0x10002b1a:  call 0x1000ce54  ; e835a30000
  0x10002b1f:  test eax, eax  ; 85c0
  0x10002b21:  je 0x10002b3b  ; 7418
  0x10002b23:  push eax  ; 50
  0x10002b24:  mov ecx, 0x101be2b0  ; b9b0e21b10
  0x10002b29:  call 0x1000cf61  ; e833a40000
  0x10002b2e:  test esi, esi  ; 85f6
  0x10002b30:  je 0x10002b3b  ; 7409
  0x10002b32:  mov eax, dword ptr [esi]  ; 8b06
  0x10002b34:  mov ecx, esi  ; 8bce
  0x10002b36:  push 1  ; 6a01
```

### `GetUsbDev` (RVA: 0x2c00)

```asm
  0x10002c00:  push ebp  ; 55
  0x10002c01:  mov ebp, esp  ; 8bec
  0x10002c03:  push ecx  ; 51
  0x10002c04:  push esi  ; 56
  0x10002c05:  mov esi, dword ptr [ebp + 8]  ; 8b7508
  0x10002c08:  push edi  ; 57
  0x10002c09:  push 0x101be2d4  ; 68d4e21b10
  0x10002c0e:  call dword ptr [0x1016d3fc]  ; ff15fcd31610
  0x10002c14:  push 0  ; 6a00
  0x10002c16:  push esi  ; 56
  0x10002c17:  mov ecx, 0x101be2b0  ; b9b0e21b10
  0x10002c1c:  call 0x1000ce54  ; e833a20000
  0x10002c21:  neg eax  ; f7d8
  0x10002c23:  mov ecx, 0x101be2cc  ; b9cce21b10
  0x10002c28:  sbb edi, edi  ; 1bff
  0x10002c2a:  mov eax, dword ptr [0x101be2cc]  ; a1cce21b10
  0x10002c2f:  call dword ptr [eax + 0x14]  ; ff5014
  0x10002c32:  and edi, esi  ; 23fe
  0x10002c34:  je 0x10002cd7  ; 0f849d000000
  0x10002c3a:  push dword ptr [ebp + 0xc]  ; ff750c
```

### `OpenDll` (RVA: 0x3e20)

```asm
  0x10003e20:  push ebp  ; 55
  0x10003e21:  mov ebp, esp  ; 8bec
  0x10003e23:  push -1  ; 6aff
  0x10003e25:  push 0x1015f0ca  ; 68caf01510
  0x10003e2a:  mov eax, dword ptr fs:[0]  ; 64a100000000
  0x10003e30:  push eax  ; 50
  0x10003e31:  sub esp, 0x1c  ; 83ec1c
  0x10003e34:  push ebx  ; 53
  0x10003e35:  push esi  ; 56
  0x10003e36:  push edi  ; 57
  0x10003e37:  mov eax, dword ptr [0x101b9e2c]  ; a12c9e1b10
  0x10003e3c:  xor eax, ebp  ; 33c5
  0x10003e3e:  push eax  ; 50
  0x10003e3f:  lea eax, [ebp - 0xc]  ; 8d45f4
  0x10003e42:  mov dword ptr fs:[0], eax  ; 64a300000000
  0x10003e48:  push 0x50  ; 6a50
  0x10003e4a:  call 0x1000cd09  ; e8ba8e0000
  0x10003e4f:  add esp, 4  ; 83c404
  0x10003e52:  mov dword ptr [ebp - 0x18], eax  ; 8945e8
  0x10003e55:  mov dword ptr [ebp - 4], 0  ; c745fc00000000
```

### `SearchUsbDev` (RVA: 0x3f70)

```asm
  0x10003f70:  push ebp  ; 55
  0x10003f71:  mov ebp, esp  ; 8bec
  0x10003f73:  push edi  ; 57
  0x10003f74:  push 0x101be2d4  ; 68d4e21b10
  0x10003f79:  call dword ptr [0x1016d3fc]  ; ff15fcd31610
  0x10003f7f:  push 0  ; 6a00
  0x10003f81:  push dword ptr [ebp + 8]  ; ff7508
  0x10003f84:  mov ecx, 0x101be2b0  ; b9b0e21b10
  0x10003f89:  call 0x1000ce54  ; e8c68e0000
  0x10003f8e:  neg eax  ; f7d8
  0x10003f90:  mov ecx, 0x101be2cc  ; b9cce21b10
  0x10003f95:  sbb edi, edi  ; 1bff
  0x10003f97:  mov eax, dword ptr [0x101be2cc]  ; a1cce21b10
  0x10003f9c:  call dword ptr [eax + 0x14]  ; ff5014
  0x10003f9f:  and edi, dword ptr [ebp + 8]  ; 237d08
  0x10003fa2:  je 0x10003fad  ; 7409
  0x10003fa4:  mov ecx, edi  ; 8bcf
  0x10003fa6:  pop edi  ; 5f
  0x10003fa7:  pop ebp  ; 5d
  0x10003fa8:  jmp 0x10007400  ; e953340000
```

### `SearchUsbDev2` (RVA: 0x3f70)

```asm
  0x10003f70:  push ebp  ; 55
  0x10003f71:  mov ebp, esp  ; 8bec
  0x10003f73:  push edi  ; 57
  0x10003f74:  push 0x101be2d4  ; 68d4e21b10
  0x10003f79:  call dword ptr [0x1016d3fc]  ; ff15fcd31610
  0x10003f7f:  push 0  ; 6a00
  0x10003f81:  push dword ptr [ebp + 8]  ; ff7508
  0x10003f84:  mov ecx, 0x101be2b0  ; b9b0e21b10
  0x10003f89:  call 0x1000ce54  ; e8c68e0000
  0x10003f8e:  neg eax  ; f7d8
  0x10003f90:  mov ecx, 0x101be2cc  ; b9cce21b10
  0x10003f95:  sbb edi, edi  ; 1bff
  0x10003f97:  mov eax, dword ptr [0x101be2cc]  ; a1cce21b10
  0x10003f9c:  call dword ptr [eax + 0x14]  ; ff5014
  0x10003f9f:  and edi, dword ptr [ebp + 8]  ; 237d08
  0x10003fa2:  je 0x10003fad  ; 7409
  0x10003fa4:  mov ecx, edi  ; 8bcf
  0x10003fa6:  pop edi  ; 5f
  0x10003fa7:  pop ebp  ; 5d
  0x10003fa8:  jmp 0x10007400  ; e953340000
```

## 字符串分类

### ci_v_commands (1 条)

- `QueryPerformanceFrequency`

### serial_port (72 条)

- `Software\Microsoft\Windows\CurrentVersion\Policies\Comdlg32`
- `commctrl_DragListMsg`
- `Comctl32.dll`
- `InitCommonControlsEx`
- `@combobox`
- `DwmIsCompositionEnabled`
- `Comdlg32.dll`
- `ComboBox`
- `ComboBoxEx32`
- `MFCFontComboBox`
- `commdlg_LBSelChangedNotify`
- `commdlg_ShareViolation`
- `commdlg_FileNameOK`
- `commdlg_ColorOK`
- `commdlg_help`
- `commdlg_SetRGBColor`
- `CCommonDialog`
- `MFCComboBox_DrawUsingFont`
- `MFCComboBox_ShowTrueTypeFonts`
- `MFCComboBox_ShowRasterTypeFonts`
- `MFCComboBox_ShowDeviceTypeFonts`
- `COMBOBOX`
- `CComboBox`
- `AFX_WM_ON_DRAGCOMPLETE`
- `AFX_WM_ON_MOVETABCOMPLETE`
- `AFX_WM_ON_AFTER_SHELL_COMMAND`
- `CMFCToolBarComboBoxButton`
- `CMFCToolBarFontComboBox`
- `CMFCToolBarFontSizeComboBox`
- `COMBO`
- `IDB_OFFICE2007_COMBOBOX_BTN`
- `MenuCommand`
- `CHelpComboBoxButton`
- `CMFCToolBarsCommandsPropertyPage`
- `DEFAULT_COMMAND`
- `ComboBox_Font`
- `commdlg_FindReplace`
- ` Complete Object Locator'`
- `CompareStringEx`
- `CompareStringA`
- `GetComboBoxInfo`
- `CreateCompatibleDC`
- `CombineRgn`
- `CreateCompatibleBitmap`
- `GetThemePartSize`
- `GetCommandLineA`
- `GetCommandLineW`
- `CompareStringW`
- `.?AVCComObjectRootBase@ATL@@`
- `.?AV?$CComObjectRootEx@VCComSingleThreadModel@ATL@@@ATL@@`
- ... 其余 22 条

### network (15 条)

- `PortName`
- `CNotSupportedException`
- `NoNetConnectDisconnect`
- `GetCPInfo`
- `GetViewportExtEx`
- `SetViewportExtEx`
- `SetViewportOrgEx`
- `OffsetViewportOrgEx`
- `ScaleViewportExtEx`
- `GetViewportOrgEx`
- `CoDisconnectObject`
- `.?AVCNotSupportedException@@`
- `.PAVCNotSupportedException@@`
- `No error message is available.#Attempted an unsupported operation.$A required resource was unavailable.`
- `#Unable to load mail system support.`

### file_paths (558 条)

- `9O\u`
- `t/VP`
- `V\_^]`
- `>,r/`
- `S\_^[]`
- `9Ftt/`
- `tFh\ `
- `t/Wj`
- `t8h\ `
- `Ph@/`
- `<J\u`
- `j\Yf9`
- `u/9F`
- `Ph\A`
- `Ph\O`
- `9C\t*9Clu%`
- `9{\t`
- `9y\t`
- `9y\t)9ylt`
- `9W\t`
- `9P\t`
- `t\9H t`
- `Ph\r`
- `t\S3`
- `@\Pj`
- `@\SPV`
- `H\QQ`
- `@\WP`
- `@ h\`
- `t\jp`
- `@\+E`
- `+C\P`
- `N h\`
- `t9Vh\`
- `O\Ph`
- `s\_^[]`
- `9wDu\9O@uW`
- `X<u\`
- `B\+BT`
- `t49~ t/`
- `t/j4^VQ`
- `N\SSSSh`
- `V\_^[]`
- `u`h\`
- `t h\`
- `u h\`
- `t/;}`
- `<\u"W`
- `t7j\`
- `KDh\`
- ... 其余 508 条

### audio (7 条)

- `AUDIO`
- `waveOutGetNumDevs`
- `waveOutGetDevCapsA`
- `waveOutMessage`
- `waveInGetNumDevs`
- `waveInGetDevCapsA`
- `waveInMessage`

### error_msgs (25 条)

- `!This program cannot be run in DOS mode.`
- `Invalid DateTime`
- `CInvalidArgException`
- `DwmInvalidateIconicBitmaps`
- `GetLastError`
- `SetLastError`
- `SetErrorMode`
- `InvalidateRect`
- `.?AVCInvalidArgException@@`
- `.PAVCInvalidArgException@@`
- `.?AVlogic_error@std@@`
- `.?AVlength_error@std@@`
- `ERROR : Unable to initialize critical section in CAtlBaseModule`
- `An unknown error has occurred.!Encountered an improper argument.`
- `Failed to open document.`
- `Failed to save document.`
- `Save changes to %1? Failed to create empty document.`
- `Failed to launch help.`
- `Internal application error.`
- `Cannot find this file.`
- `Destination disk drive is full.5Unable to read from %1, it is opened by someone else.AUnable to write to %1, it is read-only or opened by someone else.1Encountered an unexpected error while reading %1.1Encountered an unexpected error while writing %1.`
- `No error occurred.-An unknown error occurred while accessing %1.`
- `%1 was not found.`
- `No error occurred.-An unknown error occurred while accessing %1.%Attempted to write to the reading %1.$Attempted to access %1 past its end.&Attempted to read from the writing %1.`
- `Mail system DLL is invalid.!Send Mail failed to send message.`

### format_strings (161 条)

- `u%h,`
- `9Ppu%`
- `t%9x t 9`
- `.~%f`
- `u%Sh,`
- `u%VS`
- `t%9p t `
- `u%VW`
- `RRR%`
- `t%Vh`
- `t%9s$t 9s(u`
- `t%!}`
- `t%9q t `
- `t%;p`
- `tB9{Pt%`
- `t%WWhN`
- `9%u|`
- `8%tt`
- `|%=2`
- `VIDPID%d`
- `%s_%s`
- `%s %s`
- `%Ts (%Ts:%d)`
- `%Ts%Ts.dll`
- `%08lX-%04X-%04x-%02X%02X-%02X%02X%02X%02X%02X%02X`
- `Afx:%p:%x`
- `Afx:%p:%x:%p:%p:%p`
- `%08lX%04X%04x%02X%02X%02X%02X%02X%02X%02X%02X`
- `%3,%7`
- `%9, %8`
- `%Ts:%x:%x:%x:%x`
- `@UUUUUU%@`
- `%TsBasePane-%d`
- `%TsBasePane-%d%x`
- `%TsPane-%d`
- `%TsPane-%d%x`
- `%d%%`
- `%TsMFCToolBar-%d`
- `%TsMFCToolBar-%d%x`
- `%TsMFCToolBarParameters`
- `%TsMFCOutlookBar-%d`
- `%TsMFCOutlookBar-%d%x`
- `&%d %Ts`
- `Hex={%02X,%02X,%02X}`
- `%TsDockingManager-%d`
- `%TsDockablePaneAdapter-%d`
- `%TsDockablePaneAdapter-%d%x`
- `ToolbarButton%p`
- `%TsMDIClientArea-%d`
- `%s%s%X.tmp`
- ... 其余 111 条

### interesting (135 条)

- `CWinThread`
- `CreateActCtxW`
- `NoClose`
- `RegOpenKeyTransactedA`
- `RegCreateKeyTransactedA`
- `AFX_WM_RECREATED2DRESOURCES`
- `CloseTouchInputHandle`
- `CloseGestureInfoHandle`
- `AFX_DIALOG_LAYOUT`
- `D2D1CreateFactory`
- `DWriteCreateFactory`
- `GetThreadPreferredUILanguages`
- `SHCreateItemFromParsingName`
- `CreateFileTransactedA`
- `&Open,0,2`
- `CDialog`
- `AfxClosePending`
- `CreatePropertySheetPageA`
- `GetOpenFileNameA`
- `CFileDialog`
- `ImageList_Create`
- `TOOLBAR_CREATE`
- `Open`
- `IDB_OFFICE2007_SYS_BTN_CLOSE`
- `Close`
- `CMFCToolBarsCustomizeDialog`
- `AFX_WM_ON_PRESS_CLOSE_BUTTON`
- `Can't create context menu!`
- `CDialogEx`
- `CColorDialog`
- `CPrintDialog`
- ``local static thread guard'`
- `AppPolicyGetThreadInitializationType`
- `SetThreadStackGuarantee`
- `log10`
- `_logb`
- `CloseDll`
- `OpenDll`
- `WritePrivateProfileStringA`
- `CloseHandle`
- `GetCurrentThreadId`
- `SetThreadPriority`
- `ResumeThread`
- `OutputDebugStringA`
- `GetCurrentThread`
- `CreateFileA`
- `FindClose`
- `ReadFile`
- `WriteFile`
- `CreateEventW`
- ... 其余 85 条

## 资源段 (50 项)

| 类型 | 偏移 | 大小 |
|---|---|---|
| CURSOR/CURSOR/type_1041 | 0x1c3c60 | 308 |
| CURSOR/BITMAP/type_1041 | 0x1c3d98 | 180 |
| CURSOR/ICON/type_1041 | 0x1c3e78 | 308 |
| CURSOR/MENU/type_1041 | 0x1c3fc8 | 308 |
| CURSOR/DIALOG/type_1041 | 0x1c4118 | 308 |
| CURSOR/STRING/type_1041 | 0x1c4268 | 308 |
| CURSOR/FONTDIR/type_1041 | 0x1c43b8 | 308 |
| CURSOR/FONT/type_1041 | 0x1c4508 | 308 |
| CURSOR/ACCELERATOR/type_1041 | 0x1c4658 | 308 |
| CURSOR/RCDATA/type_1041 | 0x1c47a8 | 308 |
| CURSOR/MESSAGETABLE/type_1041 | 0x1c48f8 | 308 |
| CURSOR/GROUP_CURSOR/type_1041 | 0x1c4a48 | 308 |
| CURSOR/type_13/type_1041 | 0x1c4b98 | 308 |
| CURSOR/GROUP_ICON/type_1041 | 0x1c4ce8 | 308 |
| CURSOR/type_15/type_1041 | 0x1c4e38 | 308 |
| CURSOR/VERSION/type_1041 | 0x1c4f88 | 308 |
| BITMAP/type_30994/type_1041 | 0x1c51f8 | 184 |
| BITMAP/type_30996/type_1041 | 0x1c52b0 | 324 |
| DIALOG/type_30721/type_1041 | 0x1c50d8 | 232 |
| DIALOG/type_30734/type_1041 | 0x1c51c0 | 52 |
| STRING/type_3841/type_1041 | 0x1c53f8 | 130 |
| STRING/type_3842/type_1041 | 0x1c5480 | 42 |
| STRING/type_3843/type_1041 | 0x1c54b0 | 388 |
| STRING/type_3857/type_1041 | 0x1c5638 | 1262 |
| STRING/type_3858/type_1041 | 0x1c5eb8 | 612 |
| STRING/type_3859/type_1041 | 0x1c5bd8 | 730 |
| STRING/type_3860/type_1041 | 0x1c6900 | 138 |
| STRING/type_3865/type_1041 | 0x1c5b28 | 172 |
| STRING/type_3866/type_1041 | 0x1c67f0 | 222 |
| STRING/type_3867/type_1041 | 0x1c6120 | 1192 |

> 其余 20 项

## DLL 依赖

| 导入自 | 函数数 |
|---|---|
| KERNEL32.dll | 156 |
| USER32.dll | 224 |
| GDI32.dll | 97 |
| MSIMG32.dll | 2 |
| WINSPOOL.DRV | 3 |
| ADVAPI32.dll | 11 |
| SHELL32.dll | 9 |
| SHLWAPI.dll | 6 |
| UxTheme.dll | 12 |
| ole32.dll | 21 |
| OLEAUT32.dll | 13 |
| SETUPAPI.dll | 9 |
| WINMM.dll | 7 |
| gdiplus.dll | 22 |
| OLEACC.dll | 3 |
| IMM32.dll | 3 |

