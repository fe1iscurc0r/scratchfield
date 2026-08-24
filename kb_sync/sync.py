"""知识库多实例离线编辑 -> 无冲突合并。

引擎选择（诚实标注）：
    pycrdt 已成功安装（0.14.3），因此本模块直接使用 pycrdt（Yjs 兼容 CRDT）
    作为合并引擎，不实现纯 Python 回退。见模块常量 ENGINE / ENGINE_VERSION。

每个知识库文档（KBDoc）由三个 Yjs 根类型构成：
    - meta    : Map[str, str]   键值元数据，同键并发写按 LWW（last-writer-wins）收敛
    - items   : Array[str]      列表，并发插入/删除按序列 CRDT 收敛
    - content : Text            正文，并发插入/删除按文本 CRDT 收敛

多实例离线合并流程（真实、非 mock）：
    1. 用一份初始状态（client_id=1）生成两个副本 docA / docB；
    2. 两个副本各自离线增删改；
    3. 交换各自的 update 字节并 apply 到对方，双方收敛到同一状态。
"""

from __future__ import annotations

import pycrdt
from pycrdt import Array, Doc, Map, Text

ENGINE = "pycrdt"
ENGINE_VERSION = getattr(pycrdt, "__version__", "unknown")


class KBDoc:
    """知识库文档，内含 meta 映射、items 列表、content 正文三个 CRDT 根类型。"""

    def __init__(
        self,
        client_id: int | None = None,
        *,
        meta: dict[str, str] | None = None,
        items: list[str] | None = None,
        content: str = "",
    ) -> None:
        self.doc: Doc = Doc(client_id=client_id)
        self.doc["meta"] = Map()
        self.doc["items"] = Array()
        self.doc["content"] = Text()

        if meta:
            self.meta.update(meta)
        if items:
            for item in items:
                self.items.append(item)
        if content:
            self.content.insert(0, content)

    # ---- 根类型访问 ----
    @property
    def meta(self) -> Map:
        return self.doc["meta"]

    @property
    def items(self) -> Array:
        return self.doc["items"]

    @property
    def content(self) -> Text:
        return self.doc["content"]

    # ---- 序列化 / 同步 ----
    def to_py(self) -> dict:
        """导出为纯 Python 结构，供断言与观测。"""
        return {
            "meta": self.meta.to_py(),
            "items": self.items.to_py(),
            "content": self.content.to_py(),
        }

    def get_update(self) -> bytes:
        """导出本副本自空状态以来的完整 update（Yjs 增量，幂等）。"""
        return self.doc.get_update()

    def apply_update(self, update: bytes) -> None:
        """应用来自另一副本的 update。"""
        self.doc.apply_update(update)

    def merge(self, other: "KBDoc") -> None:
        """将 other 的 update 合并进本副本（单向）。"""
        self.apply_update(other.get_update())

    def clone(self, client_id: int) -> "KBDoc":
        """基于本副本的当前状态创建一个新的独立副本（共享初始 item ID）。"""
        replica = KBDoc(client_id=client_id)
        replica.apply_update(self.get_update())
        return replica

    # ---- meta 操作 ----
    def set_meta(self, key: str, value: str) -> None:
        self.meta[key] = value

    def get_meta(self, key: str) -> str | None:
        return self.meta.get(key)

    # ---- items 操作 ----
    def insert_item(self, index: int, value: str) -> None:
        self.items.insert(index, value)

    def delete_item(self, index: int) -> None:
        del self.items[index]

    def append_item(self, value: str) -> None:
        self.items.append(value)

    # ---- content 操作 ----
    def insert_text(self, index: int, value: str) -> None:
        self.content.insert(index, value)

    def delete_text(self, index: int, length: int) -> None:
        del self.content[index : index + length]
