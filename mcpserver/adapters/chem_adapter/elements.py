"""chem_adapter.elements —— 数据模块的顶层再导出桥。

上游 `chemformula.py`（此处为 `core.py`）用 `from . import elements` 引用元素数据，
而数据文件按 SPEC 存放在 `data/` 子包。为保证 `core.py` 零修改即可运行，
本文件仅做一层薄转发，把 `data.elements` 的公开接口上抛到包顶层。
"""
from .data.elements import *  # noqa: F401,F403