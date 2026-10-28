"""授粉-C3 验收：Planner-Executor Send() fan-out 图。

- 一个"三步任务"分解为 3 个子任务并行跑，结果按序汇总
- 不引入 langgraph 依赖（import 级检查）
"""

from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import os
import sys
import threading
import time
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, REPO_ROOT)

from research.execution.local_backend import LocalBackend
from research.planner import PlannerExecutor, Send, SubTaskError


class TestC3ThreeStepTask(unittest.TestCase):
    """验收：三步任务 → 3 子任务并行 → 按序汇总。"""

    def setUp(self):
        self.backend = LocalBackend()
        self.backend.initialize(max_workers=4)
        self.pe = PlannerExecutor(self.backend)

    def tearDown(self):
        self.backend.shutdown()

    def _setup_three_steps(self, delays=(0.0, 0.0, 0.0), spans=None):
        """spans：可选，传入 list 则记录每个分支的 (起始, 结束) 时刻（用于并行性判据）。"""
        seen_threads: list[int] = []

        def make_handler(step_name: str, delay: float):
            def handler(payload: dict):
                t0 = time.perf_counter()
                time.sleep(delay)
                seen_threads.append(threading.get_ident())
                if spans is not None:
                    spans.append((t0, time.perf_counter()))
                return f"{step_name}:{payload['x']}"

            return handler

        self.pe.register("文献调研", make_handler("文献调研", delays[0]))
        self.pe.register("实验执行", make_handler("实验执行", delays[1]))
        self.pe.register("数据分析", make_handler("数据分析", delays[2]))

        def planner(task: dict) -> list[Send]:
            return [
                Send(target="文献调研", payload={"x": task["topic"] + "-文献"}),
                Send(target="实验执行", payload={"x": task["topic"] + "-实验"}),
                Send(target="数据分析", payload={"x": task["topic"] + "-数据"}),
            ]

        return planner, seen_threads

    def test_three_steps_decompose_and_aggregate_in_order(self):
        planner, _ = self._setup_three_steps()
        result = self.pe.run(
            planner,
            {"topic": "木质素碳化"},
            reducer=lambda rs: " | ".join(rs),
        )
        self.assertTrue(result.ok)
        self.assertEqual(len(result.sends), 3)
        self.assertEqual(
            result.results,
            ["文献调研:木质素碳化-文献", "实验执行:木质素碳化-实验", "数据分析:木质素碳化-数据"],
        )
        self.assertEqual(
            result.summary,
            "文献调研:木质素碳化-文献 | 实验执行:木质素碳化-实验 | 数据分析:木质素碳化-数据",
        )

    def test_order_preserved_despite_completion_jitter(self):
        """分支#0 最慢完成，汇总仍按分解顺序 0→1→2。"""
        planner, _ = self._setup_three_steps(delays=(0.3, 0.05, 0.0))
        result = self.pe.run(planner, {"topic": "水凝胶"})
        self.assertEqual([r.split(":")[0] for r in result.results], ["文献调研", "实验执行", "数据分析"])

    def test_branches_run_in_parallel(self):
        """3 分支各睡 0.5s：**执行区间必须重叠**（这才是并行的直接证据），且动用多个线程。

        判据演进（两次踩坑记录，别再退回墙钟）：
        · 初版：`elapsed < 0.55` 对 3×0.2s（串行下界 0.6s）——全量负载下实测 0.94s，**超过串行理论上界**，
          纯属机器负载导致的假失败；
        · 二版：sleep 拉到 0.5s、阈值 1.2s（串行下界 1.5s）——更重的负载下（全量 7m19s 那轮）仍假失败；
        · 本版：**放弃墙钟**。直接看每个分支的 (起始, 结束) 区间是否有交叠——
          串行执行时区间必然**两两不相交**，并行时必然重叠，这个判据**与机器负载无关**。
        """
        spans: list[tuple[float, float]] = []
        planner, seen_threads = self._setup_three_steps(delays=(0.5, 0.5, 0.5), spans=spans)
        t0 = time.perf_counter()
        self.pe.run(planner, {"topic": "并行性"})
        elapsed = time.perf_counter() - t0

        self.assertEqual(len(spans), 3, f"应记录 3 个分支的执行区间，实得 {len(spans)}")
        self.assertGreaterEqual(len(set(seen_threads)), 2, "未观察到多线程并行")

        def overlap(a, b) -> float:
            return min(a[1], b[1]) - max(a[0], b[0])

        best = max(overlap(spans[i], spans[j])
                   for i in range(len(spans)) for j in range(i + 1, len(spans)))
        # 串行时每个区间互不相交 → best ≤ 0；并行（各睡 0.5s）时重叠应远大于 0.1s。
        self.assertGreater(
            best, 0.1,
            f"分支执行区间无重叠（best={best:.3f}s）→ 实为串行；spans={spans}，墙钟={elapsed:.2f}s")


class TestC3FanOutErrorHandling(unittest.TestCase):
    def setUp(self):
        self.backend = LocalBackend()
        self.backend.initialize()
        self.pe = PlannerExecutor(self.backend)
        self.pe.register("good", lambda payload: payload.get("v", 1))

        def bad(payload: dict):
            raise ValueError("分支炸了")

        self.pe.register("bad", bad)

    def tearDown(self):
        self.backend.shutdown()

    def test_raise_on_error_default(self):
        planner = lambda _t: [Send(target="good"), Send(target="bad")]  # noqa: E731
        with self.assertRaises(RuntimeError) as ctx:
            self.pe.run(planner, None)
        self.assertIn("bad", str(ctx.exception))

    def test_error_placeholder_keeps_order(self):
        planner = lambda _t: [  # noqa: E731
            Send(target="good", payload={"v": 1}),
            Send(target="bad"),
            Send(target="good", payload={"v": 3}),
        ]
        result = self.pe.run(planner, None, raise_on_error=False)
        self.assertFalse(result.ok)
        self.assertEqual(result.results, [1, None, 3], "失败分支以 None 占位，顺序不散")
        self.assertEqual(len(result.errors), 1)
        err = result.errors[0]
        self.assertIsInstance(err, SubTaskError)
        self.assertEqual(err.index, 1)
        self.assertEqual(err.target, "bad")


class TestC3PlannerValidation(unittest.TestCase):
    def setUp(self):
        self.backend = LocalBackend()
        self.backend.initialize()
        self.pe = PlannerExecutor(self.backend)
        self.pe.register("ok", lambda payload: 0)

    def tearDown(self):
        self.backend.shutdown()

    def test_empty_plan_rejected(self):
        with self.assertRaises(ValueError):
            self.pe.run(lambda _t: [], None)

    def test_unregistered_target_rejected_at_plan_time(self):
        with self.assertRaises(KeyError):
            self.pe.run(lambda _t: [Send(target="没注册")], None)

    def test_no_langgraph_dependency(self):
        """自写 fan-out，不引入 langgraph。"""
        import research.planner.planner as mod
        self.assertNotIn("langgraph", mod.__dict__)
        self.assertNotIn("langgraph", sys.modules)


if __name__ == "__main__":
    unittest.main()
