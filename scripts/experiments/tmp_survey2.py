# -*- coding: utf-8 -*-
"""剩余分支盘点：本地/远程分支 ahead/behind + 已合并检测。"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
R = r"d:\my git\scratchpad"


def run(*a):
    r = subprocess.run(["git", "-C", R] + list(a), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stdout


# 1. 本地分支
locals_ = [l[2:].strip() for l in run("branch", "-vv").splitlines()]
print("=== 本地分支 (%d) ===" % len(locals_))
for b in locals_:
    ahead = run("rev-list", "--count", f"main..{b}").strip()
    behind = run("rev-list", "--count", f"{b}..main").strip()
    merged = run("branch", "--merged", "main").find(" " + b) >= 0 or \
             run("merge-base", "--is-ancestor", b, "main") == ""
    anc = subprocess.run(["git", "-C", R, "merge-base", "--is-ancestor", b, "main"]
                         ).returncode
    tip = run("log", "-1", "--format=%h %ad %s", "--date=short", b).strip()
    print(f"  {b:42s} +{ahead}/-{behind} {'已入main' if anc==0 else ''} | {tip[:80]}")

# 2. 远程分支
remotes = [l.strip() for l in run("branch", "-r").splitlines()
           if "->" not in l and l.strip()]
print("\n=== 远程分支 (%d) ===" % len(remotes))
for b in remotes:
    ahead = run("rev-list", "--count", f"main..{b}").strip()
    behind = run("rev-list", "--count", f"{b}..main").strip()
    anc = subprocess.run(["git", "-C", R, "merge-base", "--is-ancestor", b, "main"]
                         ).returncode
    tip = run("log", "-1", "--format=%h %ad %s", "--date=short", b).strip()
    print(f"  {b:42s} +{ahead}/-{behind} {'已入main' if anc==0 else ''} | {tip[:80]}")
