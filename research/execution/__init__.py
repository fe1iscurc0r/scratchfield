"""多后端执行抽象（授粉-C1）。

改编自 ChemGraph execution/base.py（Apache-2.0，
github_haul/fusion/chemgraph/src/chemgraph/execution/base.py）。
下游代码只依赖本层抽象，不绑定具体后端。
"""

from research.execution.base import ExecutionBackend, TaskSpec
from research.execution.local_backend import LocalBackend

__all__ = ["ExecutionBackend", "LocalBackend", "TaskSpec"]
