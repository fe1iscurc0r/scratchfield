# SPEC-01: rf_brain 全自动闭环 · 射频大脑主线

> 版本 v1 | 2026-08-22 | 委托：外部 agent（类 Trae）
> 定位：项目最大主线，代码量以万行计，真机可验证

## 背景

rf_brain 已有 Phase1-4（解调链通：sensor → 特征 → LLM 决策 → demod_ref），
Trae 已交付 liquid_backend.py / mesh_layer.py / pocsag.py / doa.py。
本 SPEC 目标是：把"人工点单"的解调链升级为"频谱感知→决策→解调→反馈"的**自主闭环**。

## 目标

1. 全自动频谱扫描 → 信号检测 → 特征分类 → 自动选解调器 → 解码 → 日志/告警
2. 多协议解码器库（APRS/PSK/AX.25/DTMF 新增）
3. IC-705 USB 音频流实时输入（替代 numpy 仿真）
4. LoRa mesh 组网 + MUSIC 测向整合进决策层

## 阶段拆解

### Phase 5: 自主闭环（核心，优先）
- 任务 5.1: 频谱扫描调度器（scan → energy detect → 候选信号表）
- 任务 5.2: 特征提取缓存（IQ 快照 → 特征向量 → 分类器）
- 任务 5.3: LLM 决策路由（候选信号 → 选解调器 → 参数）
- 任务 5.4: 反馈环（解码失败 → 换解调器重试 → 学习记录）
- 验收: 模拟信号 30 秒内自动识别+解码，误检率 <10%

### Phase 6: 多协议解码器库
- 任务 6.1: APRS AX.25 解码（现有参考）
- 任务 6.2: PSK31 / PSK63 解码
- 任务 6.3: DTMF 解码
- 任务 6.4: 解码器注册表（provider 模式，抄 dsh Service Definition）
- 验收: 每协议独立单测 + 模拟帧解码成功

### Phase 7: 真机集成（用户配合）
- 任务 7.1: IC-705 USB 声卡输入适配
- 任务 7.2: UV-K6 发射 / IC-705 接收闭环验证
- 验收: 真机信号闭环分析成功

## 硬约束

- 不碰 NEKO/apiserver 主流程（git diff --stat 验证 = 0）
- 解码器注册表架构先行，禁止硬编码协议分支
- 射频频段白名单校验（业余频段，与 rsba1_adapter 对齐）

## 远期规划（Phase 8+）

- 8.1: 多节点测向融合（4×SDR 阵列 → MUSIC 实时）
- 8.2: 频谱指纹库（已知信号自动标记）
- 8.3: 传播预测集成（QRP/传播模型）
- 8.4: 无人值守频谱监控告警
- 8.5: 跨频段跳频扫描（HF/VHF/UHF）

## 目录结构（预期）

```
mcpserver/rf_brain/
├── scanner/       # 频谱扫描调度器
├── classify/      # 特征提取 + 分类
├── demod_ref/     # 解码器注册表 + 各协议实现
├── decision/      # LLM 决策路由
├── feedback/      # 反馈学习环
├── mesh/          # LoRa mesh（Trae 已交基础）
├── doa/           # MUSIC 测向（沈遥已交原型）
└── device/        # IC-705 / SDR 输入抽象
```
