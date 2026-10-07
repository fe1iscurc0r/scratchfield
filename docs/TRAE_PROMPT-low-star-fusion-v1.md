# TRAE 低星项目融合工单 · v1

> 施工方：Trae｜审查：沈遥（Hermes）
> 日期：2026-08-16
> 定位：把 17 个「未受 AI 红利的低星优质项目」按五层分类融合进 scratchpad（NEKO 身体 + 陆墨大脑 + MCP 工具体系）。
> 前置：先读 `docs/SPEC-Writing-Standard-v1.md`（SPEC 规范）——你产出的每份融合 SPEC 都要按它卡。

---

## 一、背景（自包含，不共享上下文）

scratchpad 定位：**NEKO（Live2D 桌宠身体）+ 陆墨（材料科研大脑）+ MCP 工具体系 + 记忆/RAG**。三元融合：Hermes 决策 / NagaAgent 执行 / N.E.K.O. 交互。

这批低星项目是「冷门低星扫货」的成果——星数低但许可友好、结构精巧，是被 AI 流量盖住但没吃到红利的角落。融合它们 = 补上语音、VAD、TTS、桌宠框架这几块的能力拼图。

## 二、融合五层分类（先搞清每层是什么）

| 层 | 接入方式 | 标志 |
|----|---------|------|
| **MCP** | manifest.json + Python class → `mcpserver/` | 无 UI、单一功能 |
| **Skill** | .md 工作流 → `skills/` | Hermes 执行的工作流 |
| **融合参考** | 不直接接入，产出「授粉分析报告」 | 有架构但非即插即用 |
| **耦合** | 完整源码进 scratchpad | 自有前端 + 生命周期 |
| **基础设施** | 独立部署 | broker / 数据库 / 服务 |

## 三、17 个项目清单（按优先级排序）

### P0 — 直接耦合（最高价值）

| 项目 | ⭐ | 许可 | 语言 | 融合方式 |
|------|-----|------|------|---------|
| **seanyang1983/omnilimb-face** | 6 | AGPL-3.0 | Python | **耦合**：hermes-agent 的 VTuber 插件（Live2D/Live3D），与主仓同许可，直接吞 |

### P1 — MCP 封装 + 关键参考（高价值）

| 项目 | ⭐ | 许可 | 语言 | 融合方式 |
|------|-----|------|------|---------|
| **babutree/TTS-API** | 37 | MIT | Python | **MCP**：自托管流式 TTS 网关 → 封装为 tts MCP server |
| **garan0613/voice-mcp** | 33 | MIT | TS | **MCP**：AI 语音合成 MCP server，直接接入 |
| **shreyaskarnik/voice-mcp** | 16 | Apache-2.0 | Python | **MCP**：Claude Code 双向语音 MCP，直接接入 |
| **xucailiang/cascade** | 84 | MIT | Python | **融合参考**：生产级 VAD，授粉到语音层 |

### P2 — 授粉参考（中价值）

| 项目 | ⭐ | 许可 | 语言 | 融合方式 |
|------|-----|------|------|---------|
| **thooton/aspen** | 18 | CC0 | Python | **融合参考**：语音打断逻辑（最小可读版），授粉 |
| **qiyueblues-design/zhuomianling** | 17 | MIT | TS | **融合参考**：Live2D 桌宠框架，参考架构 |
| **soniqo/speech-core** | 68 | Apache-2.0 | C++ | **融合参考**：端侧 VAD/STT/TTS/diarization，参考 |
| **meet447/Meuxe** | 72 | MIT | TS | **融合参考**：自托管 AI 伴侣 web app（Live2D），参考 |

### P3 — 观望 + 备选（低价值，先记着）

| 项目 | ⭐ | 许可 | 语言 | 融合方式 |
|------|-----|------|------|---------|
| **AreevAI/flowcat** | 97 | Apache-2.0 | Rust | **基础设施**：实时语音 agent runtime |
| **stimm-ai/stimm** | 52 | AGPL-3.0 | Python | **融合参考**：语音 agent 平台 |
| **ddxfish/sapphire** | 281 | AGPL-3.0 | Python | **融合参考**：回家型 AI 伴侣产品形态 |
| **khromalabs/ainara** | 34 | LGPL-3.0 | Python | **融合参考**：本地 AI 伙伴框架 |
| **second-state/silero_vad_server** | 17 | GPL-3.0 | Rust | **基础设施**：VAD 即服务 |
| **cyijun/hachimi** | 4 | MIT | Python | **融合参考**：模块化多进程语音助手 |
| **dwgx/Live2DPet-Enhanced** | 2 | MIT | JS | **融合参考**：Live2D 桌宠记忆系统 |
| **marine841023/duty-on** | 3 | MIT | Rust | **融合参考**：Tauri 2 桌宠 |

## 四、硬约束（铁律，不可违反）

1. **许可铁律**：主仓 AGPL v3。MIT/BSD/Apache-2.0/CC0 → 直接吞；AGPL/GPL → 同许可直接吞；LGPL → 可吞但标注。**无 LICENSE → 一律暂缓**（不拉）。
2. **先读 SPEC 规范再动手**：每份融合 SPEC 按 `docs/SPEC-Writing-Standard-v1.md` 十条卡。
3. **不碰主流程**：融合走旁路（独立 adapter / 独立目录），不改 NEKO 源码（`NEKO/N.E.K.O/`）和陆墨核心（`apiserver/` 主链路）。
4. **自包含**：每份 SPEC 的代码骨架可直接粘贴运行，引用到文件 + 行号。
5. **路径用 `$PKG_DIR`**：源码包路径用变量，不硬编码绝对路径（你跑在另一台机器）。

## 五、施工步骤（按优先级顺序执行）

### 第一批：P0 + P1（5 项，本周）

1. **omnilimb-face**（耦合）：clone → 分析 plugin 结构 → 写「耦合接入 SPEC」（它本身就是 hermes 插件，重点看 plugin 契约能否直接复用）
2. **TTS-API**（MCP）：clone → 读 REST 接口 → 写「MCP 封装 SPEC」（manifest + handler）
3. **voice-mcp × 2**（MCP）：clone → 读现有 MCP 实现 → 写「接入评估 SPEC」（能否直接用 or 需改造）
4. **cascade**（融合参考）：clone → 读 VAD 逻辑 → 写「授粉分析报告」（核心数据结构 → 语音层映射）

### 第二批：P2（4 项，下周）

5. **aspen**：语音打断逻辑授粉（2KB 仓库，重点读 interrupt 实现）
6. **zhuomianling**：Live2D 框架参考（框架=可扩展，不是成品）
7. **speech-core**：端侧语音管线参考（C++，只读不改造）
8. **Meuxe**：自托管伴侣 web 参考（注意 998KB 体积，可能有打包垃圾）

### 第三批：P3（8 项，观望）

先拉源码归档，不急着融合。每项只做「可行性标注」（能否用 + 运行依赖 + 接入成本），不写完整 SPEC。

## 六、产出物规范

每项融合产出，按五层分类落盘：

| 层 | 产出 | 位置 |
|----|------|------|
| MCP | `mcpserver/<name>/`（manifest + handler） | 主仓 mcpserver/ |
| 耦合 | `coupled/<name>/`（完整源码） | 主仓 coupled/ |
| 融合参考 | `<name>-授粉报告.md` | `docs/` |
| 基础设施 | 部署说明 + 源码归档 | `github_haul/infra/` |

## 七、提交规范

```
feat(mcp): <name> MCP 封装
feat(coupled): <name> 耦合接入
docs: <name> 授粉分析报告
```

每项单独 commit，不攒批。许可有疑问的项目，先 `gh api repos/X/Y/license` 确认再拉。

## 八、验收标准（可量化）

1. 每个 MCP 产出：`python -m pytest mcpserver/<name>/` 跑通
2. 每份授粉报告：含「源领域 → 目标域」映射 + 核心数据结构共鸣 + 难度×收益
3. 许可：`grep -rn "license" mcpserver/<name>/manifest.json` 返回非空
4. 不碰主流程：`git diff --stat` 无 `NEKO/N.E.K.O/` 和 `apiserver/` 主链路改动
