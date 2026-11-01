"""一次性：把上游 N.E.K.O f7d2744646 落到 scratchfield 的 NEKO/N.E.K.O/。

和 scratchpad 那次同一套路（plumbing 层写 index，不碰工作树），差别是 scratchfield
自己带的一批补丁要保住：22 个与 scratchpad 逐字节相同的补丁文件 + 我们自维护的两份
文档。这两组内容随资产一起进来，先 git hash-object -w 落成本地对象再进 index。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PRE = "NEKO/N.E.K.O/"
HERE = Path(".neko-sync")
UPSTREAM_SHA = "f7d274464691cc5fccc3bcf1fae9d82cfa46296e"

# 补丁文件（路径 -> 资产里的扁平文件名）。前 22 个来自 scratchpad 的合并结果，
# scratchfield 侧与 scratchpad 逐字节相同，直接复用不会引入分叉。
OURS = {
    "app/monitor.py": "app_monitor.py",
    "config/__init__.py": "config___init__.py",
    "config/network.py": "config_network.py",
    "local_server/survey_server/security.py": "local_server_survey_server_security.py",
    "local_server/survey_server/server.py": "local_server_survey_server_server.py",
    "local_server/telemetry_server/security.py": "local_server_telemetry_server_security.py",
    "local_server/telemetry_server/server.py": "local_server_telemetry_server_server.py",
    "main_logic/core/lifecycle.py": "main_logic_core_lifecycle.py",
    "main_logic/cross_server.py": "main_logic_cross_server.py",
    "main_logic/proactive_chat/state.py": "main_logic_proactive_chat_state.py",
    "main_routers/agent_router.py": "main_routers_agent_router.py",
    "main_routers/system_router/steam.py": "main_routers_system_router_steam.py",
    "plugin/plugins/app_launcher/__init__.py": "plugin_plugins_app_launcher___init__.py",
    "plugin/plugins/app_launcher/plugin.meta.json": "plugin_plugins_app_launcher_plugin.meta.json",
    "scripts/telemetry_smoke.py": "scripts_telemetry_smoke.py",
    "static/app/app-websocket.js": "static_app_app-websocket.js",
    "templates/chat.html": "templates_chat.html",
    "templates/index.html": "templates_index.html",
    "tests/unit/test_cfa_resilience.py": "tests_unit_test_cfa_resilience.py",
    "tests/unit/test_recent_compress_backup.py": "tests_unit_test_recent_compress_backup.py",
    "utils/survey_client.py": "utils_survey_client.py",
    "utils/token_tracker/reporting.py": "utils_token_tracker_reporting.py",
}

# 我们自维护的两份文档（上游没有这两个路径，不在 diff 里，要单独写）
DOCS = {
    "docs/plugins/use-claw.md": "docs_plugins_use-claw.md",
    "docs/zh-CN/plugins/use-claw.md": "docs_zh-CN_plugins_use-claw.md",
}

# 上游 PR #3015（2026-08-31）移除 OpenFang 通道时删掉的三处
EXTRA_DELETE = [
    "app/agent_server/channels/openfang.py",
    "brain/openfang_adapter.py",
    "tests/unit/test_openfang_provider_detection.py",
]


def sh(*args: str, check: bool = True, input_bytes: bytes | None = None) -> str:
    r = subprocess.run(list(args), capture_output=True, input=input_bytes)
    if check and r.returncode != 0:
        sys.stderr.write(r.stdout.decode("utf-8", "replace"))
        sys.stderr.write(r.stderr.decode("utf-8", "replace"))
        raise SystemExit(f"failed: {' '.join(args)}")
    return r.stdout.decode("utf-8", "replace").strip()


def main() -> None:
    entries = json.loads((HERE / "_neko_entries.json").read_text(encoding="utf-8"))
    diff = json.loads((HERE / "_neko_diff.json").read_text(encoding="utf-8"))

    added = list(diff["added"])
    modified = [p for p in diff["modified"] if p not in OURS]
    deleted = list(diff["deleted"])

    got = sh("git", "rev-parse", "FETCH_HEAD")
    if got != UPSTREAM_SHA:
        raise SystemExit(f"FETCH_HEAD 不是预期上游提交: {got}")

    print(f"新增 {len(added)} / 替换 {len(modified)} / 我们的补丁 {len(OURS)} / 文档 {len(DOCS)} / 删除 {len(deleted)}")

    lines = []
    for p in sorted(set(added) | set(modified)):
        mode, sha = entries[p]
        lines.append(f"{mode} blob {sha}\t{PRE}{p}")

    # 我们的内容：先落到本地对象库，再进 index（write-tree 会校验对象在本地）
    for group in (OURS, DOCS):
        for p, flat in sorted(group.items()):
            src = HERE / "ours" / flat
            sha = sh("git", "hash-object", "-w", str(src))
            mode = entries[p][0] if p in entries else "100644"
            lines.append(f"{mode} blob {sha}\t{PRE}{p}")
            print(f"  ours {p} -> {sha[:12]}")

    sh("git", "update-index", "--index-info", input_bytes=("\n".join(lines) + "\n").encode("utf-8"))
    print(f"index 写入 {len(lines)} 条")

    remove = [PRE + p for p in deleted] + [PRE + p for p in EXTRA_DELETE]
    # 只有真正在 index 里的才删，避免对不存在的路径报错
    tracked = set(sh("git", "ls-files", "--", *remove).splitlines()) if remove else set()
    remove = [p for p in remove if p in tracked]
    if remove:
        sh("git", "update-index", "--force-remove", "--", *remove)
    print(f"index 移除 {len(remove)} 条")

    # 资产自身不进最终提交
    subprocess.run(["git", "rm", "-r", "-q", "-f", "--cached", "--ignore-unmatch", ".neko-sync"],
                   capture_output=True)
    subprocess.run(["git", "update-index", "--force-remove", "--", ".github/workflows/neko-sync.yml"],
                   capture_output=True, check=False)

    listing = sh("git", "ls-files", "-s", "--", PRE + "pyproject.toml", PRE + "README.MD")
    print("抽样:\n" + listing)
    print("APPLY-OK")


if __name__ == "__main__":
    main()
