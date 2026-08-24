# SPEC-12 · 哨兵网格 Phase 1 —— 第七批工单总纲

> 源：POLLINATION-2026-08-23-hybrid-brainstorm.md 收敛目标「哨兵网格」
> Phase 1 范围：ESP32-S3 + SX1278 边缘频谱哨兵 —— rtl_433 解码逻辑（独立实现）+ DSP 滤波 → 433MHz 传感器信号 → 串口/USB 上报 → 云服 rf_brain 存记忆
> 分工铁律：Trae 走 GitHub 写码（agent-n 分支）；沈遥出 SPEC + review；用户定方向测试（真机验证）
> 前置：rf_brain Phase4-7 已通（SDR 解码→记忆 MaaS→决策）；ESP32-S3 SuperMini + SX1278 + NEO6M 硬件已到手

---

## 施工范围矩阵（防重复）

| 智能体 | 领域 | 层 | 工单 | 与既有工单边界 |
|--------|------|----|------|----------------|
| N | 边缘频谱哨兵 | 勘察/固件/桥接 | N-01~04 | 不碰 A/B/C（sdrtrunk/meshtastic）；不碰 H/I（SPEC-10 解冻）；不碰 K/L/M（SPEC-09 威胁情报） |

## 硬约束（全组共用）

1. **rtl_433 为 GPL-2.0-or-later**：解码逻辑**独立实现**（协议格式是公开事实，不受版权保护；C 代码不得整段复制）。ESP32 固件与解码器若参考 rtl_433 源码，须在文件头标注「参考 rtl_433（GPL-2.0）协议文档独立实现」，主仓不落 GPL 代码。
2. **SX1278 只支持 OOK/FSK**：本阶段目标是 433MHz OOK 传感器（温湿度/门磁/遥控类）。协议选型必须确认 SX1278 OOK 模式可收（带宽/灵敏度匹配），不做 SDR 才做得到的复杂调制。
3. 固件不引入 RTOS 重型依赖；ESP-IDF/Arduino 二选一，选型在 N-01 报告里定。
4. 上报协议为 JSON 行（NDJSON），与 rf_brain 现有 schema 对齐（见 rf_brain/schemas.py）。
5. 真机验证点明确标注，云服侧用模拟串口数据先验收（无真机也全绿）。

---

## 智能体 N —— 边缘频谱哨兵组（分支 trae/agent-n）

### N-01: 433MHz 传感器协议勘察报告（文档级）

- **层**: 勘察
- **目标**: 确定 2~3 个 SX1278 OOK 可收、有公开协议文档、解码逻辑可独立实现的 433MHz 传感器协议
- **输入**: rtl_433 协议列表（https://github.com/merbanan/rtl_433 的 README 协议清单，只读参考格式，不抄代码）+ SX1278 数据手册 OOK 模式参数 + rf_brain/decoders/ 现有解码器风格
- **动作**:
  1. 从 rtl_433 支持列表筛 433MHz OOK、单载波、短帧（<200 bit）协议，候选 ≥5 个（如 Acurite/LaCrosse/OSv1/门磁类）
  2. 对候选逐个核对：调制方式 / 帧长 / 编码（PWM/PPM/Manchester）/ 校验 / 公开文档来源，填对照表
  3. 结合 SX1278 OOK 灵敏度（-112dBm@1.2kbps 量级）与带宽约束，选出 2~3 个可落地协议
  4. 输出 docs/sentinel-协议勘察报告.md：候选对照表 ≥5 行 + 最终选型 2~3 个 + 每个的帧格式图 + SX1278 参数配置建议（带宽/灵敏度/解调模式）
- **验收**: 报告落盘；选型协议每个有帧格式字段表；SX1278 配置参数具体到寄存器级建议（OOK 模式带宽/灵敏度/AGC）
- **硬约束**: 只读勘察，不写码；协议文档引用真实来源

### N-02: OOK 解码核心独立实现（纯 Python + C 参考）

- **层**: 写码（解码库）
- **目标**: 把 N-01 选型的 2~3 个协议解码器实现为纯 Python 模块，输入脉冲序列（pulse width 数组）输出结构化 JSON——与 rf_brain 解码器家族同构
- **输入**: N-01 报告帧格式 + rf_brain/decoders/ 现有风格（aprs.py/psk31.py 参考）+ mcpserver/rf_brain/schemas.py
- **动作**:
  1. `mcpserver/rf_brain/decoders/ook/` 目录：`pulse_demod.py`（脉冲宽度 → bit 流，处理 PWM/PPM/Manchester 三种编码）+ 每协议一个解码器 `acurite.py` / `lacrosse.py` 等
  2. 解码器输出统一 dict：{protocol, id, channel, temperature, humidity, battery, raw_bits, crc_ok}
  3. `registry.py` 注册新解码器（照 decoders/registry.py 模式）
  4. `tests/test_ook_decoders.py`：≥6 用例——用 N-01 报告里的真实帧样例合成脉冲序列 → 断言解出正确字段 + CRC 校验对/错两路
- **验收**: `python -m pytest mcpserver/rf_brain/decoders/tests/test_ook_decoders.py -q` 全过；`grep -n "crc" mcpserver/rf_brain/decoders/ook/*.py` 非空；测试 assert 温度/湿度字段精度正确
- **硬约束**: 独立实现，不复制 rtl_433 C 代码；纯 Python 无新重依赖（numpy 可用）；文件头注明协议文档来源

### N-03: ESP32-S3 固件（SX1278 接收 + 解码 + 串口上报）

- **层**: 写码（固件）
- **目标**: ESP32-S3 上 SX1278 以 OOK 模式收 433MHz，脉冲序列解出协议字段，NDJSON 行经 USB-CDC 串口上报
- **输入**: N-01 报告 SX1278 配置 + N-02 解码器逻辑（C 移植或 MicroPython 调 Python 解码）+ 硬件：ESP32-S3 SuperMini + SX1278
- **动作**:
  1. 固件工程（ESP-IDF 或 Arduino，N-01 定）：SX1278 SPI 初始化（OOK 模式、中心频 433.92MHz、带宽/灵敏度按 N-01）
  2. 接收循环：捕获 OOK 包 → 提取脉冲序列 → 解码（协议逻辑按 N-02，C 实现或 MicroPython 复用）
  3. USB-CDC 串口输出 NDJSON 行：{"src":"sentinel","protocol":"acurite","id":...,"temperature":...}，带 RSSI 字段
  4. 串口命令接口：`STATUS` → 返回固件版本/SX1278 寄存器状态；`RESET`
  5. 根目录 `firmware/README.md`：烧录步骤（esptool/Arduino CLI 命令）、接线图（SPI 引脚表）、串口测试命令
- **验收**: 固件可编译（构建日志成功）；`firmware/README.md` 含接线图 + 烧录命令；串口协议文档含 NDJSON schema 示例 ≥3 行；真机验证点列明（接上后 `STATUS` 返回寄存器值）
- **硬约束**: 固件与解码逻辑独立实现（GPL 约束同上）；不引入 WiFi/蓝牙（本阶段纯串口）；无真机时构建+单测全绿即可，真机清单留给用户

### N-04: 云服串口桥 + rf_brain 记忆入库

- **层**: 写码（桥接）
- **目标**: 云服收 ESP32 串口 NDJSON → 校验 → rf_brain 记忆 MaaS 存库 → mcpserver 工具总线暴露查询
- **输入**: N-03 串口协议 + rf_brain 现有记忆写入路径（decision_layer/loop.py 或 memory 相关）+ mcpserver agent-manifest.json 模式
- **动作**:
  1. `mcpserver/rf_brain/sentinel_bridge.py`：串口设备读取（pyserial，dev 路径/波特率可配，无设备时 mock 模式可跑）
  2. 解析 NDJSON → schema 校验（照 schemas.py）→ 写入 rf_brain 记忆（事件+特征，按现有 MaaS 路径）
  3. `agent-manifest.json` 注册：`sentinel_ingest`（收一条）/ `sentinel_status`（最近 N 条）/ `sentinel_query`（按协议/id 查）
  4. `tests/test_sentinel_bridge.py`：≥6 用例——mock 串口数据过桥 → 入库 → 查询返回；坏 JSON/未知协议降级不崩
- **验收**: `python -m pytest mcpserver/rf_brain/tests/test_sentinel_bridge.py -q` 全过；`grep -n "sentinel_ingest" mcpserver/rf_brain/agent-manifest.json` 非空；mock 串口 3 条入库后 `sentinel_query` 返回 3 条
- **硬约束**: 不碰 NEKO/apiserver 主流程；无真机时 mock 模式验收；串口配置走环境变量不硬编码

---

## 通用约束

- 分项 commit: docs: / feat(rf_brain): / feat(firmware): / test:
- 全部中文输出，完成一个报一个（路径 + 验收结果）
- 阻塞（缺数据/许可/硬件）不硬做，写清原因返回
- 成果推 trae/agent-n 分支
- 真机验证点统一列在 N-03/N-04 末尾，用户按清单实测

**启动口令**：用户说「开始执行第七批工单」→ N 组按序推进；「只跑 N-xx」→ 单跑。
