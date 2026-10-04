"""依赖漏洞图谱最小原型（P2-2 · W73-10 Athena KG）。

依据 docs/memory-security-audit-评估.md：Athena 把依赖漏洞图谱化，图谱化追踪
漏洞影响面。作为 third-party-code-audit 的图谱化增强。

原型（纯 stdlib）：
  - VulnGraph：dep ↔ CVE 双向索引
  - add_vuln(dep, cve, severity)
  - vulns_for(dep)、affected_deps(cve)、impact_chain(dep)（可达漏洞集）

运行：python tools/dependency_vuln_graph.py
"""
from __future__ import annotations

from collections import defaultdict, deque


class VulnGraph:
    """依赖漏洞知识图谱：dep ↔ CVE 双向 + 传递影响链。"""

    def __init__(self) -> None:
        self.dep_cves: dict[str, set[str]] = defaultdict(set)      # dep -> {cve}
        self.cve_deps: dict[str, set[str]] = defaultdict(set)      # cve -> {dep}
        self.deps: dict[str, list[str]] = defaultdict(list)        # dep -> 直接依赖

    def add_dependency(self, parent: str, child: str) -> None:
        self.deps[parent].append(child)

    def add_vuln(self, dep: str, cve: str, severity: str) -> None:
        self.dep_cves[dep].add(cve)
        self.cve_deps[cve].add(dep)

    def vulns_for(self, dep: str) -> set[str]:
        return self.dep_cves[dep]

    def affected_deps(self, cve: str) -> set[str]:
        return self.cve_deps[cve]

    def impact_chain(self, root: str) -> set[str]:
        """BFS 沿依赖链收集可达子依赖的漏洞。"""
        seen = {root}
        q = deque([root])
        vulns = set()
        while q:
            cur = q.popleft()
            vulns |= self.dep_cves[cur]
            for child in self.deps[cur]:
                if child not in seen:
                    seen.add(child)
                    q.append(child)
        return vulns


if __name__ == "__main__":
    g = VulnGraph()
    g.add_dependency("app", "lib-a")
    g.add_dependency("lib-a", "lib-b")
    g.add_vuln("lib-b", "CVE-2026-0001", "high")
    g.add_vuln("lib-a", "CVE-2026-0002", "medium")
    print("[app 影响链]", g.impact_chain("app"))
    print("[CVE-2026-0001 影响]", g.affected_deps("CVE-2026-0001"))
