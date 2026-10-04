"""事件流记忆最小原型（P2-1 · W73-03 cognee event_protocol）。

依据 docs/cognee-图记忆-评估.md：把交互作为事件流接入记忆，而非全量对话快照；
实体抽取复用 lightrag_graph 的启发式抽取。

原型（纯 stdlib）：
  - EventMemory：ingest(event) 把事件（来源/文本/时间）接入记忆，抽实体索引
  - recall(query)：按实体交集召回相关事件
  - 事件流 = 结构化增量，替代「全量历史快照」

运行：python tools/memory_event_stream.py
"""
from __future__ import annotations

import re
from collections import defaultdict

from lightrag_graph import extract_entities


class EventMemory:
    """事件流记忆：结构化事件增量接入 + 实体索引召回。"""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.entity_index: dict[str, list[int]] = defaultdict(list)  # 实体 -> 事件下标

    def ingest(self, event_id: str, text: str, source: str = "agent") -> None:
        idx = len(self.events)
        self.events.append({"id": event_id, "text": text, "source": source})
        for e in extract_entities(text):
            self.entity_index[e].append(idx)

    def recall(self, query: str, top_k: int = 3) -> list[dict]:
        """按查询实体交集召回相关事件。"""
        q_ents = extract_entities(query)
        scores: dict[int, int] = defaultdict(int)
        for e in q_ents:
            for idx in self.entity_index.get(e, []):
                scores[idx] += 1
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]
        return [self.events[i] for i, _ in ranked]


if __name__ == "__main__":
    m = EventMemory()
    m.ingest("e1", "Alice configured the ESP32 radio at 433MHz.")
    m.ingest("e2", "Bob measured the noise floor on the SDR.")
    m.ingest("e3", "Alice tuned the ESP32 antenna and re-measured noise.")
    print("[recall 'ESP32 noise']", m.recall("ESP32 noise"))
