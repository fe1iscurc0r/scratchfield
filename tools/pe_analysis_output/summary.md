# RS-BA1 PE 全量静态分析汇总

| 文件 | 大小 | 类型 | 机器 | 导出数 | 导入DLL数 | ASCII字符串 | Unicode字符串 |
|---|---|---|---|---|---|---|---|
| RemoteCtrl.exe | 44,931,072 | EXE | x86 | 300 | 15 | 44258 | 1201 |
| CivCtrl.dll | 151,040 | DLL | x86 | 18 | 3 | 971 | 32 |
| HidCtrl.dll | 16,896 | DLL | x86 | 10 | 4 | 169 | 17 |
| UtyCtrl.dll | 204,288 | DLL | x86 | 9 | 8 | 1257 | 49 |
| RS-BA1V2Ck.dll | 2,014,720 | DLL | x86 | 1 | 15 | 7373 | 453 |
| RemoteUty.exe | 3,010,048 | EXE | x86 | 0 | 20 | 11714 | 166 |
| RadioSch.dll | 1,972,736 | DLL | x86 | 5 | 16 | 8295 | 506 |
| UtilityCk.dll | 201,728 | DLL | x86 | 1 | 8 | 1232 | 49 |
| english.dll | 812,032 | DLL | x86 | 0 | 0 | 474 | 451 |

## DLL 间交叉引用

| 消费者 | 导入自 | 函数数 |
|---|---|---|
| RemoteCtrl.exe | ADVAPI32.DLL | 11 |
| RemoteCtrl.exe | KERNEL32.DLL | 121 |
| RemoteCtrl.exe | RPCRT4.DLL | 1 |
| RemoteCtrl.exe | VERSION.DLL | 3 |
| RemoteCtrl.exe | WINSPOOL.DRV | 4 |
| RemoteCtrl.exe | COMCTL32.DLL | 25 |
| RemoteCtrl.exe | COMDLG32.DLL | 4 |
| RemoteCtrl.exe | GDI32.DLL | 90 |
| RemoteCtrl.exe | MSIMG32.DLL | 2 |
| RemoteCtrl.exe | SHELL32.DLL | 2 |
| RemoteCtrl.exe | USER32.DLL | 203 |
| RemoteCtrl.exe | WINMM.DLL | 23 |
| RemoteCtrl.exe | OLE32.DLL | 5 |
| RemoteCtrl.exe | OLEAUT32.DLL | 17 |
| RemoteCtrl.exe | WTSAPI32.DLL | 2 |
| CivCtrl.dll | KERNEL32.DLL | 70 |
| CivCtrl.dll | USER32.DLL | 3 |
| CivCtrl.dll | WINMM.DLL | 1 |
| HidCtrl.dll | KERNEL32.dll | 23 |
| HidCtrl.dll | SETUPAPI.dll | 4 |
| HidCtrl.dll | HID.DLL | 6 |
| HidCtrl.dll | msvcrt.dll | 23 |
| UtyCtrl.dll | KERNEL32.dll | 109 |
| UtyCtrl.dll | SHLWAPI.dll | 2 |
| UtyCtrl.dll | OLEACC.dll | 2 |
| UtyCtrl.dll | USER32.dll | 88 |
| UtyCtrl.dll | GDI32.dll | 23 |
| UtyCtrl.dll | WINSPOOL.DRV | 3 |
| UtyCtrl.dll | ADVAPI32.dll | 9 |
| UtyCtrl.dll | OLEAUT32.dll | 3 |
| RS-BA1V2Ck.dll | KERNEL32.dll | 161 |
| RS-BA1V2Ck.dll | USER32.dll | 224 |
| RS-BA1V2Ck.dll | MSIMG32.dll | 2 |
| RS-BA1V2Ck.dll | SHLWAPI.dll | 6 |
| RS-BA1V2Ck.dll | UxTheme.dll | 12 |
| RS-BA1V2Ck.dll | OLEACC.dll | 3 |
| RS-BA1V2Ck.dll | gdiplus.dll | 22 |
| RS-BA1V2Ck.dll | IMM32.dll | 3 |
| RS-BA1V2Ck.dll | WINMM.dll | 1 |
| RS-BA1V2Ck.dll | GDI32.dll | 97 |
| RS-BA1V2Ck.dll | WINSPOOL.DRV | 3 |
| RS-BA1V2Ck.dll | ADVAPI32.dll | 11 |
| RS-BA1V2Ck.dll | SHELL32.dll | 9 |
| RS-BA1V2Ck.dll | ole32.dll | 21 |
| RS-BA1V2Ck.dll | OLEAUT32.dll | 13 |
| RemoteUty.exe | SETUPAPI.dll | 4 |
| RemoteUty.exe | MSPORTS.DLL | 3 |
| RemoteUty.exe | VERSION.dll | 3 |
| RemoteUty.exe | KERNEL32.dll | 173 |
| RemoteUty.exe | USER32.dll | 218 |
| RemoteUty.exe | GDI32.dll | 98 |
| RemoteUty.exe | MSIMG32.dll | 2 |
| RemoteUty.exe | COMDLG32.dll | 1 |
| RemoteUty.exe | WINSPOOL.DRV | 3 |
| RemoteUty.exe | ADVAPI32.dll | 12 |
| RemoteUty.exe | SHELL32.dll | 8 |
| RemoteUty.exe | COMCTL32.dll | 2 |
| RemoteUty.exe | SHLWAPI.dll | 7 |
| RemoteUty.exe | oledlg.dll | 1 |
| RemoteUty.exe | ole32.dll | 32 |
| RemoteUty.exe | OLEAUT32.dll | 13 |
| RemoteUty.exe | gdiplus.dll | 19 |
| RemoteUty.exe | WS2_32.dll | 18 |
| RemoteUty.exe | IMM32.dll | 3 |
| RemoteUty.exe | WINMM.dll | 25 |
| RadioSch.dll | KERNEL32.dll | 156 |
| RadioSch.dll | USER32.dll | 224 |
| RadioSch.dll | GDI32.dll | 97 |
| RadioSch.dll | MSIMG32.dll | 2 |
| RadioSch.dll | WINSPOOL.DRV | 3 |
| RadioSch.dll | ADVAPI32.dll | 11 |
| RadioSch.dll | SHELL32.dll | 9 |
| RadioSch.dll | SHLWAPI.dll | 6 |
| RadioSch.dll | UxTheme.dll | 12 |
| RadioSch.dll | ole32.dll | 21 |
| RadioSch.dll | OLEAUT32.dll | 13 |
| RadioSch.dll | SETUPAPI.dll | 9 |
| RadioSch.dll | WINMM.dll | 7 |
| RadioSch.dll | gdiplus.dll | 22 |
| RadioSch.dll | OLEACC.dll | 3 |
| RadioSch.dll | IMM32.dll | 3 |
| UtilityCk.dll | SHLWAPI.dll | 2 |
| UtilityCk.dll | OLEACC.dll | 2 |
| UtilityCk.dll | KERNEL32.dll | 104 |
| UtilityCk.dll | USER32.dll | 88 |
| UtilityCk.dll | GDI32.dll | 23 |
| UtilityCk.dll | WINSPOOL.DRV | 3 |
| UtilityCk.dll | ADVAPI32.dll | 9 |
| UtilityCk.dll | OLEAUT32.dll | 3 |

## 导出函数 → 被谁导入

| 函数名 | 导出者 | 导入者 |
|---|---|---|
