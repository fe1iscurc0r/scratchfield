# SPEC-13 · 三链路授粉落地（dcp 帧 / 语音管线 / 工具注册）—— 第八批工单总纲

> 源：POLLINATION-2026-08-24-round5.md（授粉流水线·超限战轮）三链路收敛
> 链路1：aci App/Function 模式 → Lumo 材料工具注册中心
> 链路2：achatbot Pipeline → NEKO 语音层配置化
> 链路3：dcp sub-50B 帧 → rf_brain Phase5 LoRa ESP32↔云服通讯
> 分工铁律：Trae 走 GitHub 写码（agent-p / agent-r / agent-s 分支）；沈遥出 SPEC + review；用户定方向测试
> 前置：第七批 N/O/Q 线已合入 main（M 线 OSINT 采集器同步完成）；三条链路均为纯软件，零新增采购

---

## 施工范围矩阵（防重复）

| 智能体 | 领域 | 层 | 工单 | 与既有工单边界 |
|--------|------|----|------|----------------|
| P | rf_brain Phase5 LoRa 通讯 | 写码 | P-01~02 | 不碰 A/B/C（sdrtrunk/meshtastic）；不碰 N 线（哨兵 OOK 接收已完）；不碰 K/L/M（威胁情报） |
| R | NEKO 语音层配置化 | 勘察+重构 | R-01~02 | 不碰 NEKO 记忆层（F 线已做）；只动 voice_turn/voice_input 接口 |
| S | Lumo 工具注册中心 | 勘察+写码 | S-01~02 | 不碰 I 线（chembl/scikit_fingerprints/bofire 已封装）；只加统一注册层 |

## 硬约束（全组共用）

1. **上游只读参考，不 copy 代码**：aci（Apache-2.0）/ achatbot（BSD-3-Clause）/ dcp（MIT）按授粉纪律重写，文件头标注来源。
2. **纯软件，许可干净**：三链路来源均 Apache-2.0 / MIT / BSD-3-Clause，无 GPL 传染；若勘察中发现引用组件许可不干净，标注并隔离。
3. **不碰 NEKO 记忆层与 apiserver 主流程**：`git diff --stat -- NEKO/N.E.K.O/main_logic/memory* | wc -l` 必须为 0（R 线只动 voice 相关）。
4. **测试可离线全绿**：网络调用全部可 mock；无真机（ESP32）用 mock 帧验收。
5. **真机验证点明确标注**：LoRa 帧真机联调清单留给用户，云服侧 mock 全绿即算交付。

---

## 智能体 P —— rf_brain Phase5 LoRa 二进制帧（分支 trae/agent-p）

### P-01: dcp sub-50B 帧协议实现（纯 Python）

- **层**: 写码（协议库）
- **目标**: 把 dcp 论文（arXiv 2605.26159）的极简二进制帧设计实现为 rf_brain 的 LoRa 通讯帧协议——每帧 <50B，替代 MQTT-over-TCP 的 ESP32→云服上报通道
- **输入**: POLLINATION-2026-08-24-round5.md §3.3（dcp 带宽边界）+ dcp 论文/实现（只读参考）+ mcpserver/rf_brain/schemas.py + mesh_layer.py（现有 LoRa 相关，读其接口不破坏）
- **动作**:
  1. `mcpserver/rf_brain/dcp/` 目录：`frame.py`（编码/解码：magic + 消息类型 + 序列号 + 载荷 + CRC，全部 <50B）+ `types.py`（消息类型枚举：上报/命令/ACK/心跳）+ `transmit.py`（超时重传 + 去重，纯逻辑可 mock）
  2. 帧格式：magic(2B) + type(1B) + seq(2B) + payload(N) + crc(2B)，载荷区支持温度/湿度/RSSI/电压等字段（对齐 schemas.py）
  3. `tests/test_dcp.py`：≥8 用例——编解码往返 / 帧长断言 <50B / CRC 错帧丢弃 / 重传超时 / 去重 / 消息类型枚举边界 / 载荷字段对齐 schema / mock 传输层
- **验收**: `python -m pytest mcpserver/rf_brain/tests/test_dcp.py -q` 全过；测试内 assert 最大帧长 < 50；`grep -n "crc" mcpserver/rf_brain/dcp/frame.py` 非空
- **硬约束**: 独立实现不 copy dcp 源码；纯 Python 零新重依赖；不碰 sentinel_bridge.py（N 线产物）

### P-02: ESP32 固件侧 LoRa 帧改造（替换 MQTT-over-LoRa 方案文档 + 固件适配骨架）

- **层**: 写码（固件适配）
- **目标**: 哨兵网格固件从「MQTT over TCP」改为「dcp 二进制帧 over LoRa」——本单交付固件侧编解码骨架 + 方案文档，真机联调留用户
- **输入**: P-01 dcp 帧协议 + firmware/（N-03 产物，PlatformIO Arduino）+ SX1278 LoRa 模式（非 OOK，收发切换）
- **动作**:
  1. `firmware/` 新增 `dcp_lora/`：`dcp_frame.h`/`dcp_frame.cpp`（帧编解码 C 实现，与 P-01 Python 版逐字节兼容——同一套帧格式两份实现）
  2. SX1278 LoRa 收发例程：`dcp_lora/sx1278_lora.cpp`（LoRa 模式初始化 + 发帧 + 收帧，SPI 引脚沿用 N-03）
  3. `docs/dcp-lora-方案.md`：帧格式表 + MQTT→dcp 对比（开销/时延/可靠性）+ 真机联调清单（至少 5 步：烧录 → 发 STATUS → 收帧 → 校验 CRC → 云服解帧入库）
  4. C 侧单测（PlatformIO test 或 Arduino 断言宏）：编解码往返 ≥5 用例
- **验收**: `docs/dcp-lora-方案.md` 落盘且含帧格式表 + 真机联调清单；`grep -n "dcp" firmware/dcp_lora/*` 非空；C 编解码测试（可编译或断言宏）通过；无工具链时标注「未编译验证」照 N-03 惯例
- **硬约束**: 帧格式与 P-01 严格一致（同一份格式文档两份实现）；不引入 WiFi（LoRa 专用）；真机点留用户

---

## 智能体 R —— NEKO 语音层配置化（分支 trae/agent-r）

### R-01: achatbot processor 接口勘察报告（文档级）

- **层**: 勘察
- **目标**: 从 ai-bot-pro/achatbot（BSD-3-Clause）的 src/processors/ 提取 VAD/Turn/ASR/LLM/TTS 五段接口契约，为 NEKO 语音模块化提供参照
- **输入**: GitHub ai-bot-pro/achatbot（只读）+ NEKO/N.E.K.O/main_logic/voice_turn、voice_input、voice_identity（现有硬编码链路）+ NEKO/N.E.K.O/docs/design/asr-client-phase1.md、voice-design-architecture.md
- **动作**:
  1. 直拉 achatbot 只读：src/processors/vad/、turn/、asr/、tts/ 的接口定义（类名/方法签名/输入输出/配置项）
  2. 对照 NEKO 现有 voice_turn/voice_input：逐段列出「NEKO 现状 → achatbot 参照 → 差距」，五段每段一行表
  3. 输出 `docs/neko-voice-pipeline-勘察报告.md`：接口契约提取表 + NEKO 差距清单 + 配置化改造建议（JSON pipeline 配置示例，照 round5 §3.2）
- **验收**: 报告落盘；五段（VAD/Turn/ASR/LLM/TTS）每段有接口契约 + NEKO 现状对照；含 pipeline JSON 配置示例
- **硬约束**: 只读勘察不写码；不 copy achatbot 代码（BSD-3 按授粉纪律重写为接口描述）

### R-02: NEKO 语音 Pipeline 配置化重构（写码）

- **层**: 写码（重构）
- **目标**: 把 NEKO 语音链路从「硬编码 VAD→ASR→LLM→TTS」改为「配置驱动可插拔」，换 ASR/TTS 后端只改配置不动代码
- **输入**: R-01 勘察报告 + NEKO/N.E.K.O/main_logic/voice_turn 等现有实现 + NEKO/N.E.K.O/docs/design/voice-design-architecture.md
- **动作**:
  1. 新增 `NEKO/N.E.K.O/main_logic/voice_pipeline/`：`base.py`（VAD/Turn/ASR/LLM/TTS 五个抽象基类，定义 run()/config 契约）+ `registry.py`（后端注册表，按配置名查找）
  2. 现有 Edge TTS 封装为 TTS 后端；现有 ASR（如有）封装为 ASR 后端；缺后端时保留现有直调路径（降级不破坏）
  3. `pipeline_config.json` 默认配置（照 round5 §3.2 示例：silero_vad / energy_threshold / sense_voice / openai / edge_tts）
  4. `tests/test_voice_pipeline.py`：≥6 用例——配置加载 / 注册表查找 / 默认后端实例化 / 换后端 mock（改配置换 mock ASR）/ 降级路径 / 配置非法报错
- **验收**: `python -m pytest NEKO/N.E.K.O/tests/unit/test_voice_pipeline.py -q` 全过（路径以实际为准）；`grep -n "registry" NEKO/N.E.K.O/main_logic/voice_pipeline/*.py` 非空；现有 voice_turn 调用不被破坏（回归）
- **硬约束**: 不碰 NEKO 记忆层；不引新重依赖（silero-vad 等如未装走降级）；改动最小化，优先加抽象不删旧路径

---

## 智能体 S —— Lumo 工具注册中心（分支 trae/agent-s）

### S-01: aci-mcp tool registry 勘察报告（文档级）

- **层**: 勘察
- **目标**: 从 aci-mcp server（253★ MIT）的 src/tools/ 提取 tool registry 注册+发现模式，为 Lumo 材料工具统一注册层提供参照
- **输入**: GitHub aci-mcp（只读）+ mcpserver/ 现有 agent-manifest.json 模式（已读 chembl/scikit_fingerprints/bofire 三份）+ POLLINATION-2026-08-24-round5.md §3.1（App/Function 二元定义）
- **动作**:
  1. 直拉 aci-mcp 只读：src/tools/ 的注册表结构（工具如何登记/发现/校验参数/鉴权）
  2. 对照 mcpserver 现有 agent-manifest.json：列出「现有一致点 / 差距 / aci 可借鉴点」三列
  3. 输出 `docs/aci-tool-registry-勘察报告.md`：registry 结构图 + mcpserver 差距清单 + 统一 meta.yaml 建议（照 aci app.json/function.json 拆两层）
- **验收**: 报告落盘；含 registry 注册/发现流程说明 + mcpserver 差距表 + meta.yaml 建议样例
- **硬约束**: 只读勘察不写码；不 copy aci-mcp 代码（MIT 按授粉纪律重写为结构描述）

### S-02: Lumo 材料工具统一 meta.yaml 落地（写码）

- **层**: 写码（注册层）
- **目标**: 给 Lumo 材料实验工具（BoFire / pycalphad / smiles-transformer 等）写统一 meta.yaml（aci 两层结构：app 元数据 + function 调用接口），实现「工具即资源」统一注册
- **输入**: S-01 勘察报告 + mcpserver/bofire/（I 线已封装）+ mcpserver/academic/（MODEL_INTERFACE 扩展）+ docs/academic/ 授粉报告（pycalphad/smiles 调研）
- **动作**:
  1. `mcpserver/tool_registry/`：`meta.py`（meta.yaml 加载/校验/索引，照 aci app.json + function.json 两层）+ `schemas/`（统一 meta.yaml JSON Schema）
  2. 为 BoFire / pycalphad / smiles-transformer 各写一个 `meta.yaml`（照 round5 §3.1 示例：app 层 name/display_name/security_schemes/categories；function 层 name/description/parameters）——已封装的 bofire 直接从真实接口提取
  3. `registry.py`：扫描 mcpserver/*/agent-manifest.json 转统一 meta（兼容旧格式，增量不破坏）
  4. `tests/test_tool_registry.py`：≥6 用例——meta.yaml 校验 / 索引构建 / 三库发现 / 旧 manifest 兼容转换 / 非法 meta 报错 / 参数 schema 校验
- **验收**: `python -m pytest mcpserver/tool_registry/tests/ -q` 全过；`ls mcpserver/tool_registry/*.yaml` ≥3 个 meta；`grep -n "function" mcpserver/tool_registry/meta.py` 非空；现有 mcpserver 测试无回归
- **硬约束**: 不碰 I 线已封装的 bofire/chembl/scikit_fingerprints 内部实现（只读其 manifest）；不碰 NEKO/apiserver 主流程；meta.yaml 用 YAML 标准格式

---

## 通用约束（三份提示词都带）

- 分项 commit: P 线 `feat(dcp):` 前缀；R 线 `feat(voice):` / `docs(voice):` 前缀；S 线 `feat(registry):` / `docs(registry):` 前缀
- 全部中文输出，完成一个报一个（路径 + 验收结果）
- 阻塞（缺数据/许可/硬件）不硬做，写清原因返回
- 成果推 trae/agent-p | trae/agent-r | trae/agent-s 分支
- 真机验证点统一列在 P-02 末尾，用户按清单实测

**启动口令**：用户说「开始执行第八批工单」→ P/R/S 组并行推进；「只跑 P-xx」→ 单跑。

*—— 沈遥 · 三链路同台：帧格式 / 语音管线 / 工具注册，全是可当天验证的轻量件 ✨*
