# W70-04 · radio-modulation-classifier 评估（调制识别模型）

> 2026-09-02 · 第二十四期三榜单扫描批 · 勘察/评估（不写实现）
> 上游：alirezaaminzadeh/radio-modulation-classifier（HF，MIT，dl=25，likes=0，pipeline=audio-classification）

## 一、项目定位

无线电调制分类模型：以 IQ/基带信号（或音频化频谱）为输入，用深度学习分类调制方式（BPSK/QPSK/FSK/GFSK/OOK/AM 等）。属于「AI 调制识别」路线（基于 RadioML 类数据集训练），likes=0、成熟度低（诚实标注）。

## 二、架构拆解

- 输入：IQ 复采样序列（或频谱图），音频分类 pipeline 形式（audio-classification）。
- 主干：CNN/ResNet 类（RadioML 常用），softmax 输出调制类别。
- 训练：RadioML2016/2018 等合成调制数据集。

## 三、与本仓对照（AI 分类 vs 规则解调）

| 维度 | rf_brain 规则解调（GFSK/FSK/OOK） | AI 调制分类 |
|------|-----------------------------------|------------|
| 方式 | 特征（包络/瞬时频率）+ 规则 | 端到端神经网络 |
| 鲁棒性 | 低 SNR 下特征漂移 | 训练充分时更鲁棒 |
| 可解释 | 高（特征可读） | 低 |
| 部署 | 轻量（纯 numpy/定点） | 需 ONNX/量化 |
| 许可 | 本仓 | MIT（可借鉴） |

结论：**互补**——规则解调做「已知协议高可解释快速解调」，AI 分类补「未知/复杂调制盲识别」侧。

## 四、可落地借鉴点（≥3）

1. **AI 盲调制识别作为规则解调的前置**：先 AI 分类粗判调制类型，再规则/特征细解调——补 rf_brain 对未知调制的盲识别。
2. **RadioML 类数据集与数据增强**：合成 IQ + 信道损伤（多径/频偏/噪声）增强，可复用到 rf_brain 的调制识别训练。
3. **IQ → 分类的 CNN 结构**：复数输入处理（I/Q 双通道或复卷积）可借鉴到 rf_brain 的深度学习分支。

## 五、接入建议与许可裁定

- 接入：作为 rf_brain「调制识别」的可选 AI 后端（`demod_ref`/`rule_engine` 之外），ONNX 导出后轻量部署；非替代规则解调。
- 许可：**MIT，可借鉴代码**（likes=0、下载少，参考架构/数据集思路为主，直接接价值有限）。
