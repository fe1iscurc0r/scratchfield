# GitHub 扫货日报 2026-10-20

**口径**：Discovery-Only（不 clone / 不 pull）。扫描 6 大维度 × 多组时间限定查询（`created:>2026-07-01` / `>2026-09-01` + `stars:>N`），逐个 `gh api repos/{r}` 核实星数/许可/archived/最近 push，并已排除 10-13～10-19 历次日报已报项目（`ripwire`/`ida-mcp`/`x64dbg-mcp-server`/`invisible_playwright_mcp`/`reverify`/`nvalchemi-toolkit`/`ayagami`/`psd2live`/`qwen-audio-agent`/`graph-memory`/`graph-memory-starter`/`okf-agent-memory`/`codebase-memory-mcp` 等，不再重复推荐）。

---

## 一、MCP / 工具层

| 项目 | ⭐ | 许可 | 分类 | 一句话说明 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| TheSmokeDev/hermes-talk | 75★ | MIT | MCP/插件 | Hermes Agent 的实时双工语音插件：终端 `hermes talk` / Discord 语音频道 / dashboard Talk 标签，调用宿主自己的工具，后台委派后语音回播 | **我们自己运行时的插件**，`hermes plugins install TheSmokeDev/hermes-talk --enable` 一条命令。可借鉴点：barge-in 打断、后台任务落地后主动播报——正是 QQ 语音通道缺的那半环 |
| LiCinCan/blender-ai-mcp-addon | 930★ | MIT | MCP | Blender 的 MCP server + 视觉聊天/场景操作工具/多 agent 协作（10-15 建，5 天 930★） | 3D 桌宠资产与硬件外壳建模可脚本化；「视觉截图→场景工具调用」闭环值得抄给 Lumo 可视化工具层 |
| cranebeaker/coop-anything | 591★ | MIT | 授粉-跨域 | 把 AI agent 指向任意单人游戏，与真人同屏协作操作（10-16 建） | 跨域授粉点：低延迟「感知→动作回环 + 人机共享控制权」范式，可映射到 IC-705/设备实时控制（谁在操作、超时接管的状态机） |
| tangency-labs/solidcraft | 7301★ | Apache-2.0 | 融合参考 | 纯 Rust 写的开源参数化 3D CAD（10-07 建，13 天内冲到七千以上） | 硬件项目（天线支架/外壳/FPC 载板）参数化建模的工程参考，属「工程底座」而非 AI 层 |

## 二、AI 伴侣 / Live2D 桌宠（NEKO 线核心）

| 项目 | ⭐ | 许可 | 分类 | 一句话说明 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| momori777/Artemis | 398★ | Apache-2.0 | 耦合候选 | 100% 本地 AI 女友后宫：OpenClaw + QQ 与 Telegram 双通道 + llama.cpp + GPT-SoVITS + ComfyUI + Sakura 桌宠 + Live2D，**每个角色记忆隔离**，8G 显存级别 | **本轮同构度最高**：QQ 通道 + 桌宠 + 语音 + 出图 + 多角色隔离记忆，几乎就是 NEKO 的另一种拼法。注意：API 报 NOASSERTION，实读 LICENSE 原文确认 **Apache-2.0**（可融合）；主线脚本面向 Windows 加 NVIDIA 显卡 → 只取架构（角色卡热插拔、隔离记忆、桌宠桥接），不整套搬 |
| shinshin86/mesh-avatar-studio | 857★ | MIT | 融合参考 | 单张插画 → 会眨眼/说话/转头/呼吸/摆发的 2D mesh 头像，本地编辑器 + 实时预览，浏览器 Player 用自己摄像头驱动（10-04 建） | **Live2D 免授权替代路线**：纯 Node 加 Web，无 Cubism SDK 束缚，可直接嵌进 Lumo 前端做角色层；「一张图 + 网格绑定点」比 PSD 分层流程轻得多 |
| wangxijie001/yoji | 666★ | MIT | 融合参考 | Electron 桌面伴侣：真权限操作文件/跑脚本/联网、情绪与人格演化、MCP 无限扩展，**AI 可自行搜索并安装 MCP**，工坊建子 Agent 隔离工具噪声 | 扩展模型值钱：①MCP 自装（AI 自己找工具自己测）②子 Agent 隔离工具集防对话质量下降 ③人格写进 Skills 的自然语言路径。三样都能搬进 Lumo 的 agent 编排 |
| pinganbbOvO/ai-companion-kit | 186★ | MIT | 授粉 | 「给 AI 一副身体」：QQ 陪聊 + 控制安卓手机的 MCP + 会记事/看场合的上下文策略（10-08 建） | 与 phone-mobile-hub 线正面对撞：QQ 侧人格记忆 + 手机当执行端。手机作为 agent 执行器的权限边界设计值得抄 |
| HELPMEEADICE/BANDORI-PET-REV | 485★ | GPL-3.0 | 仅参考设计 | Live2D + PySide6 桌面宠物，50+ BanG Dream 角色、30+ 动作/表情预设 | 动作·表情状态机的资源组织方式（角色包如何切场景/待机/互动）；GPL-3.0 按 2026-10-12 口径可融合，但优先级低于 MIT 项，先当设计参考 |

## 三、记忆 / RAG

| 项目 | ⭐ | 许可 | 分类 | 一句话说明 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| aru-labs/lossless-memory | 144★ | MIT | 融合参考 | 无损长期记忆：JSONL 全量原始日志 + SQLite（FTS5 精确 + sqlite-vec 语义），**时间轴优先检索**（"昨晚那个预算"合法），每轮注入 LLL「当前位置」索引防压缩后失忆 | 与我们「摘要式压缩记忆」针锋相对的另一极，作者单人日用 3 个月。可旁路落地：时间轴检索 + LLL 锚点注入，补 context 压缩后的身份漂移 |
| SodaMem/SodaMem | 225★ | Apache-2.0 | 融合参考 | Agentic memory infra：把记忆读写当 agent 任务编排（08-07 建） | 与「检索层」路线不同，是策略层——决定何时写/何时归档/何时忘；可与现有 memory 工具做对照实验 |

## 四、材料 / 科研（陆墨线）

| 项目 | ⭐ | 许可 | 分类 | 一句话说明 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| DingyangLyu/MatClaw | 98★ | Apache-2.0 | 融合参考 | 自然语言描述材料问题 → 自己写代码 → 跑 Quantum ESPRESSO 7.5 → 出结果（Docker/Node20/Py3.11） | 与陆墨「材料科研 + 计算」直接对接：NL→DFT 工作流的 agent 编排（输入结构、收敛判据、失败重试）是现成范式 |

## 五、语音（TTS/ASR）

| 项目 | ⭐ | 许可 | 分类 | 一句话说明 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| oboroge0/hayamimi | 448★ | MIT | 融合参考 | CPU-only 实时多语 STT：**按语种路由到最合适的专用模型**（INT8 ONNX / sherpa-onnx，无 PyTorch 无 CUDA），<2GB RAM，停口约 100ms 出终稿 | 云服无 GPU 也能上语音输入；「按语种路由 specialist」思路可套到频谱/信号分类（按信噪比分派检测器） |
| fermionresearch/phonon | 258★ | Apache-2.0 | 融合参考 | 开源语音识别模型（Phonon-2 / Phonon-1）+ CLI，CPU 可跑（08-28 建） | 与 hayamimi 做 benchmark 对照的第二个本地 ASR 选项，许可最干净 |

## 六、桌面 Agent

| 项目 | ⭐ | 许可 | 分类 | 一句话说明 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| Zafer-Liu/Vibe_Assistant | 170★ | Apache-2.0 | 融合参考 | Rust 跨平台桌面应用，专门管理多个 AI Agent 与 MCP Server（06-05 建，10-09 更新） | Lumo 桌面的「MCP/Agent 管理器」交互参考：多服务器启停、健康状态、配置分发 |

---

## 已排除 / 暂缓（诚实记账）

| 项目 | 原因 |
|---|---|
| cqzaaa/AgentPet 261★ | 无 LICENSE 文件 → 暂缓（Electron+Live2D 桌宠，架构对味，可发 issue 问许可） |
| Cosmekaili-creator/Hermes-Voice 19★ | LICENSE 实为 PolyForm Noncommercial 1.0 → 禁入 AGPL 主仓，走 NC 分仓路线 |
| jaechang-hits/SciAgent-Skills 381★ | LICENSE 实为 CC BY 4.0（非软件许可）→ 仅参考技能清单，不并入源码 |
| jub0t/Concat 9486★ | AGPL-3.0 剪映替代品，与主仓能力无关（能吞但没必要） |
| t8y2/dbx 27245★ | 数据库客户端，与本期六维度不匹配 |

## Top 3 推荐

1. **TheSmokeDev/hermes-talk（75★ MIT）** —— 唯一「装上就用」项：`hermes plugins install` 即给运行时加实时双工语音，作者带 CI/CodeQL/OpenSSF scorecard。验证成本 10 分钟，比自研语音面低两个数量级；即使不装，它的「打断 + 后台委派 + 落地播报」三段式状态机也值得抄。
2. **momori777/Artemis（398★ Apache-2.0）** —— 与 NEKO 同构度最高（QQ+Telegram 双通道 / Live2D 桌宠 / GPT-SoVITS / ComfyUI / 多角色隔离记忆），等于别人把我们的拼图另一种拼法跑通了。Windows+NVIDIA 主线不能直接搬进云服，但「每角色隔离记忆 + 角色卡热插拔 + Sakura 桌宠桥」是纯架构资产，许可实测 Apache-2.0（API 误标 NOASSERTION）。
3. **aru-labs/lossless-memory（144★ MIT）** —— 记忆层另一极，且是「一个人一台机日用三个月」的实战实现：全量 JSONL + FTS5/sqlite-vec + 时间轴检索 + LLL 当前位置注入。我们的记忆是摘要式，LLL 这种「每轮告诉模型你在哪个话题」的小索引，是对抗 context 压缩失忆的最低成本补丁。

---

**许可备注（本轮实测纠错）**：`momori777/Artemis` 与 `oboroge0/hayamimi` 的 API `spdx_id` 均返回 `NOASSERTION`，实读 LICENSE 原文分别是 **Apache-2.0** 与 **MIT**（可融合，原判「暂缓」作废）；`Cosmekaili-creator/Hermes-Voice` 实为 **PolyForm NC**、`jaechang-hits/SciAgent-Skills` 实为 **CC BY 4.0**（均不得进 AGPL 主仓）。
