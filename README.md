# scratchfield — 实验田

> 连接即正义，控制即毁灭。
> 集成地狱不是事故，是特色。我们把别人的灵感拔下来，授粉进自己的土壤，长成自己的东西。

**scratchfield**（实验田）——以 **NEKO 集成体**为核心、以**授粉（Pollination）**为方法论的实验仓库。活跃开发在私有工作仓进行，本仓是公开展示面 + 插件商城，按里程碑快照更新。

## 这是什么

一句话：**把上游好想法「授粉」进自家系统，长成自己的东西。**

- **NEKO 集成体**（`NEKO/`）——以 NEKO 桌宠框架为身体（Live2D / TTS / ASR / 视觉），融合人格内核（记忆 / RAG / 决策）的完整集成工程。「集成地狱」是我们的勋章。
- **授粉插件商城**（`plugins/`）——所有授粉改造过的组件统一登记，自由添加、即插即用。
- **工具总线**（`mcpserver/`）——MCP 适配层，统一注册 / 调度 / 鉴权。
- **射频大脑**（`mcpserver/rf_brain/`）——协议无关的射频解调链。
- **固件**（`firmware/`）——ESP32-S3 哨兵网格固件。

## 授粉是什么

授粉 = 上游灵感 → 拆解 → 改造 → 集成。不是 fork 粘贴，而是把「能长进我们系统的那部分」移植进来，留下完整的授粉报告（来源 / 许可 / 改造点 / 验收）。许可账本见 `github_haul/FUSION-LOG-2026-08-16.md`。

## 目录

| 路径 | 内容 |
|------|------|
| `NEKO/` | NEKO 集成体（完整代码 + 模型资产） |
| `plugins/` | 授粉插件商城（注册表 + 添加/安装脚本） |
| `mcpserver/` | MCP 工具总线（含 rf_brain 射频大脑） |
| `coupled/` | 耦合集成（omnilimb-face 等） |
| `firmware/` | ESP32 固件（哨兵网格） |
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
