"""语义网补层 · 接口协议 schema（Phase 0）

协议无关抽象层的基石：语义层只认 RDF 三元组 (S, P, O) + SPARQL 查询，
底层是 rdflib 内存图还是 pyoxigraph RocksDB 都不关心。

两个 schema 字段必须与 SPEC 3.1 映射规则完全一致。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Quintuple:
    """GRAG 五元组，与 summer_memory 的 (S, S_type, P, O, O_type) 结构一致。"""

    s: str = ""        # 主语（永远是 URI 资源）
    s_type: str = ""   # 主语类型（rdf:type 取值）；空串 = 无类型标注
    p: str = ""        # 谓词（映射为 lk: 命名空间属性 URI）
    o: str = ""        # 宾语（O_type 非空 → 实体 URI；空 → xsd:string 字面量）
    o_type: str = ""   # 宾语类型；空串 = 字面量，非空 = 实体（URI 资源）

    def to_tuple(self) -> tuple[str, str, str, str, str]:
        """转回 GRAG 原生 tuple，便于与 summer_memory 数据互操作。"""
        return (self.s, self.s_type, self.p, self.o, self.o_type)


@dataclass(frozen=True)
class Triple:
    """RDF 三元组，SPARQL 查询/推理的统一输出单元。"""

    s: str              # 主语（URI 或字面量，字符串形式）
    p: str              # 谓词（URI 字符串）
    o: str              # 宾语（URI 或字面量，字符串形式）
    is_uri: bool = True  # o 是否为 URI 资源（False = 字面量）

    def to_tuple(self) -> tuple[str, str, str]:
        """转成 (S, P, O) 三元组。"""
        return (self.s, self.p, self.o)


def quintuple_from_raw(raw) -> Quintuple:
    """把任意形态的 GRAG 五元组归一化为 Quintuple。

    兼容输入：
    - (S, S_type, P, O, O_type) 五元组
    - (S, P, O) 三元组（S_type / O_type 缺省为空 → 宾语当字面量）
    """
    if isinstance(raw, Quintuple):
        return raw
    vals = list(raw)
    if len(vals) == 5:
        return Quintuple(s=str(vals[0]), s_type=str(vals[1]), p=str(vals[2]), o=str(vals[3]), o_type=str(vals[4]))
    if len(vals) == 3:
        return Quintuple(s=str(vals[0]), s_type="", p=str(vals[1]), o=str(vals[2]), o_type="")
    raise ValueError(f"无法识别的五元组形态: {raw!r}")
