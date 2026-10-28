# 工单 264 · 论文日报 10-17 跨域授粉点转化 + 10-19 口径 bug 修复

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-264 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_264.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-264-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_264.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-19
> **触发**：师傅 10-19 在 QQ 下令"把授粉、论文、日报全部转换成工单"。本单对应**论文**类。
> **素材漏斗**（双源）：
> - ① `cron ad17cd9d341f` 10-19 02:14 跑批产出（**0 新增** + 1 口径告警）
> - ② `cron ad17cd9d341f` 10-17 02:42 跑批产出（**+1658 / 1553 真新增**，5 趋势 + 3 跨域授粉点），原文在 `/home/ubuntu/.hermes/cron/output/ad17cd9d341f/2026-10-17_02-42-36.md` 与 `/home/ubuntu/research/papers/weekly_pollination.md` 末尾段
> **守卫**：anti_hallucination_guard 默认对论文日报跑批不触发（本侧非代码层）；口径核查由 fetch_arxiv.py 的 seen 集合承担
> **前序**：WO-239（10-15 论文单）2026-10-17 师傅拍板**部分复活为 260**（任务 A 仓外脚本，**不动**；任务 B/C 复活）；本工单不交叉

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 10-19 cron 跑批产出 | ✅ | 0 新增 + 1 口径告警（已写 weekly_pollination.md） |
| 2 | 10-17 cron 跑批产出已落 weekly_pollination.md | ✅ | 1553 篇 + 5 趋势 + 3 授粉点 |
| 3 | 10-17 跨域授粉点 → 工单转化 | ❌ | **本工单任务 A-C** |
| 4 | 10-19 暴露的 base-id 口径 bug 修复 | ❌ | **本工单任务 D**（仓外脚本，**结构同 WO-239-A**，需师傅显式授权） |
| 5 | arXiv API 通道 406 死锁的旁路评估 | ❌ | **本工单任务 E**（要不要继续靠 RSS） |

**核心痛点**：
- 10-17 那批跨域授粉点写得很扎实（物理层射频指纹 / 技能版本化治理 / 颗粒填充弹性体均匀化），但 weekly_pollination.md 是**追加累积文件**，没人把它"摘出来立项"——`已扫` ≠ `已落地`
- arXiv API 自 10-15 起不响应（406 / hang），整个流程已回退到 RSS；10-19 完全 0 新增说明 RSS 也跟不上了
- base-id 口径 bug：6736 行版本重复全部被算成"待处理"，表面差异报 800 篇实际是空——本工单不修，下一轮跑批会**再次**被误报

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | ① 10-17 三条跨域授粉点各落 1 份立项 SPEC（不并码，先设计）；② 10-19 base-id 口径 bug 给出修法（仓外脚本，需师傅授权）；③ arXiv API 406 旁路评估出 1 份决策单 |
| **M** Measurable | ① 3 份 SPEC 各含"借鉴点 / 落点 / 难度×收益 / 验收"4 段；② base-id bug 修法有具体 diff；③ API 旁路评估有 2-3 个备选方案 + 推荐 |
| **A** Achievable | 3 份 SPEC 每份 ≤ 200 行；base-id 修法 ≤ 50 行 diff；API 旁路评估纯文本 |
| **R** Relevant | 师傅三条核心技术栈（无线电/嵌入式/Agent/生物质材料）；与 WO-262（授粉轮 46 设备完整性）、WO-263（10-19 扫货日报）形成**同一周的三联** |
| **T** Time-bound | 1 周（W2 与 WO-262/263 同期 review） |

## §2 · 任务清单

### 任务 A · 跨域授粉点 ① — 低成本可实测射频链

来源：10-17 跑批 `eess.SP / cs.AR / astro-ph.IM` 多篇

核心论文：
- `cs.AR 2610.20677`（LoRa 兼容接收机，噪声-功耗折中 + 集成 WuRX）
- `physics.app-ph 2610.22095`（等离子体负电容电小天线宽带匹配）
- `eess.SP 2610.21968`（事件触发在线频响辨识）
- `cs.IT 2610.22304`（Age-of-Actuation）/ `2610.22265`（AoII 最小化）
- `astro-ph.IM 2610.20847`（射电望远镜 RFI 相关监测器）
- `astro-ph.IM 2610.20848`（脉冲星脉冲抖动——"弱周期信号 + 非高斯噪声"经典口径）

落点：`docs/pollination/2026-10-17-授粉点-射频链.md`

| 段 | 内容 |
|---|---|
| 借鉴点 | ① 2610.20677 的 WuRX 集成 → 拆 SX1278 节点的"长期监听偶发唤醒"；② 2610.22095 的"有源负电抗换带宽"概念 → IC-705 中频匹配；③ 2610.22304/22265/21968 三件套 → LoRa/APRS 遥测调度的"何时传、传什么、传完算新鲜吗"决策骨架；④ 2610.20847 的相关 RFI 监测器 → HF/VHF 底噪普查；⑤ 2610.20848 的脉冲星 jitter noise → QRP 弱信号累积 |
| 落点 | IC-705 + 泉盛 UV-K6 + SDR + ESP32-S3 SuperMini + SX1278 + RP2040 六件套 |
| 难度×收益 | 中×高（每条子借鉴点都是"可上手"而非"待做 R&D"） |
| 验收 | 1）至少 1 个子借鉴点跑通（推荐 2610.20847 相关 RFI 监测器移植 IC-705 + SDR）；2）2610.22304/22265 的 Age-of-* 度量在中性频率上至少跑 1 个实验 |

### 任务 B · 跨域授粉点 ② — 技能 / 流程 / 记忆的版本化治理

来源：10-17 跑批 `cs.AI / cs.CL / cs.CR` 多篇

核心论文：
- `cs.AI 2610.22061`（FAOPs：Agent Operating Procedures）
- `cs.CL 2610.20927`（TEM：事实按版本+来源存，旧值不因被替换而失效）
- `cs.CL 2610.21900`（Prune the Summary, Not the History）
- `cs.CR 2610.21458`（covert rewriting attack / harness 溯源）
- `cs.CR 2610.22301`（MCP 能力洗白扫描）
- `cs.AI 2610.20845`（Agent Status Protocol，JSON POST + SSE）

落点：`docs/pollination/2026-10-17-授粉点-技能治理.md`

| 段 | 内容 |
|---|---|
| 借鉴点 | ① FAOPs → 当前工单提示词 + INDEX-active.md 状态机的形式化模板（"工单→步骤→证据"四元组）；② ASP 的 JSON POST + SSE → 3 profile gateway 状态聚合；③ TEM → 群聊记忆的版本化（旧值不覆盖而是标记失效，跨轮可回溯）；④ Prune the Summary → 摘要必须区分"环境事实 vs 压缩器推断/承诺"；⑤ covert rewriting attack → skill/插件市场（52）的溯源与许可留痕 |
| 落点 | NEKO + Lumo + skill/插件市场 + 工单流 |
| 难度×收益 | 中高×高（"Agent 记忆=有来源/有版本/有遗忘义务的数据库"是范式级变化） |
| 验收 | 1）FAOPs 形式化 1 个样例工单（用 WO-264 本工单作样本）；2）ASP 改 1 个 profile 跑通 JSON POST；3）TEM 在 1 处群聊记忆层留 v1/v2 痕迹 |

### 任务 C · 跨域授粉点 ③ — 半监督 / 颗粒填充 / 干燥分层

来源：10-17 跑批 `cond-mat.mtrl-sci / cond-mat.soft / physics.chem-ph / cs.LG` 多篇

核心论文：
- `cs.LG 2610.22025`（Not All Unlabeled Data Are Equal — 半监督 QSAR 的"挑样本"比模型值钱）
- `cond-mat.mtrl-sci 2610.20624`（颗粒填充弹性体二阶均匀化损伤）
- `cond-mat.mtrl-sci 2610.21911`（Voronoi 胞拓扑自动枚举）
- `cond-mat.soft 2610.20812`（AEM 膜"水活度梯度→溶胀→反过来改传输"双向耦合）
- `cond-mat.soft 2610.21816`（干燥液滴里多分散体系的尺寸偏析与分层）

落点：`docs/pollination/2026-10-17-授粉点-材料建模.md`

| 段 | 内容 |
|---|---|
| 借鉴点 | ① 2610.22025 的"挑未标注样本"策略 → 木质素/共熔凝胶配方筛选前先建"实验驱动 benchmark"；② 2610.20624 的二阶均匀化 → 木质素 NPs 填充水凝胶的"填充量→模量→损伤"桥接；③ 2610.20812 的 AEM 双向耦合 → 水下电子/凝胶器件（含水量作耦合变量而非外参）；④ 2610.21816 的尺寸偏析 → 太阳能蒸发/蒸发诱导自组装成膜；⑤ 2610.21911 的 Voronoi 拓扑枚举 → 非晶/多晶凝胶网络局部结构分类 |
| 落点 | 生物质材料（邵长优惠方向）：木质素 NPs → 水凝胶/共熔凝胶 → 水下电子/太阳能蒸发 |
| 难度×收益 | 高×高（实验驱动 benchmark 与模型外推都是长期工作） |
| 验收 | 1）"未标注数据选择"策略对邵老师方向给 1 份方法论对照（vs 既有"先模型"做法）；2）选 1 个子借鉴点（如 2610.21816）建 1 个最小数值实验 |

### 任务 D · 10-19 暴露的 base-id 口径 bug 修复

**问题**（来自 10-19 cron 跑批产出原文）：
> corpus 49197 行 = 42461 篇唯一论文 + 6736 行版本重复（同一 base id 的 v1/v2/v3 各占一行，API 与 RSS 双通道写入所致）。"corpus 行数 − processed 行数"不能当待处理数用，必须先按 base id 去重。

**结构同 WO-239-A**：`fetch_arxiv.py` 在仓外（`/home/ubuntu/research/papers/`），Trae GitHub 侧**改不了**。

**修法建议**（沈遥侧，**需师傅显式授权**才动）：
1. `fetch_arxiv.py` 的 `seen` 集合改用 base id（去掉末尾的 `vN`）：
   ```python
   def base_id(arxiv_id: str) -> str:
       return arxiv_id.split('v')[0] if 'v' in arxiv_id else arxiv_id
   ```
2. 写一遍 `dedup_corpus.py` 把当前 49197 行去重成 42461 行（保留每条 base id 最新版本）
3. `processed_ids.txt` 同样按 base id 写一份（49197 → 42461 行）
4. 下一次跑批前要再跑 `git -C /home/ubuntu/research rev-parse HEAD` 标"v2026-10-19-baseid-dedup"

**本工单不触发执行**——只把修法落到 `docs/operate/fetch-arxiv-baseid-bugfix-2026-10-19.md`，**等师傅授权**。

### 任务 E · arXiv API 406 旁路决策单

**现象**：
- 10-15 起 arXiv API 对本机全程 406 / hang / `max_results=80` 时 45s 挂死
- 10-17 跑批全部回退到 RSS（`published` 为 RFC822，缺 `announce_type` 之外的元数据）
- 10-19 跑批 RSS 也没新批次（arXiv 公告端口从 10-15 起停发）

**三个备选**（新文件 `docs/operate/arxiv-source-decision-2026-10-19.md`）：

| 方案 | 描述 | 优 | 劣 |
|---|---|---|---|
| A. 保持 RSS + 加 arxiv-sanity 镜像 | `http://export.arxiv.org/api/` 挂了就走 `https://arxiv.org/list/cs.LG/2026-10` 之类静态页 | 0 改 | 摘要质量下降 |
| B. 走 oai-pmh（`http://export.arxiv.org/oai2`） | 标准协议，分页稳定 | 抗限流好 | 字段映射要写 |
| C. 切到 HuggingFace Daily Papers 镜像 | 第三方策展，每日 50-100 篇精选 | 信号质量高 | 漏大量冷门 |

**推荐**：A 为主 B 为兜底 C 不用（与"31 大类全扫"目标冲突）。

## §3 · 验收标准

| 项 | 阈值 |
|---|---|
| 1. 跨域授粉点 ① SPEC 落 `docs/pollination/2026-10-17-授粉点-射频链.md` | ≥ 80 行，4 段齐全 |
| 2. 跨域授粉点 ② SPEC 落 `docs/pollination/2026-10-17-授粉点-技能治理.md` | ≥ 80 行，4 段齐全 |
| 3. 跨域授粉点 ③ SPEC 落 `docs/pollination/2026-10-17-授粉点-材料建模.md` | ≥ 80 行，4 段齐全 |
| 4. base-id 修法 SPEC 落 `docs/operate/fetch-arxiv-baseid-bugfix-2026-10-19.md` | 含 diff + 验收命令 |
| 5. arXiv API 旁路决策单 落 `docs/operate/arxiv-source-decision-2026-10-19.md` | 3 备选 + 推荐 |
| 6. 跑批 02:00 后无 base-id 误报 | next run `naive_diff=0` |
| 7. 不抢既有工单流（FAOPs 形式化不直接改 docs/workorders/INDEX-active.md） | `git diff --stat -- docs/workorders/INDEX-active.md` = 0 |

## §4 · 关联

- **WO-262**（授粉轮 46 落地）：同期同批，PR 一起合
- **WO-263**（10-19 扫货日报转化）：同期同批，PR 一起合
- **WO-239-A**（10-15 fetch_arxiv.py 限流护栏）：任务 D 是它的"姊妹单"——都涉及仓外脚本，都需师傅授权
- **WO-260**（WO-239 复活工单）：任务 D 与 WO-260 的"任务 A"同源，**本工单不触发执行**，合并到 WO-260 统一处理
- **WO-243**（工单台账）：任务 B 的"FAOPs 形式化"可能与 WO-243 撞——若撞，本工单只**写 SPEC 不改台账**

## §5 · 风险与边界

| 风险 | 缓解 |
|---|---|
| 任务 A 借鉴点过多（5 子借鉴点）导致 SPEC 失焦 | 每个子借鉴点写"难度+收益"两栏，标"立即/本周/季度"三档 |
| 任务 B FAOPs 形式化撞 WO-243 | 不改 `INDEX-active.md`，只写 SPEC 引用 |
| 任务 C 涉及邵长优惠方向，需 1 周以上 | SPEC 而非代码；本工单不出数值实验 |
| 任务 D 仓外脚本，Trae 改不了 | 修法落仓内 SPEC，等师傅授权 |
| 任务 E 切 oai-pmh 工程量大 | 推荐 A+简单兜底，C 不用 |

**不在本工单范围**：
- 10-17 五条趋势的逐条立项（趋势是"判读"，本工单只取 3 授粉点）
- 复审 9-02 / 9-07 等历史 paper-digest（旧单不复活，按日报"现跑现报"原则）
- 改 NEKO / Lumo 主仓代码（任务 B 只写 SPEC）
- 改工单台账状态机（WO-243 撞点不碰）

## §6 · 落地物清单

| 类别 | 文件 | 数量 |
|---|---|---|
| 跨域授粉点 ① | `docs/pollination/2026-10-17-授粉点-射频链.md` | 1 |
| 跨域授粉点 ② | `docs/pollination/2026-10-17-授粉点-技能治理.md` | 1 |
| 跨域授粉点 ③ | `docs/pollination/2026-10-17-授粉点-材料建模.md` | 1 |
| base-id 修法 | `docs/operate/fetch-arxiv-baseid-bugfix-2026-10-19.md` | 1 |
| arXiv 旁路决策 | `docs/operate/arxiv-source-decision-2026-10-19.md` | 1 |
| （合计） |  | 5 |

## §7 · 编号防撞

- **指令文件**：`TRAE_WORKORDER_PROMPT_AGENT_264.md`（仓库根，input）
- **施工记录**：本文件 `docs/WO-264-*`（output）
- 与已发的 `TRAE_WORKORDER_PROMPT_AGENT_*` 不撞号（已用 254~263，**264 下一号**）
