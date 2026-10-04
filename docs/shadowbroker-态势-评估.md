# W73-05 Shadowbroker 态势 OSINT 评估

> 上游：github.com/BigBodyCobain/Shadowbroker · AGPL-3.0 · 11K★ · Python

## 1. 项目定位

去中心化全球态势 OSINT 聚合平台：60+ 实时情报源（飞机、船舶、卫星、冲突区、CCTV、GPS 干扰、警务扫描、mesh 无线电节点）汇聚到单一 dark-ops 地图界面。

## 2. 架构拆解

- **多域遥测聚合**：ADS-B 航班 + 船舶 AIS + 侦察卫星 + 震情 + GIS 统一接入。
- **单一面板**：实时地图 + 事件流。
- **去中心化**：含混淆通信协议与信息交换基础设施。

## 3. 与本仓对照

| 维度 | Shadowbroker | 本仓 |
|---|---|---|
| 态势聚合 | ADS-B+卫星+震情 60+ 源 | worldmonitor 情报评估（docs/worldmonitor-情报-评估.md）+ sentinel_intel 实体图谱 |

## 4. 可落地借鉴点（≥3）

1. **多域态势聚合范式**：ADS-B/AIS/卫星/震情统一接入单一面板，可作为我们态势情报面板的数据源组织参考。
2. **60+ 实时情报源清单**：数据源目录可直接作为 sentinel_intel 的扩展清单（合规源优先）。
3. **暗操作地图可视化**：地理空间 + 多域事件的实时可视化，可借鉴到 worldmonitor 面板。

## 5. 许可裁定 + 结论

- **许可**：AGPL-3.0 → **只参考设计不融合**（AGPL 传染性，不抄代码）。
- **结论**：参考「多域聚合 + 态势面板 + 数据源清单」设计，不引入 AGPL 代码；数据源接入走自研 + sentinel_intel。
