"""A03 Thinkingbox 可靠性评测脚本：pass@1 vs pass^k（终端状态一致性）。

用法：被测 Agent 需实现 `Agent.run(task, seed) -> terminal_state`，
判定函数 judge(terminal_state) -> bool 决定终端状态是否"正确"。
"""
from collections import defaultdict


def evaluate(agent, tasks, k=20, judge=None):
    """对每个任务跑 k 次（不同 seed），度量 pass@1 与 pass^k。

    - pass@1 : k 次中至少一次成功（"曾经成功"）
    - pass^k : k 次全部终端状态一致成功（"重复可靠"）
    两者之差即"响应正确 ≠ 任务完成"的可靠性鸿沟。
    """
    judge = judge or (lambda st: bool(st.get("done") and st.get("correct")))
    pass_at_1 = pass_at_k = 0
    report = {}

    for t in tasks:
        outcomes = []
        for i in range(k):
            st = agent.run(t, seed=i)
            outcomes.append(bool(judge(st)))
        p1 = any(outcomes)
        pk = all(outcomes)
        pass_at_1 += p1
        pass_at_k += pk
        report[t.id] = {
            "pass@1": p1,
            f"pass^{k}": pk,
            "success_rate": sum(outcomes) / k,
            "outcomes": outcomes,
        }

    n = len(tasks)
    return {
        "pass@1": pass_at_1 / n,
        f"pass^{k}": pass_at_k / n,
        "reliability_gap": (pass_at_1 - pass_at_k) / n,
        "per_task": dict(report),
    }


if __name__ == "__main__":
    # 示例：一个"单次侥幸成功"型假 Agent，用于演示 pass@1 与 pass^k 的鸿沟
    class FlakyAgent:
        def run(self, task, seed=0):
            # 只有 seed==0 时碰巧正确，其余失败 → pass@1 高、pass^k=0
            correct = (seed == 0)
            return {"done": True, "correct": correct, "task": task.id}

    class Task:
        def __init__(self, i):
            self.id = f"t{i}"

    tasks = [Task(i) for i in range(50)]
    result = evaluate(FlakyAgent(), tasks, k=20)
    print("pass@1      :", round(result["pass@1"], 4))
    print("pass^20     :", round(result["pass^20"], 4))
    print("reliability_gap:", round(result["reliability_gap"], 4))
