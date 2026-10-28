# GitHub 扫货日报 — 2026-10-19

**扫描**：6 维度 × 38 条查询（新建 + 活跃双路）→ 639 原始结果 → 对照近 6 期日报与 scratchpad docs 去重 → 34 项 `gh api` 补 license/archived/size → 铁条件过滤 → **15 项入表**
**模式**：Discovery-Only（只发现 + 评估，**未** clone / pull）
**许可口径**：2026-10-12 纠正版（MIT/BSD/Apache/ISC ✅；AGPL/GPL/LGPL/MPL/SSPL ✅ 可融合；专有/BSL/Elastic/source-available ❌；无 LICENSE ⚠️暂缓）
**核实**：星数/许可/archived 全部 `gh api repos/*` 实测；NOASSERTION 项逐项读 LICENSE 原文

---

## ① Live2D / 桌宠（本日最大发现：Live2D 生产线被打通）

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `tsunehimatoi/psd2live` | 683★ | GPL-3.0 + MIT（双段） | Live2D 绑骨 | 开源 2D 角色绑定/动画编辑器：分层 PSD 自动出可动初版，同工作区修形、绑骨骼、物理与模拟，导出 Cubism / VTube Studio / 网页 / 游戏引擎 | 🆕 **NEKO 资产管线缺的就是这一段**。过去只有「找模型」，没有「从 PSD 造模型」；自动绑定把美术成本从小时级压到分钟级。许可分段干净：引擎 `umamo` 是 GPL-3.0，中立绑定 IR `format-model`、导出框架 `format-compile`、Rust 运行时是 **MIT 可单独复用**——授粉只取 MIT 那半边，不碰 GPL 主程序 |
| `AyagamiDev/ayagami` | 367★ | MIT + Apache-2.0（双许可） | Live2D 运行时 | Rust 写的 2D 纸偶加载/渲染 SDK，**兼容 Live2D 模型格式**，可扩展新格式 | 🆕 **绕开 Cubism 专有 SDK 的关键件**。官方 SDK 闭源且带商用条款，NEKO 越做越深越受制；Ayagami 用 MIT 与 Apache 双许可重写加载与渲染。仓库仅 1.6MB，授权文件是 `LICENSE-MIT` + `LICENSE-APACHE`（非标准名，只查 `LICENSE` 会误判无许可） |
| `Pal-AI-Lab/Coopanion` | 384★ | AGPL-3.0 | 桌宠（Electron） | 极简 AI 桌面伙伴，Windows 10 与 11，基于自家 MIT 框架 Cortico；语音链路用 sherpa-onnx + SenseVoice/Whisper | 🆕 与我们同构的**成品参照**：桌宠窗口 + 语音唤醒 + 多模型连接（含复用 ChatGPT 订阅登录）整条打通。AGPL 兼容；重点读它的**连接管理与唤醒节流**（一次唤醒最多 40 次模型请求，超限优雅收尾）——NEKO 缺的正是「别把 API 打爆」这层 |
| `jamro/tiny-engineer` | 715★ | MIT（软件）+ CERN-OHL-S-2.0（硬件） | 实体桌宠 | ESP32 + 舵机 + OLED + 喇叭小机器人，随 coding agent 状态动：读文件东张西望、写码打字、完成摇铃 | 把「agent 运行态」映射成物理动作的状态机，与 10-18 的 `clawd-on-desk`（像素态）互补——这套是**实体态**。⚠️ 需 3D 打印 + 舵机 + 主控板（硬件依赖，只标注不否决）；`3d_models/` 425MB 占体积大头 |

## ② 语音

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `breezeblue-ai/breeze-tts` | 615★ | Apache-2.0 | TTS | Breeze TTS 2：开放权重实时 TTS，中英双语，支持自然语言描述造音色（免参考音频）+ **文内情绪事件** `[笑]`/`[咳嗽]`/`[叹气]` | 🆕 **对 NEKO 是本日最高性价比**。伴侣角色的「声音表情」过去要自己切音效，它把 `[笑]` 写进文本流就出情绪音——省掉一套事件调度。若其宣称的第三方榜单（Artificial Analysis 开放权重第一）属实，是可替代 OmniVoice 的中文更强路线 |
| `Edge0-AI/Audio8_TTS` | 1835★ | Apache-2.0 | TTS（端侧） | 0.6B 多语言 TTS + 零样本克隆，提供 **ONNX INT4** 量化版 | 🆕 与 10-18 的 MOSS-TTS-Nano 同思路但更小：ONNX INT4 = 无 GPU 也能跑。适合低功耗模式兜底音色，或塞进手机端（`phone-mobile-hub` 线） |

## ③ 材料 / 化学

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `AtomFlow-AI/MoleCode` | 306★ | MIT | 分子语言 | 「把分子写成代码」的 LLM 原生分子语言，让模型直接对分子结构做推理（arXiv 2605.16480） | 🆕 **直接对上授粉表里「化学式→结构化」那一格**：H₂SO₄→`{H:2,S:1,O:4}` 这类解析，它给的是图显式的语法层，而不是让模型猜 SMILES。木质素/凝胶结构式入库可走这条路 |
| `jinzhezenggroup/computational-chemistry-agent-skills` | 153★ | LGPL-3.0 | Agent Skill 集 | 计算化学任务的可执行 Agent Skill 集（JCTC 论文配套，用于 OpenClaw 等） | 🆕 **它是「Skill 而不是 MCP」的科研样板**：把我们 `skills/` 里科研类工作流写成可执行 skill 的先例，含任务编排与校验。LGPL 兼容，读它的 skill 粒度划分即可 |
| `aligfellow/xyzrender` | 621★ | MIT | 分子可视化 | 出版级分子图：从 XYZ、mol、SDF、MOL2、PDB、SMILES、CIF、cube 及量化输入输出直接出 SVG/PNG/PDF/动图，CLI 与 Python 双入口 | 🆕 **论文配图的现成工具**。3Dmol.js 是网页交互，它是「静态出版级」——直接进论文图；537MB 大头是示例资产，读码走 API 即可 |

## ④ 记忆 / 知识图谱

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `codejunkie99/graph-engineering` | 543★ | MIT | KG 方法论 | 「图工程」双半：知识图（实体/事实/带时间的边，本体→抽取→融合→服务）+ 任务图（并行扇出、独立校验、停止规则、人工闸门），脱胎于东南大学 KG 研究生课 | 🆕 不是代码库是**方法论库**（36KB 纯文档），正对两个痛点：记忆该是带 provenance 的图而非流水、多步链该有拓扑而非 prompt 堆砌。与已授粉的 `graph-memory-starter`（轻量三表 KG）互补：那个给实现，这个给纪律 |

## ⑤ 桌面 / 前端（lumo 侧）

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `deeplethe/solid-glass` | 2049★ | MIT | 设计系统 | 为 AI 应用而做的设计系统：Material、物理、触感语义（10-12 建仓，一周破 2,000 星） | 🆕 **lumo 前端换皮可直接抄的词汇表**。卖点不是好看，是把「物理材质语义」写成 token——前端现在靠零散 CSS，缺这套统一语汇。极新（7 天），需评估 API 稳定性 |
| `Glass-HQ/liquid-glass` | 437★ | MIT | 组件库 | React、Web、Electron 的液态玻璃材质与控件，支持明暗外观、实时折射背景内容 | 若 lumo 走 Electron 或 Web，这是现成的高质感层（`npm i @glass-sdk/liquid-glass`）。⚠️ 版本 0.0.2，早期 |

## ⑥ MCP 工具 / 契约

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `openai/mcp-extensions` | 1084★ | Apache-2.0 | MCP 契约 | OpenAI 给 MCP 加的一层 ChatGPT 专属扩展：侧边栏入口、原生级 UI 插件等（9-29 新建） | 🆕 与 10-18 的 `hermes-official-plugins` 对照读：**MCP 正在长出「UI 契约」**（不只是 tool 调用）。NEKO 想把面板做成 agent 可驱动的原生组件，这份 spec 是最接近的先例 |
| `Tencent/wave-mcp` | 242★ | Apache-2.0 | MCP（EDA） | 腾讯蓬莱实验室的 RTL 波形调试 MCP：读 FST 波形 + 网表，提供层次探索、信号查询、驱动分析、X 值追踪 | 🆕 **「领域工具包降维成 MCP」的范本**：把需要昂贵 license 的专业调试器（Verdi）做成免 license 工具集。授粉点不是波形本身，是它**工具粒度怎么切**（prepare 会话 → 层次 → 信号 → 驱动）——给 IC-705 与 SDR 做 MCP 时照这个骨架 |
| `HexRaysSA/ida-mcp` | 1274★ | MIT | MCP（逆向） | Hex-Rays 官方 IDA MCP Server（GUI 插件 + hcli 安装） | 逆向/固件分析线（IC-705 汉化）的官方入口，替掉一堆社区版。⚠️ 硬依赖 IDA 9.4+ 及 idalib（商业授权）——是**依赖**不是许可问题，标注即可 |

---

## 🔍 许可核实说明（NOASSERTION 处置）

`gh api` 的 `spdx_id` 对以下 3 项返回 NOASSERTION，均已读 LICENSE/README 原文裁决（不采信 badge）：

| 项目 | 裁决 | 依据 |
|---|---|---|
| `Pal-AI-Lab/Coopanion` | AGPL-3.0-or-later ✅ 可融合 | LICENSE 文件 + README「License」节明示 AGPL-3.0-or-later（0.1.10 及以前为 MIT）；Cortico 框架本体 MIT |
| `jamro/tiny-engineer` | 软件 MIT ✅ / 硬件 CERN-OHL-S-2.0 ✅ | README「License」节分段声明，`LICENSING.md` 划范围；商标 Tiny Engineer 名称与 logo 不授权 |
| `Tencent/wave-mcp` | Apache-2.0 ✅ | LICENSE 文件存在，README 中英文均标 Apache-2.0 且明示免商用 license |

> 反例留档：`Nomily-Ai/nomily-app` 的 LICENSE 文件名为「Nomily Small Team License」，README badge 直接写 **Source-available** → 硬排除，与 AGPL 主仓不兼容。

---

## Top 3 推荐

1. **`tsunehimatoi/psd2live`（683★ GPL-3.0+MIT 双段）** — NEKO 的瓶颈一直不在渲染而在**资产**：没有 PSD→可动模型的低成本路径，角色就只能靠现成模型。这个项目把自动绑定 + 骨骼 + 物理 + 导出 Cubism 塞进一个工作区，且 MIT 段可单独复用（IR/导出框架/Rust 运行时）。落地：只引 MIT 半边做离线资产工具链，不把 GPL 主程序并进主仓。
2. **`AyagamiDev/ayagami`（367★ MIT+Apache）** — 它解决的是**法务级依赖**：Cubism SDK 闭源带商用条款，NEKO 越做越深越受制；Ayagami 用 Rust 重写加载/渲染并兼容 Live2D 格式，1.6MB 双宽松许可。这是「摆脱单一供应商」的一步，优先级高于任何语音/UI 亮点。
3. **`breezeblue-ai/breeze-tts`（615★ Apache-2.0）** — 中文伴侣角色的语音短板是「情绪与停顿假」，它把 `[笑]`/`[叹气]` 直接写进文本、双语单模型、许可干净，接入成本一条 provider 即可。

> 次席单独看一眼：**`deeplethe/solid-glass`（2049★ MIT）** 建仓一周破 2,000 星，是 lumo 前端「材质语义 token 化」现成参照；因太新不进 Top3。

## 📦 去重 / 排除记录（禁止当新发现立项）

- **已扫 / 已授粉（本期不重复立项）**：
  - `chiang-yuan/llamp` 100★ BSD-3（LBNL）—— **10-04 日报已授粉、10-12 复扫确认**，材料多模态 RAG，只做上游同步
  - `tigerless-labs/agent-memory` 4237★ MIT（WO-240 已扫）
  - `memvid/memvid` 16603★ Apache-2.0（09-02 扫货已录）
  - `K-Dense-AI/scientific-agent-skills` 52657★ MIT（09-02 已扫，科研 skill 库）
  - `xzf-thu/VoiceMem` 2579★ Apache-2.0（09-30 日报）
  - `QwenAudio/qwen-audio-agent` 2939★ Apache-2.0（10-08 日报）
  - `Glitch-Cat-Club/graph-memory-starter` 245★ MIT（**已授粉**：`docs/授粉-graph-memory-starter-轻量KG记忆-落地报告-2026-09-20.md`）
  - `okf-memory/okf-agent-memory` 823★ MIT（09-23 调研已录）
  - `lnkiai/m3e-canvas` 9482★ MIT（09-07 全社区扫货已录）
- **暂缓（无 LICENSE 文件，默认保留所有权利）**：
  - `VictorTaelin/OptMem` 2208★ 无 LICENSE —— 概念（426-token 提示 + 脚本做「永久记忆」）值得读，但不拉包
  - `kevinzhow/Rungic` 415★ 无 LICENSE —— 「手机即 AgentOS」与 `phone-mobile-hub` 撞题，先记着
- **硬排除**：
  - `Nomily-Ai/nomily-app` 797★ **Source-available**（LICENSE 明写 Small Team License）——伪开源，按专有处理
  - `jaredrhod/fullstack-agent` 1119★ AGPL 但仓库是 **Claude Code 专属安装向导（68KB Batchfile）**，无可复用代码，仅作架构故事读
- **已存在等效实现（⚡ 重叠）**：
  - `mrpulor-gh/nuphus-mcp`（MIT）—— Rust 桌面自动化 MCP，与 10-18 已入表的 Linux 桌面控制 MCP 同层，暂不重复评估
- **备选（贴手但未入前 15）**：
  - `FireRedTeam/FireRedTTS3` 1777★ Apache-2.0（统一生成+编辑，但以推理代码为主，权重需核实）
  - `NVIDIA/nvalchemi-toolkit` 192★ Apache-2.0（ALCHEMI 原子势训练工具包）—— **已授粉**：`docs/超限战轮23-化学信息学弹药-授粉报告-2026-09-23.md`，只做上游同步
  - `xav1c34/ChemoSuite` 22★ MIT（污泥木质素 FT-ICR MS 化学计量平台，刚建仓 10-02）

## 守卫结论

**FAIL=0 / WARN=17**（`anti_hallucination_guard.py --check-report --detect-upstream`）：本地已引用 10 项全部在「去重/排除」区标注为已扫或已授粉（含 `nvalchemi-toolkit` 已授粉）；NOASSERTION 3 项已读 LICENSE 原文裁决并单列说明；无 LICENSE 2 项按铁条件暂缓；首轮 FAIL 项（许可连写被误判成仓库名、Windows 版本号被当成仓库、以及一处星数放大）已全部改写修正后归零。星数全部为 `gh api` 当前实测值。
