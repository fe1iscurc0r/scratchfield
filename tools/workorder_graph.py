"""W71-03 · 工单↔代码知识图谱原型（吞入自 GitLab knowledge-graph 思路，MIT 可吞）。

GitLab KG 的核心：把「代码/issue/MR/CI」建成图，供 AI agent 导航生命周期。
本原型自研实现「提交 ↔ 文件 ↔ 工单」三类实体图，供 Hermes/Trae 多 agent 做
「从工单跳代码、从文件跳工单」的上下文导航。纯标准库。
"""
from __future__ import annotations

from collections import defaultdict


class WorkorderGraph:
    """提交 ↔ 文件 ↔ 工单 的有向索引图（邻接表）。"""

    def __init__(self):
        self._commits: list[tuple[str, list[str], str]] = []  # (commit_id, files, workorder_id)
        self._file_to_commits: dict[str, list[str]] = defaultdict(list)
        self._workorder_to_files: dict[str, set[str]] = defaultdict(set)
        self._file_to_workorders: dict[str, set[str]] = defaultdict(set)

    def add_commit(self, commit_id: str, files: list[str], workorder_id: str) -> None:
        self._commits.append((commit_id, list(files), workorder_id))
        for f in files:
            self._file_to_commits[f].append(commit_id)
            self._file_to_workorders[f].add(workorder_id)
            self._workorder_to_files[workorder_id].add(f)

    def files_for_workorder(self, workorder_id: str) -> set[str]:
        """某工单触及的文件集合。"""
        return set(self._workorder_to_files.get(workorder_id, set()))

    def workorders_for_file(self, file: str) -> set[str]:
        """某文件涉及的工单集合。"""
        return set(self._file_to_workorders.get(file, set()))

    def commits_touching_file(self, file: str) -> list[str]:
        """某文件的提交历史。"""
        return list(self._file_to_commits.get(file, []))

    def trace(self, file: str) -> str:
        """导航摘要：文件 → 工单 → 兄弟文件（生命周期上下文）。"""
        wos = self.workorders_for_file(file)
        siblings = set()
        for w in wos:
            siblings |= self.files_for_workorder(w)
        return f"{file} 关联工单 {sorted(wos)}，兄弟文件 {sorted(siblings - {file})}"


def run_demo() -> None:
    g = WorkorderGraph()
    g.add_commit("c1", ["tools/adif.py", "docs/x-qsl-adif-评估.md"], "w71-09")
    g.add_commit("c2", ["tools/soft_lora_phy.py"], "w71-08")
    g.add_commit("c3", ["tools/adif.py", "tools/test_adif.py"], "w71-09")
    print(f"[W71-03] w71-09 触及文件: {sorted(g.files_for_workorder('w71-09'))}")
    print(f"[W71-03] tools/adif.py 涉及工单: {sorted(g.workorders_for_file('tools/adif.py'))}")
    print(f"[W71-03] 导航: {g.trace('tools/adif.py')}")


if __name__ == "__main__":
    run_demo()
