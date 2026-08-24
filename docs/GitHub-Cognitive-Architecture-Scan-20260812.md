# GitHub 思路采集：系统工程动力学层 → Cognitive Architecture 赛道

> 采集：2026-08-12
> 目的：为「系统工程 → Agent 工作流蒸馏」的动力学层找可落地的实现参考
> 结论：蒸馏方向被 GitHub 验证，且已有具体实现可借鉴

---

## 一、核心信号

GitHub 上 2026 年涌现出一批 **cognitive architecture（认知架构）** 项目，它们几乎逐条对应系统工程动力学层的五个概念：

| 系统论概念 | GitHub 实现 | 代表项目 |
|-----------|------------|---------|
| **遗忘 = 适应性**（熵增逆操作） | 激活衰减 / 艾宾浩斯曲线 / 势场衰减 | mtrace, mamba-memory, uctg-mem |
| **反馈回路** | reflection loop（generate→critique→refine） | MemoryLoop, 一堆 self-improving |
| **涌现协调** | 全局工作空间理论（GWT） | Global-Workspace-Agents |
| **记忆巩固** | consolidation（从会话提炼长期） | cognitive-memory-agent |
| **自组织** | 生物启发（神经化学/菌丝体/梦巩固） | agentbrain, mycelium, scallopbot |

**结论：我蒸馏的「动力学层」不是理论空想，是 GitHub 正在验证的方向。** 遗忘、反馈、涌现这三个最反直觉的概念，都已有工程实现。

---

## 二、五个可落地思路（按价值排序）

### 思路 1：记忆加「遗忘衰减」（最轻量，最该做）

- **mtrace**（ACT-R 激活模型，零依赖 sqlite）：每个记忆有激活值，随时间衰减，被检索则强化。遗忘不是删除，是激活值降到阈值以下不再召回。
- **uctg-mem**（势场动力学）：记忆在势场上自然衰减，数学基础最扎实（potential decay）。
- **mamba-memory**（艾宾浩斯遗忘曲线）：模仿人类遗忘规律，带学习门控。

**对 Hermes 的启示**：memory 工具现在是「只增不减」的扁平清单。应该加激活值/衰减——记过的信息不主动删，但检索时按激活值排序，久未用到的自然沉底。**遗忘是检索层的过滤，不是存储层的删除。**

### 思路 2：记忆「巩固」自动化（最有价值）

- **cognitive-memory-agent**：4 记忆系统（语义 RAG + 情景回忆 + 程序规则 + 工作记忆）+ 周期巩固。巩固 = 从会话记忆中提炼出跨会话的稳定事实。

**对 Hermes 的启示**：Hermes 已有三层记忆（工作/会话/长期），但**缺「巩固」这一步**——从 session_search 自动提炼长期记忆的过程。现在这个动作靠我手动做，应该自动化成 cron：定期扫描近期会话，提炼出「值得长期记住的稳定事实」。

### 思路 3：skill 自改进回路（已在做，可强化）

- **MemoryLoop / reflection agent**：从错误中学习，generate → critique → refine 循环。

**对 Hermes 的启示**：Hermes 已经做了「用 skill 发现过时 → patch」的反射回路（skill 维护原则）。可以强化为显式的「从失败中学习」——任务失败后，把根因沉淀成 skill 的 pitfall。

### 思路 4：GWT 涌现协调（远期）

- **Global-Workspace-Agents**：多个专家 agent 竞争「广播」到全局工作空间，由全局工作空间决定下一个焦点。认知科学的「意识」理论映射到多 agent 协调。

**对 Hermes 的启示**：这是「涌现可观测性」的候选答案。不是中央调度（违背涌现），是竞争广播——每个 agent 提交候选，全局工作空间选出最相关的。对多 Hermes 实例协调有参考价值。

### 思路 5：Hermes 已在被当作参考架构

- **autonomous-ai-hiring-agent** 明确写「inspired by Hermes Agent featuring semantic search, memory systems, skill orchestration, reflection loops」。

**启示**：你的方向被验证是对的，但也意味着别人在追。拉开差距的关键，正是思路 1-3 这些别人还没做全的「动力学层」——记忆遗忘、巩固、自改进回路。

---

## 三、优先级建议

| 思路 | 成本 | 收益 | 建议 |
|------|------|------|------|
| 1 记忆遗忘衰减 | 低（sqlite 加激活值字段） | 高（记忆不再污染） | **立即做** |
| 2 记忆巩固自动化 | 中（cron + 提炼 prompt） | 最高（省我手动） | **近期做** |
| 3 skill 自改进 | 低（已有基础） | 中（强化已有） | 顺手强化 |
| 4 GWT 协调 | 高（架构级） | 远期（多实例） | 观望 |

---

## 四、关键项目清单

| 项目 | 机制 | 许可 | 备注 |
|------|------|------|------|
| mtrace | ACT-R 激活+遗忘 | 待确认 | 零依赖 sqlite，最轻量 |
| mamba-memory | 艾宾浩斯三层 | 待确认 | SSM 启发，F1=0.945 |
| uctg-mem | 势场衰减+知识图谱 | 待确认 | 物理启发，数学扎实 |
| cognitive-memory-agent | 4记忆+巩固 | 待确认 | 语义/情景/程序/工作 |
| Global-Workspace-Agents | GWT 广播 | 待确认 | 多 agent 涌现协调 |
| agentbrain | 神经化学情绪 | 待确认 | 本地 OpenClaw |
| mycelium | 菌丝体+主动推理 | 待确认 | 生物启发+P2P |

---

## 元记录

- 关联：`System-Engineering-to-Agent-Workflow-Distillation.md`（动力学层）
- 验证：蒸馏的「遗忘=适应性」「反馈」「涌现不可控」三条被 GitHub 逐条印证
- 下一步：思路 1（记忆遗忘）可直接做，参考 mtrace 的 ACT-R 激活模型
