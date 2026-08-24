# RemoteUty.exe 静态分析报告

> 文件大小: 3,010,048 bytes | 机器: x86 | 类型: EXE | 入口: 0x15f84d | ImageBase: 0x400000
> 编译时间: 2020-06-24 09:26:09

---

## 区段

| 名称 | 虚拟地址 | 虚拟大小 | 原始大小 | 熵值 |
|---|---|---|---|---|
| .text | 0x1000 | 1,628,216 | 1,628,672 | 6.58 |
| .rdata | 0x18f000 | 361,954 | 361,984 | 5.16 |
| .data | 0x1e8000 | 68,596 | 39,424 | 4.47 |
| .rsrc | 0x1f9000 | 798,492 | 798,720 | 2.39 |
| .reloc | 0x2bc000 | 179,948 | 180,224 | 5.65 |

## 导入表

### SETUPAPI.dll (4 函数)

- `SetupDiDestroyDeviceInfoList`
- `SetupDiGetDeviceInterfaceDetailA`
- `SetupDiEnumDeviceInterfaces`
- `SetupDiGetClassDevsA`

### MSPORTS.DLL (3 函数)

- `ComDBGetCurrentPortUsage`
- `ComDBOpen`
- `ComDBClose`

### VERSION.dll (3 函数)

- `GetFileVersionInfoA`
- `GetFileVersionInfoSizeA`
- `VerQueryValueA`

### KERNEL32.dll (173 函数)

- `TerminateProcess`
- `UnhandledExceptionFilter`
- `SetUnhandledExceptionFilter`
- `IsDebuggerPresent`
- `GetACP`
- `IsValidCodePage`
- `GetStringTypeA`
- `GetStringTypeW`
- `GetTimeZoneInformation`
- `GetStdHandle`
- `HeapCreate`
- `VirtualFree`
- `FreeEnvironmentStringsA`
- `GetEnvironmentStrings`
- `FreeEnvironmentStringsW`
- `GetFileType`
- `SetHandleCount`
- `QueryPerformanceCounter`
- `CompareStringW`
- `InitializeCriticalSectionAndSpinCount`
- `LCMapStringA`
- `LCMapStringW`
- `GetConsoleCP`
- `GetConsoleMode`
- `WriteConsoleA`
- `GetConsoleOutputCP`
- `WriteConsoleW`
- `SetEnvironmentVariableA`
- `ExitThread`
- `SetStdHandle`
- ... 其余 143 个

### USER32.dll (218 函数)

- `UnpackDDElParam`
- `ReuseDDElParam`
- `InsertMenuItemA`
- `InvalidateRgn`
- `CharNextA`
- `RegisterClipboardFormatA`
- `EnumChildWindows`
- `WaitMessage`
- `PostThreadMessageA`
- `UnregisterClassA`
- `LockWindowUpdate`
- `BringWindowToTop`
- `CreateAcceleratorTableA`
- `GetKeyboardState`
- `GetKeyboardLayout`
- `ToAsciiEx`
- `CopyAcceleratorTableA`
- `DeleteMenu`
- `SetClassLongA`
- `NotifyWinEvent`
- `CreatePopupMenu`
- `DestroyAcceleratorTable`
- `IsMenu`
- `GetAsyncKeyState`
- `UpdateLayeredWindow`
- `EnableScrollBar`
- `SetWindowRgn`
- `DrawEdge`
- `IsClipboardFormatAvailable`
- `ShowOwnedPopups`
- ... 其余 188 个

### GDI32.dll (98 函数)

- `LineTo`
- `MoveToEx`
- `SetTextAlign`
- `DeleteObject`
- `SelectClipRgn`
- `CreateRectRgn`
- `GetViewportExtEx`
- `GetWindowExtEx`
- `GetPixel`
- `PtVisible`
- `RectVisible`
- `TextOutA`
- `Escape`
- `SelectObject`
- `SetViewportOrgEx`
- `OffsetViewportOrgEx`
- `SetViewportExtEx`
- `ScaleViewportExtEx`
- `SetWindowOrgEx`
- `OffsetWindowOrgEx`
- `SetWindowExtEx`
- `ScaleWindowExtEx`
- `ExtSelectClipRgn`
- `DeleteDC`
- `CreatePatternBrush`
- `GetStockObject`
- `SelectPalette`
- `GetObjectType`
- `CreateHatchBrush`
- `CreateRectRgnIndirect`
- ... 其余 68 个

### MSIMG32.dll (2 函数)

- `AlphaBlend`
- `TransparentBlt`

### COMDLG32.dll (1 函数)

- `GetFileTitleA`

### WINSPOOL.DRV (3 函数)

- `OpenPrinterA`
- `DocumentPropertiesA`
- `ClosePrinter`

### ADVAPI32.dll (12 函数)

- `RegEnumKeyExA`
- `RegQueryValueExA`
- `RegCloseKey`
- `RegSetValueExA`
- `RegDeleteValueA`
- `RegCreateKeyExA`
- `RegEnumValueA`
- `RegOpenKeyA`
- `RegDeleteKeyA`
- `RegOpenKeyExA`
- `RegQueryValueA`
- `RegEnumKeyA`

### SHELL32.dll (8 函数)

- `DragFinish`
- `SHBrowseForFolderA`
- `SHGetPathFromIDListA`
- `SHGetSpecialFolderPathA`
- `SHGetFileInfoA`
- `SHAppBarMessage`
- `DragQueryFileA`
- `ShellExecuteA`

### COMCTL32.dll (2 函数)

- `InitCommonControlsEx`
- `ImageList_GetIconSize`

### SHLWAPI.dll (7 函数)

- `PathRemoveFileSpecA`
- `PathStripToRootA`
- `PathIsUNCA`
- `PathRemoveFileSpecW`
- `PathFindExtensionA`
- `SHDeleteKeyA`
- `PathFindFileNameA`

### oledlg.dll (1 函数)

- `ordinal_8`

### ole32.dll (32 函数)

- `CoTaskMemFree`
- `CoCreateGuid`
- `CoInitializeEx`
- `CoUninitialize`
- `ReleaseStgMedium`
- `CoTaskMemAlloc`
- `OleDuplicateData`
- `CreateStreamOnHGlobal`
- `CoCreateInstance`
- `CLSIDFromProgID`
- `CLSIDFromString`
- `OleGetClipboard`
- `CoGetClassObject`
- `StgOpenStorageOnILockBytes`
- `StgCreateDocfileOnILockBytes`
- `CreateILockBytesOnHGlobal`
- `OleCreateMenuDescriptor`
- `OleDestroyMenuDescriptor`
- `OleTranslateAccelerator`
- `IsAccelerator`
- `OleLockRunning`
- `CoRegisterMessageFilter`
- `CoRevokeClassObject`
- `RevokeDragDrop`
- `CoLockObjectExternal`
- `RegisterDragDrop`
- `OleInitialize`
- `CoFreeUnusedLibraries`
- `OleUninitialize`
- `DoDragDrop`
- ... 其余 2 个

### OLEAUT32.dll (13 函数)

- `SystemTimeToVariantTime`
- `VariantTimeToSystemTime`
- `SafeArrayDestroy`
- `VariantCopy`
- `SysAllocStringLen`
- `VariantInit`
- `VariantChangeType`
- `VariantClear`
- `SysAllocStringByteLen`
- `OleCreateFontIndirect`
- `SysAllocString`
- `SysFreeString`
- `SysStringLen`

### gdiplus.dll (19 函数)

- `GdiplusStartup`
- `GdiplusShutdown`
- `GdipBitmapLockBits`
- `GdipCreateBitmapFromScan0`
- `GdipCreateBitmapFromStreamICM`
- `GdipCreateBitmapFromStream`
- `GdipGetImagePalette`
- `GdipGetImagePaletteSize`
- `GdipGetImagePixelFormat`
- `GdipGetImageHeight`
- `GdipGetImageWidth`
- `GdipDisposeImage`
- `GdipDeleteGraphics`
- `GdipAlloc`
- `GdipFree`
- `GdipDrawImageI`
- `GdipCloneImage`
- `GdipBitmapUnlockBits`
- `GdipGetImageGraphicsContext`

### WS2_32.dll (18 函数)

- `ntohs`
- `getsockname`
- `closesocket`
- `shutdown`
- `bind`
- `htons`
- `socket`
- `WSAGetLastError`
- `ntohl`
- `inet_ntoa`
- `WSACleanup`
- `gethostbyname`
- `WSAStartup`
- `htonl`
- `recvfrom`
- `sendto`
- `WSAIoctl`
- `setsockopt`

### IMM32.dll (3 函数)

- `ImmReleaseContext`
- `ImmGetContext`
- `ImmGetOpenStatus`

### WINMM.dll (25 函数)

- `waveInStart`
- `waveInAddBuffer`
- `waveInPrepareHeader`
- `waveInOpen`
- `waveOutClose`
- `waveOutUnprepareHeader`
- `waveOutWrite`
- `waveOutPrepareHeader`
- `waveOutOpen`
- `waveInStop`
- `waveOutGetPosition`
- `waveOutGetNumDevs`
- `waveInGetNumDevs`
- `waveOutGetDevCapsA`
- `waveInGetDevCapsA`
- `timeKillEvent`
- `timeSetEvent`
- `timeEndPeriod`
- `timeBeginPeriod`
- `timeGetTime`
- `waveInReset`
- `waveInUnprepareHeader`
- `waveOutReset`
- `PlaySoundA`
- `waveInClose`

## 字符串分类

### ci_v_commands (44 条)

- `CCIVCmdDlg`
- `CCIVComIF::CCIVComIF`
- `CCIVComIF::~CCIVComIF`
- `CCIVComIF::Open`
- `MUTEX_REMOTEUTY_CCIVCOMIF_COM%d`
- `CCIVComIF::Read`
- `CCIVComIF::Write`
- `CCIVComIF::EscapeCommFunction`
- `CCIVComIF::GetCommModemStatus`
- `CCIVComIF::Close`
- `CCIVComIF::AddRecvData`
- `CCIVCom::CCIVCom`
- `CCIVCom::~CCIVCom`
- `CCIVCom::Open`
- `CCIVCom::CloseSub`
- `CCIVCom::Close`
- `CCIVCom::AddIF`
- `CCIVCom::RemoveIF`
- `CCIVCom::Send`
- `CCIVCom::EscapeCommFunction`
- `CCIVCom::GetCommModemStatus`
- `CCIVCom::SendThread`
- `CCIVCom::RecvThread`
- `CivCommRXEvtCnt %d`
- `CivCommOtherEvtCnt %d`
- `CivCommSendCnt %d`
- `CivCommReadCnt %d`
- `Transceiver`
- `UseCIV`
- `CIVAddress`
- `Baudrate`
- `.\Transceiver.cpp`
- `CTransceiver::createDevice`
- `CTransceiver::deleteDevice`
- `.?AVCCIVCmdDlg@@`
- `.?AV?$CUsrPtrList@PAVCCIVComIF@@@@`
- `.?AV?$CUsrPtrList@PAVCCIVCom@@@@`
- `.?AV?$CUsrPtrList@PAVCTransceiver@@@@`
- `.?AVCTransceiver@@`
- `CI-V`
- `#CI-V`
- `"CI-V USB`
- `/CI-V`
- `eCI-V`

### serial_port (197 条)

- `InitCommonControls`
- `InitCommonControlsEx`
- `commctrl_DragListMsg`
- `CComboBox`
- `COMBOBOX`
- `DwmIsCompositionEnabled`
- `comctl32.dll`
- `comdlg32.dll`
- `Software\Microsoft\Windows\CurrentVersion\Policies\Comdlg32`
- `combobox`
- `CommandsUsage`
- `IDB_OFFICE2007_COMBOBOX_BTN`
- `COMBO`
- `CommandsWithoutImages`
- `%sCommandManager`
- `CCommonDialog`
- `commdlg_SetRGBColor`
- `commdlg_help`
- `commdlg_ColorOK`
- `commdlg_FileNameOK`
- `commdlg_ShareViolation`
- `commdlg_LBSelChangedNotify`
- `AFX_WM_ON_AFTER_SHELL_COMMAND`
- `CHelpComboBoxButton`
- `MenuCommand`
- `AFX_WM_ON_DRAGCOMPLETE`
- `AFX_WM_ON_MOVETABCOMPLETE`
- `GetThemePartSize`
- `CMFCToolBarComboBoxButton`
- `CMFCToolBarsCommandsPropertyPage`
- `commdlg_FindReplace`
- `This indicates a bug in your application. It is most likely the result of calling an MSIL-compiled (/clr) function from a native constructor or from DllMain.`
- ` Complete Object Locator'`
- `CAddTransWizDlg`
- `\\.\COM%d`
- `baud=%d parity=N data=8 stop=1`
- `CCommandCtrl::sendRecv`
- `CCommandCtrl::send`
- `CCommandCtrl::addCallback`
- `CCommandCtrl::delCallback`
- `CClientCommandCtrl::ConnectServer`
- `.\CommandCtrl.cpp`
- `CClientCommandCtrl::DisconnectServer`
- `CClientCommandCtrl::GetInfo`
- `CClientCommandCtrl::ConnectTrans`
- `pSerial->open`
- `pSerial->openDevice`
- `pSerial->startSerialRecvThread`
- `pSerial->enableConnect`
- `CClientCommandCtrl::DisconnectTrans`
- ... 其余 147 条

### network (79 条)

- `FTCP`
- `tcPW`
- `CNotSupportedException`
- `NoNetConnectDisconnect`
- `Please contact the application's support team for more information.`
- `- floating point support not loaded`
- `CAudioCtrl::CheckPostUdpRecv`
- `CheckPostUdpRecv recvsize = %d`
- `CheckPostUdpRecv m_pPlayBuffer->getSize() = %d recvsize = %d m_pPlayBuffer->getPreBufferSize() = %d cutsize = %d`
- `CheckPostUdpRecv cutsize = %d`
- `pAudio->enableConnect`
- `Connect`
- `CConnectTransDlg`
- `CONNECT`
- `AudioPort`
- `NetConnect`
- `Port`
- `MUTEX_SERVER_PORTLIST`
- `CRemoteServer::ConnectThread`
- `CNetCtrl::connect`
- `CUdp::CUdp`
- `CUdp::~CUdp`
- `CUdp::open`
- `CUdp::close`
- `CUdp::send`
- `CUdp::recv`
- `CUdp::recvThread`
- `CUdp::addCallback`
- `CUdp::delCallback`
- `MUTEX_REMOTEUTY_CUDPCtrl`
- `CUDPCtrl::CUDPCtrl`
- `CUDPCtrl::~CUDPCtrl`
- `CUDPCtrl::sendUdp`
- `CUDPCtrl::closeUdp`
- `CUDPCtrl::ExClose`
- `CUDPCtrl::ExSessionClose`
- `CUDPCtrl::ExOpen`
- `CUDPCtrl::ExConnect`
- `CUDPCtrl::ExAccept`
- `CUDPCtrl::ExSend`
- `CUDPCtrl::recvCallback`
- `CUDPCtrl::sendDisconnect`
- `CUDPCtrl2::CUDPCtrl2`
- `CUDPCtrl2::~CUDPCtrl2`
- `CUDPCtrl2::ExOpen`
- `CUDPCtrl2::ExInit`
- `CUDPCtrl2::recvCallback`
- ` port = %d seq = %d`
- `CUDPCtrl2::recvProc`
- `CUDPCtrl2::ExSend`
- ... 其余 29 条

### file_paths (788 条)

- `D$\C`
- `D$\d`
- `L$\d`
- `D$\SRP`
- `\$TR`
- `\$DP`
- `\$LQV`
- `\$@9`
- `Ph\u[`
- `PVh\`
- `T$\h `
- `u\h'`
- `\SUW`
- `\$$;`
- `T$\R`
- `uHf9\$ruA`
- `C;\$`
- `t3h\`
- `j Uh\`
- `D$\SW`
- `D$\R`
- `L$\3`
- `\$lh`
- `\$d3`
- `h\u_`
- `D$ h\`
- `C;\$ |`
- `\$ j`
- `t\hE`
- `\$8+`
- `9\$4`
- `h/]X`
- `u/SV`
- `D$(9\$`
- `\$ 3`
- `|/;_`
- `t\VW`
- `t.h\`
- `\$(h(b[`
- `D$\j`
- `L$\QR`
- `|$ C;\$`
- `D$\/`
- `\$`;`
- `\$X;`
- `\$ ;`
- `\$0;`
- `\$\8`
- `T$\V`
- `\$L;`
- ... 其余 738 条

### audio (185 条)

- `WAVE`
- `CAudioDlg`
- `CSampleConv::Init`
- `CSampleConv::exec`
- `%02X: %d>%d size = %d srcsample = %d dstsample = %d m_BufferSize = %d`
- `CSampleConv::get`
- `CSampleConv::conv`
- `CSampleConv::bitchnconv`
- `CSampleConv::conv1`
- `CSampleConv::conv3`
- `CSampleConv::lpf`
- `CWaveSetting::Is_Vista_or_Later`
- `CAudioCtrl::CAudioCtrl`
- `CAudioCtrl::~CAudioCtrl`
- `CAudioCtrl::openDevice`
- `CAudioCtrl::closeDevice`
- `CAudioCtrl::startCapture`
- `CAudioCtrl::stopCapture`
- `CAudioCtrl::sendNetwork`
- `CAudioCtrl::SetRecvBuffer`
- `CAudioCtrl::GetDataSizeOfPacket`
- `CAudioCtrl::AddSilenceRecvBuffer`
- `CAudioCtrl::recvExec`
- `CAudioCtrl::audioRecvThread`
- `CAudioCtrl::sendPacket`
- `CAudioCtrl::audioSendThread`
- `m_InConf: fs:%d bit:%d ch:%d codec:%s cnt:%d time:%d`
- `m_OutConf: fs:%d bit:%d ch:%d codec:%s cnt:%d time:%d`
- `m_SendConf: fs:%d bit:%d ch:%d codec:%s cnt:%d time:%d`
- `m_RecvConf: fs:%d bit:%d ch:%d codec:%s cnt:%d time:%d`
- `CAudioCtrl::m_Session.m_SendList.`
- `CAudioCtrl::m_SendList`
- `CAudioCtrl::m_RecvList`
- `CClientAudioCtrl::CClientAudioCtrl`
- `CClientAudioCtrl::~CClientAudioCtrl`
- `CClientAudioCtrl::createDevice`
- `CClientAudioCtrl::ExOpenDevice`
- `CClientAudioCtrl::ExCloseDevice`
- `CClientAudioCtrl::deleteDevice`
- `CClientAudioCtrl::selectInput`
- `CClientAudioCtrl::ClearVADRecv`
- `CClientAudioCtrl::ExStartCapture`
- `CClientAudioCtrl::ExStopCapture`
- `CClientAudioCtrl::TimerProc`
- `CClientAudioCtrl::vaudioSendBlock`
- `CClientAudioCtrl::WaveDataSet`
- `CClientAudioCtrl::PostProcess`
- `CClientAudioCtrl::AudioRecv`
- `CClientAudioCtrl::sendMic`
- `CClientAudioCtrl::setSpkVolume`
- ... 其余 135 条

### error_msgs (16 条)

- `!This program cannot be run in DOS mode.`
- `CInvalidArgException`
- `runtime error `
- `TLOSS error`
- `SING error`
- `DOMAIN error`
- `- unexpected heap error`
- `- unexpected multithread lock error`
- `Runtime Error!`
- `GetLastError`
- `SetLastError`
- `SetErrorMode`
- `InvalidateRect`
- `InvalidateRgn`
- `.PAVCInvalidArgException@@`
- `.?AVCInvalidArgException@@`

### format_strings (270 条)

- `%Wh?`
- `L$,%`
- `h%mX`
- `~%9G`
- `t%VQ`
- `}%;,`
- `h%LF`
- `t%QP`
- `%$4_`
- `% 4_`
- `u%j0`
- `u%SSSS`
- `%d@_`
- `j%Xt`
- `j%XtL9E`
- `%@B_`
- `t%9=`
- `t%SSSj`
- `9] t%`
- `%XK_`
- `t%9_pt`
- `%(M_`
- `%$M_`
- `t%j!`
- `u%9}`
- `9Xlu%`
- `t%@P`
- `u%9{`
- `t%9y t `
- `^~%S`
- `OOtBOt%`
- `u%9]`
- `;A u%`
- `%x6_`
- `%hX_`
- `%9s|`
- `u%Wj`
- `t%Pj`
- `u*9G8u%`
- `tsItgItSItAIt%IIt`
- `t%9F`
- `t*9~ t%`
- `%t-Ht`
- `t%9]`
- `ty<%tA`
- `|%=2`
- `t%HHt`
- `n<%u`
- `(%`1[`
- `~%9M`
- ... 其余 220 条

### interesting (173 条)

- `CDialog`
- `CMutex`
- `CEvent`
- `ImageList_Create`
- `CWinThread`
- `CreateActCtxW`
- `CFileDialog`
- `p4GetOpenFileNameA`
- `SHCreateItemFromParsingName`
- `CreateActCtxA`
- `NoClose`
- `NotifyWinEvent`
- `CloseThemeData`
- `OpenThemeData`
- `TOOLBAR_CREATE`
- `IDB_OFFICE2007_SYS_BTN_CLOSE`
- `&Open,0,2`
- `Open`
- `0@Close`
- `CDialogEx`
- `Can't create context menu!`
- `AFX_WM_ON_PRESS_CLOSE_BUTTON`
- `CMFCToolBarsCustomizeDialog`
- `AfxClosePending`
- `CreatePropertySheetPageA`
- `CColorDialog`
- `COleBusyDialog`
- `COleDialog`
- `SetThreadStackGuarantee`
- `- unable to open console device`
- `- not enough space for thread data`
- `log10`
- `_logb`
- ``local static thread guard'`
- `open`
- `CBlockRingBuffer::Read`
- `CBlockRingBuffer::Write`
- `CDebugDialog`
- `CDebugServerDlg`
- `REMOTEUTY_DEBUGINFO_MUTEX`
- `CDebugStatusDlg`
- `CEasySetupDialog`
- `CExitDialog`
- `CLocalSverDialog`
- `COpenDialog`
- `CRemoteUtyDlg::OnInitDialog`
- `CRemoteServer::KeepAliveThread`
- `CRemoteTrans::closeDevices`
- `MUTEX_REMOTEUTY_CTransList`
- `MUTEX_REMOTEUTY_CTRC`
- ... 其余 123 条

## 资源段 (155 项)

| 类型 | 偏移 | 大小 |
|---|---|---|
| PNG/type_1264/type_1041 | 0x1fae60 | 3970 |
| PNG/type_1265/type_1041 | 0x1fbde4 | 4709 |
| PNG/type_1266/type_1041 | 0x1fd04c | 3373 |
| PNG/type_1267/type_1041 | 0x1fdd7c | 4309 |
| CURSOR/MENU/type_1041 | 0x1fee54 | 308 |
| CURSOR/DIALOG/type_1041 | 0x1fef88 | 180 |
| CURSOR/STRING/type_1041 | 0x1ff03c | 308 |
| CURSOR/FONTDIR/type_1041 | 0x1ff170 | 308 |
| CURSOR/FONT/type_1041 | 0x1ff2a4 | 308 |
| CURSOR/ACCELERATOR/type_1041 | 0x1ff3d8 | 308 |
| CURSOR/RCDATA/type_1041 | 0x1ff50c | 308 |
| CURSOR/MESSAGETABLE/type_1041 | 0x1ff640 | 308 |
| CURSOR/GROUP_CURSOR/type_1041 | 0x1ff774 | 308 |
| CURSOR/type_13/type_1041 | 0x1ff8a8 | 308 |
| CURSOR/GROUP_ICON/type_1041 | 0x1ff9dc | 308 |
| CURSOR/type_15/type_1041 | 0x1ffb10 | 308 |
| CURSOR/VERSION/type_1041 | 0x1ffc44 | 308 |
| CURSOR/type_17/type_1041 | 0x1ffd78 | 308 |
| CURSOR/type_18/type_1041 | 0x1ffeac | 308 |
| CURSOR/type_19/type_1041 | 0x1fffe0 | 308 |
| BITMAP/type_171/type_1041 | 0x200114 | 720042 |
| BITMAP/type_172/type_1041 | 0x2afdc0 | 232 |
| BITMAP/type_173/type_1041 | 0x2afea8 | 232 |
| BITMAP/type_174/type_1041 | 0x2aff90 | 232 |
| BITMAP/type_175/type_1041 | 0x2b0078 | 232 |
| BITMAP/type_176/type_1041 | 0x2b0160 | 232 |
| BITMAP/type_177/type_1041 | 0x2b0248 | 232 |
| BITMAP/type_178/type_1041 | 0x2b0330 | 232 |
| BITMAP/type_30994/type_1041 | 0x2b0418 | 184 |
| BITMAP/type_30996/type_1041 | 0x2b04d0 | 324 |

> 其余 125 项

## DLL 依赖

| 导入自 | 函数数 |
|---|---|
| SETUPAPI.dll | 4 |
| MSPORTS.DLL | 3 |
| VERSION.dll | 3 |
| KERNEL32.dll | 173 |
| USER32.dll | 218 |
| GDI32.dll | 98 |
| MSIMG32.dll | 2 |
| COMDLG32.dll | 1 |
| WINSPOOL.DRV | 3 |
| ADVAPI32.dll | 12 |
| SHELL32.dll | 8 |
| COMCTL32.dll | 2 |
| SHLWAPI.dll | 7 |
| oledlg.dll | 1 |
| ole32.dll | 32 |
| OLEAUT32.dll | 13 |
| gdiplus.dll | 19 |
| WS2_32.dll | 18 |
| IMM32.dll | 3 |
| WINMM.dll | 25 |

