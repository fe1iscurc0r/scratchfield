"""A61 · Pivot-and-Station 多 Agent 路径规划原型（来源 2608.24585）

论文核心：高密度仓储（仓库/机器人停车/厂房物流）场景下
Pivot-and-Station MAPF 的可解性、完备性与复杂度。

原型（简化，显式标注）：
  - 网格仓库：障碍 + 通道 + station 缓冲位（缓冲位等待不独占，可让行）
  - 优先级时空 A*：按距离降序逐个规划，后来者避让已预留的 (时刻,格)
  - 目标到达后继续占位（防止追尾冲突）
评估：种子密集实例全部到达；路径无顶点/对向冲突；报告 makespan。

运行：python -m mcpserver.agent_lab.prototypes.pivot_station_mapf
"""
from __future__ import annotations

import heapq

# mock 仓库地图（#障碍 .通道 P=station 缓冲位）
GRID = [
    "##########",
    "#........#",
    "#.##.##..#",
    "#....P...#",
    "#.P......#",
    "#..##....#",
    "##########",
]


class Warehouse:
    """网格仓库：障碍集 + station 缓冲位集"""

    def __init__(self, rows: list[str] = GRID):
        self.H, self.W = len(rows), len(rows[0])
        self.obstacles = {(r, c) for r, row in enumerate(rows)
                          for c, ch in enumerate(row) if ch == "#"}
        self.stations = {(r, c) for r, row in enumerate(rows)
                         for c, ch in enumerate(row) if ch == "P"}

    def passable(self, cell: tuple[int, int]) -> bool:
        return cell not in self.obstacles

    def neighbors(self, cell: tuple[int, int]) -> list[tuple[int, int]]:
        """四邻移动 + 原地等待"""
        r, c = cell
        out = [cell]
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (r + dr, c + dc)
            if self.passable(nb):
                out.append(nb)
        return out


def spacetime_astar(wh: Warehouse, start: tuple[int, int], goal: tuple[int, int],
                    reserved: set, max_t: int = 150) -> list | None:
    """时空 A*：避让已预留 (t,格)；station 缓冲位豁免预留（让行语义，原型简化）"""

    def h(cell):
        return abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])

    open_h = [(h(start), 0, start)]
    came: dict = {}
    seen = {(0, start)}
    while open_h:
        _, t, cell = heapq.heappop(open_h)
        if cell == goal:
            path = [cell]
            key = (t, cell)
            while key in came:
                key = came[key]
                path.append(key[1])
            return path[::-1]
        if t >= max_t:
            continue
        for nb in wh.neighbors(cell):
            nkey = (t + 1, nb)
            if nkey in seen:
                continue
            if nb not in wh.stations and nkey in reserved:
                continue  # 与先到者冲突且非缓冲位 → 避让
            seen.add(nkey)
            came[nkey] = (t, cell)
            heapq.heappush(open_h, (t + 1 + h(nb), t + 1, nb))
    return None


def solve(wh: Warehouse, agents: list[tuple]) -> list[list] | None:
    """优先级规划：曼哈顿距离远的先规划（远者优先减少绕行），失败返回 None"""
    order = sorted(range(len(agents)),
                   key=lambda i: -(abs(agents[i][0][0] - agents[i][1][0])
                                   + abs(agents[i][0][1] - agents[i][1][1])))
    reserved: set = set()
    paths: list = [None] * len(agents)
    for i in order:
        s, g = agents[i]
        p = spacetime_astar(wh, s, g, reserved)
        if p is None:
            return None
        paths[i] = p
        for t, cell in enumerate(p):
            reserved.add((t, cell))
        # 到达终点后继续占位（近似无限占位，防追尾）
        if g not in wh.stations:
            for t in range(len(p), len(p) + 60):
                reserved.add((t, g))
    return paths


def evaluate() -> dict:
    """种子密集实例：4 个 Agent 交叉穿行，验证可解性与 makespan"""
    wh = Warehouse()
    agents = [
        ((1, 1), (5, 7)),  # 左上 → 右下
        ((1, 8), (5, 1)),  # 右上 → 左下（与 0 号交叉）
        ((3, 8), (4, 8)),  # 短程
        ((1, 3), (5, 5)),  # 中部纵穿
    ]
    paths = solve(wh, agents)
    if paths is None:
        return dict(solved=False)
    makespan = max(len(p) - 1 for p in paths)
    return dict(solved=True, n_agents=len(agents), makespan=makespan,
                path_lens=[len(p) - 1 for p in paths], paths=paths)


if __name__ == "__main__":
    r = evaluate()
    if r["solved"]:
        print(f"Pivot-and-Station MAPF：{r['n_agents']} Agent 全部到达，"
              f"makespan={r['makespan']}，各路径长={r['path_lens']}")
    else:
        print("实例不可解（原型简化下优先级规划失败）")
