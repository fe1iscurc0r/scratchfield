# 物理层 AI 红利盲区摸底报告

> 日期：2026-08-13 | 范围：物理层（射频/机器人/地图/无人机/硬件）+ AI 红利盲区判断
> 目的：为 scratchpad "物理层加码" 找候选库

---

## 一、核心洞察

物理层分两层，AI 红利的分布极不均匀：

| 层 | 现状 | AI 红利 |
|---|---|---|
| **感知层**（SLAM/视觉/信号检测） | 深度学习已渗透 | ✅ 吃到了 |
| **控制层**（路径规划/运动控制/决策） | A* / DWA / PID / ACO / PSO 传统算法 | ❌ **最大盲区** |

**结论**：感知层不缺 AI，缺的是**决策/规划/控制层**的 AI 大脑。这正是 scratchpad 能补的位置——它天生是"推理 + 规划"的载体。

- **射频/无线电 = 纯盲区**：SDR 项目全是传统 DSP + 接收机，频谱感知/信号识别/自动调参全靠人工经验，零 AI。
- **硬件控制 = 碎片化盲区**：ESP32 自动化项目 0~几星，无统一抽象层。
- **无人机自主 = 空白**：学术 demo 星数极低，蜂群协同无成熟方案。

---

## 二、各方向摸底

### 1. 射频/SDR（纯盲区，你的主场）

| 项目 | ★ | 许可 | 价值 |
|---|---|---|---|
| jgaeddert/liquid-dsp | 2280 | MIT | DSP 底座库，可做信号处理后端 |
| DSheirer/sdrtrunk | 2156 | GPL-3.0 | 解码/监控框架 |
| tapparelj/gr-lora_sdr | 991 | GPL-3.0 | LoRa SDR（你已有关联） |
| JiaoXianjun/BTLE | 924 | Apache-2.0 | BLE sniffer |
| ha7ilm/csdr | 576 | 无 | 轻量 DSP 命令行 |
| martinmarinov/TempestSDR | 1608 | GPL-3.0 | TEMPEST 电磁侧信道（防御研究向） |

### 2. 机器人/路径规划（控制层盲区）

| 项目 | ★ | 许可 | 价值 |
|---|---|---|---|
| AtsushiSakai/PythonRobotics | 30298 | other | 机器人算法大全（教科书级） |
| atb033/multi_agent_path_planning | 1462 | MIT | 多机器人路径规划 |
| rlnav/motion_planning | 409 | MIT | 规划/建图/探索算法 |
| Kei18/mapf-IR | 145 | MIT | 实时多机器人路径规划 |
| HusseinLezzaik/Deep-Learning-for-Multi-Robotics | 68 | MIT | GNN+RL（少见的 AI 尝试） |

### 3. GIS/地图

| 项目 | ★ | 许可 | 价值 |
|---|---|---|---|
| CesiumGS/cesium | 15559 | Apache-2.0 | 3D 地理空间 |
| qgis/QGIS | 14211 | GPL-2.0 | 桌面 GIS |
| Turfjs/turf | 10431 | MIT | 地理空间分析库 |
| gboeing/osmnx | 5808 | MIT | OSM 网络分析（可做路径规划） |
| hyperknot/openfreemap | 5776 | other | 自由地图 |

### 4. SLAM（感知层，已吃红利，作参考）

| 项目 | ★ | 许可 | 价值 |
|---|---|---|---|
| cartographer-project/cartographer | 7940 | Apache-2.0 | Google SLAM |
| UZ-SLAMLab/ORB_SLAM3 | 8943 | GPL-3.0 | 视觉 SLAM |

### 5. 无人机 / 硬件控制（空白/碎片化）

- 无人机自主：全是学术 demo（几~几十星），无成熟项目，暂不拉。
- 硬件控制：ESP32 自动化项目 0~几星，极度碎片化，等有明确需求再定向。

---

## 三、传统工程/科学/行业软件（第二轮扩展摸底）

### 分档判断

| 档 | 特征 | 领域 | 加码价值 |
|---|---|---|---|
| **荒漠档** | 连传统底座都没有，开源 0~几星 | 机械仿真、工业控制、仪器控制 | 开荒代价大，暂缓 |
| **甜点档** | 传统底座成熟，AI 优化层空白 | CNC、FEA、电力、化工、EDA、卫星 | **主攻方向** |

### 甜点档项目清单

| 领域 | 传统底座 | AI 萌芽 | 机会 |
|---|---|---|---|
| CNC | LinuxCNC(2397★)、PyCNC(MIT)、svg2gcode(MIT) | 无 | 智能加工/工艺优化 |
| 有限元 | SolidsPy(MIT)、pycalculix(Apache)、gismo(MPL) | 无 | AI 代理模型/降阶 |
| 电力 | OpenDSS、JuliaGrid.jl(MIT)、simona(BSD) | PowerSkills | 调度/决策 AI |
| 化工流程 | DWSIM | dwsim-claude-integration(MIT)、Agentic-Process-Simulation | LLM 流程模拟 |
| EDA | lepton-eda(GPL) | awesome-ai4eda、CircuitNet(BSD)、HDLGen-ChatGPT(AGPL) | AI 辅助电路设计 |
| 卫星 | SatNOGS、wx-ground-station(MIT)、FAASGS(GPL) | 无 | 信号 AI/自动跟踪 |

---

## 四、scratchpad 加码机会（结合摸底）

| 机会 | 底座项目 | scratchpad 补什么 |
|---|---|---|
| **射频大脑** | liquid-dsp + gr-lora_sdr | 频谱感知 AI、信号识别、自动调参 |
| **小车/机器人规划** | PythonRobotics + multi_agent_path_planning | LLM 任务规划 → 路径规划的决策层 |
| **地图规划** | osmnx + openfreemap | 空间推理、动态路径、语义导航 |
| **定位** | cartographer | 语义 SLAM、场景理解 |

**关键判断**：scratchpad 不是去"重写"这些底座（DSP/规划算法已经很成熟），而是**当它们的 AI 决策大脑**——用 LLM 推理 + 逻辑引擎，补上控制/规划层的智能空白。这就是"没吃到 AI 红利"的地方，也就是你的护城河。
