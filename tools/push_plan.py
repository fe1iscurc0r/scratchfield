"""push_plan.py — 推送前的冲突分析（卷189-192 落地远端 main）。

REST 推送要用远端 main 的 tree 作 base_tree、只叠加"我的净变更"。
但如果远端也改过我改过的同一文件，直接覆盖会**丢掉远端的新改动**。

实现要点：**不用 `GET /git/trees?recursive=1`**（本仓 2 万+ 文件，该响应会被超时/中断），
改为只对我改动的文件逐个查 `GET /contents/<path>?ref=main` 拿 blob sha（并发）。

分类：
  A. 安全覆盖 —— 远端该文件 == 我 base 的版本（远端没动过）
  B. ⚠️ 远端也改过 —— 需人工判断
  C. ⚠️ 新增但远端已有同名
  D. 远端缺失 —— 远端没这文件
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.github.com/repos/fe1iscurc0r/scratchpad"


def token() -> str:
    out = subprocess.run(
        ["C:/Program Files/Git/mingw64/bin/git-credential-manager.exe", "get"],
        input="protocol=https\nhost=github.com\n\n", text=True,
        capture_output=True, cwd=ROOT).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    raise SystemExit("✗ 未能从 GCM 取到 token")


def api(path: str, tok: str, timeout: int = 30) -> dict | None:
    req = urllib.request.Request(API + path, headers={
        "Authorization": f"token {tok}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "lumo-push-plan",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout


def local_tree(rev: str) -> dict[str, str]:
    out = git("ls-tree", "-r", rev)
    d = {}
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        mode, typ, sha = meta.split()
        if typ == "blob":
            d[path] = sha
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="8cce2ac5c")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--remote", default="main")
    ap.add_argument("--out", default="pushplan.json")
    args = ap.parse_args()

    tok = token()
    ref = api(f"/git/ref/heads/{args.remote}", tok)
    remote_sha = ref["object"]["sha"]
    print(f"远端 {args.remote} = {remote_sha}")

    base = local_tree(args.base)
    head = local_tree(args.head)
    changed = sorted({p for p in set(head) | set(base)
                      if head.get(p) != base.get(p)})
    add = [p for p in changed if p not in base]
    mod = [p for p in changed if p in base]
    print(f"本地 base={args.base} ({len(base)} 文件) → HEAD ({len(head)} 文件)")
    print(f"净变更 {len(changed)}：新增 {len(add)} / 修改 {len(mod)}")
    print("查询远端 sha（并发 8）…")

    def probe(p: str):
        d = api(f"/contents/{urllib.parse.quote(p)}?ref={args.remote}", tok)
        return p, (d or {}).get("sha")

    remote: dict[str, str | None] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (p, sha) in enumerate(ex.map(probe, changed), 1):
            remote[p] = sha
            if i % 30 == 0:
                print(f"  … {i}/{len(changed)}")

    safe, conflict, new_conflict, absent = [], [], [], []
    for p in mod:
        r = remote.get(p)
        if r is None:
            absent.append(p)
        elif r == base[p]:
            safe.append(p)
        else:
            conflict.append(p)
    for p in add:
        (new_conflict if remote.get(p) else absent).append(p)

    print(f"\n  A 安全覆盖（远端未动）    : {len(safe)}")
    print(f"  B ⚠️ 远端也改过          : {len(conflict)}")
    print(f"  C ⚠️ 新增撞同名          : {len(new_conflict)}")
    print(f"  D 远端缺失               : {len(absent)}")
    for label, items in (("B", conflict), ("C", new_conflict)):
        if items:
            print(f"\n--- {label} 类明细 ---")
            for p in items:
                print(f"  {p}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"remote_sha": remote_sha, "changed": changed,
                   "add": add, "mod": mod, "safe": safe,
                   "conflict": conflict, "new_conflict": new_conflict,
                   "absent": absent}, f, ensure_ascii=False, indent=2)
    print(f"\n已写出 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
