# RemoteCtrl.exe 静态分析报告

> 文件大小: 44,931,072 bytes | 机器: x86 | 类型: EXE | 入口: 0x1798 | ImageBase: 0x400000
> 编译时间: 2020-12-09 01:34:49

---

## 区段

| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 熵值 |
|---|---|---|---|---|
| .text | 0x1000 | 2,187,264 | 2,184,192 | 6.53 |
| .data | 0x217000 | 3,645,440 | 3,567,616 | 2.43 |
| .tls | 0x591000 | 4,096 | 512 | 0.0 |
| .rdata | 0x592000 | 4,096 | 512 | 0.21 |
| .idata | 0x593000 | 16,384 | 13,312 | 5.14 |
| .edata | 0x597000 | 16,384 | 12,800 | 5.71 |
| .rsrc | 0x59b000 | 38,993,920 | 38,991,360 | 4.69 |
| .reloc | 0x2acb000 | 159,744 | 159,232 | 6.59 |

## 导入表

### ADVAPI32.DLL (11 函数)

- `RegCloseKey`
- `RegCreateKeyExA`
- `RegDeleteKeyA`
- `RegDeleteValueA`
- `RegEnumKeyExA`
- `RegEnumValueA`
- `RegFlushKey`
- `RegOpenKeyExA`
- `RegQueryInfoKeyA`
- `RegQueryValueExA`
- `RegSetValueExA`

### KERNEL32.DLL (121 函数)

- `CloseHandle`
- `CompareStringA`
- `CreateDirectoryA`
- `CreateEventA`
- `CreateFileA`
- `CreateMailslotA`
- `CreateMutexA`
- `CreateThread`
- `DeleteCriticalSection`
- `DeleteFileA`
- `EnterCriticalSection`
- `EnumCalendarInfoA`
- `ExitProcess`
- `ExitThread`
- `FileTimeToDosDateTime`
- `FileTimeToLocalFileTime`
- `FindClose`
- `FindFirstFileA`
- `FindNextFileA`
- `FindResourceA`
- `FormatMessageA`
- `FreeLibrary`
- `FreeResource`
- `GetACP`
- `GetCPInfo`
- `GetCommandLineA`
- `GetCurrentDirectoryA`
- `GetCurrentProcessId`
- `GetCurrentThreadId`
- `GetDateFormatA`
- ... 其余 91 个

### RPCRT4.DLL (1 函数)

- `UuidFromStringA`

### VERSION.DLL (3 函数)

- `GetFileVersionInfoA`
- `GetFileVersionInfoSizeA`
- `VerQueryValueA`

### WINSPOOL.DRV (4 函数)

- `ClosePrinter`
- `DocumentPropertiesA`
- `EnumPrintersA`
- `OpenPrinterA`

### COMCTL32.DLL (25 函数)

- `ImageList_Add`
- `ImageList_BeginDrag`
- `ImageList_Destroy`
- `ImageList_DragEnter`
- `ImageList_DragLeave`
- `ImageList_DragMove`
- `ImageList_DragShowNolock`
- `ImageList_Draw`
- `ImageList_DrawEx`
- `ImageList_EndDrag`
- `ImageList_GetBkColor`
- `ImageList_GetDragImage`
- `ImageList_GetIconSize`
- `ImageList_GetImageCount`
- `ImageList_Read`
- `ImageList_Remove`
- `ImageList_Replace`
- `ImageList_ReplaceIcon`
- `ImageList_SetBkColor`
- `ImageList_SetIconSize`
- `ImageList_SetOverlayImage`
- `ImageList_Write`
- `ordinal_17`
- `_TrackMouseEvent`
- `ImageList_Create`

### COMDLG32.DLL (4 函数)

- `ChooseColorA`
- `GetOpenFileNameA`
- `GetSaveFileNameA`
- `PrintDlgA`

### GDI32.DLL (90 函数)

- `BitBlt`
- `CombineRgn`
- `CopyEnhMetaFileA`
- `CreateBitmap`
- `CreateBrushIndirect`
- `CreateCompatibleBitmap`
- `CreateCompatibleDC`
- `CreateDCA`
- `CreateDIBSection`
- `CreateDIBitmap`
- `CreateFontIndirectA`
- `CreateHalftonePalette`
- `CreateICA`
- `CreatePalette`
- `CreatePen`
- `CreatePenIndirect`
- `CreatePolygonRgn`
- `CreateRectRgn`
- `CreateSolidBrush`
- `DeleteDC`
- `DeleteEnhMetaFile`
- `DeleteObject`
- `Ellipse`
- `EndDoc`
- `EndPage`
- `ExcludeClipRect`
- `ExtCreatePen`
- `ExtFloodFill`
- `ExtTextOutA`
- `GdiFlush`
- ... 其余 60 个

### MSIMG32.DLL (2 函数)

- `AlphaBlend`
- `GradientFill`

### SHELL32.DLL (2 函数)

- `SHGetSpecialFolderLocation`
- `SHGetPathFromIDListA`

### USER32.DLL (203 函数)

- `ActivateKeyboardLayout`
- `AdjustWindowRectEx`
- `BeginPaint`
- `CallNextHookEx`
- `CallWindowProcA`
- `CharLowerA`
- `CharLowerBuffA`
- `CharNextA`
- `CharNextW`
- `CharToOemA`
- `CharUpperBuffA`
- `CheckMenuItem`
- `ChildWindowFromPoint`
- `ClientToScreen`
- `ClipCursor`
- `CloseClipboard`
- `CreateCaret`
- `CreateIcon`
- `CreateMenu`
- `CreatePopupMenu`
- `CreateWindowExA`
- `DefFrameProcA`
- `DefMDIChildProcA`
- `DefWindowProcA`
- `DeleteMenu`
- `DestroyCaret`
- `DestroyCursor`
- `DestroyIcon`
- `DestroyMenu`
- `DestroyWindow`
- ... 其余 173 个

### WINMM.DLL (23 函数)

- `PlaySoundA`
- `mciSendCommandA`
- `mmioAscend`
- `mmioClose`
- `mmioDescend`
- `mmioOpenA`
- `mmioRead`
- `timeBeginPeriod`
- `timeGetTime`
- `timeKillEvent`
- `timeSetEvent`
- `waveInGetErrorTextA`
- `waveOutClose`
- `waveOutGetDevCapsA`
- `waveOutGetErrorTextA`
- `waveOutGetNumDevs`
- `waveOutOpen`
- `waveOutPause`
- `waveOutPrepareHeader`
- `waveOutReset`
- `waveOutRestart`
- `waveOutUnprepareHeader`
- `waveOutWrite`

### OLE32.DLL (5 函数)

- `CoCreateInstance`
- `CoInitialize`
- `CoTaskMemAlloc`
- `CoUninitialize`
- `StringFromGUID2`

### OLEAUT32.DLL (17 函数)

- `GetErrorInfo`
- `SafeArrayAccessData`
- `SafeArrayCreate`
- `SafeArrayGetElement`
- `SafeArrayGetLBound`
- `SafeArrayGetUBound`
- `SafeArrayPtrOfIndex`
- `SafeArrayPutElement`
- `SafeArrayUnaccessData`
- `SysAllocStringLen`
- `SysFreeString`
- `SysReAllocStringLen`
- `VariantChangeType`
- `VariantClear`
- `VariantCopy`
- `VariantCopyInd`
- `VariantInit`

### WTSAPI32.DLL (2 函数)

- `WTSUnRegisterSessionNotification`
- `WTSRegisterSessionNotification`

## 导出表

| 名称 | Ordinal | RVA | 虚拟地址 |
|---|---|---|---|
| `@$xp$10TCCalendar` | 123 | 0x1eb88c | 0x5eb88c |
| `@$xp$16Cspin@TCSpinEdit` | 58 | 0xa3c00 | 0x4a3c00 |
| `@$xp$17TPerformanceGraph` | 243 | 0x1f266c | 0x5f266c |
| `@$xp$18Cspin@TCSpinButton` | 60 | 0xa4208 | 0x4a4208 |
| `@$xp$23Cspin@TTimerSpeedButton` | 213 | 0x1f0d44 | 0x5f0d44 |
| `@$xp$27Cdiroutl@TCDirectoryOutline` | 145 | 0x1ed530 | 0x5ed530 |
| `@$xp$7TCGauge` | 167 | 0x1ef38c | 0x5ef38c |
| `@$xp$ynpqqrp14System@TObject$v` | 2 | 0x1b360 | 0x41b360 |
| `@$xp$ynpqqrp14System@TObjecti$v` | 146 | 0x1edc98 | 0x5edc98 |
| `@$xp$ynpqqrp14System@TObjectii$v` | 3 | 0x1b380 | 0x41b380 |
| `@$xp$ynpqqrp14System@TObjectiir17System@AnsiString$v` | 5 | 0x1b514 | 0x41b514 |
| `@$xp$ynpqqrp14System@TObjectiiro$v` | 6 | 0x1b754 | 0x41b754 |
| `@$xp$ynpqqrp14System@TObjectiirx11Types@TRect42System@%Set$t14Grids@Grids__3$iuc$0$iuc$2%$v` | 4 | 0x1b4b4 | 0x41b4b4 |
| `@$xp$ynpqqrp14System@TObjectiix17System@AnsiString$v` | 7 | 0x1b798 | 0x41b798 |
| `@@Ccalendr@Finalize` | 126 | 0x1ebf90 | 0x5ebf90 |
| `@@Ccalendr@Initialize` | 125 | 0x1ebf80 | 0x5ebf80 |
| `@@Cdiroutl@Finalize` | 148 | 0x1ede94 | 0x5ede94 |
| `@@Cdiroutl@Initialize` | 147 | 0x1ede84 | 0x5ede84 |
| `@@Cgauges@Finalize` | 169 | 0x1ef790 | 0x5ef790 |
| `@@Cgauges@Initialize` | 168 | 0x1ef780 | 0x5ef780 |
| `@@Cspin@Finalize` | 215 | 0x1f0ddc | 0x5f0ddc |
| `@@Cspin@Initialize` | 214 | 0x1f0dcc | 0x5f0dcc |
| `@@Frmclone@Finalize` | 53 | 0x6e640 | 0x46e640 |
| `@@Frmclone@Initialize` | 52 | 0x6e630 | 0x46e630 |
| `@@Iuicallselect@Finalize` | 55 | 0x9d7c8 | 0x49d7c8 |
| `@@Iuicallselect@Initialize` | 54 | 0x9d7b8 | 0x49d7b8 |
| `@@Iuircalldisp@Finalize` | 57 | 0xa2e24 | 0x4a2e24 |
| `@@Iuircalldisp@Initialize` | 56 | 0xa2e14 | 0x4a2e14 |
| `@@Iuirmessage@Finalize` | 64 | 0xa4720 | 0x4a4720 |
| `@@Iuirmessage@Initialize` | 63 | 0xa4710 | 0x4a4710 |
| `@@Perfgrap@Finalize` | 245 | 0x1f2930 | 0x5f2930 |
| `@@Perfgrap@Initialize` | 244 | 0x1f2920 | 0x5f2920 |
| `@@Unit1@Finalize` | 66 | 0xcb110 | 0x4cb110 |
| `@@Unit1@Initialize` | 65 | 0xcb0f8 | 0x4cb0f8 |
| `@@Unitafc@Finalize` | 51 | 0x6d86c | 0x46d86c |
| `@@Unitafc@Initialize` | 50 | 0x6d85c | 0x46d85c |
| `@@Unitagc@Finalize` | 9 | 0x62960 | 0x462960 |
| `@@Unitagc@Initialize` | 8 | 0x62948 | 0x462948 |
| `@@Unitant@Finalize` | 33 | 0x69738 | 0x469738 |
| `@@Unitant@Initialize` | 32 | 0x69720 | 0x469720 |
| `@@Unitapf@Finalize` | 11 | 0x636b8 | 0x4636b8 |
| `@@Unitapf@Initialize` | 10 | 0x636a0 | 0x4636a0 |
| `@@Unitbkin@Finalize` | 13 | 0x63d20 | 0x463d20 |
| `@@Unitbkin@Initialize` | 12 | 0x63d08 | 0x463d08 |
| `@@Unitcomp@Finalize` | 15 | 0x64360 | 0x464360 |
| `@@Unitcomp@Initialize` | 14 | 0x64348 | 0x464348 |
| `@@Unitcsql@Finalize` | 17 | 0x64798 | 0x464798 |
| `@@Unitcsql@Initialize` | 16 | 0x64788 | 0x464788 |
| `@@Unitcw@Finalize` | 19 | 0x65d08 | 0x465d08 |
| `@@Unitcw@Initialize` | 18 | 0x65cf0 | 0x465cf0 |
| `@@Unitcwkeyer@Finalize` | 80 | 0xf5b00 | 0x4f5b00 |
| `@@Unitcwkeyer@Initialize` | 79 | 0xf5af0 | 0x4f5af0 |
| `@@Unitdialdeviceselect@Finalize` | 98 | 0x108840 | 0x508840 |
| `@@Unitdialdeviceselect@Initialize` | 97 | 0x108830 | 0x508830 |
| `@@Unitdigisel@Finalize` | 21 | 0x66564 | 0x466564 |
| `@@Unitdigisel@Initialize` | 20 | 0x6654c | 0x46654c |
| `@@Unitdsplitofs@Finalize` | 82 | 0xf5f50 | 0x4f5f50 |
| `@@Unitdsplitofs@Initialize` | 81 | 0xf5f40 | 0x4f5f40 |
| `@@Unitdv@Finalize` | 23 | 0x66a6c | 0x466a6c |
| `@@Unitdv@Initialize` | 22 | 0x66a5c | 0x466a5c |
| `@@Unitfilter@Finalize` | 25 | 0x67cf4 | 0x467cf4 |
| `@@Unitfilter@Initialize` | 24 | 0x67cdc | 0x467cdc |
| `@@Unitfilteradj@Finalize` | 27 | 0x687d8 | 0x4687d8 |
| `@@Unitfilteradj@Initialize` | 26 | 0x687c0 | 0x4687c0 |
| `@@Unitinit@Finalize` | 68 | 0xcb33c | 0x4cb33c |
| `@@Unitinit@Initialize` | 67 | 0xcb32c | 0x4cb32c |
| `@@Unitmemch@Finalize` | 70 | 0xcd890 | 0x4cd890 |
| `@@Unitmemch@Initialize` | 69 | 0xcd878 | 0x4cd878 |
| `@@Unitmicset@Finalize` | 88 | 0xffd50 | 0x4ffd50 |
| `@@Unitmicset@Initialize` | 87 | 0xffd38 | 0x4ffd38 |
| `@@Unitmnotch2@Finalize` | 31 | 0x69124 | 0x469124 |
| `@@Unitmnotch2@Initialize` | 30 | 0x69114 | 0x469114 |
| `@@Unitmnotch@Finalize` | 29 | 0x68ddc | 0x468ddc |
| `@@Unitmnotch@Initialize` | 28 | 0x68dc4 | 0x468dc4 |
| `@@Unitmoni@Finalize` | 35 | 0x69d78 | 0x469d78 |
| `@@Unitmoni@Initialize` | 34 | 0x69d60 | 0x469d60 |
| `@@Unitnb@Finalize` | 39 | 0x6b3d4 | 0x46b3d4 |
| `@@Unitnb@Initialize` | 38 | 0x6b3bc | 0x46b3bc |
| `@@Unitnr@Finalize` | 37 | 0x6a568 | 0x46a568 |
| `@@Unitnr@Initialize` | 36 | 0x6a550 | 0x46a550 |
| `@@Unitoffset@Finalize` | 41 | 0x6b964 | 0x46b964 |
| `@@Unitoffset@Initialize` | 40 | 0x6b954 | 0x46b954 |
| `@@Unitopening@Finalize` | 72 | 0xce6c4 | 0x4ce6c4 |
| `@@Unitopening@Initialize` | 71 | 0xce6b4 | 0x4ce6b4 |
| `@@Unitportselect@Finalize` | 74 | 0xd658c | 0x4d658c |
| `@@Unitportselect@Initialize` | 73 | 0xd6574 | 0x4d6574 |
| `@@Unitpre@Finalize` | 43 | 0x6be58 | 0x46be58 |
| `@@Unitpre@Initialize` | 42 | 0x6be40 | 0x46be40 |
| `@@Unitpsk@Finalize` | 45 | 0x6c17c | 0x46c17c |
| `@@Unitpsk@Initialize` | 44 | 0x6c16c | 0x46c16c |
| `@@Unitreceiver@Finalize` | 76 | 0xe327c | 0x4e327c |
| `@@Unitreceiver@Initialize` | 75 | 0xe3264 | 0x4e3264 |
| `@@Unitreflv@Finalize` | 90 | 0x10050c | 0x50050c |
| `@@Unitreflv@Initialize` | 89 | 0x1004fc | 0x5004fc |
| `@@Unitremoteset@Finalize` | 86 | 0xff3f8 | 0x4ff3f8 |
| `@@Unitremoteset@Initialize` | 85 | 0xff3e8 | 0x4ff3e8 |
| `@@Unitrtty@Finalize` | 47 | 0x6c5b8 | 0x46c5b8 |
| `@@Unitrtty@Initialize` | 46 | 0x6c5a8 | 0x46c5a8 |
| `@@Unitscope@Finalize` | 100 | 0x10bab0 | 0x50bab0 |
| `@@Unitscope@Initialize` | 99 | 0x10ba98 | 0x50ba98 |
| `@@Unitscopeset@Finalize` | 96 | 0x10428c | 0x50428c |
| `@@Unitscopeset@Initialize` | 95 | 0x10427c | 0x50427c |
| `@@Unitshortcut@Finalize` | 78 | 0xe9ff0 | 0x4e9ff0 |
| `@@Unitshortcut@Initialize` | 77 | 0xe9fd8 | 0x4e9fd8 |
| `@@Unittone@Finalize` | 49 | 0x6d5d4 | 0x46d5d4 |
| `@@Unittone@Initialize` | 48 | 0x6d5bc | 0x46d5bc |
| `@@Unittonecontrol@Finalize` | 84 | 0xfef88 | 0x4fef88 |
| `@@Unittonecontrol@Initialize` | 83 | 0xfef70 | 0x4fef70 |
| `@@Unitvoice@Finalize` | 92 | 0x101b40 | 0x501b40 |
| `@@Unitvoice@Initialize` | 91 | 0x101b28 | 0x501b28 |
| `@@Unitvoiceedit@Finalize` | 94 | 0x102998 | 0x502998 |
| `@@Unitvoiceedit@Initialize` | 93 | 0x102988 | 0x502988 |
| `@Cdiroutl@TCDirectoryOutline@` | 251 | 0x576380 | 0x976380 |
| `@Cdiroutl@TCDirectoryOutline@$bctr$qqrp18Classes@TComponent` | 127 | 0x1ebfa0 | 0x5ebfa0 |
| `@Cdiroutl@TCDirectoryOutline@APointer` | 250 | 0x575c90 | 0x975c90 |
| `@Cdiroutl@TCDirectoryOutline@AssignCaseProc$qqrv` | 128 | 0x1ec100 | 0x5ec100 |
| `@Cdiroutl@TCDirectoryOutline@BuildOneLevel$qqrl` | 129 | 0x1ec148 | 0x5ec148 |
| `@Cdiroutl@TCDirectoryOutline@BuildSubTree$qqrl` | 131 | 0x1ec70c | 0x5ec70c |
| `@Cdiroutl@TCDirectoryOutline@BuildTree$qqrv` | 130 | 0x1ec61c | 0x5ec61c |
| `@Cdiroutl@TCDirectoryOutline@Change$qqrv` | 132 | 0x1ec76c | 0x5ec76c |
| `@Cdiroutl@TCDirectoryOutline@Click$qqrv` | 133 | 0x1ec79c | 0x5ec79c |
| `@Cdiroutl@TCDirectoryOutline@CreateWnd$qqrv` | 134 | 0x1ec80c | 0x5ec80c |
| `@Cdiroutl@TCDirectoryOutline@CurDir$qv` | 142 | 0x1ece28 | 0x5ece28 |
| `@Cdiroutl@TCDirectoryOutline@DriveToInt$qqrc` | 140 | 0x1eccec | 0x5eccec |
| `@Cdiroutl@TCDirectoryOutline@Expand$qqri` | 135 | 0x1ec8fc | 0x5ec8fc |
| `@Cdiroutl@TCDirectoryOutline@ForceCase$qqrrx17System@AnsiString` | 137 | 0x1ec974 | 0x5ec974 |
| `@Cdiroutl@TCDirectoryOutline@GetChildNamed$qqrrx17System@AnsiStringl` | 143 | 0x1ecf44 | 0x5ecf44 |
| `@Cdiroutl@TCDirectoryOutline@InvalidIndex` | 299 | 0x58d198 | 0x98d198 |
| `@Cdiroutl@TCDirectoryOutline@Loaded$qqrv` | 136 | 0x1ec938 | 0x5ec938 |
| `@Cdiroutl@TCDirectoryOutline@RootIndex` | 300 | 0x58d19c | 0x98d19c |
| `@Cdiroutl@TCDirectoryOutline@SetDirectory$qqr17System@AnsiString` | 138 | 0x1eca2c | 0x5eca2c |
| `@Cdiroutl@TCDirectoryOutline@SetDrive$qqrc` | 139 | 0x1ecbe0 | 0x5ecbe0 |
| `@Cdiroutl@TCDirectoryOutline@SetTextCase$qqr18Cdiroutl@TTextCase` | 141 | 0x1ecd60 | 0x5ecd60 |
| `@Cdiroutl@TCDirectoryOutline@WalkTree$qqrrx17System@AnsiString` | 144 | 0x1ed124 | 0x5ed124 |
| `@Cspin@TCSpinButton@` | 248 | 0x285684 | 0x685684 |
| `@Cspin@TCSpinButton@$bctr$qqrp18Classes@TComponent` | 170 | 0x1ef7a0 | 0x5ef7a0 |
| `@Cspin@TCSpinButton@$bdtr$qqrv` | 62 | 0xa462c | 0x4a462c |
| `@Cspin@TCSpinButton@AdjustSize$qqrrit1` | 172 | 0x1ef9b0 | 0x5ef9b0 |
| `@Cspin@TCSpinButton@BtnClick$qqrp14System@TObject` | 179 | 0x1efd4c | 0x5efd4c |
| `@Cspin@TCSpinButton@BtnMouseDown$qqrp14System@TObject21Controls@TMouseButton46System@%Set$t18Classes@Classes__1$iuc$0$iuc$6%ii` | 178 | 0x1efc70 | 0x5efc70 |
| `@Cspin@TCSpinButton@CreateButton$qqrv` | 171 | 0x1ef8c8 | 0x5ef8c8 |
| `@Cspin@TCSpinButton@Dispatch$qqrpv` | 61 | 0xa45f8 | 0x4a45f8 |
| `@Cspin@TCSpinButton@GetDownGlyph$qqrv` | 185 | 0x1eff60 | 0x5eff60 |
| `@Cspin@TCSpinButton@GetUpGlyph$qqrv` | 183 | 0x1efec8 | 0x5efec8 |
| `@Cspin@TCSpinButton@KeyDown$qqrrus46System@%Set$t18Classes@Classes__1$iuc$0$iuc$6%` | 177 | 0x1efbb8 | 0x5efbb8 |
| `@Cspin@TCSpinButton@Loaded$qqrv` | 182 | 0x1efe68 | 0x5efe68 |
| `@Cspin@TCSpinButton@SetBounds$qqriiii` | 173 | 0x1efa44 | 0x5efa44 |
| `@Cspin@TCSpinButton@SetDownGlyph$qqrp16Graphics@TBitmap` | 186 | 0x1eff84 | 0x5eff84 |
| `@Cspin@TCSpinButton@SetFocusBtn$qqrp23Cspin@TTimerSpeedButton` | 180 | 0x1efdb4 | 0x5efdb4 |
| `@Cspin@TCSpinButton@SetUpGlyph$qqrp16Graphics@TBitmap` | 184 | 0x1efeec | 0x5efeec |
| `@Cspin@TCSpinButton@WMGetDlgCode$qqrr20Messages@TWMNoParams` | 181 | 0x1efe4c | 0x5efe4c |
| `@Cspin@TCSpinButton@WMKillFocus$qqrr21Messages@TWMKillFocus` | 176 | 0x1efb34 | 0x5efb34 |
| `@Cspin@TCSpinButton@WMSetFocus$qqrr20Messages@TWMSetFocus` | 175 | 0x1efafc | 0x5efafc |
| `@Cspin@TCSpinButton@WMSize$qqrr16Messages@TWMSize` | 174 | 0x1efa88 | 0x5efa88 |
| `@Cspin@TCSpinEdit@` | 247 | 0x285504 | 0x685504 |
| `@Cspin@TCSpinEdit@$bctr$qqrp18Classes@TComponent` | 187 | 0x1efff8 | 0x5efff8 |
| `@Cspin@TCSpinEdit@$bdtr$qqrv` | 188 | 0x1f0190 | 0x5f0190 |
| `@Cspin@TCSpinEdit@CMEnter$qqrr20Messages@TWMNoParams` | 206 | 0x1f081c | 0x5f081c |
| `@Cspin@TCSpinEdit@CMExit$qqrr20Messages@TWMNoParams` | 202 | 0x1f064c | 0x5f064c |
| `@Cspin@TCSpinEdit@CheckValue$qqrl` | 205 | 0x1f07b8 | 0x5f07b8 |
| `@Cspin@TCSpinEdit@CreateParams$qqrr22Controls@TCreateParams` | 193 | 0x1f032c | 0x5f032c |
| `@Cspin@TCSpinEdit@CreateWnd$qqrv` | 194 | 0x1f0354 | 0x5f0354 |
| `@Cspin@TCSpinEdit@Dispatch$qqrpv` | 59 | 0xa41b8 | 0x4a41b8 |
| `@Cspin@TCSpinEdit@DownClick$qqrp14System@TObject` | 199 | 0x1f05bc | 0x5f05bc |
| `@Cspin@TCSpinEdit@GetChildren$qqrynpqqrp18Classes@TComponent$vp18Classes@TComponent` | 189 | 0x1f01f4 | 0x5f01f4 |
| `@Cspin@TCSpinEdit@GetMinHeight$qqrv` | 197 | 0x1f04d8 | 0x5f04d8 |
| `@Cspin@TCSpinEdit@GetValue$qqrv` | 203 | 0x1f0690 | 0x5f0690 |
| `@Cspin@TCSpinEdit@IsValidChar$qqrc` | 192 | 0x1f02a0 | 0x5f02a0 |
| `@Cspin@TCSpinEdit@KeyDown$qqrrus46System@%Set$t18Classes@Classes__1$iuc$0$iuc$6%` | 190 | 0x1f0208 | 0x5f0208 |
| `@Cspin@TCSpinEdit@KeyPress$qqrrc` | 191 | 0x1f025c | 0x5f025c |
| `@Cspin@TCSpinEdit@SetEditRect$qqrv` | 195 | 0x1f0370 | 0x5f0370 |
| `@Cspin@TCSpinEdit@SetValue$qqrl` | 204 | 0x1f075c | 0x5f075c |
| `@Cspin@TCSpinEdit@UpClick$qqrp14System@TObject` | 198 | 0x1f057c | 0x5f057c |
| `@Cspin@TCSpinEdit@WMCut$qqrr20Messages@TWMNoParams` | 201 | 0x1f0624 | 0x5f0624 |
| `@Cspin@TCSpinEdit@WMPaste$qqrr20Messages@TWMNoParams` | 200 | 0x1f05fc | 0x5f05fc |
| `@Cspin@TCSpinEdit@WMSize$qqrr16Messages@TWMSize` | 196 | 0x1f0404 | 0x5f0404 |
| `@Cspin@TTimerSpeedButton@` | 253 | 0x576c34 | 0x976c34 |
| `@Cspin@TTimerSpeedButton@$bctr$qqrp18Classes@TComponent` | 207 | 0x1f08a8 | 0x5f08a8 |
| `@Cspin@TTimerSpeedButton@$bdtr$qqrv` | 208 | 0x1f0964 | 0x5f0964 |
| `@Cspin@TTimerSpeedButton@MouseDown$qqr21Controls@TMouseButton46System@%Set$t18Classes@Classes__1$iuc$0$iuc$6%ii` | 209 | 0x1f09fc | 0x5f09fc |
| `@Cspin@TTimerSpeedButton@MouseUp$qqr21Controls@TMouseButton46System@%Set$t18Classes@Classes__1$iuc$0$iuc$6%ii` | 210 | 0x1f0b0c | 0x5f0b0c |
| `@Cspin@TTimerSpeedButton@Paint$qqrv` | 212 | 0x1f0bf4 | 0x5f0bf4 |
| `@Cspin@TTimerSpeedButton@TimerExpired$qqrp14System@TObject` | 211 | 0x1f0b54 | 0x5f0b54 |
| `@TCCalendar@` | 249 | 0x575ae4 | 0x975ae4 |
| `@TCCalendar@$bctr$qqrp18Classes@TComponent` | 101 | 0x1eab50 | 0x5eab50 |
| `@TCCalendar@Change$qqrv` | 102 | 0x1ead14 | 0x5ead14 |
| `@TCCalendar@ChangeMonth$qqri` | 116 | 0x1eb470 | 0x5eb470 |
| `@TCCalendar@Click$qqrv` | 103 | 0x1ead44 | 0x5ead44 |
| `@TCCalendar@DaysPerMonth$qqrii` | 105 | 0x1eae5c | 0x5eae5c |
| `@TCCalendar@DaysThisMonth$qqrv` | 106 | 0x1eaeac | 0x5eaeac |
| `@TCCalendar@Dispatch$qqrpv` | 124 | 0x1ebe38 | 0x5ebe38 |
| `@TCCalendar@DrawCell$qqriirx11Types@TRect42System@%Set$t14Grids@Grids__3$iuc$0$iuc$2%` | 107 | 0x1eaee4 | 0x5eaee4 |
| `@TCCalendar@GetCellText$qqrii` | 108 | 0x1eb00c | 0x5eb00c |
| `@TCCalendar@GetDateElement$qqri` | 112 | 0x1eb284 | 0x5eb284 |
| `@TCCalendar@IsLeapYear$qqri` | 104 | 0x1eae10 | 0x5eae10 |
| `@TCCalendar@NextMonth$qqrv` | 118 | 0x1eb5a4 | 0x5eb5a4 |
| `@TCCalendar@NextYear$qqrv` | 119 | 0x1eb5bc | 0x5eb5bc |
| `@TCCalendar@PrevMonth$qqrv` | 117 | 0x1eb58c | 0x5eb58c |
| `@TCCalendar@PrevYear$qqrv` | 120 | 0x1eb638 | 0x5eb638 |
| `@TCCalendar@SeTCCalendarDate$qqr16System@TDateTime` | 110 | 0x1eb210 | 0x5eb210 |
| `@TCCalendar@SelectCell$qqrii` | 109 | 0x1eb150 | 0x5eb150 |
| `@TCCalendar@SetDateElement$qqrii` | 113 | 0x1eb2e4 | 0x5eb2e4 |
| `@TCCalendar@SetStartOfWeek$qqrs` | 114 | 0x1eb3cc | 0x5eb3cc |
| `@TCCalendar@SetUseCurrentDate$qqro` | 115 | 0x1eb424 | 0x5eb424 |
| `@TCCalendar@StoreCalendarDate$qqrv` | 111 | 0x1eb268 | 0x5eb268 |
| `@TCCalendar@UpdateCalendar$qqrv` | 121 | 0x1eb6b4 | 0x5eb6b4 |
| `@TCCalendar@WMSize$qqrr16Messages@TWMSize` | 122 | 0x1eb7a4 | 0x5eb7a4 |
| `@TCGauge@` | 252 | 0x576854 | 0x976854 |
| `@TCGauge@$bctr$qqrp18Classes@TComponent` | 149 | 0x1ee008 | 0x5ee008 |
| `@TCGauge@AddProgress$qqrl` | 166 | 0x1ef200 | 0x5ef200 |
| `@TCGauge@GetPercentDone$qqrv` | 150 | 0x1ee148 | 0x5ee148 |
| `@TCGauge@Paint$qqrv` | 151 | 0x1ee180 | 0x5ee180 |
| `@TCGauge@PaintAsBar$qqrp16Graphics@TBitmaprx11Types@TRect` | 155 | 0x1ee924 | 0x5ee924 |
| `@TCGauge@PaintAsNeedle$qqrp16Graphics@TBitmaprx11Types@TRect` | 157 | 0x1eec5c | 0x5eec5c |
| `@TCGauge@PaintAsNothing$qqrp16Graphics@TBitmaprx11Types@TRect` | 154 | 0x1ee8e8 | 0x5ee8e8 |
| `@TCGauge@PaintAsPie$qqrp16Graphics@TBitmaprx11Types@TRect` | 156 | 0x1eea8c | 0x5eea8c |
| `@TCGauge@PaintAsText$qqrp16Graphics@TBitmaprx11Types@TRect` | 153 | 0x1ee6dc | 0x5ee6dc |
| `@TCGauge@PaintBackground$qqrp16Graphics@TBitmap` | 152 | 0x1ee65c | 0x5ee65c |
| `@TCGauge@SeTCGaugeKind$qqr11TCGaugeKind` | 158 | 0x1eee7c | 0x5eee7c |
| `@TCGauge@SetBackColor$qqr15Graphics@TColor` | 162 | 0x1eef4c | 0x5eef4c |
| `@TCGauge@SetBorderStyle$qqr22Forms@TFormBorderStyle` | 160 | 0x1eeee4 | 0x5eeee4 |
| `@TCGauge@SetForeColor$qqr15Graphics@TColor` | 161 | 0x1eef18 | 0x5eef18 |
| `@TCGauge@SetMaxValue$qqrl` | 164 | 0x1ef084 | 0x5ef084 |
| `@TCGauge@SetMinValue$qqrl` | 163 | 0x1eef80 | 0x5eef80 |
| `@TCGauge@SetProgress$qqrl` | 165 | 0x1ef180 | 0x5ef180 |
| `@TCGauge@SetShowText$qqro` | 159 | 0x1eeeb0 | 0x5eeeb0 |
| `@TPerformanceGraph@` | 254 | 0x576fb4 | 0x976fb4 |
| `@TPerformanceGraph@$bctr$qqrp18Classes@TComponent` | 216 | 0x1f0dec | 0x5f0dec |
| `@TPerformanceGraph@$bdtr$qqrv` | 218 | 0x1f102c | 0x5f102c |
| `@TPerformanceGraph@DataPoint$qqr15Graphics@TColorl` | 233 | 0x1f1808 | 0x5f1808 |
| `@TPerformanceGraph@DisplayPoints$qqrl` | 235 | 0x1f1c54 | 0x5f1c54 |
| `@TPerformanceGraph@FirstY$qqrv` | 238 | 0x1f1f14 | 0x5f1f14 |
| `@TPerformanceGraph@GetBandCount$qqrv` | 217 | 0x1f0ff0 | 0x5f0ff0 |
| `@TPerformanceGraph@Initialize$qqrl` | 219 | 0x1f10c8 | 0x5f10c8 |
| `@TPerformanceGraph@LastY$qqri` | 236 | 0x1f1dc0 | 0x5f1dc0 |
| `@TPerformanceGraph@NextY$qqri` | 239 | 0x1f1f28 | 0x5f1f28 |
| `@TPerformanceGraph@Paint$qqrv` | 220 | 0x1f1324 | 0x5f1324 |
| `@TPerformanceGraph@PaintBar$qqr15Graphics@TColorll` | 231 | 0x1f1624 | 0x5f1624 |
| `@TPerformanceGraph@PaintLine$qqr15Graphics@TColorll` | 232 | 0x1f170c | 0x5f170c |
| `@TPerformanceGraph@ReallocHistory$qqrv` | 237 | 0x1f1de8 | 0x5f1de8 |
| `@TPerformanceGraph@Replay$qqrv` | 242 | 0x1f20f0 | 0x5f20f0 |
| `@TPerformanceGraph@RoundUp$qqrll` | 227 | 0x1f153c | 0x5f153c |
| `@TPerformanceGraph@ScrollGraph$qqrv` | 234 | 0x1f1a9c | 0x5f1a9c |
| `@TPerformanceGraph@SetBackColor$qqr15Graphics@TColor` | 223 | 0x1f1414 | 0x5f1414 |
| `@TPerformanceGraph@SetForeColor$qqr15Graphics@TColor` | 222 | 0x1f13e0 | 0x5f13e0 |
| `@TPerformanceGraph@SetGradient$qqrl` | 228 | 0x1f1570 | 0x5f1570 |
| `@TPerformanceGraph@SetGraphKind$qqr10TGraphKind` | 221 | 0x1f13ac | 0x5f13ac |
| `@TPerformanceGraph@SetGridSize$qqrl` | 224 | 0x1f1448 | 0x5f1448 |
| `@TPerformanceGraph@SetGridlines$qqro` | 229 | 0x1f15a4 | 0x5f15a4 |
| `@TPerformanceGraph@SetPenWidth$qqrl` | 230 | 0x1f15d8 | 0x5f15d8 |
| `@TPerformanceGraph@SetScale$qqrl` | 226 | 0x1f14d0 | 0x5f14d0 |
| `@TPerformanceGraph@SetStepSize$qqrl` | 225 | 0x1f1488 | 0x5f1488 |
| `@TPerformanceGraph@ShiftY$qqrv` | 241 | 0x1f2068 | 0x5f2068 |
| `@TPerformanceGraph@Update$qqrv` | 240 | 0x1f1f64 | 0x5f1f64 |
| `_CallSelectPanel` | 278 | 0x581fd0 | 0x981fd0 |
| `_Form1` | 281 | 0x584f30 | 0x984f30 |
| `_FormAfc` | 276 | 0x57df8c | 0x97df8c |
| `_FormAgc` | 255 | 0x57dee4 | 0x97dee4 |
| `_FormAnt` | 267 | 0x57df44 | 0x97df44 |
| `_FormApf` | 256 | 0x57deec | 0x97deec |
| `_FormBkin` | 257 | 0x57def4 | 0x97def4 |
| `_FormClone` | 277 | 0x57df94 | 0x97df94 |
| `_FormComp` | 258 | 0x57defc | 0x97defc |
| `_FormCsql` | 259 | 0x57df04 | 0x97df04 |
| `_FormCw` | 260 | 0x57df0c | 0x97df0c |
| `_FormCwKeyer` | 288 | 0x588ec8 | 0x988ec8 |
| `_FormDSplitOfs` | 289 | 0x588ee8 | 0x988ee8 |
| `_FormDialDeviceSelect` | 297 | 0x589698 | 0x989698 |
| `_FormDigisel` | 261 | 0x57df14 | 0x97df14 |
| `_FormDv` | 262 | 0x57df1c | 0x97df1c |
| `_FormFilter` | 263 | 0x57df24 | 0x97df24 |
| `_FormFilterAdj` | 264 | 0x57df2c | 0x97df2c |
| `_FormInit` | 282 | 0x5867d4 | 0x9867d4 |
| `_FormMNotch` | 265 | 0x57df34 | 0x97df34 |
| `_FormMNotch2` | 266 | 0x57df3c | 0x97df3c |
| `_FormMemCH` | 283 | 0x5867dc | 0x9867dc |
| `_FormMicSet` | 292 | 0x588f14 | 0x988f14 |
| `_FormMoni` | 268 | 0x57df4c | 0x97df4c |
| `_FormNb` | 270 | 0x57df5c | 0x97df5c |
| `_FormNr` | 269 | 0x57df54 | 0x97df54 |
| `_FormOffset` | 271 | 0x57df64 | 0x97df64 |
| `_FormOpening` | 284 | 0x5867e4 | 0x9867e4 |
| `_FormPortSelect` | 285 | 0x5867ec | 0x9867ec |
| `_FormPre` | 272 | 0x57df6c | 0x97df6c |
| `_FormPsk` | 273 | 0x57df74 | 0x97df74 |
| `_FormReceiver` | 286 | 0x5867f8 | 0x9867f8 |
| `_FormRefLv` | 293 | 0x588f1c | 0x988f1c |
| `_FormRemoteSet` | 291 | 0x588f0c | 0x988f0c |
| `_FormRtty` | 274 | 0x57df7c | 0x97df7c |
| `_FormScope` | 298 | 0x5896a0 | 0x9896a0 |
| `_FormScopeSet` | 296 | 0x588f34 | 0x988f34 |
| `_FormShortCut` | 287 | 0x586a18 | 0x986a18 |
| `_FormTone` | 275 | 0x57df84 | 0x97df84 |
| `_FormToneControl` | 290 | 0x588f04 | 0x988f04 |
| `_FormVoice` | 294 | 0x588f24 | 0x988f24 |
| `_FormVoiceEdit` | 295 | 0x588f2c | 0x988f2c |
| `_MessagePanel` | 280 | 0x581fe0 | 0x981fe0 |
| `_ReceiveCallPanel` | 279 | 0x581fd8 | 0x981fd8 |
| `__GetExceptDLLinfo` | 1 | 0x17f1 | 0x4017f1 |
| `___CPPdebugHook` | 246 | 0x217098 | 0x617098 |

## 导出函数反汇编（前 20 条指令）

### `@$xp$10TCCalendar` (RVA: 0x1eb88c)

```asm
  0x5eb88c:  pop es  ; 07
  0x5eb88d:  or dl, byte ptr [ebx + eax*2 + 0x43]  ; 0a544343
  0x5eb891:  popal  ; 61
  0x5eb892:  insb byte ptr es:[edi], dx  ; 6c
  0x5eb893:  outsb dx, byte ptr gs:[esi]  ; 656e
  0x5eb895:  popal  ; 6461
  0x5eb897:  jb 0x5eb87d  ; 72e4
  0x5eb899:  pop edx  ; 5a
  0x5eb89a:  xchg edi, eax  ; 97
  0x5eb89b:  add byte ptr [eax], al  ; 0000
  0x5eb89d:  add al, 0x56  ; 0456
  0x5eb89f:  add byte ptr [0x63630800], dh  ; 003500086363
  0x5eb8a5:  popal  ; 61
  0x5eb8a6:  insb byte ptr es:[edi], dx  ; 6c
  0x5eb8a7:  outsb dx, byte ptr gs:[esi]  ; 656e
  0x5eb8a9:  jb 0x5eb8d4  ; 647228
  0x5eb8ac:  add ah, cl  ; 00cc
  0x5eb8ae:  mov al, 0x41  ; b041
  0x5eb8b0:  add byte ptr [ebx], bl  ; 005b00
  0x5eb8b3:  add bh, bh  ; 00ff
```

### `@$xp$16Cspin@TCSpinEdit` (RVA: 0xa3c00)

```asm
  0x4a3c00:  pop es  ; 07
  0x4a3c01:  or dl, byte ptr [ebx + eax*2 + 0x53]  ; 0a544353
  0x4a3c05:  jo 0x4a3c70  ; 7069
  0x4a3c07:  outsb dx, byte ptr [esi]  ; 6e
  0x4a3c08:  inc ebp  ; 45
  0x4a3c09:  imul esi, dword ptr fs:[esp + eax + 0x55], 0x72cc0068  ; 64697404556800cc72
  0x4a3c12:  push esp  ; 54
  0x4a3c13:  add byte ptr [0x75690b00], dh  ; 0035000b6975
  0x4a3c19:  imul edx, dword ptr [edx + 0x4d], 0x61737365  ; 69524d65737361
  0x4a3c20:  sub byte ptr gs:[bx + si], al  ; 67652800
  0x4a3c24:  and al, 0xb1  ; 24b1
  0x4a3c26:  inc ecx  ; 41
  0x4a3c27:  add byte ptr [ecx], ah  ; 006100
  0x4a3c2a:  add bh, bh  ; 00ff
  0x4a3c2c:  adc cl, bl  ; 10d9
  0x4a3c2e:  pop eax  ; 58
  0x4a3c2f:  add byte ptr [edx + ebx*8], ch  ; 002cda
  0x4a3c32:  pop eax  ; 58
  0x4a3c33:  add byte ptr [eax], al  ; 0000
  0x4a3c35:  add byte ptr [eax], al  ; 0000
```

### `@$xp$17TPerformanceGraph` (RVA: 0x1f266c)

```asm
  0x5f266c:  pop es  ; 07
  0x5f266d:  adc dword ptr [eax + edx*2 + 0x65], edx  ; 11545065
  0x5f2671:  jb 0x5f26d9  ; 7266
  0x5f2673:  outsd dx, dword ptr [esi]  ; 6f
  0x5f2674:  jb 0x5f26e3  ; 726d
  0x5f2676:  popal  ; 61
  0x5f2677:  outsb dx, byte ptr [esi]  ; 6e
  0x5f2678:  arpl word ptr [ebp + 0x47], sp  ; 636547
  0x5f267b:  jb 0x5f26de  ; 7261
  0x5f267d:  jo 0x5f26e7  ; 7068
  0x5f267f:  mov ah, 0x6f  ; b46f
  0x5f2681:  xchg edi, eax  ; 97
  0x5f2682:  add byte ptr [eax + 0x1e0058a5], cl  ; 0088a558001e
  0x5f2688:  add byte ptr [eax], cl  ; 0008
  0x5f268a:  jo 0x5f26f1  ; 7065
  0x5f268c:  jb 0x5f26f4  ; 7266
  0x5f268e:  jb 0x5f26f2  ; 677261
  0x5f2691:  jo 0x5f26a4  ; 7011
  0x5f2693:  add ah, cl  ; 00cc
  0x5f2695:  mov al, 0x41  ; b041
```

### `@$xp$18Cspin@TCSpinButton` (RVA: 0xa4208)

```asm
  0x4a4208:  pop es  ; 07
  0x4a4209:  or al, 0x54  ; 0c54
  0x4a420b:  inc ebx  ; 43
  0x4a420c:  push ebx  ; 53
  0x4a420d:  jo 0x4a4278  ; 7069
  0x4a420f:  outsb dx, byte ptr [esi]  ; 6e
  0x4a4210:  inc edx  ; 42
  0x4a4211:  jne 0x4a4287  ; 7574
  0x4a4213:  je 0x4a4284  ; 746f
  0x4a4215:  outsb dx, byte ptr [esi]  ; 6e
  0x4a4216:  test byte ptr [esi + 0x68], dl  ; 845668
  0x4a4219:  add byte ptr [eax - 0x5c], ch  ; 0068a4
  0x4a421c:  pop eax  ; 58
  0x4a421d:  add byte ptr [eax], ch  ; 0028
  0x4a421f:  add byte ptr [ebx], cl  ; 000b
  0x4a4221:  imul esi, dword ptr [ebp + 0x69], 0x73654d52  ; 697569524d6573
  0x4a4228:  jae 0x4a428b  ; 7361
  0x4a422a:  sbb eax, dword ptr gs:[bx + si]  ; 67651b00
  0x4a422e:  int3  ; cc
  0x4a422f:  mov al, 0x41  ; b041
```

### `@$xp$23Cspin@TTimerSpeedButton` (RVA: 0x1f0d44)

```asm
  0x5f0d44:  pop es  ; 07
  0x5f0d45:  adc dword ptr [esp + edx*2 + 0x69], edx  ; 11545469
  0x5f0d49:  insd dword ptr es:[edi], dx  ; 6d
  0x5f0d4a:  jb 0x5f0da0  ; 657253
  0x5f0d4d:  jo 0x5f0db4  ; 7065
  0x5f0d4f:  inc edx  ; 656442
  0x5f0d52:  jne 0x5f0dc8  ; 7574
  0x5f0d54:  je 0x5f0dc5  ; 746f
  0x5f0d56:  outsb dx, byte ptr [esi]  ; 6e
  0x5f0d57:  xor al, 0x6c  ; 346c
  0x5f0d59:  xchg edi, eax  ; 97
  0x5f0d5a:  add ah, cl  ; 00cc
  0x5f0d5c:  int 0x53  ; cd53
  0x5f0d5e:  add byte ptr [0x73630500], ch  ; 002d00056373
  0x5f0d64:  jo 0x5f0dcf  ; 7069
  0x5f0d66:  outsb dx, byte ptr [esi]  ; 6e
  0x5f0d67:  add byte ptr [eax], al  ; 0000
  0x5f0d69:  nop  ; 90
  0x5f0d6a:  nop  ; 90
  0x5f0d6b:  nop  ; 90
```

### `@$xp$27Cdiroutl@TCDirectoryOutline` (RVA: 0x1ed530)

```asm
  0x5ed530:  pop es  ; 07
  0x5ed531:  adc dl, byte ptr [ebx + eax*2 + 0x44]  ; 12544344
  0x5ed535:  imul esi, dword ptr [edx + 0x65], 0x726f7463  ; 69726563746f72
  0x5ed53c:  jns 0x5ed58d  ; 794f
  0x5ed53e:  jne 0x5ed5b4  ; 7574
  0x5ed540:  insb byte ptr es:[edi], dx  ; 6c
  0x5ed541:  imul ebp, dword ptr [esi + 0x65], 0x976380  ; 696e6580639700
  0x5ed548:  cmp byte ptr [edi + ebx*2], ch  ; 382c5f
  0x5ed54b:  add byte ptr [eax + eax], bh  ; 003c00
  0x5ed54e:  or byte ptr [ebx + 0x64], ah  ; 086364
  0x5ed551:  imul esi, dword ptr [edx + 0x6f], 0x2f6c7475  ; 69726f75746c2f
  0x5ed558:  add byte ptr [ebx + esi*4 + 0x41], bl  ; 005cb341
  0x5ed55c:  add byte ptr [eax + 3], dl  ; 005003
  0x5ed55f:  add bh, bh  ; 00ff
  0x5ed561:  push eax  ; 50
  0x5ed562:  add eax, dword ptr [eax]  ; 0300
  0x5ed564:  inc dword ptr [ecx]  ; ff01
  0x5ed566:  add byte ptr [eax], al  ; 0000
  0x5ed568:  add byte ptr [eax], al  ; 0000
  0x5ed56a:  add byte ptr [eax], al  ; 0000
```

### `@$xp$7TCGauge` (RVA: 0x1ef38c)

```asm
  0x5ef38c:  pop es  ; 07
  0x5ef38d:  pop es  ; 07
  0x5ef38e:  push esp  ; 54
  0x5ef38f:  inc ebx  ; 43
  0x5ef390:  inc edi  ; 47
  0x5ef391:  popal  ; 61
  0x5ef392:  jne 0x5ef3fb  ; 7567
  0x5ef394:  push esp  ; 6554
  0x5ef396:  push 0xa5880097  ; 68970088a5
  0x5ef39b:  pop eax  ; 58
  0x5ef39c:  add byte ptr [ecx], ah  ; 0021
  0x5ef39e:  add byte ptr [edi], al  ; 0007
  0x5ef3a0:  arpl word ptr [edi + 0x61], sp  ; 636761
  0x5ef3a3:  jne 0x5ef40c  ; 7567
  0x5ef3a5:  jae 0x5ef3bc  ; 657314
  0x5ef3a8:  add ah, cl  ; 00cc
  0x5ef3aa:  mov al, 0x41  ; b041
  0x5ef3ac:  add byte ptr [ebx], bl  ; 005b00
  0x5ef3af:  add bh, bh  ; 00ff
  0x5ef3b1:  pushfd  ; 9c
```

### `@$xp$ynpqqrp14System@TObject$v` (RVA: 0x1b360)

```asm
  0x41b360:  or byte ptr [eax], al  ; 0800
  0x41b362:  add byte ptr [ecx], al  ; 0001
  0x41b364:  or byte ptr [esi], al  ; 0806
  0x41b366:  push ebx  ; 53
  0x41b367:  outsb dx, byte ptr gs:[esi]  ; 656e
  0x41b369:  jb 0x41b374  ; 64657207
  0x41b36d:  push esp  ; 54
  0x41b36e:  dec edi  ; 4f
  0x41b36f:  bound ebp, qword ptr [edx + 0x65]  ; 626a65
  0x41b372:  arpl word ptr [eax + eax], si  ; 63740000
  0x41b376:  add byte ptr [eax], al  ; 0000
  0x41b378:  add byte ptr [eax], al  ; 0000
  0x41b37a:  add byte ptr [eax], al  ; 0000
  0x41b37c:  xor byte ptr [ebx + 0x80041], 0  ; 80b34100080000
  0x41b383:  add ecx, dword ptr [eax]  ; 0308
  0x41b385:  push es  ; 06
  0x41b386:  push ebx  ; 53
  0x41b387:  outsb dx, byte ptr gs:[esi]  ; 656e
  0x41b389:  jb 0x41b394  ; 64657207
  0x41b38d:  push esp  ; 54
```

### `@$xp$ynpqqrp14System@TObjecti$v` (RVA: 0x1edc98)

```asm
  0x5edc98:  or byte ptr [eax], al  ; 0800
  0x5edc9a:  add byte ptr [edx], al  ; 0002
  0x5edc9c:  or byte ptr [esi], al  ; 0806
  0x5edc9e:  push ebx  ; 53
  0x5edc9f:  outsb dx, byte ptr gs:[esi]  ; 656e
  0x5edca1:  jb 0x5edcac  ; 64657207
  0x5edca5:  push esp  ; 54
  0x5edca6:  dec edi  ; 4f
  0x5edca7:  bound ebp, qword ptr [edx + 0x65]  ; 626a65
  0x5edcaa:  arpl word ptr [eax + eax + 5], si  ; 63740005
  0x5edcae:  dec ecx  ; 49
  0x5edcaf:  outsb dx, byte ptr [esi]  ; 6e
  0x5edcb0:  js 0x5edcb7  ; 64657803
  0x5edcb4:  imul ebp, dword ptr [esi + 0x74], 0  ; 696e7400000000
  0x5edcbb:  add byte ptr [eax], al  ; 0000
  0x5edcbd:  add byte ptr [eax], al  ; 0000
  0x5edcbf:  nop  ; 90
```

### `@$xp$ynpqqrp14System@TObjectii$v` (RVA: 0x1b380)

```asm
  0x41b380:  or byte ptr [eax], al  ; 0800
  0x41b382:  add byte ptr [ebx], al  ; 0003
  0x41b384:  or byte ptr [esi], al  ; 0806
  0x41b386:  push ebx  ; 53
  0x41b387:  outsb dx, byte ptr gs:[esi]  ; 656e
  0x41b389:  jb 0x41b394  ; 64657207
  0x41b38d:  push esp  ; 54
  0x41b38e:  dec edi  ; 4f
  0x41b38f:  bound ebp, qword ptr [edx + 0x65]  ; 626a65
  0x41b392:  arpl word ptr [eax + eax + 9], si  ; 63740009
  0x41b396:  inc esi  ; 46
  0x41b397:  jb 0x41b408  ; 726f
  0x41b399:  insd dword ptr es:[edi], dx  ; 6d
  0x41b39a:  dec ecx  ; 49
  0x41b39b:  outsb dx, byte ptr [esi]  ; 6e
  0x41b39c:  js 0x41b3a3  ; 64657803
  0x41b3a0:  imul ebp, dword ptr [esi + 0x74], 0x6f540700  ; 696e740007546f
  0x41b3a7:  dec ecx  ; 49
  0x41b3a8:  outsb dx, byte ptr [esi]  ; 6e
  0x41b3a9:  js 0x41b3b0  ; 64657803
```


> 其余 290 个函数的反汇编见 JSON 输出

## 字符串分类

### ci_v_commands (71 条)

- `CCIVBase *`
- `CCIVObject *[2]`
- `CCIVObject *`
- `CCIVObject`
- `CCIVBase`
- `CCIVCtrl`
- `CCIVCtrl *`
- `CCIVMain *`
- `CCIVMain *[2]`
- `CCIVMain`
- `deque<stRxCivData,allocator<stRxCivData> > *`
- `std::deque<stRxCivData,std::allocator<stRxCivData> >`
- `std::_Deque_val<stRxCivData,std::allocator<stRxCivData> >`
- `std::_Deque_map<stRxCivData,std::allocator<stRxCivData> >`
- `stCivIntfData`
- `Frequency`P^`
- `\CivCtrl.dll`
- `civOpen`
- `civSetAddress`
- `civSetAddPreamble`
- `civSetCivTot`
- `civClose`
- `civSend`
- `civGetRecvSize`
- `civRecv`
- `civIsSendEnable`
- `civSetRetryFA`
- `civSetWaitTime`
- `civResetOthAnsCount`
- `civGetOthAnsCount`
- `civResetRxByteCount`
- `civGetRxByteCount`
- `civSetConType`
- `civGetConType`
- `#GI_Sys_TransceiverTitle`
- `  Checking can result in a frequency deviation.`
- `Write to transceiver. Are you sure?`
- `Turn the transceiver power off and on to use`
- `the transceiver under its new conditions.`
- `No answer from transceiver.`
- `Transceiver version does not match.`
- `Connected transceiver is not compatible model.`
- ` - transceiver power is ON.`
- ` - Appropriate cloning software for the transceiver is being used.`
- ` - The revision number of the transceiver.`
- `The transceiver cannot be programmed with the current setting.`
- `Settings don't match with transceiver's version.`
- `Some settings will be changed to suit to the transceiver.`
- `If the actual connection is different from the "Connection" item, the transceiver cannot be remotely turned ON.`
- `|{WH^-(Font=,,,%120,,fsBold,)(%CL_CloneTop_Transceiver)}\_    Cloning Software for IC-0000    \_`
- ... 其余 21 条

### serial_port (280 条)

- `Classes::TComponent`
- `iuiSh_Common *`
- `Comctrls::TStatusBar`
- `iuiSh_Common`
- `Comctrls::TCustomStatusBar`
- `Dialogs::TCommonDialog`
- `TComboBox *`
- `Stdctrls::TComboBox`
- `Stdctrls::TCustomComboBox`
- `Stdctrls::TCustomCombo`
- `Comctrls::TTreeView`
- `Comctrls::TTreeNodes`
- `Comctrls::TCustomTreeView`
- `TFormComp *`
- `TFormComp`
- `UnitComp`
- `lcdIF_lcd_tag::lcdIF_tuner_com_tag`
- `lcdIF_lcd_tag::lcdIF_tuner_com_tag::lcdIF_visible_maxtxpwr_tag`
- `TFormPortSelect *`
- `TFormPortSelect`
- `TFormPortSelectD1i`
- `UnitPortSelect`
- `comctl32.dll`
- `TCustomComboBoxStrings`
- `TCustomComboBoxStringsX`
- `TCustomCombo`
- `TCustomCombop`
- `TComboBoxStyle`
- `TCustomComboBox`
- `TComboBox`
- `AutoComplete`
- `AutoCompleteDelay`
- `TComboBoxStrings`
- `COMBOBOX`
- `TListCompareEvent`
- `OnCompare,`
- `VertScrollBar`
- `Command`
- `TCommonDialog`
- `commdlg_help`
- `commdlg_FindReplace`
- `ImmSetCompositionWindow`
- `ImmSetCompositionFontA`
- `ImmGetCompositionStringA`
- `ComCtrls`
- `ComCtrlsH`
- `ComCtrls#`
- `ComCtrls6`
- `ComCtrls,`
- `TTVCompareEvent`
- ... 其余 230 条

### network (114 条)

- `clWebIndianRed`
- `clWebIndigo`
- `poProportional`
- `Proportional`
- `TabIndex`
- `MSH_WHEELSUPPORT_MSG`
- `#GI_Sys_Dialog_FExport`
- `No Printer is connected.`
- `Connect a printer.`
- ` - USB cable connections.`
- `#GI_Mess_Confirm_ImportFile`
- `Import from the file.`
- `#GI_Mess_Confirm_ImportFile_All_Rpt`
- `#GI_Mess_Import_OpenErr`
- `#GI_Mess_Import_TitleErr`
- `#GI_Mess_Import_NoData`
- `#GI_Mess_Import_NoChSpace`
- `Some channels are not imported.`
- `#GI_Mess_Import_Discard`
- `#GI_Mess_Import_Correct`
- `#GI_Mess_ImportGps_NoData`
- `#GI_Mess_ImportGps_NoChSpace`
- `#GI_Mess_ImportGps_Discard`
- `#GI_Mess_ImportGps_Correct`
- `#GI_AppMess_Connect_PwrCmd`
- `When using the Remote power ON/OFF function, select %s in the "Connection" item.`
- `First, confirm that the actual connection is the same as the "Connection" item setting, and then click [OK]. `
- `#GI_AppMess_Connect_PwrCmd_Conjuction`
- `#GI_AppMess_Connect_PwrCmd_NowSet`
- `Current Connection Setting : `
- `#GI_AppMess_Connect_SetAudio2Ch_WhenAudio1ChAndDual`
- `#GI_AppMess_Connect_SetAudio1Ch_WhenAudio2ChAndSingle`
- `When the radio is connected to a Server PC and its USB audio microphone is set to 1 channel on the Windows "Sound Setting" screen, the receive audio for the Sub band cannot be output.`
- `#GI_Sheet_Top_Support`
- `Connect O&N`
- `Connect &OFF`
- `&Connect Setting...`
- `&Import...`
- `&Export...`
- `Connect ON/OFF`
- `Connect Setting`
- `#GI_Main_PortErr`
- `#GI_Main_Port_Setting_Label`
- `IC-PW1 is connected.`
- `Connection`
- ` +&Import...`
- `{(%CL_Menu_File_Import)}`
- ` +&Export...`
- `{(%CL_Menu_File_Export)}`
- ` +&Import`
- ... 其余 64 条

### file_paths (3978 条)

- `t\It}`
- `n}/3`
- `C\^[]`
- `VisibleRowCount\`
- `OnContextPopup\`
- `OnEndDrag\`
- `OnEnter\`
- `OnStartDrag\`
- `OnTopLeftChanged\`
- `C\j2`
- `u\hh`
- `u\h``
- `u\hx`
- `Q8G;{\~`
- `P\;PX}`
- `CX;C\u`
- `C\PS`
- `h/&d`
- `/uAj`
- `{(/t'`
- `It/It`
- `;P8t\`
- `Rh\0`
- `jJj/jQR`
- `j]j/Q`
- `Ht#Ht/`
- `/t%3`
- `/3Mh`
- `O/QhPR`
- `h\1h`
- `h/5h`
- `Visible\`
- `OnChange\`
- `OnClick\`
- `Ctl3D\`
- `TabStop\`
- `T$\Y`
- `r2Jt/`
- `TFormMemCH\`
- `jrj/`
- `h\Ci`
- `h\Fi`
- `h\Ii`
- `jrjrj\`
- `h\Pi`
- `h\Si`
- `h\Xi`
- `j:h/`
- `jqh\Yi`
- `76543210/`
- ... 其余 3928 条

### registry (10 条)

- `TRegistry *[2]`
- `TRegistry *`
- `Registry::TRegistry`
- `ERegistryException`
- `TRegistryS`
- `||{($eWh)(%CL_RS_NOTCHKey_SSB)}`
- `||{($eWh)(%CL_RS_NOTCHKey_AM)}`
- `CL_RS_NOTCHKey_SSB`
- `CL_RS_NOTCHKey_AM`
- `RegFlushKey`

### audio (121 条)

- `TVoicePlay *`
- `TVoicePlayCore *`
- `WAVEt`
- `TVoiceThread *[2]`
- `TVoiceThread *`
- `TVoiceThread`
- `TVoicePlayCore`
- `TVoicePlay`
- `VoicePlay`
- `TFormVoice *`
- `TFormVoice`
- `UnitVoice`
- `TFormVoice::Voice_Form_Setting`
- `TFormVoice::Voice_Form_Setting::Voice_Form_Setting_Ch[8]`
- `TFormVoice::Voice_Form_Setting::Voice_Form_Setting_Ch`
- `TFormVoiceEdit *`
- `TFormVoiceEdit`
- `UnitVoiceEdit`
- `std::codecvt<char,char,int> *`
- `std::codecvt_base *`
- `std::codecvt_base`
- `std::codecvt<char,char,int>`
- `std::codecvt<wchar_t,char,int> *`
- `std::codecvt<wchar_t,char,int>`
- `#GI_Sys_Voice_WOpen`
- `The codec setting for the received audio on the Remote Utility is set to 1 channel.`
- `If it is set to 1 channel, the receive audio for the Sub band cannot be output.`
- `The codec setting for the received audio on the Remote Utility is set to 2 channels.`
- `When the Microphone of the USB audio is set to 1 channel on the Windows "Sound Setting" screen, the receive audio for the Sub band cannot be output.`
- `&Voice Memory`
- `Voice Memory`
- `Audio Device (Voice Memory)`
- `#GI_Main_Voice_Label`
- `#GI_Main_VoiceEdit_Label`
- `Voice Memory Setting`
- `Waveform`
- `Waveform Type`
- `Waveform Color (Current)`
- `Waveform Color (Line)`
- `Waveform Color (Max Hold)`
- `Waveform colors will return to default.`
- `|{($iCR)}USB Audio SQL`
- `||{($eWh)(%CL_RS_USB_Audio_SQL)}`
- `|{($iCR)<}USB Audio Output Level`
- `||{($eWh)(%CL_RS_17_USB_Audio_Output_Lv)}`
- `|{($iCR)<}USB Audio SQL`
- `||{($eWh)(%CL_RS_17_USB_Audio_SQL)}`
- `#GI_Main_ShortCut_Voice`
- `CL_RS_USB_Audio_SQL`
- `CL_RS_17_USB_Audio_Output_Lv`
- ... 其余 71 条

### error_msgs (128 条)

- `std::length_error`
- `length_error *`
- `logic_error *`
- `std::logic_error`
- `const EFCreateError &`
- `Classes::EFCreateError`
- `Classes::EFileStreamError`
- `EFCreateError *`
- `EFileStreamError *`
- `EStreamError *`
- `Classes::EStreamError`
- `EMenuError`
- `EDBEditError`
- `EInvalidGridOperation`
- `EInvalidGraphicL`
- `EInvalidGraphicOperation`
- `ETreeViewError`
- `EStreamError`
- `EFileStreamError`
- `EFCreateError`
- `EFOpenError`
- `EFilerError`
- `EReadError`
- `EWriteError`
- `EListError`
- `EBitsError`
- `EStringListError`
- `EInvalidOperation`
- `EPropertyError`
- `EPropertyConvertError`
- `EOleError`
- `EOleSysError`
- `EInOutError O]`
- `EIntError`
- `ERangeError`
- `EMathError`
- `EInvalidOp`
- `EInvalidPointerPS]`
- `EInvalidCast`
- `EConvertError`
- `EVariantError`
- `EAssertionFailed`
- `EAbstractError`
- `EIntfCastError`
- `EOSError`
- `TErrorRec`
- `EVariantInvalidOpError`
- `EVariantTypeCastError`
- `EVariantOverflowError`
- `EVariantInvalidArgErrorP`
- ... 其余 78 条

### format_strings (2161 条)

- `;3t%`
- `{$@|%`
- `Ht%Ht`
- `%<Ar`
- `h%3h`
- `j%h``
- `j%hh`
- `j%j%hH`
- `j&j%hP`
- `jrj%`
- `*)('&%$#"! `
- `,+*)('&%$#"! `
- `t%WP`
- `j#jBj%j`
- `j#jXj%hA`
- `j#jBj%h`
- `j#jUj%jMP`
- `j#j2j%h`
- `j#jUj%h`
- `j%SV`
- `j<h%`
- ` !"#$%`
- `h%(T`
- `|%G3`
- `t%;C`
- `h%pX`
- `%.6x`
- `WndProcPtr%.8X%.8X`
- `t%Jt?Jt[`
- `%s (%s)`
- `@P@t%`
- `;XDt%`
- `Delphi%.8X`
- `ControlOfs%.8X%.8X`
- `TWorkAreasd%Z`
- `t%HtUHt:`
- `|%F3`
- `Uh%n[`
- `|%C3`
- `%s[%d]`
- `%s_%d`
- `Uh%6]`
- `t%HtIHtm`
- `w)f%`
- `u%Nt`
- `t%:J`
- `h%E_`
- `%u8F3`
- `C$Pj%W`
- `D<"u%`
- ... 其余 2111 条

### interesting (391 条)

- `bdRightToLeftReadingOnly`
- `bsDialog`
- `Sender`
- `TOpenDialog *[2]`
- `TSaveDialog *[2]`
- `cuiDebugWin *`
- `cuiEeDebugWin *`
- `TSaveDialog *`
- `Dialogs::TSaveDialog`
- `cuiEeDebugWin`
- `cuiDebugWin`
- `TOpenDialog *`
- `Dialogs::TOpenDialog`
- `TPrinterSetupDialog *[2]`
- `TPrinterSetupDialog *`
- `Dialogs::TPrinterSetupDialog`
- `ReadOnly<`
- `TFormOpening *`
- `TFormOpening`
- `UnitOpening`
- `TStonThread *[2]`
- `TStonThread *`
- `TStonThread`
- `TStonThread|`
- `Classes::TThread`
- `TBeepThread *[2]`
- `TBeepThread *`
- `TBeepThread`
- `bkClose`
- `BBCLOSE`
- `ImageList_WriteEx`
- `THintEvent`
- `ReadOnly`
- `TDrawItemEvent`
- `TMeasureItemEvent`
- `AutoCloseUp`
- `OnCloseUp`
- `TLBGetDataEvent`
- `TLBGetDataObjectEvent`
- `TLBFindDataEvent`
- `CreateHandle`
- `TMenuChangeEvent`
- `TMenuDrawItemEvent`
- `TAdvancedMenuDrawItemEvent`
- `TMenuMeasureItemEvent`
- `TGetItemCountEvent`
- `TItemSelectedEvent`
- `TGetVirtualItemEvent`
- `TGetItemEvent`
- `TSelectCellEvent`
- ... 其余 341 条

## 资源段 (1044 项)

| 类型 | 偏移 | 大小 |
|---|---|---|
| WAVE/BEEP_ERR/type_0 | 0x5b2c44 | 4454 |
| WAVE/BEEP_EXIT/type_0 | 0x5b3dac | 4454 |
| WAVE/BEEP_OK/type_0 | 0x5b4f14 | 1632 |
| WAVE/BEEP_STBY/type_0 | 0x5b5574 | 3572 |
| WAVE/BEEP_STBYM/type_0 | 0x5b6368 | 3572 |
| WAVE/BEEP_WC/type_0 | 0x5b715c | 5864 |
| CURSOR/CURSOR/type_1033 | 0x5b8844 | 308 |
| CURSOR/BITMAP/type_1033 | 0x5b8978 | 308 |
| CURSOR/ICON/type_1033 | 0x5b8aac | 308 |
| CURSOR/MENU/type_1033 | 0x5b8be0 | 308 |
| CURSOR/DIALOG/type_1033 | 0x5b8d14 | 308 |
| CURSOR/STRING/type_1033 | 0x5b8e48 | 308 |
| CURSOR/FONTDIR/type_1033 | 0x5b8f7c | 308 |
| BITMAP/BBABORT/type_1033 | 0x5b90b0 | 464 |
| BITMAP/BBALL/type_1033 | 0x5b9280 | 484 |
| BITMAP/BBCANCEL/type_1033 | 0x5b9464 | 464 |
| BITMAP/BBCLOSE/type_1033 | 0x5b9634 | 464 |
| BITMAP/BBHELP/type_1033 | 0x5b9804 | 464 |
| BITMAP/BBIGNORE/type_1033 | 0x5b99d4 | 464 |
| BITMAP/BBNO/type_1033 | 0x5b9ba4 | 464 |
| BITMAP/BBOK/type_1033 | 0x5b9d74 | 464 |
| BITMAP/BBRETRY/type_1033 | 0x5b9f44 | 464 |
| BITMAP/BBYES/type_1033 | 0x5ba114 | 464 |
| BITMAP/CLOSED/type_1033 | 0x5ba2e4 | 216 |
| BITMAP/LEAF/type_1033 | 0x5ba3bc | 216 |
| BITMAP/MINUS/type_1033 | 0x5ba494 | 216 |
| BITMAP/OPEN/type_1033 | 0x5ba56c | 216 |
| BITMAP/PLUS/type_1033 | 0x5ba644 | 216 |
| BITMAP/PREVIEWGLYPH/type_1033 | 0x5ba71c | 232 |
| BITMAP/RSB_BG_MAINDTB_DUAL_SIZE0/type_0 | 0x5ba804 | 137736 |

> 其余 1014 项

## DLL 依赖

| 导入自 | 函数数 |
|---|---|
| ADVAPI32.DLL | 11 |
| KERNEL32.DLL | 121 |
| RPCRT4.DLL | 1 |
| VERSION.DLL | 3 |
| WINSPOOL.DRV | 4 |
| COMCTL32.DLL | 25 |
| COMDLG32.DLL | 4 |
| GDI32.DLL | 90 |
| MSIMG32.DLL | 2 |
| SHELL32.DLL | 2 |
| USER32.DLL | 203 |
| WINMM.DLL | 23 |
| OLE32.DLL | 5 |
| OLEAUT32.DLL | 17 |
| WTSAPI32.DLL | 2 |

