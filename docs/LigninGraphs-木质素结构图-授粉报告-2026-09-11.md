# LigninGraphs → 木质素结构图建模 授粉报告（卷101 W101-04）

- 日期：2026-09-11
- 源：https://github.com/VlachosGroup/LigninGraphs（MIT License，GPL 兼容，可直接借鉴）
- 目标：`tools/lig_graph_probe.py`（networkx 木质素单元图最小骨架）
- 施工分支：trae/agent-101

## 一、源→目标映射

| 源（LigninGraphs/ligning/） | 目标（本仓库） | 映射关系 |
|---|---|---|
| `polymer.py:16 PolymerGraph`（networkx 图为内核的高分子容器） | `lig_graph_probe.build_lignin_graph` | 图容器概念迁移：节点=木质素单元，边=单元间连接，属性挂图 |
| `characterization.py:167 count_linkages` / `:137 count_types` | `unit_counts` / `linkage_counts` | 键型/单元计数逻辑对应 |
| `characterization.py:394 cal_branching`（支化系数 = 支化单体/总单体） | `graph_features.mean_degree` | 结构特征→ML 输入特征的概念映射 |
| `rules.py:21-32` 键型符号体系（β-O-4/5-5/β-5/β-β/β-1） | `_LINKAGE_SYMBOLS` 常量集 | 键型命名体系直接借鉴（领域公共命名，非代码复制） |

## 二、核心数据结构共鸣（附源行号）

1. **networkx 作为单一事实来源**：源在 `polymer.py:4` 引入 `import networkx as nx`，整个库以 `nx.Graph` 承载单体与连接；本探针同样以 `nx.Graph` 为核心，节点属性 `unit`、边属性 `linkage`，与源「节点属性 + 边属性」模式一致（`characterization.py:176` 用 `self.G.edges[ei]['btype']` 从边属性读键型）。
2. **键型枚举集中定义**：源将全部键型符号集中在 `rules.py`（`# Linkage mapping` 注释块起于 :21，β-O-4/5-5/β-5/β-β1/β-1 全部列出）；本探针将 `_LINKAGE_SYMBOLS = {"beta-O-4","beta-5","beta-beta","5-5"}` 集中定义并做入参校验，属同一治理模式。
3. **计数型表征函数族**：源 `CharacterizeGraph` 提供 `count_types`（:137）/`count_monomers`（:155）/`count_linkages`（:167）/`count_OCH3`（:192）/`cal_MW`（:229）一套纯统计表征；本探针的 `unit_counts/linkage_counts/graph_features` 是同一「统计特征喂 ML」范式的精简版。
4. **结构特征字典化输出**：源 `cal_metrics`（:275）把表征结果组织为数值向量输出；本探针 `graph_features` 返回字典（S/G 比、β-O-4 占比、平均度），语义同源，载体换为人类可读 dict。

## 三、难度 × 收益

- 难度：★★☆（networkx 已装；图建模本体 ~100 行，无算法难点）
- 收益：★★☆（木质素结构→ML 特征通道打通；键型/单元校验逻辑可在后续质谱、热解建模中复用）

## 四、借鉴点清单（≥3）

1. 键型符号体系集中管理 + 严格校验（拒绝未知键型/单元，报错可读）——借鉴自 `rules.py` 的集中定义模式。
2. 「图 + 边属性读键型」的特征提取路径——借鉴自 `characterization.py:176` 的 btype 读取。
3. S/G 比、β-O-4 占比作为默认结构特征——借鉴自 `count_types`/`count_linkages` 的计数语义（均为领域常识性特征，实现独立）。
4. 图对象与统计函数分离（构造一次、统计多次）——借鉴自 `Polymer` 与 `Characterize` 的类分层。

## 五、许可裁定

LigninGraphs 为 **MIT License**（仓库根 `LICENSE` 文件）：可自由借鉴与融合。本探针为独立实现，未复制任何源文件代码；键型命名属领域公共符号。裁定：**安全**。

## 六、验收

`tools/test_lig_graph_probe.py`：5 项测试全绿（构造/计数/特征/两类非法输入拒绝）。
