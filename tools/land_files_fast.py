"""land_files_fast.py — 大批量文件落地（并发 blob 上传 + `base_tree` 一次建树）。

与 `land_files.py` 的区别：后者逐文件串行上传 + 逐级 mktree（1200+ 文件要 15-20 分钟）；
本脚本用线程池并发的 `POST /git/blobs`，再以 `POST /git/trees` 的 **`base_tree` 参数**
一次性把全部条目叠加到基树上（GitHub 服务端合并，无需本地递归建树）。

manifest 格式（同 land_files.json，多一个可选 `mode`）：
    {"branch": str, "base_parent": str(sha40), "message": str,
     "files": [{"local": path, "repo": path, "mode": "100644"|"100755"}]}

用法：python tools/land_files_fast.py <manifest.json> [--workers 10]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPO = "fe1iscurc0r/scratchpad"
API = f"https://api.github.com/repos/{REPO}"
TOKEN = os.environ.get("GTOK", "").strip()
HEADERS = {"Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json",
           "Content-Type": "application/json"}


def call(path: str, method: str = "GET", payload: dict | None = None, ok: tuple = (200, 201)):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(payload).encode() if payload else None,
                                 headers=HEADERS)
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        return e.code, {"err": e.read().decode()[:200]}


def upload_blob(item: dict, _attempt: int = 0) -> dict:
    """上传单文件 blob。403/429（二级速率限制）→ **指数退避重试**（GitHub 限制并发调用）。"""
    data = open(item["local"], "rb").read()
    st, r = call("/git/blobs", "POST",
                 {"content": base64.b64encode(data).decode(), "encoding": "base64"})
    if st != 201:
        if st in (403, 429, 500, 502, 503) and _attempt < 6:
            time.sleep(2.0 * (2 ** _attempt) * (0.7 + random.random() * 0.6))
            return upload_blob(item, _attempt + 1)
        raise RuntimeError(f"{item['repo']}: blob 上传失败 HTTP {st} {r.get('err')}")
    if _attempt:
        time.sleep(0.15)      # 退避恢复后稍微错开，避免再次撞限
    return {"path": item["repo"], "mode": item.get("mode", "100644"),
            "type": "blob", "sha": r["sha"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    m = json.load(open(args.manifest, encoding="utf-8"))
    files = m["files"]
    parent = m["base_parent"]
    print(f"目标分支 {m['branch']} | 基座 {parent[:12]} | 文件 {len(files)} | 并发 {args.workers}")

    st, info = call(f"/git/commits/{parent}")
    if st != 200:
        print("基座提交不可读:", st, info)
        return 1
    base_tree = info["tree"]["sha"]
    print(f"基树 {base_tree[:12]}")

    entries: list[dict] = []
    failed: list[str] = []
    cache = args.manifest + ".blobs.json"
    if os.path.exists(cache):
        entries = json.load(open(cache, encoding="utf-8"))
        print(f"复用 blob 缓存：{len(entries)} 条（跳过重复上传）")
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for i, res in enumerate(ex.map(upload_blob, files), 1):
                if isinstance(res, Exception):
                    failed.append(str(res))
                else:
                    entries.append(res)
                if i % 200 == 0:
                    print(f"  已上传 {i}/{len(files)}")
        print(f"blob 上传完成：成功 {len(entries)} / 失败 {len(failed)}")
        if failed:
            for f in failed[:5]:
                print("  ✗", f)
            return 1
        json.dump(entries, open(cache, "w", encoding="utf-8"))

    # 分批建树：单请求带 1272 条会被服务端拒（502），每批 300 条基于上一棵树迭代叠加
    tree_sha = base_tree
    CHUNK = 300
    for i in range(0, len(entries), CHUNK):
        batch = entries[i:i + CHUNK]
        st, t = call("/git/trees", "POST", {"base_tree": tree_sha, "tree": batch})
        if st != 201:
            print(f"建树失败（第 {i // CHUNK + 1} 批 {len(batch)} 条）:", st, t)
            return 1
        tree_sha = t["sha"]
        print(f"  建树批次 {i // CHUNK + 1}/{(len(entries) + CHUNK - 1) // CHUNK} -> {tree_sha[:12]}")
    tree = {"sha": tree_sha}
    print(f"新树 {tree['sha'][:12]}")

    st, commit = call("/git/commits", "POST",
                      {"message": m["message"], "tree": tree["sha"], "parents": [parent]})
    if st != 201:
        print("建提交失败:", st, commit)
        return 1
    print(f"提交 {commit['sha'][:12]}")

    st, ref = call("/git/refs", "POST",
                   {"ref": f"refs/heads/{m['branch']}", "sha": commit["sha"]}, ok=(201, 422))
    if st not in (201, 422):
        print("建分支失败:", st, ref)
        return 1
    print(f"分支 {m['branch']} -> {commit['sha'][:12]}")
    print("OK")
    print("COMMIT_SHA=" + commit["sha"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
