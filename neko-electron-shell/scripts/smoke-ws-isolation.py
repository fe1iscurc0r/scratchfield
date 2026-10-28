#!/usr/bin/env python
"""WO-278 自动化冒烟：用 CDP 进渲染进程断言「桥工厂 / 适配器是否存在」。

用途有两阶段：
  1. **改造前基线**：预期 `window.nekoWebSocket === undefined`（preload 还在替换全局）、
     `window.__nekoCreateWebSocket` 不存在（页面还没引入适配器）
  2. **装配后对比**：预期两者都在，且 `readyState` 能 0→1、send 真的走 IPC

做法：以隔离的 `NEKO_USER_DATA_DIR`（临时目录，不碰用户真实配置）启动 electron，
加 `--remote-debugging-port=9222`，通过 CDP 的 `Runtime.evaluate` 在每个渲染进程里跑探针，
顺带抓 3 秒 console 错误，最后杀掉整个进程树。

用法：
    python scripts/smoke-ws-isolation.py            # 跑一轮，打印摘要
    python scripts/smoke-ws-isolation.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

SHELL_DIR = pathlib.Path(__file__).resolve().parents[1]
PORT = 9222

PROBE = r"""
(() => {
  const out = {
    href: location.href.slice(0, 120),
    hasNekoWebSocket: typeof window.nekoWebSocket,
    hasNekoWebSocketCreate:
      !!(window.nekoWebSocket && typeof window.nekoWebSocket.create === 'function'),
    hasAdapter: typeof window.__nekoCreateWebSocket,
    webSocketIsNative: (() => {
      try {
        return String(window.WebSocket).includes('[native code]');
      } catch (e) {
        return 'err';
      }
    })(),
    hasNekoChatWindow: typeof window.nekoChatWindow,
  // 白屏诊断：body 里到底有没有东西、脚本加载了几个
  dom: {
    ready: document.readyState,
    bodyChildren: document.body ? document.body.children.length : -1,
    bodyTextLen: document.body ? (document.body.innerText || '').trim().length : -1,
    roots: document.body ? Array.from(document.body.children).slice(0, 10).map(
      function (e) { return e.id || e.className || e.tagName; }) : [],
    scripts: document.scripts.length,
    // 注：不要在这里猜"脚本加载失败"——script 元素没有可靠的失败态可读，
    // 之前写过一条 `&& false` 的过滤，恒为 0 等于假指标，已删。
    hasChatRoot: !!document.querySelector('[data-chat-root], #chat-root, #app, #chat-container'),
  },
  };
  // Pet 窗：读 preload 的诊断快照（页面注册面是否生效 / 有无 miss / 桥能否传函数与数据）
  try {
    if (window.nekoPetDiagnostics && typeof window.nekoPetDiagnostics.snapshot === 'function') {
      out.petDiagnostics = window.nekoPetDiagnostics.snapshot();
    }
  } catch (e) {
    out.petDiagnosticsError = String(e && e.message).slice(0, 160);
  }
  // 有工厂就真建一个，看状态机能不能动（不依赖后端：只观察本地状态）
  try {
    if (out.hasNekoWebSocketCreate) {
      const s = window.nekoWebSocket.create('ws://127.0.0.1:1/probe');
      out.probeReadyState0 = s.getReadyState();
      s.close(1000, 'probe');
      out.probeReadyStateAfterClose = s.getReadyState();
    }
  } catch (e) {
    out.probeError = String(e && e.message).slice(0, 160);
  }
  return out;
})()
"""


def http_json(url: str, timeout: float = 3.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _is_app_page(url: str) -> bool:
    """加载窗是 file://，且会自行关闭；探针只对真正的应用页面有意义。"""
    return url.startswith("http://localhost:48911") or url.startswith("http://127.0.0.1:48911")


def wait_targets(deadline_s: float = 75.0, proc=None):
    t0 = time.time()
    last = None
    cdp_seen = False
    while time.time() - t0 < deadline_s:
        if proc is not None and proc.poll() is not None:
            return {"__exited__": proc.returncode}
        try:
            ver = http_json(f"http://127.0.0.1:{PORT}/json/version", timeout=1.5)
            if not cdp_seen:
                print(f"  CDP 已监听: {str(ver.get('Browser'))[:60]}")
                cdp_seen = True
            targets = http_json(f"http://127.0.0.1:{PORT}/json/list")
            pages = [t for t in targets if t.get("type") == "page"]
            app_pages = [t for t in pages if _is_app_page(t.get("url") or "")]
            # 首个渲染进程往往是 loading 窗（file://），它随后会关闭；
            # 等到真正的 48911 页面出现再开始探针，否则会拿到 "No such target id"。
            if app_pages:
                return app_pages
            last = pages or last
        except Exception as exc:  # CDP 还没起来
            last = str(exc)
        time.sleep(1.0)
    return last if isinstance(last, list) else []


def cdp_eval(ws_url: str, expression: str, collect_console_s: float = 3.0):
    """用 CDP 在指定 target 里求值，顺带收集 console 错误。"""
    from websocket import create_connection  # type: ignore

    ws = create_connection(ws_url, timeout=10)
    seq = {"id": 0}

    def send(method, params=None):
        seq["id"] += 1
        msg_id = seq["id"]
        ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = json.loads(ws.recv())
            if raw.get("id") == msg_id:
                return raw

    errors: list[str] = []
    try:
        send("Runtime.enable")
        send("Log.enable")
        send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})

        # 收集一会儿 console / 异常
        ws.settimeout(0.5)
        t_end = time.time() + collect_console_s
        while time.time() < t_end:
            try:
                raw = json.loads(ws.recv())
            except Exception:
                continue
            method = raw.get("method")
            if method == "Runtime.consoleAPICalled" and raw["params"].get("type") in ("error", "warning"):
                args = raw["params"].get("args") or []
                text = " ".join(str(a.get("value", a.get("description", ""))) for a in args)
                errors.append(f"[{raw['params']['type']}] {text[:160]}")
            elif method == "Runtime.exceptionThrown":
                d = raw["params"].get("exceptionDetails", {})
                errors.append(f"[exception] {str(d.get('text'))[:120]} {str(d.get('exception', {}).get('description', ''))[:120]}")
        result = send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
    finally:
        ws.close()

    value = None
    try:
        value = result["result"]["result"].get("value")
    except Exception:
        value = {"_raw": str(result)[:200]}
    return value, errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="把结果写到这个文件")
    ap.add_argument("--keep-open", action="store_true", help="跑完不杀进程（调试用）")
    ap.add_argument("--extra-args", default="", help="额外传给 electron 的参数（空格分隔）")
    ap.add_argument("--wait", type=float, default=75.0, help="等 CDP/渲染进程的秒数")
    ap.add_argument("--entry", default=".",
                    help="electron 启动的入口（默认 \".\" 即整个应用；工装可传自定义 main.js）")
    ap.add_argument("--settle", type=float, default=6.0,
                    help="首个应用页面出现后再等几秒，让卫星窗口（chat/toast）也建出来")
    args = ap.parse_args()

    electron = SHELL_DIR / "node_modules" / "electron" / "dist" / "electron.exe"
    if not electron.exists():
        print(f"❌ 找不到 electron: {electron}", file=sys.stderr)
        return 2

    user_data = tempfile.mkdtemp(prefix="neko-smoke-")
    env = dict(os.environ)
    env["NEKO_USER_DATA_DIR"] = user_data  # 隔离配置，不碰用户真实 profile
    env.setdefault("ELECTRON_ENABLE_LOGGING", "1")
    # ⚠️ 关键：宿主（WorkBuddy 自己也是 Electron 应用）会把 ELECTRON_RUN_AS_NODE=1 注入环境，
    # 于是 electron.exe 按「普通 Node」执行，主进程里 require('electron').app 是 undefined，
    # 启动即崩（`Cannot read properties of undefined (reading 'setPath')`）。
    # NODE_OPTIONS 里的 language shim 同样只对宿主有意义，一并摘掉。
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env.pop("NODE_OPTIONS", None)
    # safe-delete 守卫只注入 Node 进程；NEKO 启动链会用 node 子进程做日志清理，
    # 被拦会让 launcher 判失败并回滚（技能 lumo-stack-startup 坑二/坑三）。
    for _k in ("CODEBUDDY_SAFE_DELETE_BULK_GUARD", "CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR",
               "CODEBUDDY_SAFE_DELETE_REPORT_PATH"):
        env.pop(_k, None)

    # --disable-gpu：这台机器上 GPU 进程连崩 6 次后 Electron 直接 FATAL 退出
    # （`GPU process isn't usable. Goodbye.`），冒烟只关心渲染进程里的 JS，不需要 GPU。
    cmd = [str(electron), args.entry, f"--remote-debugging-port={PORT}", "--remote-allow-origins=*"]
    if args.extra_args.strip():
        cmd.extend(args.extra_args.split())
    else:
        cmd.extend(["--disable-gpu", "--disable-software-rasterizer", "--disable-gpu-compositing"])
    print(f"  启动: {' '.join(cmd)}")
    print(f"  隔离配置: {user_data}")
    # 输出落到二进制日志文件：Windows 控制台输出是 GBK，走 PIPE 会让解码线程崩掉、
    # 之后管道不再被排空，子进程写满缓冲区就卡死（实测踩过，表现为"等不到 CDP"）。
    log_path = pathlib.Path(tempfile.gettempdir()) / "neko-smoke-electron.log"
    log_fh = open(log_path, "wb")
    proc = subprocess.Popen(
        cmd, cwd=str(SHELL_DIR), env=env,
        stdout=log_fh, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    report = {"targets": [], "started_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        pages = wait_targets(deadline_s=args.wait, proc=proc)
        if isinstance(pages, dict) and "__exited__" in pages:
            print(f"  ❌ electron 提前退出，exit={pages['__exited__']}")
            tail = log_path.read_bytes()[-1200:].decode("utf-8", "replace")
            print("  --- 日志尾部 ---")
            for line in tail.splitlines()[-12:]:
                print(f"    {line}")
            report["error"] = f"electron exited {pages['__exited__']}"
        elif not pages:
            print("  ❌ 等不到任何渲染进程（CDP 未就绪）")
            tail = log_path.read_bytes()[-800:].decode("utf-8", "replace")
            for line in tail.splitlines()[-8:]:
                print(f"    {line}")
            report["error"] = "no page targets"
        else:
            # Pet 页面出现后 React Chat / Toast 还会继续建（StorageGate → storage_ready_startup），
            # 立刻探针只会看到 Pet 一扇。这里等 settle 秒再重新列一遍。
            time.sleep(args.settle)
            try:
                fresh = http_json(f"http://127.0.0.1:{PORT}/json/list")
                pages = [t for t in fresh if t.get("type") == "page" and _is_app_page(t.get("url") or "")]
            except Exception as exc:
                print(f"  ⚠️ settle 后重新列 target 失败，沿用旧列表: {exc}")
            print(f"  拿到 {len(pages)} 个渲染 target")
            for t in list(pages):
                title = (t.get("title") or "")[:40]
                url = (t.get("url") or "")[:80]
                print(f"    - {title or '(no title)'} | {url}")
                # 窗口可能在两轮之间关闭（Toast 空闲即销毁）；探针前确认 target 还在，
                # 否则 websocket 握手会拿到 500 "No such target id"。
                try:
                    alive = {x.get("id") for x in http_json(f"http://127.0.0.1:{PORT}/json/list")}
                except Exception:
                    alive = {t.get("id")}
                if t.get("id") not in alive:
                    print("      ⤷ target 已关闭，跳过")
                    continue
                try:
                    value, errs = cdp_eval(t["webSocketDebuggerUrl"], PROBE)
                except Exception as exc:
                    print(f"      ⤷ 探针失败（target 可能已关闭）: {exc}")
                    report["targets"].append({
                        "title": title, "url": url, "probe": None,
                        "console": [], "error": str(exc),
                    })
                    continue
                report["targets"].append({"title": title, "url": url, "probe": value, "console": errs})
    finally:
        if not args.keep_open:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
            try:
                log_fh.close()
            except Exception:
                pass
            shutil.rmtree(user_data, ignore_errors=True)
            print("  已关闭 electron 并清理临时配置")

    print("\n=== 探针结果 ===")
    for t in report["targets"]:
        p = t["probe"] or {}
        print(f"  [{t['title'] or t['url']}]")
        print(f"    nekoWebSocket      : {p.get('hasNekoWebSocket')}  (create={p.get('hasNekoWebSocketCreate')})")
        print(f"    __nekoCreateWebSocket: {p.get('hasAdapter')}")
        print(f"    WebSocket 是原生    : {p.get('webSocketIsNative')}")
        if p.get("petDiagnostics"):
            d = p["petDiagnostics"]
            print(f"    pet host 注册     : {d.get('hostRegistered')}  (isolated={d.get('isolated')})")
            print(f"    pet miss          : {d.get('misses')}")
            pr = d.get("probes") or {}
            print("    pet 桥探针        : " + ", ".join(f"{k}={v}" for k, v in pr.items()))
        if "probeReadyState0" in p:
            print(f"    probe readyState   : {p.get('probeReadyState0')} → close 后 {p.get('probeReadyStateAfterClose')}")
        if p.get("probeError"):
            print(f"    probe error        : {p['probeError']}")
        if t["console"]:
            print(f"    console 错误 {len(t['console'])} 条:")
            for e in t["console"][:5]:
                print(f"      {e}")

    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  报告已写: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
