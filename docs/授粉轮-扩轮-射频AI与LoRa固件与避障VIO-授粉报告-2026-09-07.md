# 授粉轮 · 扩轮：射频 AI + LoRa 固件层 + 无人机避障/VIO + 中文 EE — 授粉报告 2026-09-07

**沈遥签** | 2026-09-07 23:00 | 守卫核验：两轮 109 候选，全部经 gh api 仓库级核实（星数/许可/archived/pushed）；NOASSERTION/NONE 项按前轮流程读 LICENSE 原文二次确认后分类。
**数据源**：GitHub Search API 21 组查询（5.8GHz图传/FPV、VIO/视觉避障/光流、LoRa mesh 固件、中文实体链接/事件抽取、射频信号分类/频谱感知/AMC/RF无人机探测）+ repos API 逐项核实。
**零重复判定**：与 09-05~09-07 全部报告（madflight/esp-fc/OpenNRE/CasRel/graph-rag-agent/DroneBridge/lora-packet/MeshTNC/meshcore-open/LLMs4OL/wfb-ng/OpenHD 等）+ 历史授粉库逐项对照——本轮 21 项全部为新条目（grep 全库验证命中 0）。

## 本轮角度（扩轮三直补 + 二新方向）

1. **LoRa mesh 固件层**：09-06 留「固件层 MeshCore 闭源、开源替代仍缺」→ 本轮判明正主 **Meshtastic firmware**（开源 LoRa mesh 固件第一把交椅，433 频段业余可直接用）——缺口是搜索遗漏，不是社区空缺。
2. **射频 AI / 信号识别**：频谱诊疗主线的新候选层——无线电信号识别参考实现 + 无人机 RF 探测 + AMC 自动调制分类。
3. **无人机视觉避障 / VIO**：连续四轮缺口的**前置状态估计层**（VIO/SLAM）与**首个深度相机避障可落地对照**。
4. **5.8GHz 模拟图传 SDR 采集**：多词搜索均无成熟开源 → **判真实空缺**（等社区/自研/OEM），本轮如实标注。
5. **中文 EE 干净 LICENSE 补段**：KG 线中文事件抽取补 MIT 干净件（前几轮 liuhuanyong 系均无 LICENSE）。

## 新增可落地候选（来源可核 / 落点明确 / 零重复）

### 🟢 P0（立即授粉）

**meshtastic/firmware**（8268★ · GPL-3.0 ✅ · **2026-09-07 刚 push**）〔P0-1〕
- **LoRa mesh 开源固件正主**（ESP32/SX1262/SX1278 全支持，433 业余频段可用，生态最大）。
- 09-06 缺口「固件层 MeshCore 闭源，开源替代仍缺」的**正解**：Meshtastic 一直开源且活跃（8268★ 全场最大）；用户 LoRa 储备（SX1278×2 + LR21-433）直接对口，天线云台 LoRa433 遥控的组网侧升级路径。GPL-3.0 可吞（不并入主仓可独立集成）。→ **立即授粉**（LoRa mesh 固件层 P0-1）。

**kitoweeknd/RFUAV**（436★ · Apache-2.0 ✅ · 2026-07-29 活跃）〔P0-2〕
- **无人机 RF 探测/识别基准数据集 + 检测实现**（RFUAV 论文官方；多类无人机 RF 特征）。
- 授粉轮「射频 AI」侧防御候选：无人机 RF 指纹 → 频谱监测/反制态势感知（**只写防御分析**：探测/告警/识别，不涉攻击载荷）。Apache-2.0 干净可吞。→ **立即授粉**（无人机 RF 探测 P0-2）。

**AresValley/Artemis**（569★ · GPL-3.0 ✅ · 2026-07-22 活跃）〔P0-3〕
- **无线电信号识别参考实现**（自称 "the reference for radio signal identification"）。
- 频谱诊疗主线直接对口：信号分类/识别做频谱监测与干扰源的「识别人」。GPL-3.0 可吞（独立件不并主仓）。→ **立即授粉**（信号识别 P0-3）。

**luciobaiocchi/heard**（88★ · Apache-2.0 ✅ · 2026-08-08 活跃）〔P0-4〕
- **ESP32 + GPS + LoRa 离线组网**（hikers 群组安全 mesh，含 firmware-in-the-loop 模拟器 + 3D replay）。
- ESP32-S3 SuperMini 栈**直接对口**（SX1278/LoRa + GPS=NEO6M 全匹配）；SITL 模拟器 = 无真机也能先跑链路仿真的工程方法论。Apache-2.0 干净。→ **立即授粉**（ESP32 LoRa 组网 P0-4）。

### 🟡 P1（进树通道，待工单）

**MIT-SPARK/Kimera-VIO**（1912★ · **BSD-2-Clause** ✅ · 2026-08-06 活跃）〔P1-1〕— VIO + SLAM + 3D mesh（MIT 开源，BSD 最干净）；视觉避障缺口的前置状态估计层——先解决「我在哪/怎么动」，避障才有输入；BSD-2 可深度借鉴。
**LEE-YOONSU/offboard_rail_following_drone**（0★ · MIT ✅ · **2026-09-02 刚活跃**）〔P1-2〕— PX4 + MAVROS + 深度相机避障完整管线；**连续四轮缺口（实时视觉避障）的第一个可落地对照**——星数低但直接对口（PX4 offboard 已有对照 + 深度相机避障闭环），MIT 干净。
**zjwfufu/AMC-Net + AWN**（72★ + 84★ · MIT ✅ · 2024）〔P1-3〕— AMC 自动调制分类双件（ICASSP'23 官方 + TCCN'23 自适应小波网络）；射频 AI 供料，MIT 可直接借鉴特征/网络结构。
**pe1hvh/meshcore-gui**（26★ · MIT ✅ · **2026-09-06 刚活跃**）〔P1-4〕— MeshCore mesh 桌面 GUI（BLE 直连，无需改固件）；LoRa mesh 生态补件（meshcore-open 客户端之外的桌面侧），lumo 可借鉴形态。
**ahsi/Multilingual_Event_Extraction**（35★ · MIT ✅ · 2017）〔P1-5〕— 含中文的三语 ACE 风格事件抽取——中文 EE 段**少见的干净 LICENSE 件**（前几轮 liuhuanyong 系、hendrydong 系全无 LICENSE）；模型方法（触发词+论元联合）可作 SPEC-G1 EE 段骨架。
**longlongint/Fin-PTPCG**（12★ · MIT ✅ · 2024）〔P1-6〕— 中文金融事件抽取（Fin-BERT + 跨句触发词）；中文 EE 模型候选第二件（领域窄但方法通用）。

### 🟢 P2（参考/低优先）

- Darth-Kronos/Spectrum-Sensing（68★ · MIT）— 信号处理特征 + ML 频谱感知，教学件
- Al-Sad/DroneRF（191★ · Apache-2.0 · 2021）— 无人机 RF 数据集早期标杆（RFUAV 对照系）
- Hydra-Designs/project-hydra-meshtastic-pcb（165★ · GPL-3.0）— Meshtastic 1W LoRa PCB 硬件设计（用户不做手搓 PCB → 只读）
- cheeseBG/meta-transformer-amc（45★ · MIT）— 元学习 AMC
- widjit/SDR_Hunter（0★ · MIT · 2026-08）— SDR 信号识别+基线+无人机识别（太小，方向确认）
- voxel_svio（827★ · GPL-3.0 · 2025-10）— 立体 VIO 轻量参考（RA-L'25）
- hku-mars/FAST-LIVO2（4604★ · GPL-2.0）— LiDAR-Inertial-Visual 里程计，**需 LiDAR 硬件，超预算**，架构参考级

### ⚠️ 暂缓（LICENSE / 硬件前置）

- KumarRobotics/msckf_vio（1972★，NOASSERTION）— 经典 MSCKF VIO
- ucla-vision/xivo（890★，NOASSERTION）
- PetWorm/LARVIO（807★，NONE）
- tesorrells/RF-Drone-Detection（224★，NONE · 2025 活跃）
- meshdeck-os/meshdeck（11★，NOASSERTION · 2026-09 活跃）— MeshCore 开源替代固件（可惜，等作者补 LICENSE）
- lukeswitz/AntiHunter（655★，**AGPL-3.0** · 2026-09-04）— DIGI Node 反猎网固件，AGPL 只参考设计
- HITsz-TMG/Hansel（24★，NONE）— WSDM'23 中文 few-shot EL benchmark（数据参考）
- Mzzzhu/CMNEE（52★，NONE）— COLING'24 中文军事事件抽取数据集（数据参考）

### 🔴 排除 / 确认真空

- **5.8GHz 模拟图传 SDR 采集**：两轮 8 组查询（5.8ghz fpv / fpv video receiver sdr / ntsc pal demodulation sdr / esp32 camera fpv / ntsc decoder esp32 等）均无成熟开源实现（最高星 hybrayhem/pi-camera-fpv-transmitter 5★ 且只做发射侧）→ **判真实空缺**：社区无人做「模拟图传 NTSC/PAL → SDR 采样解调」的干净开源，等自研/OEM/下轮换词再探
- FAST-LIVO / LVI-SAM / Kimera 系 VIO 需要 LiDAR/双目硬件，超用户现有预算 → 仅架构参考

## 🎯 差距直补确认

| 上轮/持续差距 | 本轮结果 |
|---------|---------|
| LoRa mesh 固件层开源替代仍缺（09-06） | ✅ **直补正主 Meshtastic firmware（8268★ GPL-3.0）**——缺口是搜索遗漏 |
| 无人机视觉避障仍缺（连续四轮） | 🟡 部分破缺：前置 VIO 层（Kimera-VIO 1912★ BSD）+ 深度相机避障管线（PX4 offboard 对照）双件到手；**实时视觉避障完整集成仍待落地**，但「无参照可抄」阶段结束 |
| 中文 EE 干净 LICENSE 仍薄 | ✅ MIT 双件（Multilingual_EE + Fin-PTPCG）补段 |
| 5.8GHz 模拟图传 SDR 采集未扫（09-07） | 🔴 多词搜索无成熟开源 → 判真实空缺（如实标注） |
| 射频 AI（频谱诊疗识别侧） | ✅ 本轮新增候选层（Artemis/RFUAV/AMC 双件） |

## P0 优先级（交付顺序）

1. **meshtastic/firmware → LoRa mesh 固件层**（GPL-3.0，8268★ 生态最大，433 业余可用，SX1278 储备对口；先读固件架构/配置协议再定集成深度）
2. **kitoweeknd/RFUAV → 无人机 RF 探测**（Apache-2.0，防御态势感知侧，数据集+检测一条龙）
3. **AresValley/Artemis → 信号识别**（GPL-3.0，频谱诊疗「识别人」）
4. **luciobaiocchi/heard → ESP32 LoRa 组网**（Apache-2.0，SX1278+GPS 全对上，SITL 模拟器方法论加分）

## 交付确认
- 报告落盘 docs/授粉轮-扩轮-射频AI与LoRa固件与避障VIO-授粉报告-2026-09-07.md
- 工单：AGENT_95~98 四卷（LoRa 固件层 / 射频 AI / 避障 VIO / 中文 EE），扩入第三十四期
- 守卫：21 项新条目 FAIL=0，来源可核/落点明确/与已有零重复

**金果数/份持续+**：本轮 P0×4 + P1×6 + P2×7 + 暂缓×8 + 确认真空×1。P0 立即授粉 = 四项，其中 **LoRa 固件层缺口直补闭合**（Meshtastic 正主）+ **射频 AI 新候选层开张** + **避障参照阶段结束**。