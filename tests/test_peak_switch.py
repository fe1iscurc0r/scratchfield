"""工单229 任务二 · ``tools/peak_switch.sh`` 时段判定回归测试。

做法：**真实执行脚本**，只把 ``date`` 与 ``hermes`` 两个外部命令换成临时 bin 目录里的
假可执行文件（置于 PATH 首位）。因此被测的是真正会跑的那条代码路径，而不是复刻的逻辑。

覆盖：
* 工单要求的 6 个时段用例（Sat 20:00 / Mon 09:30 / Mon 13:00 / Mon 14:30 / Sun 10:00 / Fri 18:30）
* 四个边界点的「左闭右开」契约（09:00 / 12:00 / 14:00 / 18:00）
* ``--dry-run`` 不得调用 hermes
* ``CONFIG_KEYS`` 多键按给定顺序逐个切换
* 模型名可被环境变量覆盖
* 参数校验（exit 2）

若本机没有 POSIX ``sh``（Windows 外的极少数环境）则整体 skip——不假装通过。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.core]

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "peak_switch.sh"

PEAK_MODEL = "MiniMax-M3"
VALLEY_MODEL = "deepseek-flash"


@pytest.fixture()
def sh_exe() -> str:
    exe = shutil.which("sh")
    if not exe:
        pytest.skip("本机无 POSIX sh，无法执行 tools/peak_switch.sh")
    return exe


def _write_exe(path: Path, body: str) -> None:
    """写一个可执行的假命令（显式 LF + chmod +x）。"""
    path.write_text(body, encoding="utf-8", newline="")
    path.chmod(0o755)


def _harness(tmp_path: Path, date_snapshot: str) -> tuple[dict[str, str], Path]:
    """搭一个假 date / 假 hermes 的 PATH 环境，返回 (env, hermes 调用日志路径)。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(bin_dir / "date", '#!/bin/sh\nprintf "%s\\n" "' + date_snapshot + '"\n')
    log = tmp_path / "hermes.log"
    _write_exe(bin_dir / "hermes", '#!/bin/sh\nprintf "%s\\n" "$*" >> "$HERMES_CALL_LOG"\n')
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    env["HERMES_CALL_LOG"] = str(log)
    for key in ("PEAK_MODEL", "VALLEY_MODEL", "CONFIG_KEYS", "HERMES_BIN", "DATE_BIN"):
        env.pop(key, None)
    return env, log


def _run(sh_exe: str, args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sh_exe, SCRIPT.as_posix(), *args],
        env=env, cwd=str(cwd), capture_output=True, text=True, timeout=30, check=False,
    )


def _calls(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


# (用例名, 假 date 输出 "<星期> <时> <分>", 期望模型, 说明)
SEGMENT_CASES = [
    ("Sat_20-00", "6 20 00", VALLEY_MODEL, "周末全天谷段"),
    ("Mon_09-30", "1 09 30", PEAK_MODEL, "峰段 09:00-12:00"),
    ("Mon_13-00", "1 13 00", VALLEY_MODEL, "午休 12:00-14:00 是谷段"),
    ("Mon_14-30", "1 14 30", PEAK_MODEL, "峰段 14:00-18:00"),
    ("Sun_10-00", "7 10 00", VALLEY_MODEL, "周末全天谷段"),
    ("Fri_18-30", "5 18 30", VALLEY_MODEL, "18:00 之后回落谷段"),
]

# 边界点：左闭右开
BOUNDARY_CASES = [
    ("Mon_09-00", "1 09 00", PEAK_MODEL, "09:00 含在峰段（左闭）"),
    ("Mon_11-59", "1 11 59", PEAK_MODEL, "12:00 之前仍在峰段"),
    ("Mon_12-00", "1 12 00", VALLEY_MODEL, "12:00 不含在峰段（右开）"),
    ("Mon_13-59", "1 13 59", VALLEY_MODEL, "14:00 之前仍是谷段"),
    ("Mon_14-00", "1 14 00", PEAK_MODEL, "14:00 含在峰段（左闭）"),
    ("Mon_17-59", "1 17 59", PEAK_MODEL, "18:00 之前仍在峰段"),
    ("Mon_18-00", "1 18 00", VALLEY_MODEL, "18:00 不含在峰段（右开）"),
]


@pytest.mark.parametrize(
    ("snapshot", "expected", "why"),
    [c[1:] for c in SEGMENT_CASES],
    ids=[c[0] for c in SEGMENT_CASES],
)
def test_segment_selects_model(snapshot: str, expected: str, why: str, tmp_path: Path, sh_exe: str) -> None:
    env, log = _harness(tmp_path, snapshot)
    result = _run(sh_exe, [], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"→ {expected}" in result.stdout, f"{why}: stdout={result.stdout!r}"
    assert _calls(log) == [f"config set model.default {expected}"], f"{why}: {_calls(log)}"


@pytest.mark.parametrize(
    ("snapshot", "expected", "why"),
    [c[1:] for c in BOUNDARY_CASES],
    ids=[c[0] for c in BOUNDARY_CASES],
)
def test_peak_window_boundaries(snapshot: str, expected: str, why: str, tmp_path: Path, sh_exe: str) -> None:
    env, log = _harness(tmp_path, snapshot)
    result = _run(sh_exe, [], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _calls(log) == [f"config set model.default {expected}"], f"{why}: {_calls(log)}"


def test_dry_run_never_invokes_hermes(tmp_path: Path, sh_exe: str) -> None:
    env, log = _harness(tmp_path, "1 09 30")
    result = _run(sh_exe, ["--dry-run"], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "[dry-run]" in result.stdout
    assert PEAK_MODEL in result.stdout
    assert _calls(log) == [], "dry-run 不得调用 hermes"


def test_now_overrides_date(tmp_path: Path, sh_exe: str) -> None:
    """date 说峰段，--now 说周末 20:00 → 必须以 --now 为准（谷段）。"""
    env, log = _harness(tmp_path, "1 09 30")
    result = _run(sh_exe, ["--now", "6 20 00"], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _calls(log) == [f"config set model.default {VALLEY_MODEL}"]


def test_config_keys_applied_in_order(tmp_path: Path, sh_exe: str) -> None:
    env, log = _harness(tmp_path, "1 09 30")
    env["CONFIG_KEYS"] = "model.default providers.deepseek.model"
    result = _run(sh_exe, [], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _calls(log) == [
        f"config set model.default {PEAK_MODEL}",
        f"config set providers.deepseek.model {PEAK_MODEL}",
    ]


def test_model_names_are_env_overridable(tmp_path: Path, sh_exe: str) -> None:
    env, log = _harness(tmp_path, "6 20 00")
    env["VALLEY_MODEL"] = "probe-valley-model"
    result = _run(sh_exe, [], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _calls(log) == ["config set model.default probe-valley-model"]


def test_hermes_bin_is_env_overridable(tmp_path: Path, sh_exe: str) -> None:
    env, log = _harness(tmp_path, "1 09 30")
    alt_log = tmp_path / "alt.log"
    _write_exe(tmp_path / "bin" / "my-hermes", '#!/bin/sh\nprintf "%s\\n" "$*" >> "' + str(alt_log).replace("\\", "/") + '"\n')
    env["HERMES_BIN"] = "my-hermes"
    result = _run(sh_exe, [], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _calls(log) == []
    assert alt_log.read_text(encoding="utf-8").splitlines() == [f"config set model.default {PEAK_MODEL}"]


@pytest.mark.parametrize(
    "args",
    [["--now"], ["--now", "1 2 3 4"], ["--now", "Mon 09:30"], ["--bogus"]],
    ids=["missing-value", "too-many-fields", "non-numeric", "unknown-flag"],
)
def test_bad_arguments_exit_2(args: list[str], tmp_path: Path, sh_exe: str) -> None:
    env, log = _harness(tmp_path, "1 09 30")
    result = _run(sh_exe, args, env, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert _calls(log) == []


def test_help_exits_zero(tmp_path: Path, sh_exe: str) -> None:
    env, _ = _harness(tmp_path, "1 09 30")
    result = _run(sh_exe, ["--help"], env, tmp_path)
    assert result.returncode == 0
    assert "峰段" in result.stdout
