"""知识库多实例离线编辑 -> 无冲突合并（WO-04）。"""

from .sync import ENGINE, ENGINE_VERSION, KBDoc

__all__ = ["KBDoc", "ENGINE", "ENGINE_VERSION"]
