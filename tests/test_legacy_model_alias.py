"""工单229 任务一 · 废弃模型别名清扫的回归守卫（纯静态扫描，零网络）。

背景（沈遥侧实测 2026-10-10）：DeepSeek 平台把老别名 alias 到规范名
``deepseek-flash``，但走老别名的请求返回 **HTTP 200 且
``choices[0].message.content == ""``**；部分 SDK / 中间件把「200 但空 content」
判为错误，用户侧表现就是 400。故整条链路（config / fallback / peak_switch / cron）
必须统一到规范名。

本文件把「清扫干净」固化成**可检验契约**，而不是一次性 grep：

* 扫描范围 = 仓内 active 路径，**与 ``pyproject.toml`` 的 ``[tool.ruff] exclude`` 对齐**
  （跳过 NEKO / skills / vendor / 构建产物）；
* 命中废弃别名即 fail，并逐条打印 ``文件:行号:原文``；
* ``ALLOWED_LEGACY_SITES`` 是**显式契约而非遗漏**：只允许「历史证据 / 处置手册」保留旧字面量，
  每条都写明理由。新增落点会立刻红灯，逼人当场做决定，而不是让别名悄悄漂回来。

匹配是**大小写不敏感**的：同一个已废弃模型 ID 在文档 / 注释里常有不同的大小写写法，
指的都是它（本文件自身的散文里刻意不写字面量，以免被自己命中）。
"""
from __future__ import annotations

import fnmatch
import importlib.util
import os
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.core]

REPO_ROOT = Path(__file__).resolve().parent.parent

# 拼接构造针串：本文件自身不应命中扫描（否则得把守卫自己写进允许清单 = 循环论证）
DEPRECATED_ALIAS = "deepseek" + "-chat"
CANONICAL_MODEL = "deepseek-flash"

# 与 pyproject.toml [tool.ruff] exclude 对齐：上游 / 第三方 / 构建产物不是本仓 active 路径
SKIP_DIR_NAMES = frozenset({
    ".git", ".venv", "venv", "env", "node_modules", "build", "dist",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "NEKO", "skills", "vendor",
})
SKIP_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".gz", ".tar", ".7z", ".rar", ".pdf", ".docx", ".xlsx", ".pptx",
    ".mp3", ".mp4", ".wav", ".webm", ".bin", ".pack", ".idx", ".onnx", ".pt", ".safetensors",
})
MAX_BYTES = 2 * 1024 * 1024

# 允许保留废弃别名的位置 —— **显式契约，不是遗漏**。每条都必须写明理由，
# 且有 meta 测试保证「仍存在且仍命中」，防清单腐烂成静默空转。
ALLOWED_LEGACY_SITES: dict[str, str] = {
    # A. 历史证据：带日期的实测记录，改了就是伪造
    "docs/protocol-compat-audit-2026-10.md":
        "历史证据：工单216 六线矩阵的 2026-10-08 实测对照表",
    "mcpserver/rf_brain/SELFTEST.md":
        "历史证据：Phase 4 LLM 接通 2026-08-13 自测实录",
    # B. 处置手册：正文就是「怎么找到并换掉旧名」，必须写出旧名本身
    "docs/PEAK-OFFPEAK-OPS.md":
        "处置手册：§5 模型名变更 SOP 的检索示例必须给出旧名本身",
    # C. 历史快照（2026-10-16 补）：统计基线是**历史 PR 标题**的逐字快照，
    #    其 L599 恰好是 #325 的标题原文（那条标题本身就在讲这次清扫）——
    #    改了就是伪造历史。下面的 meta 测试会盯住「仍存在且仍命中」，不会烂成空转。
    "reports/workorder_conversion_stats_initial_2026-10-11.json":
        "历史证据：漏斗 2.0 闭环统计首期基线（692 行 PR/工单记录快照，含 #325 标题原文）",
    # D. 二级误伤（2026-10-30 补）：上一轮修复自己写下的报告，正文**引用了断言原文**，
    #    于是又把守卫点红了 —— 这不是漏清扫，是"修 bug 的记录被 bug 规则抓住"。
    #    同理不改报告内容：改了就是抹掉当时现场。
    "reports/fix_alias_guard_allowlist_2026-10-16.md":
        "历史证据：2026-10-16 守卫误伤修复的处置记录，正文引用了断言原文与 #325 标题",
}
# 工单正文 = prompt 归档（历史文本），不是 active 代码
ALLOWED_LEGACY_GLOB = "TRAE_WORKORDER_PROMPT_AGENT_*.md"


def is_allowed(rel: str) -> bool:
    """该相对路径是否属于允许保留旧别名的「历史证据 / 工单归档」。"""
    return rel in ALLOWED_LEGACY_SITES or fnmatch.fnmatch(rel, ALLOWED_LEGACY_GLOB)


def scan_legacy_alias(root: Path) -> list[tuple[str, int, str]]:
    """扫描 ``root`` 下的 active 文本文件，返回 ``[(相对路径, 行号, 原文)]``（排序后）。

    纯函数：不依赖仓根，便于用 ``tmp_path`` 做负向对照。
    """
    needle = DEPRECATED_ALIAS.lower()
    hits: list[tuple[str, int, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIR_NAMES)
        for name in sorted(filenames):
            path = Path(dirpath, name)
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue  # 二进制 / 不可读：跳过，不算命中
            if needle not in text.lower():
                continue
            rel = path.relative_to(root).as_posix()
            for lineno, line in enumerate(text.splitlines(), 1):
                if needle in line.lower():
                    hits.append((rel, lineno, line.strip()))
    hits.sort()
    return hits


def test_no_deprecated_alias_outside_allowlist() -> None:
    """主契约：active 路径不得再出现废弃别名。"""
    unexpected = [(rel, lineno, text) for rel, lineno, text in scan_legacy_alias(REPO_ROOT)
                  if not is_allowed(rel)]
    assert not unexpected, (
        f"active 路径仍残留废弃别名 {DEPRECATED_ALIAS!r}（应统一为 {CANONICAL_MODEL!r}）：\n"
        + "\n".join(f"  {rel}:{lineno}: {text}" for rel, lineno, text in unexpected)
    )


def test_allowlist_entries_exist_and_still_match() -> None:
    """允许清单必须仍存在且仍命中——防清单腐烂成静默空转。"""
    for rel, why in ALLOWED_LEGACY_SITES.items():
        path = REPO_ROOT / rel
        assert path.exists(), f"允许清单条目已消失：{rel}（{why}）→ 请同步删除该条目"
        assert DEPRECATED_ALIAS.lower() in path.read_text(encoding="utf-8").lower(), (
            f"允许清单条目已不再命中废弃别名：{rel} → 请同步删除该条目"
        )


def test_scanner_detects_planted_occurrence(tmp_path: Path) -> None:
    """负向对照：证明扫描器真的会命中（否则主断言可能整体空跑）。"""
    planted = tmp_path / "pkg" / "mod.py"
    planted.parent.mkdir(parents=True)
    planted.write_text('MODEL = "' + DEPRECATED_ALIAS + '"\n', encoding="utf-8")
    assert scan_legacy_alias(tmp_path) == [("pkg/mod.py", 1, 'MODEL = "' + DEPRECATED_ALIAS + '"')]


def test_scanner_is_case_insensitive(tmp_path: Path) -> None:
    """大小写变体同样命中（文档里的写法不统一）。"""
    doc = tmp_path / "note.md"
    doc.write_text("默认走 " + DEPRECATED_ALIAS.title() + " 端点\n", encoding="utf-8")
    assert [rel for rel, _, _ in scan_legacy_alias(tmp_path)] == ["note.md"]


def test_scanner_prunes_excluded_dirs(tmp_path: Path) -> None:
    """负向对照：上游 / 第三方目录即便命中也不算 active 落点。"""
    skipped = tmp_path / "vendor" / "third_party.py"
    skipped.parent.mkdir(parents=True)
    skipped.write_text('"' + DEPRECATED_ALIAS + '"\n', encoding="utf-8")
    assert scan_legacy_alias(tmp_path) == []


def test_switch_preset_points_at_canonical_model() -> None:
    """清扫的硬契约：切换器 deepseek 预设必须指向规范名。"""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location(
        "w229_switch_llm_provider", REPO_ROOT / "tools" / "switch_llm_provider.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PRESETS["deepseek"]["model"] == CANONICAL_MODEL
