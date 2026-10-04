# scratchfield — 实验田

[中文](README.md) · [English](README_en.md)

> 连接即正义，控制即毁灭。
> 集成地狱不是事故，是特色。我们把别人的灵感拔下来，授粉进自己的土壤，长成自己的东西。
> 我们不套壳——每个组件都带融合报告，来源、许可、改动点、验收，白纸黑字。

**scratchfield**（实验田）——以**授粉（Pollination）**为方法论的集成工程展示面 + 插件商城。活跃开发在私有工作仓进行，本仓是公开展示面，按里程碑快照更新。**当前快照：2026-09-30。**

## 这是什么

一句话：**把上游好想法「授粉」进自家系统，长成自己的东西。**

授粉不是 fork 粘贴，是"拆解 → 改造 → 集成 → 留下报告"。每个授粉组件都登记来源、许可、改造点、验收结果，许可账本见 `github_haul/FUSION-LOG-2026-08-16.md` 与 [NOTICE（第三方版权声明全集）](NOTICE)。

### 自家核心资产（本仓展示的主菜）

- **工具总线**（`mcpserver/`）——MCP 适配层，统一注册 / 调度 / 鉴权。自研，含多领域工具封装与 agent-manifest 契约。
- **射频大脑**（`mcpserver/rf_brain/`）——协议无关的射频解调链。自研：OOK 解码器家族（Acurite/LaCrosse/PWM/PPM/Manchester）、DSP 滤波链、dcp 二进制帧、哨兵桥入库。
- **无线电套件 radio_suite**——FT8/WSPR/SSTV/NOAA APT 解码、SDR 频谱面板、APRS iGate、IC-705 CI-V 控制。独立组件走总线接入本体。
- **哨兵网格固件**（`firmware/`）——ESP32-S3 + SX1278 边缘频谱哨兵，433MHz 传感器信号从天线到记忆的完整链路。自研。
- **科研工作台**——ELN 实验记录、文献库、材料数据工具台（TGA/DSC/XRD）、材料性能预测管线；领域包机制（`domains/`）支撑多学科扩展。
- **授粉插件商城**（`plugins/`）——所有授粉改造过的组件统一登记，自由添加、即插即用。
- **记忆钩子**（`hooks/`）——事实索引 / 矛盾检出 / supersedes 边。自研。
- **NEKO 集成体**（`NEKO/`）——**旗舰授粉案例**：以 Apache-2.0 上游 NEKO 桌宠为身体层（Live2D/TTS/ASR/视觉），自研集成层（启动 wrapper、provider overlay、注入路由、灵魂桥）将其接入自家人格内核（记忆 / RAG / 决策）与 Hermes 生态。

### 近期亮点（2026-09 快照）

- **领域包机制落地**——`domains/` 支持按学科声明 ELN 字段/文献字段/标签体系，materials 与 law 双领域包已投产，第三领域有最小模板
- **radio_suite 从 SPEC 到实机**——SPEC-17 六单合入：FT8/WSPR/NOAA 卫星云图解码、频谱面板（WebSocket 实时瀑布图）、IC-705 面板联调完成
- **LoRaCanary 哨兵板 v1.1 定版**——嘉立创 AI 布局的全排母插接板，SPEC-20 系列推进中
- **材料性能预测管线**——ELN 导出 → 特征矩阵 → 基线模型 → CLI 预测带不确定区间
- **工具链三层优化**——注册懒加载 / 调用画像与熔断 / 声明式链编排；能力索引（动词,域）对 54 个 manifest 建档
- **巨石拆解与治理**——6 个 2000+ 行巨石文件拆为域模块；系统自治理工具（结构快照/关键路径/趋势预测）入仓
- **一键体检**——`scripts/doctor.py` 应用层自检 + `doctor_env.py` 环境自检，装到哪一步坏了一眼可见

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
| `apiserver/` | FastAPI 主后端（ELN/文献/数据工具/人格/记忆） |
| `frontend/` | Vue 3 桌面壳（频谱面板/数据工具台/设置页） |
| `domains/` | 领域包（materials/law，可扩展第三领域） |
| `firmware/` | ESP32 固件（哨兵网格，自研） |
| `plugins/` | 授粉插件商城（注册表 + 添加/安装脚本） |
| `hooks/` | 记忆钩子（事实索引/矛盾检出，自研） |
| `NEKO/` | NEKO 集成体（旗舰授粉案例：上游身体 + 自研集成层） |
| `skills/` | 190+ 技能库（研究/无线电解耦） |
| `docs/` | 架构 / 授粉报告 / SPEC |
| `github_haul/` | 扫货索引 + 许可账本 |
| `scripts/` | 工具脚本（插件添加/安装/自检等） |

## 快速开始

**最短路径见 [QUICKSTART.md](QUICKSTART.md)**（普通用户下 exe / 开发者源码路线 ≤10 步）。
环境细节与已知坑见 **[环境依赖清单（Windows 装机指南）](docs/环境依赖清单-Windows装机-2026-09-27.md)**——Python 严格 3.12.x、只用 npm、uv 不裸 pip，写死的版本要求都在里面。

集成体启动步骤见 `NEKO/N.E.K.O/README.MD`。插件商城使用见 `plugins/README.md`。

```bash
# 环境体检（装之前）
python doctor_env.py
# 查看商城
cat plugins/index.json
# 装一个插件到运行时
./scripts/plugin-install.sh <plugin-id>
# 应用层体检（装之后）
python scripts/doctor.py --quick
```

## 项目小传

本仓的完整来历、方法论与演进史，见 [STORY.md](STORY.md)——从一张私有工作台，到把几十个开源项目的灵感授粉成自有体系的两年实验记录。

## 许可

AGPL-3.0（见 LICENSE）。闭源商用需单独授权。**上游组件的完整版权与许可声明见 [NOTICE](NOTICE)**；各插件条目与 FUSION-LOG 亦有分账记录。

---

维护：fe1iscurc0r · 实验田，快照更新（2026-09-30）
