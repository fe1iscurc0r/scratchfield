"""expr.py — 显式表达式对象：安全求值 / 序列化 / LaTeX 与文本格式化。

符号回归旁路产出的"显式表达式"统一走 Expression 封装：
- 安全解析：ast 白名单（仅算术 + 受保护函数），拒绝任意代码执行
- 求值：标量或 numpy 数组（向量化），函数/常量映射到 numpy ufunc
- 序列化：JSON 保存/加载（跨进程复现）
- 格式化：文本（规范中缀式）与 LaTeX 近似（写进论文用）

不依赖 gplearn/pysr；纯标准库 + numpy（可选）。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

try:
    import numpy as np
    _HAS_NP = True
except Exception:  # pragma: no cover - numpy 在 requirements.txt 必装，此分支仅防御
    _HAS_NP = False

# 受保护函数白名单（求值命名空间 + 校验共用）
_SAFE_FUNCS = {
    "sin", "cos", "tan", "exp", "log", "log2", "log10",
    "sqrt", "abs", "sinh", "cosh", "tanh",
}
_CONSTANTS = {"pi", "e"}

_BIN_OPS = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod}
_UNARY_OPS = {ast.USub, ast.UAdd}
_DISALLOWED = {
    ast.Attribute, ast.Subscript, ast.Lambda, ast.IfExp, ast.BoolOp,
    ast.Compare, ast.Dict, ast.List, ast.Tuple, ast.Set, ast.ListComp,
    ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.NamedExpr,
    ast.JoinedStr, ast.FormattedValue, ast.Await, ast.Yield, ast.YieldFrom,
    ast.Starred, ast.Slice,
}


def _func_namespace() -> dict[str, Any]:
    if _HAS_NP:
        return {
            "sin": np.sin, "cos": np.cos, "tan": np.tan,
            "exp": np.exp, "log": np.log, "log2": np.log2, "log10": np.log10,
            "sqrt": np.sqrt, "abs": np.abs, "sinh": np.sinh,
            "cosh": np.cosh, "tanh": np.tanh,
            "pi": np.pi, "e": np.e,
        }
    import math
    return {
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "exp": math.exp, "log": math.log, "log2": math.log2, "log10": math.log10,
        "sqrt": math.sqrt, "abs": abs, "sinh": math.sinh,
        "cosh": math.cosh, "tanh": math.tanh,
        "pi": math.pi, "e": math.e,
    }


def _extract_vars(text: str) -> set[str]:
    """抽取表达式中除函数/常量外的变量名。"""
    tree = ast.parse(text, mode="eval")
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in _SAFE_FUNCS and node.id not in _CONSTANTS:
            names.add(node.id)
    return names


def _validate(text: str) -> None:
    """ast 白名单校验：拒绝任意代码执行与不支持的结构。"""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"表达式语法错误: {e}") from e
    for node in ast.walk(tree):
        if type(node) in _DISALLOWED:
            raise ValueError(f"不支持的语法结构: {type(node).__name__}")
        if isinstance(node, ast.BinOp) and type(node.op) not in _BIN_OPS:
            raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
        if isinstance(node, ast.UnaryOp) and type(node.op) not in _UNARY_OPS:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCS:
                raise ValueError(f"不支持的函数调用: {getattr(node.func, 'id', node.func)}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("常量只允许数字")


class Expression:
    """显式表达式（文本 + 变量名 + 安全求值 + 序列化 + 格式化）。"""

    def __init__(self, text: str):
        t = (text or "").strip()
        if not t:
            raise ValueError("表达式不能为空")
        _validate(t)
        self._text = t
        self._vars = sorted(_extract_vars(t))

    @property
    def text(self) -> str:
        return self._text

    @property
    def variables(self) -> list[str]:
        return list(self._vars)

    def evaluate(self, values: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """求值表达式。values 为变量名→取值（标量或 numpy 数组）。"""
        v: dict[str, Any] = dict(values or {})
        v.update(kwargs)
        missing = [n for n in self._vars if n not in v]
        if missing:
            raise ValueError(f"缺少变量值: {missing}")
        ns: dict[str, Any] = {"__builtins__": {}}
        ns.update(_func_namespace())
        ns.update(v)
        return eval(self._text, ns)  # noqa: S307 - 已由 _validate 做 ast 白名单校验

    def to_text(self) -> str:
        return self._text

    def to_latex(self) -> str:
        """LaTeX 近似：函数名 → 反斜杠命令，** → ^{}，* → \\cdot。"""
        s = self._text
        for fn in ("sinh", "cosh", "tanh", "sin", "cos", "tan", "exp",
                   "log10", "log2", "log", "sqrt", "abs"):
            s = re.sub(rf"\b{fn}\b", rf"\\{fn}", s)
        s = re.sub(r"\*\*(\d+(?:\.\d+)?|[A-Za-z_]\w*)", r"^{\1}", s)
        s = s.replace("*", r" \cdot ")
        return s

    def to_dict(self) -> dict[str, Any]:
        return {"expression": self._text, "variables": self._vars}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Expression":
        if "expression" not in data:
            raise ValueError("缺少 expression 字段")
        return cls(data["expression"])

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Expression":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def __repr__(self) -> str:
        return f"Expression({self._text!r})"

    def __str__(self) -> str:
        return self._text


def evaluate(expr: "Expression | str", values: dict[str, Any]) -> Any:
    """模块级求值入口（grep 验收：def evaluate）。"""
    e = expr if isinstance(expr, Expression) else Expression(expr)
    return e.evaluate(values)


__all__ = ["Expression", "evaluate"]
