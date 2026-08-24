#!/usr/bin/env python
"""通过 pefile 解析 IAT, 把 thunk 地址映射到 API 名"""
import pefile

DLL_PATH = r"d:\my git\RS-BA1\RemoteController\CivCtrl.dll"
IMAGE_BASE = 0x400000

# 感兴趣的 IAT slot VA (从 thunk jmp [addr] 提取)
INTERESTING_IAT_VAS = [
    0x427178,  # thunk 0x41bba2
    0x42716c,  # thunk 0x41bb90
    0x42723c,  # thunk 0x41bcc8
    0x427240,  # thunk 0x41bcce
    0x427190,  # thunk 0x41bbc6
    0x4272b0,  # thunk 0x41bd48
    # 额外扫描附近 IAT 项
    0x42716c, 0x427170, 0x427174, 0x427178, 0x42717c, 0x427180,
    0x427184, 0x427188, 0x42718c, 0x427190, 0x427194, 0x427198,
    0x42723c, 0x427240, 0x427244, 0x427248, 0x42724c, 0x427250,
    0x4272b0,
]

def main():
    pe = pefile.PE(DLL_PATH, fast_load=False)
    # 构建 IAT slot VA -> (dll, api_name) 映射
    iat_map = {}
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        dll = entry.dll.decode()
        for imp in entry.imports:
            if imp.address and imp.name:
                iat_map[imp.address] = (dll, imp.name.decode())
            elif imp.address and imp.ordinal:
                iat_map[imp.address] = (dll, f"ord_{imp.ordinal}")

    print(f"[+] IAT entries total: {len(iat_map)}")
    print()
    print(f"{'IAT VA':>12}  {'thunk VA':>12}  API")
    print("-" * 70)
    seen = set()
    for iat_va in INTERESTING_IAT_VAS:
        if iat_va in seen:
            continue
        seen.add(iat_va)
        info = iat_map.get(iat_va)
        if info:
            # thunk VA = iat_va - 0x427000 + 0x41bb...  不对, thunk 是单独的
            # 实际 thunk 在 .text 末尾, 每项 6 字节 (ff25 + 4字节地址)
            # 这里直接显示 IAT 信息
            print(f"  {iat_va:#010x}              {info[0]:16s} {info[1]}")
        else:
            print(f"  {iat_va:#010x}              (not in IAT)")

    print()
    print("=== 所有关键 KERNEL32 串口/线程/事件 API ===")
    keywords = ["Comm", "CreateFile", "CreateThread", "CreateEvent",
                "ReadFile", "WriteFile", "CloseHandle", "EscapeComm",
                "Sleep", "GetLocalTime", "timeGetTime", "wsprintf",
                "MessageBox", "Mailslot"]
    for iat_va, (dll, api) in sorted(iat_map.items()):
        if any(k.lower() in api.lower() for k in keywords):
            print(f"  {iat_va:#010x}  {dll:16s} {api}")

if __name__ == "__main__":
    main()
