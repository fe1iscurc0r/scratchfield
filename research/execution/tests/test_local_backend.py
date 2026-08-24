"""授粉-C1 验收：LocalBackend 能跑通 python 任务与 shell 任务。"""

from __future__ import annotations

import os
import sys
import unittest
from concurrent.futures import Future

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), *([os.pardir] * 3)))
sys.path.insert(0, REPO_ROOT)

from research.execution import ExecutionBackend, LocalBackend, TaskSpec


def _square(x: int, offset: int = 0) -> int:
    return x * x + offset


class TestC1LocalBackend(unittest.TestCase):
    def setUp(self):
        self.backend = LocalBackend()
        self.backend.initialize(max_workers=2)

    def tearDown(self):
        self.backend.shutdown()

    def test_is_execution_backend(self):
        """抽象契约：is_async_remote / shares_filesystem 两个 property。"""
        self.assertIsInstance(self.backend, ExecutionBackend)
        self.assertFalse(self.backend.is_async_remote)
        self.assertTrue(self.backend.shares_filesystem)

    def test_python_task_runs(self):
        """验收核心：一条 python 任务跑通并返回 Future。"""
        task = TaskSpec(
            task_id="t-py", task_type="python",
            callable=_square, args=(7,), kwargs={"offset": 1},
        )
        fut = self.backend.submit(task)
        self.assertIsInstance(fut, Future)
        self.assertEqual(fut.result(timeout=10), 50)

    def test_shell_task_runs(self):
        """shell 任务走 subprocess.run，捕获 stdout。"""
        cmd = f'"{sys.executable}" -c "print(\'shell-ok\')"'
        task = TaskSpec(task_id="t-sh", task_type="shell", command=cmd)
        result = self.backend.submit(task).result(timeout=30)
        self.assertEqual(result["returncode"], 0)
        self.assertIn("shell-ok", result["stdout"])

    def test_submit_batch_preserves_order(self):
        tasks = [
            TaskSpec(task_id=f"t{i}", task_type="python", callable=_square, args=(i,))
            for i in range(4)
        ]
        futures = self.backend.submit_batch(tasks)
        self.assertEqual([f.result(timeout=10) for f in futures], [0, 1, 4, 9])

    def test_context_manager(self):
        with LocalBackend() as be:
            be.initialize(max_workers=1)
            fut = be.submit(TaskSpec(task_id="t", task_type="python", callable=_square, args=(3,)))
            self.assertEqual(fut.result(timeout=10), 9)
        # __exit__ 后已 shutdown，再提交应 fail-fast
        with self.assertRaises(RuntimeError):
            be.submit(TaskSpec(task_id="t2", task_type="python", callable=_square))

    def test_submit_before_initialize_fails_fast(self):
        be = LocalBackend()
        with self.assertRaises(RuntimeError):
            be.submit(TaskSpec(task_id="t", task_type="python", callable=_square))

    def test_python_task_without_callable_fails_fast(self):
        fut = self.backend.submit(TaskSpec(task_id="t", task_type="python"))
        with self.assertRaises(ValueError):
            fut.result(timeout=10)

    def test_shell_task_without_command_fails_fast(self):
        with self.assertRaises(ValueError):
            self.backend.submit(TaskSpec(task_id="t", task_type="shell"))


if __name__ == "__main__":
    unittest.main()
