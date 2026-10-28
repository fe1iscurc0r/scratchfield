"""KiCAD S-expression 读写核（工单245 · 真值源）。

为什么自研而不是用 `sexpdata`
------------------------------
上游 `mixelpixx/KiCAD-MCP-Server` 依赖 `sexpdata`；本模块沿用本仓
`mcpserver/toolknit_mcp` 的**零第三方**纪律 —— KiCAD 文件是**纯文本 S-expression**，
解析它只需要一个几百行的状态机，没必要为此引入依赖（也让本模块能在任何解释器上跑）。

KiCAD 语法要点（实测自上游 `tests/fixtures/canonical_schematic.kicad_sch`，eeschema 10.0）
---------------------------------------------------------------------------------------
- 顶层**恰好一个**列表：``(kicad_sch (version 20260101) (generator "eeschema") …)``
- 缩进用 **Tab**；字段是 ``(tag value)`` 或 ``(tag v1 v2 …)`` 或 ``(tag (sub …) …)``
- 字符串用双引号，内部转义为 ``\\"``；**其余一律是 bare atom**（数字也是 atom，保持文本）
- 没有注释语法 —— ``#`` 不是注释，别自作聪明（会把 `#` 开头的 atom 吃掉）

表示法
------
``SExpr = str | list``：atom 是 ``str``，列表是 ``list[SExpr]``。
**不把数字转成 float** —— KiCAD 自己按文本读写，转换只会引入精度/格式失真；
需要数值时由上层显式 ``float()``（见 :func:`atom_float`）。
"""

from __future__ import annotations

from typing import Union

SExpr = Union[str, list["SExpr"]]

_WS = " \t\r\n"
_QUOTE = '"'
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


class SExprError(ValueError):
    """S-expression 语法错误（带行列位置，便于定位上游产物里的怪格式）。"""


def parse_one(text: str) -> SExpr:
    """解析恰好一个顶层表达式；尾部有非空白内容则报错。"""
    nodes, pos = _parse_all(text)
    if len(nodes) != 1:
        raise SExprError(f"期望恰好 1 个顶层表达式，实得 {len(nodes)} 个")
    tail = text[pos:].strip()
    if tail:
        raise SExprError(f"顶层表达式之后还有多余内容：{tail[:40]!r}")
    return nodes[0]


def parse_all(text: str) -> list[SExpr]:
    """解析全部顶层表达式（KiCAD 文件通常只有一个）。"""
    nodes, _ = _parse_all(text)
    return nodes


def _parse_all(text: str) -> tuple[list[SExpr], int]:
    # 容忍 UTF-8 BOM：某些编辑器/工具会给文件加 BOM，若不当场剥掉，首个 atom 会变成
    # '\ufeffkicad_pcb'，顶层 tag 校验就会以一个**看不懂的错**失败（实测踩过）。
    if text.startswith("\ufeff"):
        text = text[1:]
    out: list[SExpr] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in _WS:
            i += 1
            continue
        node, i = _parse_node(text, i)
        out.append(node)
    return out, n


def _parse_node(text: str, i: int) -> tuple[SExpr, int]:
    n = len(text)
    if text[i] == "(":
        i += 1
        items: list[SExpr] = []
        while True:
            while i < n and text[i] in _WS:
                i += 1
            if i >= n:
                raise SExprError(f"括号未闭合（第 {_line(text, i)} 行附近）")
            if text[i] == ")":
                return items, i + 1
            node, i = _parse_node(text, i)
            items.append(node)
    if text[i] == _QUOTE:
        return _parse_string(text, i)
    start = i
    while i < n and text[i] not in _WS and text[i] not in "()":
        i += 1
    if i == start:
        raise SExprError(f"无法解析的字符 {text[i]!r}（第 {_line(text, i)} 行）")
    return text[start:i], i


def _parse_string(text: str, i: int) -> tuple[SExpr, int]:
    i += 1                                   # 跳过开引号
    buf: list[str] = []
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            if i + 1 >= n:
                raise SExprError("字符串以反斜杠结尾（不完整转义）")
            nxt = text[i + 1]
            buf.append(_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        if c == _QUOTE:
            return "".join(buf), i + 1
        buf.append(c)
        i += 1
    raise SExprError("字符串未闭合")


def _line(text: str, i: int) -> int:
    return text.count("\n", 0, i) + 1


# --------------------------------------------------------------------------- 写出


def dumps(node: SExpr, *, indent: str = "  ") -> str:
    """序列化为 KiCAD 风格文本（Tab 缩进由调用方给，默认两空格便于人读）。"""
    out: list[str] = []
    _dump(node, 0, indent, out)
    return "\n".join(out)


def _dump(node: SExpr, depth: int, indent: str, out: list[str]) -> None:
    pad = indent * depth
    if isinstance(node, str):
        out.append(pad + _quote(node))
        return
    if not node:
        out.append(pad + "()")
        return
    # `(tag a b …)` 若能单行放下就单行，否则逐项换行 —— 与 KiCAD 自己一致
    head = node[0] if isinstance(node[0], str) else None
    flat = " ".join(_flat(x) for x in node[1:])
    if head is not None and len(pad) + len(head) + len(flat) + 3 <= 100 and "\n" not in flat:
        out.append(f"{pad}({head}{(' ' + flat) if flat else ''})")
        return
    kids = node[1:] if head is not None else node
    open_tag = pad + (f"({head}" if head is not None else "(")
    if not kids:
        out.append(open_tag + ")")
        return
    out.append(open_tag)
    for k in kids:
        _dump(k, depth + 1, indent, out)
    out.append(pad + ")")


def _flat(node: SExpr) -> str:
    if isinstance(node, str):
        return _quote(node)
    return "(" + " ".join(_flat(x) for x in node) + ")"


def _quote(s: str) -> str:
    """何时加引号：空串、含空白/括号/引号/反斜杠 ⇒ 加。其余照原样（KiCAD 也这样）。"""
    if s == "":
        return '""'
    if any(c in s for c in _WS + "()" + _QUOTE + "\\"):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return s


# --------------------------------------------------------------------------- 查询


def is_list(node: SExpr) -> bool:
    return isinstance(node, list)


def tag(node: SExpr) -> str | None:
    """列表的首元素（若它是 atom）——即 ``(tag …)`` 里的 ``tag``。"""
    if isinstance(node, list) and node and isinstance(node[0], str):
        return node[0]
    return None


def atom(node: SExpr) -> str | None:
    return node if isinstance(node, str) else None


def atom_float(node: SExpr, default: float | None = None) -> float | None:
    """把 atom 转 float（KiCAD 数字是文本，上层要数值时显式转）。"""
    if isinstance(node, str):
        try:
            return float(node)
        except ValueError:
            return default
    return default


def children(node: SExpr) -> list[SExpr]:
    """列表的子节点（**不含**首元素 tag）；非列表返回空。"""
    if isinstance(node, list):
        return node[1:] if node and isinstance(node[0], str) else list(node)
    return []


def find_all(node: SExpr, want: str) -> list[list]:
    """广度优先收集所有 ``(want …)`` 列表（KiCAD 里同名块会出现在不同层级）。"""
    out: list[list] = []

    def walk(cur: SExpr) -> None:
        if not isinstance(cur, list):
            return
        if tag(cur) == want:
            out.append(cur)
        for kid in cur:
            walk(kid)

    walk(node)
    return out


def find_child(node: SExpr, want: str) -> list | None:
    """**直接子节点**里第一个 ``(want …)``（不递归 —— 同名块嵌套时语义不同）。"""
    if not isinstance(node, list):
        return None
    return next((k for k in children(node) if isinstance(k, list) and tag(k) == want), None)


def child_value(node: SExpr, want: str) -> str | None:
    """``(want v)`` 里的 ``v``；找的是直接子节点。"""
    c = find_child(node, want)
    return atom(c[1]) if c and len(c) > 1 else None


def property_value(node: SExpr, name: str) -> str | None:
    """KiCAD 的 ``(property "Name" "Value" …)`` —— 按名字取第二个 atom。"""
    for p in find_all(node, "property"):
        if len(p) > 2 and atom(p[1]) == name:
            return atom(p[2])
    return None
