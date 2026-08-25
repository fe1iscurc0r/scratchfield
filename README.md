# scratchfield — 实验田

> 连接即正义，控制即毁灭。
> 集成地狱不是事故，是特色。我们把别人的灵感拔下来，授粉进自己的土壤，长成自己的东西。
> 我们不套壳——每个组件都带融合报告，来源、许可、改动点、验收，白纸黑字。

**scratchfield**（实验田）——以**授粉（Pollination）**为方法论的集成工程展示面 + 插件商城。活跃开发在私有工作仓进行，本仓是公开展示面，按里程碑快照更新。

## 这是什么

一句话：**把上游好想法「授粉」进自家系统，长成自己的东西。**

授粉不是 fork 粘贴，是"拆解 → 改造 → 集成 → 留下报告"。每个授粉组件都登记来源、许可、改造点、验收结果，许可账本见 `github_haul/FUSION-LOG-2026-08-16.md`。

### 自家核心资产（本仓展示的主菜）

- **工具总线**（`mcpserver/`）——MCP 适配层，统一注册 / 调度 / 鉴权。自研，含多领域工具封装与 agent-manifest 契约。
- **射频大脑**（`mcpserver/rf_brain/`）——协议无关的射频解调链。自研：OOK 解码器家族（Acurite/LaCrosse/PWM/PPM/Manchester）、DSP 滤波链、dcp 二进制帧、哨兵桥入库。
- **哨兵网格固件**（`firmware/`）——ESP32-S3 + SX1278 边缘频谱哨兵，433MHz 传感器信号从天线到记忆的完整链路。自研。
- **授粉插件商城**（`plugins/`）——所有授粉改造过的组件统一登记，自由添加、即插即用。
- **记忆钩子**（`hooks/`）——事实索引 / 矛盾检出 / supersedes 边。自研。
- **NEKO 集成体**（`NEKO/`）——**旗舰授粉案例**：以 Apache-2.0 上游 NEKO 桌宠为身体层（Live2D/TTS/ASR/视觉），自研集成层（启动 wrapper、provider overlay、注入路由、灵魂桥）将其接入自家人格内核（记忆 / RAG / 决策）与 Hermes 生态。

### 身份声明

- 本仓是**授粉实验田**，不是任何上游的套壳。底层引擎（NagaAgent、NEKO、llama.cpp 等 Apache/MIT 组件）只是技术栈的一部分，列于各组件致谢；自家产出是集成层、工具总线、射频/固件、授粉插件。
- 类比：Chrome 基于 Chromium，Firefox 基于 Gecko——引擎是引擎，品牌是品牌。我们卖的是"把上游消化成自己的"这个能力。
- 每个授粉条目的来源与许可边界见 FUSION-LOG 与各插件条目，法律与道义都讲得清。

## 授粉是什么

授粉 = 上游灵感 → 拆解 → 改造 → 集成。不是 fork 粘贴，而是把「能长进我们系统的那部分」移植进来，留下完整的授粉报告（来源 / 许可 / 改造点 / 验收）。许可账本见 `github_haul/FUSION-LOG-2026-08-16.md`。

## 目录

| 路径 | 内容 |
|------|------|
| `mcpserver/` | 工具总线（自研，含 rf_brain 射频大脑） |
| `firmware/` | ESP32 固件（哨兵网格，自研） |
| `plugins/` | 授粉插件商城（注册表 + 添加/安装脚本） |
| `hooks/` | 记忆钩子（事实索引/矛盾检出，自研） |
| `NEKO/` | NEKO 集成体（旗舰授粉案例：上游身体 + 自研集成层） |
| `coupled/` | 耦合集成（omnilimb-face 等） |
| `docs/` | 架构 / 授粉报告 / SPEC |
| `github_haul/` | 扫货索引 + 许可账本 |
| `scripts/` | 工具脚本（插件添加/安装等） |

## 快速开始

集成体启动步骤见 `NEKO/N.E.K.O/README.MD`。插件商城使用见 `plugins/README.md`。

```bash
# 查看商城
cat plugins/index.json
# 装一个插件到运行时
./scripts/plugin-install.sh <plugin-id>
```

## 许可

AGPL-3.0（见 LICENSE）。闭源商用需单独授权。上游组件的许可见各插件条目与 FUSION-LOG。

---

维护：fe1iscurc0r · 实验田，快照更新
