"""sync_neko_upstream.py — 从上游 `Project-N-E-K-O/N.E.K.O` 增量同步到本仓 `NEKO/N.E.K.O/`。

背景（工单203 任务四）：
    `git fetch` 在本机被代理拦（`fetch-pack: invalid index-pack output`），
    故走 **REST Git Data API 逐 blob**（流程沿用 `docs/neko-上游同步-2026-09-30.md`
    已验证的方法：上次 295/300 文件一次通过）。

关键设计：
    - **逐提交累积 Δ**：`/compare` 的 `files` 有 300 条上限（本次已截断），
      但 `commits` 数组不受限 → 拿全部提交再逐提交取 `files`，合并为最终态；
    - **字节级同步**：blob 内容 base64 解码后**原样写盘**（不做行尾/编码转换）；
    - **本地无变化则跳过**：用 `git hash-object` 对比 blob sha，省 API 调用；
    - **删除**：上游 removed 的文件在本仓同步删除（保持与上游一致），
      但只在本地确实存在时删，并记入报告；
    - **路径安全闸**：`path` 是远端可控字符串，`LOCAL_ROOT / path` 对绝对路径会直接换根、
      对 `..` 会往上跳，所以写/删之前一律先过 `preflight()` → `_safe_target()`。
      命中即**整批中止**（不是跳过），退出码 2，磁盘一字节不动。

退出码：0 全部一致或全部写成功 / 1 个别文件写失败 / 2 安全闸整批中止。

用法：
    .venv/Scripts/python.exe tools/sync_neko_upstream.py --base 8086151 --check
    .venv/Scripts/python.exe tools/sync_neko_upstream.py --base 8086151 --write
    .venv/Scripts/python.exe tools/sync_neko_upstream.py --base <sha> --tip <sha> --write
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "Project-N-E-K-O/N.E.K.O"
UP_API = f"https://api.github.com/repos/{UPSTREAM}"
#: 上游仓库根 → 本仓子树（上游路径直接挂在这一层下）
LOCAL_ROOT = ROOT / "NEKO" / "N.E.K.O"

#: Windows 保留名：不分大小写、忽略扩展名（`CON.txt` 一样撞设备命名空间）
_WIN_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "CLOCK$", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class UnsafePath(ValueError):
    """上游给的路径字符串不能安全地落到本地子树里（写和删都算）。"""


def _safe_target(upstream_path: str, *, root: Path | None = None) -> Path:
    """把上游路径串解析成本地落盘目标；不安全就抛 ``UnsafePath``，绝不返回一个越界的 Path。

    上游文件列表里的字符串是**远端可控输入**，而 ``LOCAL_ROOT / path`` 对 ``..`` 和绝对路径
    都不设防：绝对路径会让 ``/`` 运算直接换根，``..`` 会往上跳。这里先做词法拒绝（绝对、盘符、
    反斜杠、``.``/``..``/空段、纯点名、尾点尾空格、NTFS 备用数据流的 ``:``、Windows 保留名），
    再做一次 ``resolve()`` 复核落点仍在子树内 —— 后者才拦得住符号链接把写入引出树外。
    """
    root = LOCAL_ROOT if root is None else root
    raw = str(upstream_path)
    anchor = Path(root).resolve()

    def reject(why: str) -> "NoReturn":  # noqa: F821 - 只做类型提示，不依赖 typing
        raise UnsafePath(f"{raw!r}: {why}")

    if not raw.strip():
        reject("空路径")
    if raw.startswith("/"):
        reject("绝对路径")
    if re.match(r"^[A-Za-z]:", raw):
        reject("含盘符")
    if "\\" in raw:
        reject("含反斜杠（上游路径应是 POSIX 风格；在 Windows 上它要么是分隔符要么是非法字符）")
    parts = raw.split("/")
    if any(not seg for seg in parts):
        reject("含空段（连续斜杠或首尾斜杠）")
    if any(set(seg) == {"."} for seg in parts):
        reject("含 '.' 或 '..' 段")
    if any(seg != seg.rstrip(". ") for seg in parts):
        reject("段尾的点或空格会被 Windows 静默剥掉，落点与请求名不一致")
    if any(":" in seg for seg in parts):
        reject("含冒号（NTFS 备用数据流写法会写到另一个文件里）")
    for seg in parts:
        stem = seg.split(".")[0].upper()
        if stem in _WIN_RESERVED:
            reject(f"是 Windows 保留名（{stem}）")

    joined = anchor.joinpath(*[PurePosixPath(seg).name for seg in parts])
    resolved = joined.resolve() if hasattr(joined, "resolve") else joined
    if not resolved.is_relative_to(anchor):
        reject(f"解析后落到子树之外：{resolved}")
    if resolved != anchor.joinpath(*parts):
        reject(f"经符号链接重定向：请求 {raw!r} 实际落到 {resolved}")
    return resolved


def _safe_removal(target: Path, *, root: Path | None = None) -> str | None:
    """删除前的额外条件；返回拒绝理由，``None`` 表示可以删。"""
    root = LOCAL_ROOT if root is None else root
    anchor = Path(root).resolve()
    rel = target.relative_to(anchor)
    if ".git" in rel.parts:
        return "位于 .git/ 内"
    if target.is_symlink():
        return "本身是符号链接（unlink 会删掉链接指向的东西之外的东西，且这是本地状态，上游无从描述）"
    if target.is_dir():
        return "是目录（上游只描述了文件）"
    return None


def _token() -> str:
    tok = os.environ.get("GTOK") or os.environ.get("GITHUB_TOKEN") or ""
    if tok:
        return tok
    try:
        out = subprocess.run(
            ["git", "credential-manager", "get"], capture_output=True, text=True,
            input="protocol=https\nhost=github.com\n\n")
        for line in out.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except Exception:  # noqa: BLE001
        pass
    return ""


TOKEN = _token()
HEADERS = {"Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json"}


def api(path: str, *, retries: int = 3) -> dict:
    url = path if path.startswith("http") else UP_API + path
    last: Exception | None = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                return json.loads(r.read())
        except Exception as exc:  # noqa: BLE001 - 网络抖动人肉重试
            last = exc
    raise RuntimeError(f"API 失败 {path}: {last}")


def resolve(sha: str) -> str:
    return api(f"/commits/{sha}")["sha"]


def collect_changes(base: str, tip: str, *, verbose: bool = True) -> dict[str, dict]:
    """逐提交累积 → {path: {status, sha, previous_filename}}（后出现的覆盖先出现的）。"""
    cmp = api(f"/compare/{base}...{tip}")
    commits = cmp.get("commits") or []
    if verbose:
        print(f"提交数 {len(commits)} | compare.files 上限命中: {len(cmp.get('files') or []) >= 300}")
    changes: dict[str, dict] = {}
    for i, c in enumerate(commits, 1):
        info = api(f"/commits/{c['sha']}")
        for f in info.get("files") or []:
            changes[f["filename"]] = {
                "status": f["status"],
                "sha": f.get("sha"),
                "previous_filename": f.get("previous_filename"),
            }
        if verbose and i % 20 == 0:
            print(f"  已处理 {i}/{len(commits)} 提交，累计 {len(changes)} 文件")
    return changes


def local_blob_sha(path: Path) -> str | None:
    """本地文件的 git blob sha（不存在返回 None）。用 --path 让过滤器生效（与入库态一致）。"""
    if not path.exists():
        return None
    rel = path.relative_to(ROOT).as_posix()
    out = subprocess.run(["git", "-C", str(ROOT), "hash-object", "--path", rel, str(path)],
                         capture_output=True, text=True)
    return out.stdout.strip() or None


def blob_bytes(sha: str) -> bytes:
    d = api(f"/git/blobs/{sha}")
    return base64.b64decode(d["content"])


def preflight(changes: dict[str, dict]) -> list[str]:
    """碰磁盘之前把整批路径过一遍闸，返回违规说明（空列表 = 放行）。

    违规时调用方必须**整批中止**：逐条静默跳过会留下一半新一半的树，
    比不同步更难收拾（下一次同步还会把这些文件的本地 sha 当成"已一致"）。
    """
    violations: list[str] = []
    for path, meta in sorted(changes.items()):
        try:
            target = _safe_target(path)
        except UnsafePath as exc:
            violations.append(f"[写/删目标] {exc}")
            continue
        if meta["status"] != "removed":
            continue
        why = _safe_removal(target)
        if why:
            violations.append(f"[删除] {why}")
    return violations


def sync(changes: dict[str, dict], *, write: bool) -> dict:
    violations = preflight(changes)
    if violations:
        return {"aborted": True, "violations": violations,
                "added": 0, "modified": 0, "removed": 0, "skipped": 0, "failed": 0,
                "failures": []}

    stats = {"added": 0, "modified": 0, "removed": 0, "skipped": 0, "failed": 0}
    failures: list[str] = []
    for path, meta in sorted(changes.items()):
        target = _safe_target(path)
        if meta["status"] == "removed":
            why = _safe_removal(target)
            if why:
                failures.append(f"{path}: 拒删 — {why}")
                stats["failed"] += 1
                continue
            if target.exists():
                if write:
                    target.unlink()
                stats["removed"] += 1
            continue
        cur = local_blob_sha(target)
        if cur == meta["sha"]:
            stats["skipped"] += 1
            continue
        if not write:
            stats["added" if cur is None else "modified"] += 1
            continue
        try:
            data = blob_bytes(meta["sha"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)                      # 字节级原样写盘
            got = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
            if got != meta["sha"]:
                failures.append(f"{path}: sha 不符 {got[:10]} != {meta['sha'][:10]}")
                stats["failed"] += 1
                continue
            stats["added" if cur is None else "modified"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path}: {type(exc).__name__} {exc}")
            stats["failed"] += 1
    return {**stats, "failures": failures}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="本仓最后一次同步的上游提交（可短 sha）")
    ap.add_argument("--tip", default=None, help="上游目标提交（默认上游 main）")
    ap.add_argument("--write", action="store_true", help="实际写盘（默认只报告）")
    ap.add_argument("--check", action="store_true", help="只报告 Δ（默认行为）")
    args = ap.parse_args()

    base = resolve(args.base)
    tip = resolve(args.tip) if args.tip else api("/git/refs/heads/main")["object"]["sha"]
    print(f"上游 {UPSTREAM}\n  base={base[:12]}  tip={tip[:12]}\n  落盘根={LOCAL_ROOT.relative_to(ROOT)}")

    changes = collect_changes(base, tip)
    from collections import Counter
    cnt = Counter(m["status"] for m in changes.values())
    print(f"最终态 Δ: {len(changes)} 文件 | {dict(cnt)}")

    result = sync(changes, write=args.write)
    if result.get("aborted"):
        print(f"\n✗ 整批中止：{len(result['violations'])} 条路径未通过安全闸，"
              f"磁盘一字节未动（{result['added'] + result['modified'] + result['removed']} 项待办的同步已放弃）。"
              f"\n  上游列表里出现这些名字要么是被攻击、要么是上游布局变了；"
              f"两种都不该由本工具自作主张。")
        for v in result["violations"]:
            print("  ", v)
        return 2

    print(f"\n{'已写入' if args.write else '待写入'}: "
          f"新增 {result['added']} / 修改 {result['modified']} / 删除 {result['removed']} / "
          f"跳过(本地已一致) {result['skipped']} / 失败 {result['failed']}")
    if result["failures"]:
        print("失败清单（前 10）:")
        for f in result["failures"][:10]:
            print("  ", f)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
