# agent-77 评估报告 + 执行清单（PyPI 二轮 8 + 垂直无线电 7 = 15 项）

> 智能体 77 · 勘察/评估 · 15 项（W76-01~15）

## PyPI 侧（W76-01~08）

| 编号 | 项目 | 许可 | 定位 | 借鉴点 / 结论 |
|---|---|---|---|---|
| W76-01 | mcp-materials-project | MIT | Materials Project 数据库 MCP | ✅ 借鉴：材料性质/晶体结构 MCP tool，对接陆墨 |
| W76-02 | kuzu | MIT | 嵌入式 Cypher 图库（无服务端） | ✅ 借鉴：本地图库替代 Neo4j 重依赖，对照 memory_maas |
| W76-03 | pytest-embedded | MIT | ESP32 固件自动化测试（串口/QEMU） | ✅ 借鉴：固件测试框架，对接 firmware 测试 |
| W76-04 | sigmf | LGPL | SDR 录音元数据规范（IQ+注解） | ✅ 借鉴：SDR 录音元数据标准，对接 rf_brain 数据集 |
| W76-05 | nullsec-lora-mesh | MIT | 零泄漏高速压缩 LoRa mesh | ✅ 借鉴：LoRa mesh 对照 LoRaCanary |
| W76-06 | mcp-use + antropy | MIT/BSD | 全栈 MCP 框架 + 时序熵特征 | ✅ 借鉴：MCP 编排 + 熵特征（样本熵/谱熵），对接 rf_brain 特征层 |
| W76-07 | chemprop | MIT | 分子性质预测 MPNN 标准库 | ✅ 借鉴：材料 ML 标准库，对接陆墨 |
| W76-08 | satellitetle + astroquery | MIT/BSD | TLE 抓取 + Simbad/VizieR 星表 | ✅ 借鉴：轨道根数 + 星表检索，对接卫星垂直 |

## 垂直无线电侧（W76-09~15）

| 编号 | 项目 | 许可 | 定位 | 借鉴点 / 结论 |
|---|---|---|---|---|
| W76-09 | direwolf | GPL-2.0 | 软件声卡 AX.25 TNC + APRS | ⚠️ GPL 只参考设计；APRS 编解码算法可借鉴 |
| W76-10 | Look4Sat + noaa-apt | GPL-3.0 | 卫星追踪 + NOAA APT 解码 | ⚠️ GPL 只参考；卫星过境预测 + APT 图像解码可借鉴 |
| W76-11 | NanoVNA-Saver + Hamlib | Py/NOASSERTION | VNA 读取分析 + 设备控制 | ✅ 借鉴：VNA 分析 + rigctl 设备控制，对接 IC-705/radio_suite |
| W76-12 | MeshStation + MeshTNC | GPL/MIT | Meshtastic SDR 分析 + LoRa KISS TNC | ✅ 借鉴：LoRa KISS TNC（对照 W73-02 URH），MIT 部分可借鉴 |
| W76-13 | AntennaSim | NOASSERTION | Web NEC2 天线模拟 | ⚠️ 待核；Web 天线仿真交互可参考 |
| W76-14 | chattervox | NOASSERTION | 签名+压缩 AX.25 分组无线电 | ⚠️ 待核；分组无线电签名设计可参考 |
| W76-15 | pat/shinysdr/openwebrx/IQEngine | 混合 | Winlink + Web SDR 四件 | ✅ 借鉴：Web SDR 前端 + Winlink 网关，对接 rf_brain |

## 执行清单

- **完成**：15/15 逐项评估。
- **许可**：MIT/Apache/BSD 可借鉴；GPL（direwolf/Look4Sat/MeshStation）只参考设计；NOASSERTION 待核。
- **高价值**：kuzu（本地图库）、pytest-embedded（固件测试）、mcp-use（MCP 编排）、NanoVNA-Saver（VNA/rigctl）四点最可落地。
