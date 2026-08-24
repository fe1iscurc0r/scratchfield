#!/usr/bin/env python3
"""HW-06 寄生链：工程生命周期指令流驱动器（无 GUI 全自动）。

覆盖：创建 → 打开 → 归档(.epro 导出) → 重导入/复制迭代 → 清理。
走 easyeda-agent daemon 的 debug exec 逃生口调底层 eda.* API（DMT_Project / sys_FileManager）。

用法（均需 daemon 运行 + 连接器在线）:
  python project_lifecycle.py create <名字>          # 建工程并打开，返回 uuid
  python project_lifecycle.py archive <uuid> <out.epro>  # 按 uuid 导出归档（不必当前打开）
  python project_lifecycle.py iterate <uuid> <新名字>    # copyProject 快照迭代
  python project_lifecycle.py delete <uuid>          # 删除
  python project_lifecycle.py status                 # 当前窗口/工程状态
  python project_lifecycle.py fulltest               # 一键全链路验证（建→归档→复制→清理）
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

EASYEDA = r"C:\Users\ASUS\bin\easyeda.exe"


def run_cli(args: list[str], timeout: int = 90) -> dict:
    out = subprocess.run([EASYEDA, *args], capture_output=True, text=True,
                         timeout=timeout, creationflags=0x08000000)
    txt = (out.stdout or "").strip()
    if txt.startswith("{"):
        return json.loads(txt)
    return {"raw": txt[:3000], "stderr": (out.stderr or "")[:500]}


def first_window() -> str:
    d = run_cli(["daemon", "health"])
    try:
        return d["found"]["raw"]["windows"][0]["windowId"]
    except (KeyError, IndexError):
        raise SystemExit("没有已连接的 EasyEDA 窗口（检查连接器 + 外部交互开关）")


def exec_js(code: str, timeout: int = 90) -> dict:
    w = first_window()
    return run_cli(["debug", "exec", "--window", w, "--timeout", str(timeout), "--code", code])


def ok(resp: dict) -> dict:
    if resp.get("ok"):
        r = resp.get("result") or resp.get("structuredContent", {}).get("result", {})
        if isinstance(r, dict) and set(r.keys()) == {"value"}:  # exec_js 结果统一 value 包装
            r = r["value"]
        return r
    raise SystemExit(f"动作失败: {json.dumps(resp, ensure_ascii=False)[:600]}")


def cmd_create(name: str):
    r = ok(exec_js(
        f"const uuid = await eda.dmt_Project.createProject({json.dumps(name, ensure_ascii=False)!r}"
        f".replace(/'/g, \"\\\\'\"), undefined, undefined, undefined, 'created by scratchpad project_lifecycle');"
        f"if (!uuid) return 'createProject returned undefined';"
        f"await eda.dmt_Project.openProject(uuid);"
        f"return uuid;"))
    print(json.dumps({"created": name, "uuid": r, "opened": True}, ensure_ascii=False, indent=2))


def cmd_archive(uuid: str, out: Path):
    # File 对象不能过 WS —— 在编辑器侧转 base64 分段带回
    js = (
        "const f = await eda.sys_FileManager.getProjectFileByProjectUuid(" + json.dumps(uuid) + ", "
        "'parasite-archive', undefined, 'epro2');"
        "if (!f) return {error: 'no project file', uuid: " + json.dumps(uuid) + "};"
        "const buf = new Uint8Array(await f.arrayBuffer());"
        "let b64 = ''; for (let i = 0; i < buf.length; i += 32768) {"
        "  b64 += String.fromCharCode.apply(null, buf.subarray(i, i + 32768)); }"
        "return { name: f.name, size: buf.length, b64: btoa(b64) };"
    )
    r = ok(exec_js(js, timeout=180))
    if isinstance(r, dict) and r.get("error"):
        raise SystemExit(f"归档失败: {r}")
    data = base64.b64decode(r["b64"])
    out.write_bytes(data)
    print(json.dumps({"archived": uuid, "file": str(out), "bytes": len(data),
                      "name": r.get("name")}, ensure_ascii=False, indent=2))


def cmd_iterate(uuid: str, new_name: str):
    r = ok(exec_js(
        f"const nu = await eda.dmt_Project.copyProject({json.dumps(uuid)!r}, undefined, undefined, "
        f"{json.dumps(new_name, ensure_ascii=False)!r}); return nu;"))
    print(json.dumps({"snapshot_of": uuid, "new_name": new_name, "new_uuid": r}, ensure_ascii=False, indent=2))


def cmd_delete(uuid: str):
    r = ok(exec_js(f"return eda.dmt_Project.deleteProject({json.dumps(uuid)});"))
    print(json.dumps({"deleted": uuid, "result": r}, ensure_ascii=False, indent=2))


def cmd_status():
    d = run_cli(["daemon", "health"])
    ws = d.get("found", {}).get("raw", {}).get("windows", [])
    print(json.dumps({"windows": [{"windowId": w.get("windowId"), "doc": w.get("context", {}).get("documentType"),
                                   "connectorOk": w.get("connectorVersionOk")} for w in ws]},
                     ensure_ascii=False, indent=2))
    if ws:
        r = ok(exec_js("const p = await eda.dmt_Project.getCurrentProjectInfo(); return p;"))
        print(json.dumps({"current_project": r}, ensure_ascii=False, indent=2)[:1500])


def unwrap_uuid(v):
    """createProject/getCurrentProjectInfo 的 uuid 可能是裸串或 {value: 裸串} 包装。"""
    if isinstance(v, dict):
        for k in ("value", "uuid", "projectUuid"):
            if v.get(k):
                return unwrap_uuid(v[k])
    return v


def cmd_fulltest():
    print("== 1/4 创建 ==")
    r = ok(exec_js(
        f"const uuid = await eda.dmt_Project.createProject({json.dumps('寄生链-自动验证-' + time.strftime('%H%M%S'), ensure_ascii=False)});"
        f"if (uuid) await eda.dmt_Project.openProject(uuid); return uuid;"))
    uuid = unwrap_uuid(r)
    print(json.dumps({"created": True, "uuid": uuid, "opened": bool(uuid)}, ensure_ascii=False, indent=2))
    if not uuid:
        raise SystemExit("创建失败，中止")
    print("== 2/4 归档 ==")
    out = Path.home() / "Desktop" / f"parasite-auto-{time.strftime('%H%M%S')}.epro"
    cmd_archive(uuid, out)
    print("== 3/4 复制迭代 ==")
    cmd_iterate(uuid, uuid and "迭代-" + time.strftime("%H%M%S") or "iter")
    print("== 4/4 状态 ==")
    cmd_status()
    print(f"\n全链路完成。归档在 {out}；测试工程/副本可用 delete <uuid> 清理。")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["create", "archive", "iterate", "delete", "status", "fulltest"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if a.cmd == "create":
        cmd_create(a.args[0])
    elif a.cmd == "archive":
        cmd_archive(a.args[0], Path(a.args[1]))
    elif a.cmd == "iterate":
        cmd_iterate(a.args[0], a.args[1])
    elif a.cmd == "delete":
        cmd_delete(a.args[0])
    elif a.cmd == "status":
        cmd_status()
    else:
        cmd_fulltest()
    return 0


if __name__ == "__main__":
    sys.exit(main())
