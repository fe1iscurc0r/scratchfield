"""agent_server_parts 的导入纪律（工单244d）。

背景
----
`agentserver/agent_server.py` 在工单204 任务一被拆到 `agent_server_parts/`，
每个子模块头部由 codemod 统一写成::

    from .common import *  # noqa: F401,F403
    from .common import Modules, logger  # noqa: F401

`# noqa` 只压住了 F401/F403，**压不住 F405**（`undefined-local-with-import-star-usage`）
⇒ 全仓累计 **254 条 F405**（`ruff check .` 共 314 errors），且因为 CI 的 lint job
默认被 `ENABLE_LINT` 闸门关闭，**从拆分那天起没人发现**（详见 ci.yml 的 lint 注释）。

244d 把这些星号导入改成**显式名字列表**，`ruff check .` 归零。本文件把那条纪律
**变成会真跑的测试** —— 不再依赖那个默认关闭的 CI job。

⚠️ 为什么不用 `ruff` 来做断言：pytest 环境不保证装了 ruff，而本条守的是
「**静态可解析性**」，用标准库 `ast` 自己算就够，且零外部依赖。
（口径与 ruff 的 F405 同类：**模块里用到、但全模块都没绑定、也不是内置名** ⇒ 危险。）

对照用例（本文件同时是 244d 的**等价性锚**）：`tests/test_agent_server_smoke.py`
已断言「路由总数 = 拆分前基线 75」+ 关键路由 + `/health` 真调用，
本文件只补**导入静态纪律**，两者合起来覆盖「改名不改行为」。
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PARTS_DIR = REPO_ROOT / "agentserver" / "agent_server_parts"

#: 模块级**隐式**名 —— 由导入系统在运行时注入，不需要（也不该）import。
#: 实测踩到过：`common.py` 用 `__file__` 算 `_PROJECT_ROOT`，不加白名单会误报。
_MODULE_DUNDERS = frozenset({
    "__file__", "__name__", "__doc__", "__package__", "__spec__", "__loader__",
    "__builtins__", "__dict__", "__path__", "__annotations__", "__cached__",
})

#: 拆出后由 `agent_server.py`（薄入口）导入以**触发路由注册**的子模块
PART_MODULES = ("agents", "common", "dogtag", "health", "heartbeat", "lifecycle",
                "openclaw", "search", "session", "travel", "vision")


def _part_files() -> list[Path]:
    files = sorted(PARTS_DIR.glob("*.py"))
    assert files, f"找不到拆分产物：{PARTS_DIR}"
    return files


def _bound_names(tree: ast.Module) -> set[str]:
    """模块内**任意作用域**绑定过的名字（保守近似：宁可少报，不可误报）。"""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.add(node.name)
            bound.update(a.arg for a in node.args.args + node.args.kwonlyargs)
            if node.args.vararg:
                bound.add(node.args.vararg.arg)
            if node.args.kwarg:
                bound.add(node.args.kwarg.arg)
        elif isinstance(node, ast.ClassDef):
            bound.add(node.name)  # ⚠️ ClassDef 没有 .args，别与上面合成一个 isinstance
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update(a.asname or a.name.split(".")[0] for a in node.names if a.name != "*")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Global | ast.Nonlocal):
            bound.update(node.names)
    return bound


def _loaded_names(tree: ast.Module) -> set[str]:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


@pytest.mark.parametrize("path", _part_files(), ids=lambda p: p.name)
def test_no_star_import_in_parts(path: Path):
    """① 拆分产物里**不得**再出现 `import *`。

    这是 244d 修掉的那 254 条 F405 的**根因**：星号导入让静态分析无法解析名字，
    也让「这个模块到底依赖什么」变成不可见。改法是把用到的名字显式列出来。
    ⚠️ 若把 star import 加回来，本用例立刻变红 —— 那是**回归**，不是风格分歧。
    """
    offenders = [f"L{i}: {ln.strip()}" for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if ln.strip().startswith(("from ", "import ")) and ln.split("#")[0].rstrip().endswith("*")]
    assert not offenders, (
        f"{path.name} 出现星号导入（会让 ruff F405 复活、依赖不可见）：{offenders}")


@pytest.mark.parametrize("path", _part_files(), ids=lambda p: p.name)
def test_no_unresolvable_names_in_parts(path: Path):
    """② 每个子模块里**用到却没人绑定**的名字必须为空（自带的 F405 等价检查）。

    口径：`Name(Load)` 去掉「本模块任意作用域绑定过的」与「内置名」后应为空。
    保守近似 ⇒ 可能漏报作用域错用（那是 F821 的事），但**不会误报**；
    244d 修掉的那批名字（`HTTPException` / `Any` / `config` / `asyncio` …）
    在修复前正是「全模块都没绑定」⇒ 本用例当时会红。

    若将来有人删掉某个显式导入而不改用法，这里会先红 —— **不需要依赖 CI 的 lint job**。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    unresolved = sorted(_loaded_names(tree) - _bound_names(tree)
                        - set(dir(builtins)) - _MODULE_DUNDERS)
    assert not unresolved, (
        f"{path.name} 存在无法解析的名字（缺 import 或用错作用域）：{unresolved}")


def test_parts_explicitly_import_from_common():
    """③ 每个子模块都必须**显式**从 `.common` 取它需要的共享名字。

    显式是刻意的：`.common` 持有拆分前的公共导入（`config` / `logger` / `Any` …），
    显式导入让「谁依赖什么」在文件头部一眼可见。
    """
    missing = [name for name in PART_MODULES if name != "common"
               and "from .common import" not in (PARTS_DIR / f"{name}.py").read_text(encoding="utf-8")]
    assert not missing, f"这些子模块没有显式从 .common 导入：{missing}"


def test_part_modules_are_importable():
    """④ 拆分产物必须都能导入（`agent_server.py` 靠导入即注册路由）。"""
    import importlib

    failures: list[str] = []
    for name in PART_MODULES:
        try:
            importlib.import_module(f"agentserver.agent_server_parts.{name}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, f"子模块导入失败：{failures}"
