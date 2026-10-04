"""许可快速核实 —— 本地 LICENSE 读取 + SPDX 识别 + NOASSERTION 标记。

复用 github-sweep 许可矩阵知识：
  - 仓库根目录 LICENSE/COPYING 文件存在性检查
  - SPDX 标识符识别（内容关键词 → spdx_id）
  - NOASSERTION 陷阱：GitHub API 的 spdx_id 可能为 "NOASSERTION"，
    表示无法断言许可 → 标记为「不确定」，绝不当作 PASS。

纯 stdlib，只读，不修改外来文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 常见许可证文件名（大小写不敏感兜底匹配）
LICENSE_NAMES: tuple[str, ...] = (
    "LICENSE", "LICENSE.txt", "LICENSE.md", "LICENSE.rst",
    "COPYING", "COPYING.txt", "COPYING.md",
    "LICENSE-MIT", "LICENSE-APACHE", "LICENSE-GPL", "LICENSE-AGPL", "LICENSE-BSD",
)

# SPDX 标识符 → 内容关键词（文本大写包含即判为该许可）
SPDX_KEYWORDS: dict[str, tuple[str, ...]] = {
    "MIT": ("MIT License", "Permission is hereby granted"),
    "Apache-2.0": ("Apache License", "Version 2.0"),
    "GPL-3.0-only": ("GNU GENERAL PUBLIC LICENSE", "Version 3"),
    "AGPL-3.0-only": ("GNU AFFERO GENERAL PUBLIC LICENSE", "Version 3"),
    "GPL-2.0-only": ("GNU GENERAL PUBLIC LICENSE", "Version 2"),
    "BSD-3-Clause": ("Redistribution and use in source and binary forms", "Neither the name"),
    "BSD-2-Clause": ("Redistribution and use in source and binary forms",),
    "MPL-2.0": ("Mozilla Public License", "2.0"),
    "Unlicense": ("This is free and unencumbered software",),
    "ISC": ("Permission to use, copy, modify",),
}

# 无法断言许可标记（对应 GitHub API spdx_id="NOASSERTION"）
NOASSERTION = "NOASSERTION"


@dataclass
class LicenseCheck:
    """许可核实结果。"""

    found: bool = False          # 是否找到 LICENSE/COPYING 文件
    path: str | None = None      # 许可证文件路径
    spdx_id: str | None = None   # 识别出的 SPDX 标识符（None = 未识别）
    noassertion: bool = False    # 存在文件但无法断言许可（等同 NOASSERTION）
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "path": self.path,
            "spdx_id": self.spdx_id,
            "noassertion": self.noassertion,
            "reason": self.reason,
        }


def find_license_file(root: Path) -> Path | None:
    """在 root 目录下定位许可证文件；root 为文件时改查其父目录。"""
    root = Path(root)
    if root.is_file():
        root = root.parent
    if not root.is_dir():
        return None
    for name in LICENSE_NAMES:
        cand = root / name
        if cand.is_file():
            return cand
    # 兜底：任意以 LICENSE/COPYING 开头的文件
    for cand in root.iterdir():
        if cand.is_file() and cand.name.upper().startswith(("LICENSE", "COPYING")):
            return cand
    return None


def detect_spdx(text: str) -> str | None:
    """按内容关键词识别 SPDX 标识符；无法识别返回 None。"""
    upper = text.upper()
    for spdx, keywords in SPDX_KEYWORDS.items():
        if any(k.upper() in upper for k in keywords):
            return spdx
    return None


def check_license(path: str | Path) -> LicenseCheck:
    """对给定路径（文件或目录）做许可快速核实。"""
    root = Path(path)
    lic = find_license_file(root)
    if lic is None:
        return LicenseCheck(found=False, reason="未找到 LICENSE/COPYING 文件")

    text = lic.read_text(encoding="utf-8", errors="replace")
    spdx = detect_spdx(text)
    if spdx:
        return LicenseCheck(found=True, path=str(lic), spdx_id=spdx, reason=f"识别为 {spdx}")

    return LicenseCheck(
        found=True,
        path=str(lic),
        noassertion=True,
        reason="存在 LICENSE 但无法断言许可（等同 NOASSERTION）",
    )
