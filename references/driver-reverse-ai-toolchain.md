# 驱动逆向 AI 工具链

> 来源：moyix / ESR 2026-07 讨论
> 定位：从闭源 Windows 驱动二进制 → LLM 辅助 → Linux 可用驱动

---

## 可用模型 & 工具

| 工具/模型 | 类型 | 用途 | 备注 |
|-----------|------|------|------|
| **Ghidra** | NSA 开源逆向框架 | 反编译 .sys/.dll → 伪代码 | 流水线第一级，提取函数边界/调用关系 |
| **LLM4Decompile** | 开源模型系列 (1.3B-33B) | 反编译专用，可再执行率超 GPT-4o | 专门训练的，比通用模型更准 |
| **Codex** (OpenAI) | 商业 API | libusb 类任务"势如破竹" (moyix) | 适合 USB 外设等简单场景 |
| **ChatGPT 5.5** | 商业 API | DOS 二进制 → Pascal 源码 (ESR 实验) | 可作为两阶段流水线的第一阶段 |

## 标准流水线

```
1. Windows 驱动 .sys/.dll
     ↓
2. Ghidra 反编译 → 伪代码（函数边界 + 调用关系 + 字符串）
     ↓
3. + USB 抓包日志 + 设备行为观察
     ↓
4. 喂给 LLM（Codex / LLM4Decompile / GPT-5.5）
     ↓
5. 生成 Linux 内核模块 或 libusb 用户态驱动
```

## 两阶段洁净室法（规避 DMCA）

```
阶段一：LLM 将反编译伪代码 → 行为规格说明（不含源码表达）
阶段二：另一 LLM 按规格 → 重新生成 Linux 驱动
```
同构于 Phoenix/AMI 复制 IBM PC BIOS 的 clean-room design。

## 关键前提

**Windows WDF 驱动接口文档公开**（微软 Learn）。模型不需要理解变量名——它靠的是识别 API 调用链的组合模式：
- `WdfRequestComplete` + `KeGetCurrentIrql` + `memcpy` = "从 USB 端点读数据然后标记完成"
- 这和传统逆向不同：人靠逻辑推理，模型靠模式匹配

## 甜点区

| 场景 | 难度 | 说明 |
|------|------|------|
| USB HID 键盘/鼠标 | ✅ 极低 | 协议公开，抓包清晰 |
| USB 声卡 (UAC) | ✅ 低 | 标准协议，libusb 几百行 |
| USB 串口 (FTDI/CH340) | ⚠️ 中 | 协议简单但可能有私有控制传输 |
| IC-705 CI-V 协议 | ⚠️ 中 | 命令集部分已知，固件私有部分需猜 |
| ESP32 固件行为 | ⚠️ 中 | ESP-IDF 开源，是"已知源码+未知配置"推断 |

## 边界（卡住场景）

| 场景 | 原因 |
|------|------|
| GPU 驱动 | 硬件寄存器无文档，固件 microcode 握手协议私有，百万行内核耦合 |
| Wi-Fi 固件 | 私有协议 + 状态机复杂 + RF 校准数据 opaque |
| 私有 USB bulk 传输 | 报文不干净，模型没有词典 |
| 无文档硬件寄存器 | LLM 无法替代 Nouveau 式的寄存器逆向 |

## 相关链接

- Ghidra: https://github.com/NationalSecurityAgency/ghidra
- LLM4Decompile: https://github.com/albertan017/LLM4Decompile
- 微软 WDF 文档: https://learn.microsoft.com/en-us/windows-hardware/drivers/wdf/
- Sega v. Accolade (合理使用先例): https://en.wikipedia.org/wiki/Sega_v._Accolade
