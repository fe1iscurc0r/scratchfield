# RVC 音色转换管线选型评估（W100-04）

> 2026-09-10 · 评估（不写实现）· 蒸馏依据：docs/handcrafted-lipsync-rvc-distill-2026-09-10.md Part B
> （RVCFilter / IF0Predictor / CrepeOnnxSimd / RmvpeOnnx / ContentVec / OnnxRVC）
> 上游无 LICENSE，仅蒸馏不融合。

## 一、候选选型表（Python 侧 RVC 推理，许可证已核）

| 候选 | LICENSE | 覆盖度（对照 B2 组件表） | 依赖 | 备注 |
|------|---------|--------------------------|------|------|
| rvc-python | MIT（以实际仓库 LICENSE 为准） | IF0(Crepe/RMVPE)+ContentVec+RVC 转换全链 | onnxruntime/faiss 级 | 首选候选 |
| GPT-SoVITS | MIT | f0/内容特征/RVC 变体 + TTS 一体 | 重（训练+推理同仓） | 与 Genie-TTS(ONNX) 对照 |
| fish-audio | Apache-2.0 | 端到端 TTS+转换 | 重 | 备选 |
| 自研（蒸馏复刻） | 本仓 | 按 B1 数据流从零拼装 | 中 | 不推荐（轮子已在 rvc-python） |

## 二、与蒸馏文档 B2 组件表对照

| B2 组件 | rvc-python 覆盖 | 缺口 |
|---------|----------------|------|
| RVCFilter（总入口/分块/缓存） | 部分（推理管线） | 试听 LRU 缓存需自建 |
| IF0Predictor（Crepe/RMVPE 可插拔） | ✅ | — |
| ContentVec | ✅ | — |
| OnnxRVC | ✅ | — |
| RVCVoiceProvider（音色库） | 部分 | 需按 asset manifest（W100-03）接 |

## 三、接入架构建议（≥3）

1. **独立服务优先**：RVC 推理（onnxruntime + 模型 ~数百 MB）建议独立进程/服务，经
   manifest（W100-03）管理模型下载与校验，不塞进主进程。
2. **模型下载位置**：与 W100-03 manifest 联动——模型入 `assets/` 清单（tier=voice），
   切换音色即校验 sha256。
3. **GPU 依赖**：CPU 可跑（onnxruntime），GPU 可选加速；试听 LRU 缓存（容量 2）与
   块式处理两个工程模式值得在接入时复刻。
4. **许可证前置**：RVC 模型权重许可各异——接入时逐模型核 LICENSE，不拉来源不明的权重。

## 四、结论

选型：**rvc-python（MIT，全链覆盖）**；接入形态：独立服务 + manifest 模型管理；
本单只评估不实现（按工单边界）。

---
*评估：fe1iscurc0r · 2026-09-10 · 设计参考 handcrafted-persona-engine（无 LICENSE，仅蒸馏）*
