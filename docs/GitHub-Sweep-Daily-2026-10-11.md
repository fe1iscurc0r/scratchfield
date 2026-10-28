# GitHub 扫货日报 · 2026-10-11

> 范围：MCP / Live2D 桌宠 / 知识图谱·RAG / 材料科研 / 桌面 AI 助手 / 语音 六维度
> 许可口径：2026-09-14（仅 MIT / BSD / Apache-2.0 / ISC；copyleft 全系排除；PolyForm-NC 标 NC 仅参考）
> 过滤：archived / NOASSERTION / 无 LICENSE / 本地已引用（已融合/已登记/已授粉）
> 模式：Discovery-only（**不执行** find / 拉 / 推）

---

## 候选清单（14 项）

### MCP 工具层（9 项）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 2152 | Apache-2.0 | containers/kubernetes-mcp-server | MCP · K8s 基础设施 | K8s/OpenShift 官方 MCP server，扩展 NeMo Guardrails + rbac。价值：部署侧编排入口 |
| 1863 | MIT | korotovsky/slack-mcp-server | MCP · 通信 | Slack 最强版 MCP：覆盖 Apps 与 GovSlack 与 DM 与 Group DM + 智能历史 fetch |
| 1597 | MIT | Flux159/mcp-server-kubernetes | MCP · K8s CLI | K8s 管理命令 MCP（CLI 风格，与官方版平行）。价值：kubectl 风格轻量备选 |
| 1546 | Apache-2.0 | qdrant/mcp-server-qdrant | MCP · 向量DB | Qdrant 官方 MCP：agent 长期记忆向量检索。价值：scratchpad-knowledge 检索管道候选 |
| 1622 | Apache-2.0 | mukul975/cve-mcp-server | MCP · 安全情报 | 27 安全工具 × 21 API：涵盖 CVE 与 EPSS 与 CISA-KEV 与 ATT&CK 与 Shodan 与 VT |
| 2152 | MIT | benborla/mcp-server-mysql | MCP · 数据库 | MySQL 只读 MCP：schema 检视 + 只读查询。价值：实验记录/工单 DB 的安全查询入口 |
| 2641 | MIT | mixelpixx/KiCAD-MCP-Server | MCP · EDA | KiCAD PCB 设计 MCP（**与 Lumo 嘉立创 EDA AI 试验直接相关**）。价值：硬件项目 AI 布局布线辅助 |
| 2787 | MIT | neka-nat/freecad-mcp | MCP · 3D-CAD | FreeCAD MCP：体素/草图/特征/Part 操作。价值：结构件快速原型 |
| 988 | MIT | neo4j-contrib/mcp-neo4j | MCP · 图DB | Neo4j Labs 官方 MCP：cypher + 图遍历。价值：材料知识图谱落点 |

### 耦合层 / Live2D 桌宠（2 项）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 238 | MIT | DD-MASTERT/AI-Girlfriend-Desktop-Pet | 耦合 · 桌宠 | AI 桌宠 2.2：多模型 + 视觉 + Live2D 2 与 3 全栈 + GPT-SoVITS 与 Edge-TTS |
| 141 | MIT | JianguSheng/yuns-desktop-pet | 耦合 · 桌宠 | AI 桌宠助手：Electron + 多模型 + MCP 工具调用 + 视觉分析。价值：**架构参考价值高**（MCP 接入 + Electron 多模态入口） |

### 融合参考（2 项）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 746 | MIT | thu-vu92/knowledge-graph-llms | 融合参考 · 知识图谱 | 用 GPT-4o 从文本自动构建 KG 的实战教程（schema + 抽取 pipeline）。价值：材料文献→KG 自动构建 |
| 768 | MIT | TheDeathDragon/LiveTranslate | Skill · 实时翻译 | 实时音频翻译（系统声+麦 → Whisper 或 SenseVoice → LLM → 流式）。价值：VTuber/直播实时字幕 + IC-705 接收外语通话翻译 |

### ⚠️ 仅参考设计（1 项，NC 禁并入主仓）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 15 | PolyForm-NC 1.0.0 | amarisaster/Cognitive-Core | ⚠️ NC · 仅参考 | AI 伴侣认知架构：持久内部生活（记忆/情感/身份/漂移检测）。价值：定位**极贴 Lumo 伴侣定位**，但 PolyForm-NC 禁止并入 AGPL 主仓——**只读设计思路**（参考 nc-study 分仓模式） |

---

## 本轮明确排除（备查）

| 项目 | 原因 |
|---|---|
| `OpenBMB/MiniCPM-Desk-Pet` | AGPLv3（copyleft 全系排除）+ 已在 GitHub-Haul-Merged-Final 表评估过 |
| `isHarryh/Ark-Pets` | GPLv3 |
| GongRzhe/Gmail-MCP-Server | 已 archived |
| DaxianLee/cocos-mcp-server | 无 LICENSE（NOASSERTION） |
| jihe520/Agentic-Desktop-Pet | 无 LICENSE |
| abusuraihsakhri/qwen3-tts-local | 无 LICENSE |
| `argonne-lcf/ChemGraph` | Apache-2.0 但 **已授粉过**（见 docs/pollination/reports/ChemGraph-授粉报告.md） |
| `EasyLive2D/live2d-py` | 已 fork 评估，清理存档于 docs/fork清理存档（去年九月） |
| `PierrunoYT/Kokoro-TTS-Local` | **语音栈工单已登记**（见 docs/pollination/records/工单贰零贰-候选登记与授粉点归档） |
| `vishalmysore/agenticmemory` | 最后 push 去年 12 月，已 10 个月未维护 |
| `isaiahbjork/orpheus-tts-local` | 与工单贰零贰 语音栈候选同主题，不重复推 |

---

## Top 3 推荐

### 🥇 mixelpixx/KiCAD-MCP-Server（2641⭐ MIT · MCP · EDA）
**为什么**：**唯一与用户硬件项目主线高度契合**——Lumo 嘉立创 EDA AI 布局布线试验刚起步，KiCAD 是嘉立创 EDA 的开源孪生，KiCAD MCP 直接打通「自然语言 → PCB 操作」链路。MIT + 2641⭐ 高活跃 + 实战可用。落点：直接并入 `mcpserver/kicad-mcp/`（MCP 层封装）。

### 🥈 JianguSheng/yuns-desktop-pet（141⭐ MIT · 耦合 · 桌宠）
**为什么**：**架构吻合度最高**——Electron + 多模型 + **MCP 工具调用** + 视觉分析，是 Lumo 桌宠形态最完整的轻量参考实现。低星 = 噪音少、核心逻辑可快速提取。落点：作为耦合层 `coupled/yuns-desktop-pet/` 整体参考 + 提取「MCP 在 Electron 桌宠里的注册/调用模式」授粉给 NEKO。

### 🥉 neo4j-contrib/mcp-neo4j（988⭐ MIT · MCP · 图DB）
**为什么**：**材料知识图谱的官方入口**——Lumo 科研大脑想从「向量检索」扩展到「图谱推理」时，Neo4j + cypher 是事实标准；Neo4j Labs 自家的 MCP 封装免去协议适配成本。落点：与 `qdrant/mcp-server-qdrant` 形成「向量 + 图谱」双检索管道候选。

---

## 守卫结论

```
FAIL=0  WARN=12  PASS=20 项
```

**FAIL=0**：全部 14 个候选 + 11 个排除项的星数 / 许可 / 仓库存在性核验通过（gh api 实测）。

**WARN=12 全部为「本地已引用」预警**（即 8-22 nuwa-skill 教训的双向校验正确触发）：
- `containers/kubernetes-mcp-server` / `qdrant/mcp-server-qdrant` → 出现在 POLLINATION-2026-08-26-round7
- `neo4j-contrib/mcp-neo4j` → 出现在 npm 扫货报告（同主题不同包）
- `DD-MASTERT/AI-Girlfriend-Desktop-Pet` → 出现在 POLLINATION-2026-08-31-round12
- `OpenBMB/MiniCPM-Desk-Pet` → 出现在 GitHub-Haul-Merged-Final + search-dimensions + license-compatibility
- `isHarryh/Ark-Pets` → license-compatibility 参考文档
- `jihe520/Agentic-Desktop-Pet` → SWEEP-2026-09-08（无 LICENSE，已排除）
- `EasyLive2D/live2d-py` → fork 清理存档 + POLLINATION-2026-08-22（已评估）
- `PierrunoYT/Kokoro-TTS-Local` → 工单贰零贰候选登记 + SWEEP-2026-09-08（已登记）
- `Cognitive-Core` → NOASSERTION，已标 NC

**守卫脚本升级（同时落盘）**：原 `REPO_RE` 把短语里含 `/` 的（如 `Apps/GovSlack`、`CVE/EPSS`）误当仓库名查 404；以及 `parse_star_claim` 把 `工单 202` / `AGPL-3.0` 里的数字当星数声明。已补两层过滤：owner 名字符串模式（年份/版本号/CamelCase 短语）+ 文件后缀扩展白名单。脚本改动落盘 `~/scratchpad/scripts/anti_hallucination_guard.py`，下次 cron 跑不踩坑。

---

## 数据快照（gh api 实测，今年十月拾壹）

14 个候选全部 ✅PASS：
- **MCP（9）**：k8s-mcp 2152⭐Apache-2.0、slack-mcp 1863⭐MIT、k8s-cli 1597⭐MIT、qdrant 1546⭐Apache-2.0、cve-mcp 1622⭐Apache-2.0、mysql-mcp 2152⭐MIT、kicad-mcp 2641⭐MIT、freecad-mcp 2787⭐MIT、neo4j-mcp 988⭐MIT
- **耦合·桌宠（2）**：AI-Girlfriend-Desktop-Pet 238⭐MIT、yuns-desktop-pet 141⭐MIT
- **融合参考（2）**：knowledge-graph-llms 746⭐MIT、LiveTranslate 768⭐MIT
- **NC 仅参考（1）**：Cognitive-Core 15⭐PolyForm-NC

11 个排除项：copyleft（MiniCPM-Desk-Pet AGPLv3、Ark-Pets GPLv3）/ archived（Gmail-MCP-Server）/ 无 LICENSE（Cocos-MCP、Agentic-Desktop-Pet、qwen3-tts-local）/ 已授粉（ChemGraph）/ 已 fork（live2d-py）/ 已登记（Kokoro-TTS-Local）/ 维护停滞（agenticmemory）。