"""执行后端抽象基类。

改编自 ChemGraph execution/base.py（Apache-2.0）：保留
``ExecutionBackend`` 生命周期协议与 ``TaskSpec`` 数据模型，
裁剪掉 HPC 专有的 Parsl/Globus 语义，只留本地/远程两种形态需要的接口。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from concurrent.futures import Future
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class TaskSpec(BaseModel):
    """单个任务单元的描述。

    两种执行模式：

    * **python** —— 执行一个 Python 可调用对象（``callable(*args, **kwargs)``）
    * **shell**  —— 执行一条 shell 命令

    资源 hints（``num_nodes``/``processes_per_node``/``gpus_per_task``）
    是建议值，后端可以忽略自己不支持的项。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str = Field(description="批内唯一的任务标识。")
    task_type: Literal["python", "shell"] = Field(
        default="python",
        description="执行模式：'python' 跑可调用对象，'shell' 跑命令。",
    )

    # ── Python 任务字段 ────────────────────────────────────────────────
    callable: Optional[Callable[..., Any]] = Field(
        default=None,
        description="task_type='python' 时必填。",
    )
    args: tuple = Field(default=(), description="传给 callable 的位置参数。")
    kwargs: dict = Field(default_factory=dict, description="传给 callable 的关键字参数。")

    # ── Shell 任务字段 ─────────────────────────────────────────────────
    command: Optional[str] = Field(
        default=None,
        description="task_type='shell' 时必填。",
    )
    working_dir: Optional[str] = Field(default=None, description="shell 命令的工作目录。")
    stdout: Optional[str] = Field(default=None, description="stdout 落盘路径（shell 任务）。")
    stderr: Optional[str] = Field(default=None, description="stderr 落盘路径（shell 任务）。")

    # ── 资源 hints ─────────────────────────────────────────────────────
    num_nodes: int = Field(default=1, description="请求的计算节点数。")
    processes_per_node: int = Field(default=1, description="每节点进程（rank）数。")
    gpus_per_task: int = Field(default=0, description="每任务 GPU 数。")
    env: dict[str, str] = Field(default_factory=dict, description="追加的环境变量。")


class ExecutionBackend(ABC):
    """所有执行后端适配器必须实现的抽象接口。

    生命周期
    --------
    1. ``initialize(system, **kwargs)``  —— 启动后端
    2. ``submit(task)`` / ``submit_batch(tasks)``  —— 派发任务
    3. ``shutdown()``  —— 释放资源

    支持 context-manager 协议（``with`` 语句）。
    """

    def __init__(self) -> None:
        self._initialized: bool = False

    @property
    def is_async_remote(self) -> bool:
        """是否提交到远程队列（任务可能要跑几分钟到几小时）。

        为 ``True`` 时，上层工具应在提交后立即返回，
        并提供独立的状态/结果查询入口，而不是阻塞等完成。
        """
        return False

    @property
    def shares_filesystem(self) -> bool:
        """worker 是否与提交方共享文件系统。

        为 ``True``（默认）时，服务端写的路径 worker 可直接读，
        无需文件搬运技巧；远程无共享盘的后端应覆写为 ``False``。
        """
        return True

    @abstractmethod
    def initialize(self, system: str = "local", **kwargs: Any) -> None:
        """准备后端以接受任务。

        Parameters
        ----------
        system : str
            目标系统名（``"local"`` 或远程系统名），后端可据此加载配置。
        **kwargs
            后端专属选项。
        """

    @abstractmethod
    def submit(self, task: TaskSpec) -> Future:
        """提交单个任务，返回 ``concurrent.futures.Future``。

        future 的结果是 callable/命令的返回值。
        """

    def submit_batch(self, tasks: list[TaskSpec]) -> list[Future]:
        """批量提交，按提交顺序返回 futures。默认逐个 ``submit()``。"""
        return [self.submit(t) for t in tasks]

    @abstractmethod
    def shutdown(self) -> None:
        """释放后端持有的所有资源。"""

    # ── Context-manager 协议 ────────────────────────────────────────────

    def __enter__(self) -> "ExecutionBackend":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()
