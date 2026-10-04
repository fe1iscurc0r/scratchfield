# 扫货报告：GitHub Topics（话题角度）— 2026-09-02

> 任务：深挖 GitHub 话题找遗漏项目。前面已扫关键词/各平台，本文件专扫 topic 维度。
> 数据源：`gh api search/repositories` `q=topic:<topic> stars:>100 pushed:>2025-01-01` sort=stars desc
> 已立项/已有（勿重复）：airmoe/rtl433/rtl-ml/radio-modulation/KWS/RS41ng/gr-lora_sdr/lorhammer/meshtastic_sdr/gnss-sdr/satnogs-db/gr-leo/ground-station/rf_brain/spectrum/jepa/esp32_pll/elrs_loracanary/meshpoint/esp32-tinylm/painlessMesh/graphify/neo4j图记忆/OpenKB/GitNexus/latticedb/codebase-memory-mcp/rag-skill/BiliSum/ORKG/agdb/cortex-memory-core/pmcp/adk-agent/orchestration/event_protocol/skill_gate/instincts/eln/darknet-mcp/robin/AutoProber/oh-my-openagent/QwenPaw/worldmonitor/xiaozhi/腾讯记忆/cti-expert/AntiHunter/MITRE-ATT&CK-MCP/granite-biomass/bo_materials/elm/hybrid_search/avogadro/easyeda对照/drawio-skill/Supertonic-TTS/credit/yjs_sync_persist/lumo/授粉管线/mlip/maelle/ESP-IDF 官方库 等
> 与兄弟扫描去重：本表未收录 GitLab 已提（painlessMesh/meshtastic_sdr/satnogs-db/gr-leo/orkg/gnss-sdr/lorhammer/gr-lora_sdr/theseus-cores）、crates 已提（pmcp/adk-agent/desperado/cortex-memory-core/agdb/peat-mesh/rtl-sdr-rs/misp-client/seiza）、npm 已提（sona/lora-packet/mitre-attack-mcp）、技术雷达已提（Graphiti/语义层/SLM 等）的项目。

## 扫描话题清单

sdr ✅ · software-defined-radio ✅ · lora ✅(LoRA-ML 噪声大,已过滤) · mesh-networking ✅ · amateur-radio ✅ · satellite ✅ · rtlsdr ✅ · gnuradio ✅ · esp32 ✅ · edge-ai ✅ · mcp ✅ · knowledge-graph ✅ · threat-intelligence ✅ · materials-informatics ✅ · biomass ❌(0 结果,小众话题无热门仓库)

## 候选总表（12 个，按优先级排序）

| 仓库 | 星数 | 许可 | 语言 | 描述 | 贴栈理由 | 立项建议 |
|------|------|------|------|------|----------|----------|
| ruvnet/RuView | 92,328 | MIT | Rust/TS/C | 用 WiFi 信号做空间感知/生命体征监测/存在检测，ESP32 固件+Web，无需摄像头 | RF 感知栈直接对口（rf_brain/TESLA 侧信道同族）；WiFi CSI 把现有 ESP32 硬件变成传感器阵列 | ⭐⭐⭐⭐⭐ 立项 wifi-csi-sense：ESP32 采集 WiFi CSI → 存在检测/活动感知，接 radio_brain 决策层 |
| jopohl/urh | 12,572 | GPL-3.0 | Python | Universal Radio Hacker：无线协议逆向/信号分析/解调(SIGINT) | SDR 栈缺"协议逆向"环节；与 rtl-ml/radio-modulation 天然衔接 | ⭐⭐⭐⭐⭐ 立项 protocol-reverse：URH 流水线接入信号→比特→协议解析，喂 rtl-ml 标注数据 |
| markqvist/Reticulum | 7,123 | NOASSERTION | Python | 加密 mesh 网络栈：LoRa/数据包电台/WiFi 全通吃的抗毁网络 | meshpoint/esp32-tinylm 自组网方向的"协议层"补强；离网通信核心 | ⭐⭐⭐⭐⭐ 立项 reticulum-mesh：基于 Reticulum 做应急/离网 mesh 通信，LoRa+WiFi 混合链路 |
| BigBodyCobain/Shadowbroker | 11,026 | AGPL-3.0 | Python | 全球态势 OSINT 聚合：ADS-B 航班/侦察卫星/地震/GIS 统一面板，可挂 AI agent 找关联 | worldmonitor/ground-station/OSINT 四线汇合；ADS-B+卫星观测正是现有地面站缺的数据源 | ⭐⭐⭐⭐ 立项 sky-intel-panel：聚合 ADS-B+卫星过境+震情，做态势情报面板并喂授粉情报 |
| topoteretes/cognee | 30,412 | Apache-2.0 | Python | Agent 开源记忆平台：跨会话持久记忆 + 自托管知识图谱引擎 | 记忆栈（neo4j图记忆/codebase-memory-mcp）的"图记忆引擎"成熟替代；补 Graphiti 未覆盖的本地化 | ⭐⭐⭐⭐⭐ 立项 cognee-memory：作为 Agent 跨会话图记忆引擎，对接 event_protocol 事件流 |
| HKUDS/LightRAG | 39,331 | MIT | Python | EMNLP2025 轻量图增强 RAG：简单快速的 GraphRAG 实现 | rag-skill/知识库需要"图增强检索"；比全量 GraphRAG 轻一个量级 | ⭐⭐⭐⭐ 立项 lightrag-graph：给现有 RAG 管线加图索引层，先跑知识库问答基准 |
| Egonex-AI/Understand-Anything | 81,311 | MIT | TypeScript | 任意代码→交互式知识图谱，Claude Code/Codex/Cursor 兼容 | codebase-memory-mcp/graphify 的"代码知识图谱"现成实现，多 agent CLI 兼容 | ⭐⭐⭐⭐ 立项 codegraph-explorer：代码→知识图谱交互工具，喂 codebase-memory 记忆 |
| open-sdr/openwifi | 4,779 | AGPL-3.0 | C/Verilog | 开源 IEEE 802.11 WiFi 基带 FPGA 设计（驱动+软件） | SDR 硬加速/FPGA 方向比 theseus-cores 更成熟；WiFi PHY 数据可采 | ⭐⭐⭐⭐ 立项 wifi-phy-sdr：基于 openwifi 采 WiFi 物理层/CSI，做频谱与感知联合实验 |
| SatDump/SatDump | 2,144 | GPL-3.0 | C++ | 通用卫星信号处理软件：解调+解码多种卫星下行 | ground-station 强相关；补齐 APT/LRPT/NOAA 等实际解码能力 | ⭐⭐⭐⭐ 立项 satdump-pipeline：卫星下行解调流水线，接 RTL-SDR 收 NOAA/Meteor 实景验证 |
| ainfosec/FISSURE | 2,038 | GPL-3.0 | Python | RF 信号情报/逆向工程框架（GNU Radio 集成，支持自动调制识别） | rf_brain/频谱感知强相关；自带信号库+自动化脚本，可当调制识别基座 | ⭐⭐⭐⭐ 立项 fissure-sigint：RF 信号分类/调制识别框架，扩充 rtl-ml 数据集与检测器 |
| smicallef/spiderfoot | 21,683 | MIT | Python | OSINT 自动化：威胁情报+攻击面映射 | CTI/OSINT 栈强相关；与 web2-recon 子域枚举互补 | ⭐⭐⭐ 立项 spiderfoot-osint：资产侦察自动化，纳入攻击面管理流水线 |
| google-ai-edge/LiteRT-LM | 6,350 | Apache-2.0 | C++ | Google 端侧 LLM 推理框架（edge 设备部署 LLM） | esp32-tinylm/QwenPaw 端侧 LLM 方向；生产级推理，可作对比基线 | ⭐⭐⭐ 立项 lite-edge-llm：端侧 LLM 推理评估（vs llama.cpp/cactus），服务移动终端 |

## 备选观察（看过，暂缓/需进一步评估）

- **justcallmekoko/ESP32Marauder** ⭐12,196 — ESP32 无线渗透/嗅探工具箱：嵌入式安全红队补充，与 APK/红队栈同族，但偏向攻击工具，先观察。
- **OpenCTI-Platform/opencti** ⭐9,886 — 威胁情报平台（STIX/KB）：与 cti-expert 强相关，但体系重（多组件），建议先接其 STIX feed 而非整体立项。
- **blacklanternsecurity/bbot** ⭐10,525 AGPL — 递归互联网扫描器：与 web2-recon 重叠，AGPL 许可需评估。
- **mandiant/capa** ⭐6,163 Apache-2.0 — 可执行文件能力识别：红队/恶意样本画像有用，暂缓。
- **memvid/memvid** ⭐16,460 Apache-2.0 Rust — Agent 单文件内存层（替代 RAG）：与记忆栈相关，先对比 cognee 再定。
- **cactus-compute/cactus** ⭐5,971 C++ — 端侧 LLM 推理（手机/穿戴/机器人）：与 LiteRT-LM 二选一评估。
- **off-grid-ai/OGAM** ⭐3,037 MIT — 手机/电脑全离线 AI（GGUF/Whisper/SD/MCP）：与 phone-mobile-hub 高度相关，可并入移动终端立项。
- **materialsproject/pymatgen** ⭐1,949 — 材料结构与性质分析框架：与 bo_materials/granite-biomass 相关，作为材料数据管线库引用。
- **ACEsuit/mace-foundations** ⭐301 MIT — MACE MLIP 基础模型：与已立项 mlip 方向重叠，仅作对照。
- **portapack-mayhem/mayhem-firmware** ⭐5,375 GPL-3.0 — PortaPack H2（HackRF 便携终端）固件：SDR 硬件方向候选，先评估硬件投入。
- **sh123/esp32_loraprs** ⭐273 GPL-3.0 — ESP32+LoRa APRS 追踪器：esp32/LoRa/APRS 三合一小项目，可并入 esp32_loraprs 立项。
- **JiaoXianjun/BTLE** ⭐928 Apache-2.0 — BLE 信号 SDR 解调参考：补充信号类型库，可并入 rtl-ml。

## Top 5 推荐立项

| 排名 | 仓库 | 立项建议一句话 |
|------|------|----------------|
| 1 | ruvnet/RuView | WiFi CSI 人体/空间感知，把现有 ESP32 变 RF 传感器阵列，直连 radio_brain |
| 2 | jopohl/urh | 无线协议逆向流水线，补 SDR 栈"信号→协议"缺口，喂 rtl-ml 标注数据 |
| 3 | markqvist/Reticulum | 加密离网 mesh 网络栈，meshpoint/esp32 自组网的协议层补强 |
| 4 | topoteretes/cognee | Agent 跨会话图记忆引擎，记忆栈的成熟本地化替代 |
| 5 | BigBodyCobain/Shadowbroker | 全球态势 OSINT 聚合（ADS-B/卫星/震情），世界监控+地面站数据汇合 |

## 扫描日志

- `sdr`: 15 命中，候选 11（urh/Shadowbroker/SDR++/mayhem-firmware/openwifi/srsRAN_4G/sdrangel/gqrx 等）
- `software-defined-radio`: 15 命中，候选 13（system-bus-radio/CubicSDR/RTLSDR-Airband/BTLE/hobbits/rtl-wmbus/piraterf 等）
- `lora`: 15 命中，LoRA-ML 噪声占比高；过滤后有效项 = Reticulum/ExpressLRS/OpenMQTTGateway/meshtastic 等
- `mesh-networking`: 8 命中，候选 7（wireguard-docs/yggmail/crisis-mesh-messenger/Reticulum-Hub/yip）
- `amateur-radio`: 15 命中，候选 14（Cloudlog/k3ng/HamMessenger/codec2_talkie/esp32_loraprs/SIGpi/AetherSDR/M17_spec）
- `satellite`: 15 命中，候选 14（SatDump/keeptrack/Look4Sat/satpy/gpredict/gr-satellites/Skyfall-GS）
- `rtlsdr`: 15 命中，候选 15（tar1090/SoapySDR/adsb_deku/readsb/r2cloud/skies-adsb）
- `gnuradio`: 15 命中，候选 13（FISSURE/trunk-recorder/AIS-catcher/gr-iridium/IQEngine）
- `esp32`: 15 命中，候选 12（RuView/Tasmota/lvgl/WLED/ESP32Marauder/esphome 等；含大量非 ESP32 泛项目噪声）
- `edge-ai`: 15 命中，候选 15（LiteRT-LM/cactus/OGAM/audio.cpp/Biodiversity/defradb）
- `mcp`: 15 命中，候选 13（awesome-mcp-servers/Scrapling/dify 等；多为泛 AI 大项目噪声）
- `knowledge-graph`: 15 命中，候选 13（Understand-Anything/siyuan/logseq/LightRAG/Trilium/cognee/dgraph/memvid）
- `threat-intelligence`: 15 命中，候选 15（Anthropic-Cybersecurity-Skills/spiderfoot/bbot/opencti/MISP/capa/dnstwist/IntelOwl/deepdarkCTI）
- `materials-informatics`: 15 命中，候选 15（pymatgen/matgl/mace-foundations/jarvis/RadonPy/pymatviz/awesome 列表）
- `biomass`: 0 命中（该 topic 无 stars>100 仓库，改用 keyword 已由关键词扫货覆盖）
