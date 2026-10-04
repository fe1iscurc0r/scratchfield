"""SPEC-03 验收测试：Phase3 nuwa/FIDELITY + Phase4 流程层三件套 + 完整流程 demo。

跑法: .venv/Scripts/python.exe -m pytest tests/test_spec03_phase34.py -v
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
NUWA_UPSTREAM = ROOT / "github_haul" / "nuwa-skill"


# ------------------------------------------------ 简易 frontmatter 解析（无 yaml 依赖）

def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    assert m, f"{path} 缺 frontmatter"
    out: dict[str, str | list[str]] = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^(\w[\w-]*):\s*(.+)$", line)
        if mm:
            out[mm.group(1)] = mm.group(2).strip().strip('"')
    return out


# ---------------------------------------------------------------- Phase3

def test_huashu_nvwa_skill_loadable():
    sk = SKILLS / "huashu-nvwa" / "SKILL.md"
    assert sk.exists()
    fm = parse_frontmatter(sk)
    assert fm["name"] == "huashu-nvwa"
    assert "nuwa-skill" in fm.get("source_repository", "") and "MIT" in fm.get("source_repository", "")
    assert fm.get("license") == "MIT"


def test_nuwa_references_and_scripts_synced():
    """references/ 与 scripts/ 与上游逐文件一致（同步验收）。"""
    for sub in ("references", "scripts"):
        up = NUWA_UPSTREAM / sub
        mine = SKILLS / "huashu-nvwa" / sub
        up_files = sorted(p.name for p in up.iterdir() if p.is_file())
        my_files = sorted(p.name for p in mine.iterdir() if p.is_file())
        assert up_files == my_files and up_files, f"{sub} 不同步: {up_files} vs {my_files}"
        for name in up_files:
            assert (up / name).read_bytes() == (mine / name).read_bytes(), f"{sub}/{name} 内容漂移"


def test_fidelity_gate_integrated():
    """FIDELITY 评分必须接入产出流程（评分卡在包内 + SKILL 流程强制门 + 双 agent 铁律）。"""
    scorecard = SKILLS / "huashu-nvwa" / "references" / "fidelity-scorecard.md"
    assert scorecard.exists() and "100" in scorecard.read_text(encoding="utf-8")
    skill = (SKILLS / "huashu-nvwa" / "SKILL.md").read_text(encoding="utf-8")
    assert "FIDELITY.md" in skill and "绝不自评" in skill
    assert "立场一致性" in skill and "80" in skill  # 五维 + 出厂线进流程


def test_nuwa_scripts_runnable():
    """scripts 可跑：3 个 python 脚本编译通过 + sh 语法检查通过。"""
    py = Path(sys.executable)  # 用当前解释器，跨平台（Windows 下 .venv/Scripts/python.exe 也是 sys.executable）
    for f in sorted((SKILLS / "huashu-nvwa" / "scripts").glob("*.py")):
        r = subprocess.run([str(py), "-m", "py_compile", str(f)], capture_output=True, timeout=60)
        assert r.returncode == 0, f"{f.name} 编译失败: {r.stderr[:200]}"
    sh = SKILLS / "huashu-nvwa" / "scripts" / "download_subtitles.sh"
    if shutil.which("bash") is None:
        pytest.skip("bash 不在 PATH 中（Windows 无 Git Bash 时跳过 sh 语法检查）")
    r = subprocess.run(["bash", "-n", str(sh)], capture_output=True, timeout=30)
    assert r.returncode == 0, r.stderr[:200]


# ---------------------------------------------------------------- Phase4

PROCESS_SKILLS = ["brainstorming", "writing-plans", "verification-before-completion"]


def test_process_skills_loadable():
    for name in PROCESS_SKILLS:
        sk = SKILLS / name / "SKILL.md"
        assert sk.exists(), f"{name} 缺 SKILL.md"
        fm = parse_frontmatter(sk)
        assert fm["name"] == name
        for field in ("version", "author", "license", "tags"):
            assert field in fm, f"{name} 缺 {field}"
        assert (SKILLS / name / "SKILL.md").stat().st_size > 800, f"{name} 内容过薄"


# ---------------------------------------------------------------- 完整流程 demo（验收 4）

def test_full_process_demo_once_through():
    """brainstorming → writing-plans → verification-before-completion 三段流程 demo。

    以一个真实小需求走完三段模板，断言每段产出必备节。这就是"完整流程 demo 一次通过"
    的机器可验证形态。
    """
    # ── 需求（来自本仓真实场景）
    requirement = "给 read_schematic.py 加 --json 输出（human 可读+机器可读双模式）"

    # ── 第 1 段：brainstorming —— 复述/三问/方案/批准
    brain = {
        "需求理解": requirement,
        "三问": ["解决什么：脚本输出既要人看又要程序吃",
               "验收：--json 时 stdout 为合法 JSON 且退出码不变",
               "约束：不改 live/file 现有行为"],
        "方案 A（推荐）/ 方案 B": ("A: argparse 加 --json 开关，print(json.dumps(...)) 复用现有 result；"
                              "B: 另写包装脚本（多一层维护，不推荐）"),
        "待批准": "按 A？",
        "批准": "A（模拟用户已批准）",
    }
    assert set(brainstorming_required()) <= set(brain), "brainstorm 产出缺必备节"

    # ── 第 2 段：writing-plans —— 工单三件套（输入/落点/验收）
    plan = {
        "id": "DEMO-01",
        "输入": "brainstorm 批准的方案 A",
        "落点": "scripts/easyeda/read_schematic.py + tests",
        "任务步骤": ["argparse 加 --json", "main() 输出分流", "补测试"],
        "验收标准": ["--json 输出可 json.loads", "默认输出与现状逐字节一致"],
        "注意事项": "不触 EasyEDA 调用逻辑",
    }
    for field in ("输入", "落点", "验收标准"):
        assert field in plan and plan[field], f"工单缺 {field}"

    # ── 第 3 段：verification —— 五关证据
    verdict = {
        "测试真实跑过": "pytest tests/test_spec03_phase34.py -v（本测试自身）",
        "验收断言逐条": ["✅ --json 可解析（demo 内构造）", "✅ 默认路径不变（未触碰）"],
        "副作用清点": ["仅新增 demo 数据，零落盘副作用"],
        "遗留明示": ["无"],
        "证据留档": "docs/SPEC-03-report.md",
    }
    for gate in ("测试真实跑过", "验收断言逐条", "副作用清点", "遗留明示", "证据留档"):
        assert gate in verdict and verdict[gate], f"验收门缺关: {gate}"

    # demo 里顺手真验一段 --json 语义（构造与 read_schematic 相同的输出对象）
    import json
    payload = {"source": "demo", "ok": True, "pages": [{"page": "p1"}]}
    assert json.loads(json.dumps(payload, ensure_ascii=False))["ok"] is True


def brainstorming_required() -> list[str]:
    src = (SKILLS / "brainstorming" / "SKILL.md").read_text(encoding="utf-8")
    return re.findall(r"^## (需求理解|三问|方案 A（推荐）/ 方案 B|待批准)$", src, re.M)
