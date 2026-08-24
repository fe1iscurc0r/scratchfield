"""语义网补层 · GRAG → SemanticEngine 旁路桥（Phase 3）

只读 summer_memory 五元组，喂 SemanticEngine，把"规则推理补出的新事实"
并进 RAG 召回。不改 summer_memory 写路径；semantic_web 挂了降级返回空。

数据源选择（SPEC 五·Phase 3 允许"或本地 quintuple_graph"）：
- M1 用本地 summer_memory.quintuple_graph.get_all_quintuples()，
  纯 Python、无网络依赖，Windows 零门槛可跑；
- 远程 memory_client.get_remote_memory_client() 需 token + 网络，留给后续接持久化时再加。

进程内缓存：首次 query_semantic 时灌一次五元组 + 本体并物化推理闭包，
之后复用（对话代理场景下逐问题重建不划算）；重启进程即刷新。
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from mcpserver.adapters.semantic_web.engine import SemanticEngine

# 本模块自带的科研域本体（数据文件，非代码）
_ONTOLOGY_TTL = str(Path(__file__).resolve().parent / "ontology.ttl")


def _to_five(raw) -> tuple[str, str, str, str, str]:
    """任意形态 GRAG 记录归一化为五元组 (S, S_type, P, O, O_type)。

    兼容 5 元组与旧 3 元组 (S, P, O) 形态（后者的 S_type/O_type 视为空 → 字面量）。
    """
    vals = list(raw)
    if len(vals) == 5:
        return tuple(str(v) for v in vals)  # type: ignore[return-value]
    if len(vals) == 3:
        return (str(vals[0]), "", str(vals[1]), str(vals[2]), "")
    raise ValueError(f"无法识别的 GRAG 记录: {raw!r}")


def _label(uri_str: str) -> str:
    """lk: 完整 URI → 本地标签（中文 slug 可逆）。"""
    return uri_str.rsplit("#", 1)[-1] if "#" in uri_str else uri_str


class SemanticBridge:
    """GRAG 五元组 → SemanticEngine 的只读旁路桥。"""

    def __init__(self, ontology_ttl: str | None = None) -> None:
        self._engine = SemanticEngine()
        self._ontology = ontology_ttl or _ONTOLOGY_TTL
        self._loaded = False
        self._labels: set[str] = set()  # 图里出现过的原始标签（S 与 O）

    def load(self, quintuples: Iterable | None = None) -> bool:
        """灌五元组（缺省从本地 GRAG 只读）+ 本体 → 跑一次推理。

        Returns:
            True 成功；False（数据源不可用等）→ 调用方降级跳过。
        """
        try:
            if quintuples is None:
                from summer_memory.quintuple_graph import get_all_quintuples

                quintuples = list(get_all_quintuples())
            five = [_to_five(q) for q in quintuples]
            self._engine.load(five, self._ontology)
            # 收集原始标签用于问题匹配
            self._labels = {f[0] for f in five} | {f[3] for f in five if f[3]}
            self._loaded = True
            return True
        except Exception:  # noqa: BLE001  # 降级边界：数据源/推理异常一律吞掉
            # 降级：数据源/推理任一挂了，标记未加载，query_semantic 返回空
            self._loaded = False
            return False

    def query_semantic(self, question: str, max_facts: int = 8) -> str:
        """问题 → 语义推理事实文本（规则推导出的新事实，非原始五元组）。

        匹配策略：infer() 推出的新事实里，主语或宾语标签出现在问题文本中，
        即视为相关问题。没匹配到或未加载 → 返回空串（降级）。

        Returns:
            形如 "## 语义推理事实（本体规则推导）\n- 木质素NPs 是 材料" 的文本。
        """
        if not self._loaded or not question:
            return ""
        try:
            facts = self._engine.infer()
            lines: list[str] = []
            for f in facts:
                s = _label(f["s"])
                o = _label(f["o"])
                p = _label(f["p"])
                if s in question or o in question:
                    lines.append(f"{s} {p} {o}")
                    if len(lines) >= max_facts:
                        break
            if not lines:
                return ""
            return "## 语义推理事实（本体规则推导）\n\n" + "\n".join(f"- {l}" for l in lines)
        except Exception:  # noqa: BLE001  # 降级边界：语义推理异常一律吞掉
            return ""


# ---- 进程内单例（供 lumo_proxy 复用） ----

_BRIDGE: SemanticBridge | None = None


def get_bridge() -> SemanticBridge:
    """返回进程内共享的桥实例（首次调用时懒加载）。"""
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = SemanticBridge()
    return _BRIDGE


def reset_bridge() -> None:
    """重置单例（测试用）。"""
    global _BRIDGE
    _BRIDGE = None
