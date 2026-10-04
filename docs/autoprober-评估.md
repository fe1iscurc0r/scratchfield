# W68-05 AutoProber 评估（硬件飞针探测自动化）

> 上游：github.com/GainSec/AutoProber · 许可 PolyForm Noncommercial 1.0.0（源码可见·非商用）· 330★ · Python · 2026-04-16 活跃
> 落点：docs/autoprober-评估.md · 勘察/评估 · 硬件类标「待真机」

## 1. 项目定位

硬件黑客的**飞针探测自动化栈**：agent 驱动的目标发现 → 显微镜成像映射 → 安全监控下的探针扎针。从「板上有新目标」到「逐 pin 安全探测」的全流程。

## 2. 架构拆解

- **流程**：接入工程 → 硬件自检 → 归位/标定 → 显微镜成像 → 逐帧拼接 + 标注地图（pads/pins/chips）→ 探测目标审批 → 探针扎针 → 报告。
- **控制**：Web dashboard + Python 脚本 + agent 三通道。
- **安全模型**：GRBL `Pn:P` 忽略，独立安全限位读示波器 Ch4，运动中持续监控（机器控制系统，非普通 web app）。
- **交付**：Python 控制代码 + dashboard + CAD 文件（source-available）。

## 3. 与本仓对照

| 维度 | AutoProber | 本仓 |
|---|---|---|
| 硬件在环 | 飞针探测（物理扎针） | JLC-EDA 寄生控制链 W66-06「屏幕+API 双通道」+ esp32-nearfield-probe |
| 形态 | 独立硬件栈 | EDA 自动化 + 侧信道勘察 |

## 4. 可落地借鉴点（≥3）

1. **安全监控范式**：把物理运动当「机器控制」而非 web app，独立限位 + 持续监控——对任何硬件在环测试都是必守铁律，可写入我们 EDA 链/侧信道的安全护栏。
2. **agent 驱动的目标发现 + 审批流**：探针目标「提议 → 人工 approve/deny → 执行」，可作为 EDA 寄生控制链「屏幕+API 双通道」的审批门禁参考。
3. **成像 → 拼接 → 标注地图 → 探针**的流水线：显微镜帧拼接 + 特征标注（pads/pins/chips），可作为 esp32-nearfield-probe 的可视化定位参考。

## 5. 许可裁定 + 结论

- **许可**：PolyForm Noncommercial 1.0.0 —— **源码可见、仅限非商用**，商用需单独付费授权（autoprober@gainsecmail.com）。→ **非商用可参考设计，不抄代码；商用不可用**。
- **接 EDA 链 or 独立结论**：**独立（不迁入）**。AutoProber 是物理飞针硬件栈，与本仓 EDA 自动化定位不同；只借鉴「安全监控 + 审批门禁 + 成像标注」设计，不接代码。硬件类标「待真机」。
