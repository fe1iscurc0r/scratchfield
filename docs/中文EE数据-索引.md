# W98-03 · 中文 EE/EL 数据侧参考索引（CMNEE / Hansel / GuwenEE · 只读）

**上游**（三项数据资产，只读索引、不拉包）：
- Mzzzhu/CMNEE（52★ · **仓内无 LICENSE 文件** · LREC-COLING'24 · 中文军事新闻文档级 EE）
- HITsz-TMG/Hansel（24★ · **无 LICENSE** · WSDM'23 · 中文少/零样本实体链接基准）
- Lyn4ever29/GuwenEE（25★ · **CC-BY**（文件名 LICENCE）· 古文事件抽取语料+基准代码）
**工单**：第三十四期扩轮卷98 · W98-03【评估·只读】

---

## 1. 数据索引表

| 数据集 | 规模 | 标注 schema | 分发渠道 | 许可边界 |
|---|---|---|---|---|
| CMNEE | 17,000 文档 / 29,223 事件；军事领域模式：事件类型 + 11 论元角色 | 文档级事件提及列表（event_list：event_type/trigger/args） | Google Drive / 百度网盘 / 竞赛平台（DataFountain 987） | 仓内无 LICENSE → **只读索引**；竞赛长期评测开放（可参赛式评测，不 redistribution） |
| Hansel | Train 9.88M mentions（Wikipedia 超链）/ Val 9.6K / FS 5.2K / ZS 4.7K；KB=Wikidata | mention/start/end/mention 文本 + EL 标签 | Google Drive | 无 LICENSE → **只读索引**；尾实体泛化测试切片可作 EL 评测参照 |
| GuwenEE | 1000 古文句 / 7 一级 + 72 二级事件类型 / 1928 事件（二十四史） | 句级事件标注 + 基准评测代码 | GitHub Release | **CC-BY**：可下载用于研究（署名）；代码部分同仓 CC-BY |

## 2. 各数据集许可边界说明

- **CMNEE**：无 LICENSE 文件 → 不下载入仓、不 redistribution；可引用论文 + 参加其长期评测；
  军事新闻来源为开源新闻，二次分发风险由数据集方声明承担。
- **Hansel**：无 LICENSE → 同上只读索引；Wikidata KB 本身 CC0，可独立使用。
- **GuwenEE**：CC-BY 明确 → **三者中唯一可下载研究用**（署名即可）；古文 EE 与材料
  文献 EE 同属「书面语+领域 schema」场景，schema 设计可直接参照。

## 3. 与已授粉数据（UUKG/CCKS 只读）的互补关系

- UUKG/CCKS（已授粉，只读）：通用中文 KG/RE 数据 → **RE 段**参照。
- CMNEE：**文档级 EE**（跨句）→ 补 EE 段文档级场景（材料实验记录同为文档级）。
- Hansel：**EL 段**（实体链接）尾实体泛化 → 补 EL 段评测切片设计。
- GuwenEE：**领域 schema + 小样本**范式 → 材料 EE schema 设计最直接参照（可下载）。

## 4. 执行清单

- [x] 三数据集索引表 + 许可边界 + 互补关系
- [ ] （后续）GuwenEE 下载研究用（CC-BY 署名）+ 材料 EE schema 草案对照
