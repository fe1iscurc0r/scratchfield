# 中文远监督 RE + THUNLP NRE 评估（KG 中文关系抽取双件）

> 2026-09-08 · 卷80 W79-05 · 评估（不写实现）
> 上游：xiaofei05/Distant-Supervised-Chinese-Relation-Extraction（MIT，★384）
>       + thunlp/Chinese_NRE（MIT，★274，ACL2019 多粒度注意力）

## 一、项目定位

- DS-CRE：远监督弱标注中文关系抽取（用知识库自动标注训练语料）。
- Chinese_NRE：清华 NRE 模型族（多粒度注意力），中文关系抽取标准参照。

## 二、架构拆解

- DS-CRE：远监督标注 → 去噪 → 关系分类（弱监督信号扩展）。
- Chinese_NRE：句子级/袋级注意力机制（ACL2019 多粒度 attention）。

## 三、与本仓对照

SPEC-G1（DeepKE）已立，本两件为**监督信号扩展 + 模型对照系**——同 THUNLP 生态，功能部分重叠，作对照非重复组件。

## 四、可落地借鉴点（≥3）

1. **远监督弱标注管线**：知识库→自动标注→噪声过滤，可扩展 DeepKE 的训练数据。
2. **袋级注意力去噪**：多实例学习处理远监督噪声，可并入现有 RE 管道。
3. **中文关系 schema 对齐**：与 DeepKE 的标签体系对照，统一 KG RE 输出。

## 五、许可裁定

均 MIT：可直接借鉴（数据+方法）；与 DeepKE 互补方案——DeepKE 主流程 + 本两件监督信号/模型对照。

---
*评估：fe1iscurc0r · 2026-09-08 · 基于上游公开文档，未 clone 源码*
