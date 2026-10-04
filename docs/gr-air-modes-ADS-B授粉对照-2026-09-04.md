# gr-air-modes → ADS-B 解码授粉对照（SPEC-17 Y-05 / rf_brain 新模式）

> 2026-09-04 · 扫货增量十三轮（射频AI化）P1 补充参考 · 授粉对照（不写实现、不抄代码）
> 上游：bistromath/gr-air-modes（GitHub，GPL-3.0，★483，1090MHz Mode-S/ADS-B 解码器）
> 纪律：**GPL-3.0 主仓 AGPL 可吞，但只参考协议/帧结构设计，不逐字融合**（保持 rf_brain 独立实现路径）。

## 一、项目定位

gr-air-modes 是 GNU Radio 生态的 Mode-S / ADS-B 解码器：1090MHz 飞机应答机信号 → 前导检测 → Mode-S 帧解析 → ADS-B 报文（航班号/位置/高度/速度）。2021 停更但成熟稳定，是 ADS-B 解码的经典参考实现。

## 二、与 rf_brain 现有解码器的对照

| 维度 | rf_brain 现有 | gr-air-modes | 判定 |
|------|--------------|-------------|------|
| 数字模式 | aprs/psk31/ft8/wspr/sstv/apt/dtfm/pocsag/ook | Mode-S/ADS-B | **缺口（无 ADS-B）** |
| 信号域 | HF/VHF/卫星/433 | 1090MHz（L 波段） | 新频段 |
| 帧结构 | 各协议 | Mode-S 112bit 帧 + CRC24 | 新协议 |
| 许可 | 本仓 | GPL-3.0（AGPL 可吞） | 只参考设计 |

## 三、可借鉴设计点（映射到 `decoders/adsb.py` 骨架）

1. **1090MHz 前导检测**：8μs 脉冲前导（4 个 0.5μs 脉冲）定位帧起点——映射：`decoders/adsb.py` 的前导相关检测。
2. **Mode-S 帧解析**：112bit 帧 → DF 字段 → 类型分派（识别/位置/速度）——映射：帧解析状态机。
3. **CRC24 奇偶校验**：Mode-S 用 24bit CRC 检错纠错——映射：解码校验层。
4. **PPM 调制解调**：1090MHz 使用脉冲位置调制——映射：解调链（区别于现有 FSK/AFSK）。

## 四、与 esp-drone 线的衔接

gr-air-modes（ADS-B 飞机解码）与 esp-drone（已授粉到天线云台）同属「无人机/航空」无线电域——将来 ADS-B 解码结果可作为「空中目标」数据源，与无人机姿态/云台联动（Y-04 频谱可视化 + 哨兵网格）。

## 五、许可裁定

- **GPL-3.0**：主仓 AGPL-3.0 可吞，但**只参考协议/帧结构设计**（前导/DF 字段/CRC24 属协议规范数据，独立实现路径），不逐字融合源码。
- 落地建议：`decoders/adsb.py` 独立实现 + 注册进 registry（与 ft8/sstv 同构）。

## 六、结论

**仅参考（P1 补充）**：作为「ADS-B 新模式」的协议参考登记，补齐 rf_brain 数字模式矩阵的缺口；落地为 `decoders/adsb.py` 骨架时按协议规范独立实现，不 copy gr-air-modes 源码。

---
*授粉：fe1iscurc0r · 2026-09-04 · 基于上游公开文档与扫货报告，未 clone 源码（GPL-3.0 只参考设计）*
