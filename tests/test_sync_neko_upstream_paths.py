"""工单271 T1（P0-12）· 上游同步的路径安全闸。

被测对象：``tools/sync_neko_upstream.py`` 的 ``_safe_target`` / ``_safe_removal`` /
``preflight`` / ``sync``。上游 ``/compare`` 返回的 ``filename`` 是**远端可控字符串**，
旧代码直接 ``LOCAL_ROOT / path`` 拼路径就往磁盘写、``removed`` 分支还直接 ``unlink()``。

测试口径（对应工单验收项）：
    1. 五类恶意 path 全部被拒；
    2. 拒绝发生在**任何磁盘动作之前**，且整批中止（不是跳过）；
    3. 子树外的目录快照前后一字节不差（用 tmp_path 真造一个仓库外的受害文件）。

本机约束（诚实登记，别当成覆盖够了）：
    ``os.symlink`` 在本机被权限拒（errno 22 "客户端没有所需的权限"，无开发者模式），
    所以"仓库外的软链"这一类用**目录联接（junction）**替代 —— 同样是重解析点，
    ``Path.resolve()`` 一样会跟出去，拦它的正是那道 resolve 复核；真符号链接分支
    用打桩钉住（见 ``test_removal_refuses_symlinked_target``）。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

# 卷173 测试分层标注：smoke ⊂ core；纯 stdlib + tmp_path，无网络无子进程
pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 必须在 import 被测模块之前塞 GTOK：模块级 ``TOKEN = _token()``，环境变量为空时会
# subprocess 调 `git credential-manager get`（无超时）。测试收集阶段弹凭据提示 = 全量卡死。
_PREV_GTOK = os.environ.get("GTOK")
os.environ["GTOK"] = "import-guard-not-a-real-credential"
try:
    from tools import sync_neko_upstream as mod
finally:
    if _PREV_GTOK is None:
        os.environ.pop("GTOK", None)
    else:
        os.environ["GTOK"] = _PREV_GTOK

UnsafePath = mod.UnsafePath
_safe_target = mod._safe_target
_safe_removal = mod._safe_removal


# ---------------------------------------------------------------- fixtures --

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """仓库外可写沙盘：``repo/NEKO/N.E.K.O``（子树）+ ``outside``（受害者）。"""
    repo = tmp_path / "repo"
    local = repo / "NEKO" / "N.E.K.O"
    local.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("do not touch me")
    (tmp_path / "root_config.json").write_text("{}")
    monkeypatch.setattr(mod, "ROOT", repo)
    monkeypatch.setattr(mod, "LOCAL_ROOT", local)
    return repo, local, outside


def _snapshot(base: Path) -> dict[str, str]:
    """目录树指纹（路径 → 内容哈希）。闸门失效时这里必然变。"""
    out: dict[str, str] = {}
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base).as_posix()
        out[rel + "/"] = "dir" if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _meta(status: str = "modified") -> dict:
    return {"status": status, "sha": "0" * 40, "previous_filename": None}


# ------------------------------------------------------- 恶意 path 逐类拒绝 --

#: (上游 filename 串, 期望拒绝理由片段, 这一类为什么危险)
MALICIOUS = [
    ("../../etc/passwd", "'.' 或 '..' 段", "词法上跳出自家子树"),
    ("/abs/path", "绝对路径", "`LOCAL_ROOT / '/abs/path'` 会直接换根"),
    ("a/../../../x", "'.' 或 '..' 段", "藏在合法首段后面的跳出"),
    ("CON", "Windows 保留名", "写到设备命名空间，落点和请求名不是一回事"),
    ("NUL.log", "Windows 保留名", "保留名判定要忽略扩展名"),
    ("C:\\evil\\x", "含盘符", "Windows 绝对路径"),
    (r"dir\file.txt", "含反斜杠", "反斜杠在 Windows 上是分隔符，在 POSIX 上是文件名"),
    ("a//b", "含空段", "连续斜杠会让 join 语义与上游列表对不上"),
    ("a/", "含空段", "尾斜杠 = 目录，不是文件"),
    ("a/../b", "'.' 或 '..' 段", "同级横向跳，解析后仍在树内也不给过（与上游列表不可对账）"),
    ("evil.txt:", "含冒号", "NTFS 备用数据流：写进别的文件的流里"),
    ("trailing.", "段尾的点或空格", "Windows 静默剥尾点，落盘名 ≠ 上游名"),
    ("", "空路径", "空串解析成子树根本身"),
]


@pytest.mark.parametrize("raw,why,danger", MALICIOUS)
def test_malicious_paths_rejected(sandbox, raw, why, danger):
    _, local, _ = sandbox
    with pytest.raises(UnsafePath) as caught:
        _safe_target(raw, root=local)
    assert why in str(caught.value), f"{raw!r} 该因「{danger}」被拒，实际理由：{caught.value}"


def test_symlink_outside_repo_rejected(sandbox, tmp_path):
    """第 5 类：树内的重解析点指向仓库外 —— 词法干净，只能靠 resolve() 复核拦。"""
    _, local, outside = sandbox
    _mkjunction(local / "outlink", outside)
    with pytest.raises(UnsafePath) as caught:
        _safe_target("outlink/victim.txt", root=local)
    assert "子树之外" in str(caught.value)
    # 直接删这个链接本身同样被拦（它不在子树内的解析结果上）
    with pytest.raises(UnsafePath):
        _safe_target("outlink", root=local)


def test_junction_redirect_inside_subtree_rejected(sandbox, tmp_path):
    """联接指向子树**内**的另一处：is_relative_to 放行，但落点与请求名不符 ⇒ 仍拒。"""
    _, local, _ = sandbox
    other = local / "other"
    other.mkdir()
    _mkjunction(local / "hop", other)
    with pytest.raises(UnsafePath) as caught:
        _safe_target("hop/file.txt", root=local)
    assert "符号链接重定向" in str(caught.value)


def _mkjunction(link: Path, target: Path) -> None:
    """造一个**确实会重定向**的重解析点；造不出来就 skip。

    为什么不能"符号链接没抛异常就认"：实测在部分 Windows 环境里 ``os.symlink`` 会
    **返回成功却产出坏链接**（``os.path.islink`` 为 False、目标不可达、``resolve()`` 不跳转）。
    原版在这里直接 ``return``，于是下面的断言全在"链接其实没建成"的前提下空跑，
    必然红 —— 那不是闸门有漏洞，是环境造不出前置条件。

    因此本函数改为：两条路都试 → **校验是否真的重定向** → 不行就 ``pytest.skip``
    （平台门控，不是用 skip 换绿）。判定逻辑本身另有不依赖真链接的用例覆盖。
    """

    def _redirects() -> bool:
        try:
            return link.is_dir() and link.resolve() != link
        except OSError:
            return False

    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        pass
    if _redirects():
        return

    junction_err = ""
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"New-Item -ItemType Junction -Path '{link}' -Target '{target}' | Out-Null",
            ],
            capture_output=True,
            text=True,
        )
        junction_err = (out.stderr or "").strip()[:120]
    except OSError as exc:  # 连 shell 都起不来
        junction_err = f"{type(exc).__name__}: {exc}"[:120]
    if _redirects():
        return

    pytest.skip(
        "本机造不出可用的重解析点（符号链接被拒 / 目录联接不可用）"
        f"{'：' + junction_err if junction_err else ''}"
    )


# ------------------------------------------------------------ 良性 path 放行 --

@pytest.mark.parametrize("raw", [
    "main.py",
    "app/monitor.py",
    "NEKO/N.E.K.O/x",
    "utils/net_boundary.py",
    "a/b/c/d/e/f.txt",
    "docs/WO-267-p0-service-boundary.md",
    "plugins/cOne_x/CONFig.txt",   # 保留名只认整段主干，不是子串
])
def test_benign_paths_accepted(sandbox, raw):
    _, local, _ = sandbox
    got = _safe_target(raw, root=local)
    assert got == (local / raw).resolve()
    assert got.is_relative_to(local.resolve())


def test_reserved_name_check_is_case_insensitive(sandbox):
    _, local, _ = sandbox
    for raw in ("con", "cOn.txt", "PRN", "com1", "lpt9.log", "aux"):
        with pytest.raises(UnsafePath):
            _safe_target(raw, root=local)


# -------------------------------------------------- 整批中止 & 磁盘零动作 --

def test_preflight_lists_every_violation_not_just_first(sandbox):
    _, local, outside = sandbox
    _mkjunction(local / "outlink", outside)
    changes = {
        "app/ok.py": _meta(),
        "../../etc/passwd": _meta(),
        "CON": _meta(),
        "outlink/victim.txt": _meta("removed"),
    }
    violations = mod.preflight(changes)
    assert len(violations) == 3, violations          # 列出全部，不是撞一个报一个
    assert any("'.' 或 '..' 段" in v for v in violations)
    assert any("保留名" in v for v in violations)
    assert any("子树之外" in v for v in violations)


def test_batch_aborts_before_touching_disk(sandbox, monkeypatch):
    """合法项与恶意项混在一批 ⇒ 合法项也一字节不写（工单：静默跳过会留半同步）。"""
    repo, local, outside = sandbox
    (local / "keep.txt").write_text("original")       # 会被 removed 的本地文件
    before = _snapshot(repo.parent)

    calls: list[str] = []
    monkeypatch.setattr(mod, "blob_bytes",
                        lambda sha: calls.append(sha) or b"should never be written")

    changes = {
        "keep.txt": _meta("removed"),
        "new_ok.py": _meta("added"),
        "../../outside/victim.txt": _meta("added"),
    }
    result = mod.sync(changes, write=True)

    assert result["aborted"] is True
    assert len(result["violations"]) == 1
    assert (result["added"], result["modified"], result["removed"], result["failed"]) == (0, 0, 0, 0)
    assert calls == [], "闸门之后不该再有取 blob 的动作"
    assert _snapshot(repo.parent) == before, "整批中止必须一个字节都不动"
    assert (local / "keep.txt").read_text() == "original"
    assert (outside / "victim.txt").exists()


def test_check_mode_also_aborts(sandbox):
    """--check 默认不改盘，但违规同样要整批报出：这是发现被污染的上游列表的入口。"""
    repo, local, outside = sandbox
    changes = {"a/../../../x": _meta(), "ok.py": _meta()}
    result = mod.sync(changes, write=False)
    assert result["aborted"] is True
    assert len(result["violations"]) == 1
    assert _snapshot(repo) == {"NEKO/": "dir", "NEKO/N.E.K.O/": "dir"}


# ------------------------------------------------------------- 删除侧闸门 --

def test_removal_refuses_directory_inside_git_and_symlink(sandbox):
    _, local, _ = sandbox
    d = local / "somedir"
    d.mkdir()
    assert "是目录" in _safe_removal(d, root=local)

    gitdir = local / ".git"
    gitdir.mkdir()
    head = gitdir / "HEAD"
    head.write_text("ref: refs/heads/main")
    assert "位于 .git/ 内" in _safe_removal(head, root=local)

    plain = local / "plain.txt"
    plain.write_text("x")
    assert _safe_removal(plain, root=local) is None


def test_removal_refuses_symlinked_target(sandbox, monkeypatch):
    """真符号链接本机造不出来（权限拒），用打桩钉住这条分支确实接在删除路径上。"""
    _, local, _ = sandbox
    victim = local / "linked.txt"
    victim.write_text("x")
    monkeypatch.setattr(Path, "is_symlink", lambda self: str(self) == str(victim))
    assert "符号链接" in _safe_removal(victim, root=local)


def test_removed_file_inside_git_aborts_whole_batch(sandbox):
    """上游把 ``.git/HEAD`` 报成 removed：词法合法（在子树内），必须被删除侧闸门拦下。"""
    repo, local, outside = sandbox
    (local / ".git").mkdir()
    (local / ".git" / "HEAD").write_text("ref: refs/heads/main")
    (local / "ok.py").write_text("print(1)")
    before = _snapshot(repo.parent)

    changes = {".git/HEAD": _meta("removed"), "ok.py": _meta("removed")}
    result = mod.sync(changes, write=True)

    assert result["aborted"] is True
    assert any(".git" in v for v in result["violations"])
    assert _snapshot(repo.parent) == before
    assert (local / ".git" / "HEAD").exists() and (local / "ok.py").exists()


def test_legit_removal_still_works(sandbox):
    """对照组：闸门不是把删除全关掉 —— 正常文件照删。"""
    _, local, _ = sandbox
    gone = local / "stale.py"
    gone.write_text("x")
    result = mod.sync({"stale.py": _meta("removed")}, write=True)
    assert not result.get("aborted") and result["removed"] == 1
    assert not gone.exists()


def test_legit_write_still_works(sandbox, monkeypatch):
    """对照组 2：正常路径照写，字节内容与 sha 校验都过。"""
    _, local, _ = sandbox
    data = b'"""hi"""\n'
    monkeypatch.setattr(mod, "blob_bytes", lambda sha: data)
    changes = {"pkg/new_mod.py": {"status": "added",
                                  "sha": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(),
                                  "previous_filename": None}}
    result = mod.sync(changes, write=True)
    assert not result.get("aborted"), result
    assert result["added"] == 1 and result["failed"] == 0
    assert (local / "pkg" / "new_mod.py").read_bytes() == data


# --------------------------------------------------------------- 退出码 2 --

def test_cli_exits_2_on_abort(sandbox, monkeypatch, capsys):
    """操作者拿到的是非零退出，不是"看起来同步成功了"。"""
    _, local, _ = sandbox
    monkeypatch.setattr(mod, "resolve", lambda sha: sha)
    monkeypatch.setattr(mod, "api", lambda path, **kw: {"object": {"sha": "t"}})
    monkeypatch.setattr(mod, "collect_changes",
                        lambda base, tip, **kw: {"CON": _meta(), "ok.py": _meta()})
    monkeypatch.setattr(sys, "argv", ["sync_neko_upstream.py", "--base", "b"])
    assert mod.main() == 2
    printed = capsys.readouterr().out
    assert "整批中止" in printed and "保留名" in printed


# ------------------------------------------------------- 不依赖真链接的判定逻辑 --
# 上面几条依赖"本机真能造出符号链接/目录联接"。造不出的机器上它们会 skip，
# 于是"闸门到底拦不拦得住重定向"就没人验了。下面两条 monkeypatch Path.resolve 直接
# 模拟跳转结果，**纯逻辑覆盖**，任何平台都能跑。

def test_escape_detected_via_stubbed_resolve(sandbox, monkeypatch):
    """解析结果跳到子树外 ⇒ 必须拒（不依赖真链接）。"""
    _, local, outside = sandbox
    target = local / "outlink" / "victim.txt"
    real_resolve = Path.resolve

    def fake_resolve(self, *args, **kwargs):
        if self == target:
            return (outside / "victim.txt").resolve()
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    with pytest.raises(UnsafePath) as caught:
        _safe_target("outlink/victim.txt", root=local)
    assert "子树之外" in str(caught.value)


def test_redirect_inside_subtree_detected_via_stubbed_resolve(sandbox, monkeypatch):
    """解析结果仍在子树内、但与请求名不符 ⇒ 同样拒（不依赖真链接）。"""
    _, local, _ = sandbox
    target = local / "hop" / "file.txt"
    real_resolve = Path.resolve

    def fake_resolve(self, *args, **kwargs):
        if self == target:
            return (local / "other" / "file.txt").resolve()
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    with pytest.raises(UnsafePath) as caught:
        _safe_target("hop/file.txt", root=local)
    assert "符号链接重定向" in str(caught.value)
