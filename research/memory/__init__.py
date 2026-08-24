"""research.memory —— 科研会话持久化（授粉-C2）。

改编自 ChemGraph memory/store.py（Apache-2.0，
github_haul/fusion/chemgraph/src/chemgraph/memory/store.py）。
四表按工单要求：sessions / messages / tasks / events。
"""

from research.memory.store import MemoryStore, SessionMessage

__all__ = ["MemoryStore", "SessionMessage"]
