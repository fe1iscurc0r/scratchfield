# W70-02 · Supertonic-TTS-ONNX 评估（离线 TTS 模型）

> 2026-09-02 · 第二十四期三榜单扫描批 · 勘察/评估（不写实现）
> 上游：onnx-community/Supertonic-TTS-ONNX（HF，dl=1517，likes=15，pipeline=text-to-speech，ONNX）

## 一、项目定位

Supertonic 系列 TTS 的 ONNX 版（onnx-community 导出）：**纯离线、ONNX Runtime 推理**的流式 TTS，体积小、延迟低，适合端侧/离线兜底。Supertonic 本身是「轻量级流式 TTS」（据其蒸馏自更大的 TTS 教师，强调实时性）。

## 二、架构拆解

- 文本前端 → 音素/时长 → 声学特征 → 声码器，全链 ONNX 化。
- 单模型多说话人（或单说话人）风格，ONNX Runtime 跨平台（CPU/GPU/NPU）。
- 与 kokoro-onnx 同属「ONNX 化离线 TTS」路线，但蒸馏源与声码器不同。

## 三、与本仓对照（Supertonic-ONNX vs kokoro-onnx）

| 维度 | kokoro-onnx（已有兜底） | Supertonic-TTS-ONNX |
|------|------------------------|---------------------|
| 推理 | ONNX Runtime | ONNX Runtime |
| 风格 | kokoro 声线 | Supertonic 声线（不同音色） |
| 中文 | 支持 | 待核实（需按上游模型卡确认） |
| 速度/体积 | 较小 | 相近（同为 ONNX 蒸馏 TTS） |
| 许可 | （已有） | OpenRAIL（需注意使用条款） |

结论：**可补 NEKO 语音多样性**（多一套声线/音色），非替代 kokoro。

## 四、可落地借鉴点（≥3）

1. **ONNX 全链化**：文本→声学→声码器全链 ONNX 导出，是 NEKO 离线 TTS 多后端（kokoro/supertonic 可切换）的统一运行时范式。
2. **蒸馏 TTS 教师-学生**：轻量流式 TTS 用「大教师蒸馏 + ONNX 量化」，可借鉴到 NEKO 语音线的低延迟目标。
3. **声线多样性**：多说话人单模型，补 NEKO 角色音色库（切换角色即换声线）。

## 五、接入建议与许可裁定

- 接入：作为 kokoro-onnx 的**并列后端**（`speak` 通道按角色/偏好选 TTS 后端），不做替换。
- 许可：**OpenRAIL**（非 MIT/Apache/BSD），含使用限制条款（不得用于违法/有害用途），属「可参考架构、接入需逐条核对 OpenRAIL 使用条款」，**标「许可待核」**。
