# x-qsl ADIF 工具评估（W71-09）

> 上游：yuzhenwu/x-qsl-amateur-radio-adif-tool（Gitee，15★）｜ <https://gitee.com/yuzhenwu/x-qsl-amateur-radio-adif-tool>
> 许可：NOASSERTION（Gitee 项目，许可未标注）——**许可待核**

## 1. 项目定位

**ADIF**（Amateur Data Interchange Format）格式的业余无线电日志/通联记录工具——解析/生成 ADIF，
管理通联（QSO）记录，用于呼号日志、QSL 卡片确认。

## 2. 架构拆解

- **ADIF 解析/生成**：ADIF 字段（CALL/BAND/MODE/QSO_DATE 等）的读写与校验。
- **通联记录管理**：QSO 增删改查、去重、统计。
- **导入导出**：与常见日志软件（LoTW/eQSL）交换数据。

## 3. 与本仓对照

| 维度 | x-qsl | 本仓 |
|---|---|---|
| 电台日志 | ADIF 通联记录 | IC-705（呼号 BG5GXO）电台线 |
| 现有日志 | 无专门 ADIF 工具 | HamLog（桌面已有）|

**「日志管理 vs 现有方案」结论（验收项）**：本仓已有 HamLog 日志，x-qsl 的价值在**补 ADIF 标准格式
的导入导出**（与 LoTW/eQSL 互通），而非替代现有日志——作为 ADIF 解析模块增量接入。

## 4. 可落地借鉴点（≥3）

1. **ADIF 解析/生成**：ADIF 字段表 + 校验逻辑，可接入 IC-705 电台日志的导入导出（对接 LoTW/eQSL）。
2. **通联记录字段模型**：CALL/BAND/MODE/QSO_DATE/RST 等的规范化建模，借鉴为日志数据结构。
3. **与 LoTW/eQSL 的互操作**：QSL 确认流程，为呼号 BG5GXO 的确认管理提供参考。

## 5. 许可裁定

NOASSERTION——**许可待核**；ADIF 是开放标准格式，格式本身可自由实现（参考其字段模型，不抄代码）。

## 6. 结论

可借鉴（ADIF 格式接入）。建议：给 IC-705 电台线加「ADIF 导入导出」模块，参考其字段模型自研，
对接现有 HamLog。
