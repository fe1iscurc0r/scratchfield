# W98-01 · ahsi/Multilingual_Event_Extraction 勘察（含中文的 ACE 风格 EE）

**上游**：ahsi/Multilingual_Event_Extraction（35★ · MIT · 2017 · CMU LTI）
**勘察方式**：GitHub 浅克隆（D:\wo34-recon\multilingual-ee）+ README/目录阅读
**工单**：第三十四期扩轮卷98 · W98-01【评估】

---

## 1. 项目定位

CMU 多语言事件抽取器：中/英/西三语 ACE 风格 EE（触发词+论元+事件链接），
多语言联合训练、分语测试。输出格式对齐 **2016 TAC KBP EAL**（arguments/
corpusLinking/linking/nuggets 四目录）。中文 EE 段少见的**干净 MIT 老件**——
老但方法通用（特征工程+结构化预测时代），可作 EE 段骨架的「格式与任务分解」参照。

## 2. 架构拆解（顶层实测）

```
preprocessing_2.0/     # 流水线入口：processChinese.sh / processEnglish.sh / processSpanish.sh
outputFormatting/      # 输出格式化 → TAC KBP EAL 四目录
all_predictions_4.0/   # 预测结果组织
（外部依赖：Stanford CoreNLP / MaltParser / LIBLINEAR / Stanford NER + 模型 tarball）
CONFIG.txt + config.py # 外部工具路径配置化
```

要点：
- **任务分解清晰**：触发词检测 → 论元抽取 → 事件链接（nuggets/corpusLinking）三段，
  与 DeepKE 的模块划分可对齐。
- **输出格式标准化**（TAC KBP EAL）：本仓 EE 段若做标注/评测，直接沿用该格式
  可复用公开评测脚本与对照基线。
- **配置外置**（CONFIG.txt 指外部工具路径）：老派但有效的解耦做法。

## 3. 与 DeepKE 的架构差异与融合建议

| 维度 | Multilingual-EE（2017） | DeepKE（本仓已立 SPEC-G1） |
|---|---|---|
| 方法族 | 特征工程 + 结构化预测（LIBLINEAR） | 神经网络（CNN/Transformer 系） |
| 语言 | 中/英/西 | 中文为主 |
| 输出 | TAC KBP EAL 四目录 | DeepKE 自定义 |
| 维护 | 停更（2017） | 活跃 |

融合建议：**方法不融合（代差），格式与任务分解融合**——
1) EE 段标注/评测采用 TAC KBP EAL 输出格式；
2) 触发词→论元→链接三段任务分解照此落 DeepKE 配置；
3) 多语言联合训练思路留作中文+英文材料文献 EE 的长期参考。

## 4. 可落地借鉴点（≥3）

1. **TAC KBP EAL 输出格式**作为本仓 EE 段数据契约（标注/评测/入库 ELN 统一）。
2. **三段任务分解**（触发词/论元/链接）进 DeepKE EE 配置与文档。
3. **processXxx.sh 流水线入口范式**：按语言/领域一个入口脚本 + FILELIST 输入，
   本仓材料文献 EE 批处理照此组织。
4. 模型/工具路径 CONFIG 外置（老派但有效）。

## 5. 许可裁定

- **MIT**：可吞（代码级融合允许，保留版权声明）；但代码代差大，**只借格式与分解**。
- 模型 tarball（CMU 托管）许可另核，本轮不下载不融合。

## 6. 执行清单

- [x] 克隆 + 结构/许可核验 + DeepKE 融合建议
- [x] 借鉴点 4 条 + MIT 可吞判定
- [ ] （后续工单）EE 段数据契约文档（TAC KBP EAL 映射）
