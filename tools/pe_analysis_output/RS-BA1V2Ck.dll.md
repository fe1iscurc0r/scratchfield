# RS-BA1V2Ck.dll 静态分析报告

> 文件大小: 2,014,720 bytes | 机器: x86 | 类型: DLL | 入口: 0x138be4 | ImageBase: 0x10000000
> 编译时间: 2018-06-28 00:24:33

---

## 区段

| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 熵值 |
|---|---|---|---|---|
| .text | 0x1000 | 1,447,637 | 1,447,936 | 6.57 |
| .rdata | 0x163000 | 303,108 | 303,616 | 5.43 |
| .data | 0x1ae000 | 45,556 | 20,480 | 4.97 |
| .gfids | 0x1ba000 | 106,708 | 107,008 | 4.24 |
| .giats | 0x1d5000 | 16 | 512 | 0.16 |
| .tls | 0x1d6000 | 9 | 512 | 0.02 |
| .rsrc | 0x1d7000 | 13,896 | 14,336 | 4.33 |
| .reloc | 0x1db000 | 118,940 | 119,296 | 6.49 |

## 导入表

### KERNEL32.dll (161 函数)

- `lstrcmpiA`
- `GetVolumeInformationA`
- `FileTimeToSystemTime`
- `FileTimeToLocalFileTime`
- `GetFileAttributesA`
- `GetFileAttributesExA`
- `GetFileSizeEx`
- `GetFileTime`
- `WriteFile`
- `SystemTimeToTzSpecificLocalTime`
- `VirtualProtect`
- `GetOEMCP`
- `GetCPInfo`
- `GetACP`
- `lstrcpyA`
- `FindResourceExW`
- `GetWindowsDirectoryA`
- `VerSetConditionMask`
- `VerifyVersionInfoA`
- `GetTempPathA`
- `GetTempFileNameA`
- `GetTickCount`
- `GetProfileIntA`
- `SearchPathA`
- `Sleep`
- `ResetEvent`
- `WaitForSingleObjectEx`
- `CreateEventW`
- `UnhandledExceptionFilter`
- `SetUnhandledExceptionFilter`
- ... 其余 131 个

### USER32.dll (224 函数)

- `CreatePopupMenu`
- `GetMenuDefaultItem`
- `MapVirtualKeyA`
- `GetKeyNameTextA`
- `SetLayeredWindowAttributes`
- `EnumDisplayMonitors`
- `SetClassLongA`
- `SetWindowRgn`
- `SetParent`
- `OpenClipboard`
- `CloseClipboard`
- `SetClipboardData`
- `EmptyClipboard`
- `DrawStateA`
- `DrawEdge`
- `DrawFrameControl`
- `IsZoomed`
- `LoadMenuW`
- `GetSystemMenu`
- `BringWindowToTop`
- `SetCursorPos`
- `CopyIcon`
- `FrameRect`
- `DrawIcon`
- `UnionRect`
- `UpdateLayeredWindow`
- `MonitorFromPoint`
- `LoadAcceleratorsA`
- `TranslateAcceleratorA`
- `LoadMenuA`
- ... 其余 194 个

### MSIMG32.dll (2 函数)

- `TransparentBlt`
- `AlphaBlend`

### SHLWAPI.dll (6 函数)

- `PathRemoveFileSpecW`
- `PathStripToRootA`
- `PathIsUNCA`
- `PathFindFileNameA`
- `PathFindExtensionA`
- `StrFormatKBSizeA`

### UxTheme.dll (12 函数)

- `GetThemePartSize`
- `GetThemeSysColor`
- `IsThemeBackgroundPartiallyTransparent`
- `IsAppThemed`
- `GetWindowTheme`
- `GetCurrentThemeName`
- `GetThemeColor`
- `DrawThemeBackground`
- `CloseThemeData`
- `OpenThemeData`
- `DrawThemeParentBackground`
- `DrawThemeText`

### OLEACC.dll (3 函数)

- `LresultFromObject`
- `CreateStdAccessibleObject`
- `AccessibleObjectFromWindow`

### gdiplus.dll (22 函数)

- `GdipSetInterpolationMode`
- `GdipCreateFromHDC`
- `GdipCreateBitmapFromHBITMAP`
- `GdipDrawImageI`
- `GdipDeleteGraphics`
- `GdipBitmapUnlockBits`
- `GdipBitmapLockBits`
- `GdipDrawImageRectI`
- `GdiplusShutdown`
- `GdipAlloc`
- `GdipFree`
- `GdiplusStartup`
- `GdipCloneImage`
- `GdipDisposeImage`
- `GdipGetImageGraphicsContext`
- `GdipGetImageWidth`
- `GdipGetImageHeight`
- `GdipGetImagePixelFormat`
- `GdipGetImagePalette`
- `GdipGetImagePaletteSize`
- `GdipCreateBitmapFromStream`
- `GdipCreateBitmapFromScan0`

### IMM32.dll (3 函数)

- `ImmGetContext`
- `ImmGetOpenStatus`
- `ImmReleaseContext`

### WINMM.dll (1 函数)

- `PlaySoundA`

### GDI32.dll (97 函数)

- `BitBlt`
- `CreateCompatibleDC`
- `CreateHatchBrush`
- `CreatePen`
- `CreatePatternBrush`
- `CreateRectRgn`
- `CreateSolidBrush`
- `DeleteDC`
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
- `SetBkColor`
- `SetBkMode`
- `SetMapMode`
- `SetLayout`
- ... 其余 67 个

### WINSPOOL.DRV (3 函数)

- `DocumentPropertiesA`
- `ClosePrinter`
- `OpenPrinterA`

### ADVAPI32.dll (11 函数)

- `RegCreateKeyExA`
- `RegOpenKeyExA`
- `RegCloseKey`
- `RegQueryValueExA`
- `RegDeleteKeyA`
- `RegDeleteValueA`
- `RegSetValueExA`
- `RegEnumKeyA`
- `RegQueryValueA`
- `RegEnumValueA`
- `RegEnumKeyExA`

### SHELL32.dll (9 函数)

- `SHGetDesktopFolder`
- `SHGetPathFromIDListA`
- `ShellExecuteA`
- `SHGetFileInfoA`
- `DragQueryFileA`
- `DragFinish`
- `SHBrowseForFolderA`
- `SHAppBarMessage`
- `SHGetSpecialFolderLocation`

### ole32.dll (21 函数)

- `OleDestroyMenuDescriptor`
- `OleTranslateAccelerator`
- `IsAccelerator`
- `OleCreateMenuDescriptor`
- `OleLockRunning`
- `RevokeDragDrop`
- `RegisterDragDrop`
- `CoLockObjectExternal`
- `OleGetClipboard`
- `DoDragDrop`
- `CoUninitialize`
- `CoCreateGuid`
- `CreateStreamOnHGlobal`
- `CoInitializeEx`
- `CoDisconnectObject`
- `ReleaseStgMedium`
- `OleDuplicateData`
- `CoTaskMemFree`
- `CoTaskMemAlloc`
- `CoInitialize`
- `CoCreateInstance`

### OLEAUT32.dll (13 函数)

- `SysStringLen`
- `LoadTypeLib`
- `SystemTimeToVariantTime`
- `VariantTimeToSystemTime`
- `VariantChangeType`
- `VariantClear`
- `VariantInit`
- `SysAllocStringByteLen`
- `VariantCopy`
- `VarBstrFromDate`
- `SysFreeString`
- `SysAllocString`
- `SysAllocStringLen`

## 导出表

| 名称 | Ordinal | RVA | 虚拟地址 |
|---|---|---|---|
| `RsBA1V2_GetKeyNum` | 1 | 0x1af0 | 0x10001af0 |

## 导出函数反汇编（前 20 条指令）

### `RsBA1V2_GetKeyNum` (RVA: 0x1af0)

```asm
  0x10001af0:  push ebp  ; 55
  0x10001af1:  mov ebp, esp  ; 8bec
  0x10001af3:  mov eax, dword ptr [ebp + 8]  ; 8b4508
  0x10001af6:  imul eax, eax  ; 0fafc0
  0x10001af9:  add eax, 0x5127b  ; 057b120500
  0x10001afe:  pop ebp  ; 5d
  0x10001aff:  ret 4  ; c20400
  0x10001b02:  int3  ; cc
  0x10001b03:  int3  ; cc
  0x10001b04:  int3  ; cc
  0x10001b05:  int3  ; cc
  0x10001b06:  int3  ; cc
  0x10001b07:  int3  ; cc
  0x10001b08:  int3  ; cc
  0x10001b09:  int3  ; cc
  0x10001b0a:  int3  ; cc
  0x10001b0b:  int3  ; cc
  0x10001b0c:  int3  ; cc
  0x10001b0d:  int3  ; cc
  0x10001b0e:  int3  ; cc
```

## 字符串分类

### ci_v_commands (1 条)

- `QueryPerformanceFrequency`

### serial_port (72 条)

- `Software\Microsoft\Windows\CurrentVersion\Policies\Comdlg32`
- `CompareStringEx`
- `DwmIsCompositionEnabled`
- `combobox`
- `Comctl32.dll`
- `InitCommonControlsEx`
- `commctrl_DragListMsg`
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
- `ComboBox_Font`
- `DEFAULT_COMMAND`
- `commdlg_FindReplace`
- ` Complete Object Locator'`
- `GetThemePartSize`
- `CompareStringA`
- `CompareStringW`
- `GetCommandLineA`
- `GetCommandLineW`
- `GetComboBoxInfo`
- `CreateCompatibleDC`
- `CombineRgn`
- `CreateCompatibleBitmap`
- `.?AVCComObjectRootBase@ATL@@`
- `.?AV?$CComObjectRootEx@VCComSingleThreadModel@ATL@@@ATL@@`
- ... 其余 22 条

### network (12 条)

- `NoNetConnectDisconnect`
- `CNotSupportedException`
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

### file_paths (509 条)

- `9O\u`
- `u h\c`
- `t\SS`
- `t/Vj`
- `Sh\v`
- `V\_^]`
- `>,r/`
- `S\_^[]`
- `t/VP`
- `uw/t`
- `<J\u`
- `j\Yf9`
- `<A|\<Z`
- `u/9F`
- `9C\t*9Clu%`
- `9{\t`
- `9y\t`
- `9y\t)9ylt`
- `9W\t`
- `9Wpt\9`
- `9P\t`
- `t\S3`
- `t\hXb`
- `Vh\j`
- `@\Pj`
- `H\QQ`
- `@\WP`
- `@\+E`
- `+C\P`
- `O\Ph`
- `s\_^[]`
- `9wDu\9O@uW`
- `t49~ t/`
- `\WhXb`
- `t/VW`
- `N\SSSSh`
- `V\_^[]`
- `X\!M`
- `u-h\`
- `t>h\``
- `tYh\``
- `tXh\``
- `tFh\``
- `tVh\``
- `t/VWh`
- `t/;}`
- `<\u"W`
- `t7j\`
- `/f9]`
- `9x\t`
- ... 其余 459 条

### error_msgs (11 条)

- `!This program cannot be run in DOS mode.`
- `CInvalidArgException`
- `DwmInvalidateIconicBitmaps`
- `Invalid DateTime`
- `GetLastError`
- `SetLastError`
- `SetErrorMode`
- `InvalidateRect`
- `.?AVCInvalidArgException@@`
- `.PAVCInvalidArgException@@`
- `ERROR : Unable to initialize critical section in CAtlBaseModule`

### format_strings (131 条)

- `u%h(c`
- `9Ppu%`
- `t%9w u `
- `t%9x t 9`
- `<+t%<-t!`
- `u%Sh`
- `u%VS`
- `t%9s,t 9{`
- `t%9p t `
- `%95hk`
- `RRR%`
- `t%Vh`
- `t%9s$t 9s(u`
- `t%!}`
- `t%9q t `
- `r%;{ v`
- `9sHt%`
- `9CHt%`
- `9xTt%`
- `t%hL`
- `t%WWhN`
- `v SSSSWSh0%`
- `97~%`
- `ft%9q`
- `8%tx`
- `|%=2`
- `%Ts (%Ts:%d)`
- `%Ts%Ts.dll`
- `%08lX-%04X-%04x-%02X%02X-%02X%02X%02X%02X%02X%02X`
- `%08lX%04X%04x%02X%02X%02X%02X%02X%02X%02X%02X`
- `Afx:%p:%x`
- `Afx:%p:%x:%p:%p:%p`
- `%3,%7`
- `%9, %8`
- `%Ts:%x:%x:%x:%x`
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
- ... 其余 81 条

### interesting (126 条)

- `NoClose`
- `CWinThread`
- `RegOpenKeyTransactedA`
- `RegCreateKeyTransactedA`
- `CreateActCtxW`
- `D2D1CreateFactory`
- `DWriteCreateFactory`
- `GetThreadPreferredUILanguages`
- `SHCreateItemFromParsingName`
- `AFX_WM_RECREATED2DRESOURCES`
- `CloseTouchInputHandle`
- `CloseGestureInfoHandle`
- `AFX_DIALOG_LAYOUT`
- `CreateFileTransactedA`
- `CDialog`
- `AfxClosePending`
- `CreatePropertySheetPageA`
- `GetOpenFileNameA`
- `CFileDialog`
- `&Open,0,2`
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
- `SetThreadStackGuarantee`
- `log10`
- `_logb`
- `OpenThemeData`
- `CloseThemeData`
- `CreateStdAccessibleObject`
- `GdipCreateBitmapFromStream`
- `GdipCreateBitmapFromScan0`
- `GdipCreateBitmapFromHBITMAP`
- `GdipCreateFromHDC`
- `ImmGetOpenStatus`
- `GetCurrentThread`
- `GetCurrentThreadId`
- `CloseHandle`
- `SetEvent`
- `SetThreadPriority`
- `ResumeThread`
- `WritePrivateProfileStringA`
- ... 其余 76 条

## 资源段 (50 项)

| 类型 | 偏移 | 大小 |
|---|---|---|
| CURSOR/CURSOR/type_1041 | 0x1d7c60 | 308 |
| CURSOR/BITMAP/type_1041 | 0x1d7d98 | 180 |
| CURSOR/ICON/type_1041 | 0x1d7e78 | 308 |
| CURSOR/MENU/type_1041 | 0x1d7fc8 | 308 |
| CURSOR/DIALOG/type_1041 | 0x1d8118 | 308 |
| CURSOR/STRING/type_1041 | 0x1d8268 | 308 |
| CURSOR/FONTDIR/type_1041 | 0x1d83b8 | 308 |
| CURSOR/FONT/type_1041 | 0x1d8508 | 308 |
| CURSOR/ACCELERATOR/type_1041 | 0x1d8658 | 308 |
| CURSOR/RCDATA/type_1041 | 0x1d87a8 | 308 |
| CURSOR/MESSAGETABLE/type_1041 | 0x1d88f8 | 308 |
| CURSOR/GROUP_CURSOR/type_1041 | 0x1d8a48 | 308 |
| CURSOR/type_13/type_1041 | 0x1d8b98 | 308 |
| CURSOR/GROUP_ICON/type_1041 | 0x1d8ce8 | 308 |
| CURSOR/type_15/type_1041 | 0x1d8e38 | 308 |
| CURSOR/VERSION/type_1041 | 0x1d8f88 | 308 |
| BITMAP/type_30994/type_1041 | 0x1d91f8 | 184 |
| BITMAP/type_30996/type_1041 | 0x1d92b0 | 324 |
| DIALOG/type_30721/type_1041 | 0x1d90d8 | 232 |
| DIALOG/type_30734/type_1041 | 0x1d91c0 | 52 |
| STRING/type_3841/type_1041 | 0x1d93f8 | 98 |
| STRING/type_3842/type_1041 | 0x1d9460 | 46 |
| STRING/type_3843/type_1041 | 0x1d9490 | 226 |
| STRING/type_3857/type_1041 | 0x1d9578 | 860 |
| STRING/type_3858/type_1041 | 0x1d9ae0 | 446 |
| STRING/type_3859/type_1041 | 0x1d9950 | 398 |
| STRING/type_3860/type_1041 | 0x1da1a0 | 104 |
| STRING/type_3865/type_1041 | 0x1d98d8 | 118 |
| STRING/type_3866/type_1041 | 0x1da0e8 | 142 |
| STRING/type_3867/type_1041 | 0x1d9ca0 | 740 |

> 其余 20 项

## DLL 依赖

| 导入自 | 函数数 |
|---|---|
| KERNEL32.dll | 161 |
| USER32.dll | 224 |
| MSIMG32.dll | 2 |
| SHLWAPI.dll | 6 |
| UxTheme.dll | 12 |
| OLEACC.dll | 3 |
| gdiplus.dll | 22 |
| IMM32.dll | 3 |
| WINMM.dll | 1 |
| GDI32.dll | 97 |
| WINSPOOL.DRV | 3 |
| ADVAPI32.dll | 11 |
| SHELL32.dll | 9 |
| ole32.dll | 21 |
| OLEAUT32.dll | 13 |

