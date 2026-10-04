# SatNOGS / gr-leo 评估（W71-05）

> 上游：librespacefoundation/satnogs/satnogs-db（21★，Python）+ gr-leo（17★，C++）｜ <https://gitlab.com/librespacefoundation/satnogs/satnogs-db>
> 许可：SatNOGS AGPL-3.0 / gr-leo GPL-3.0（仅参考设计）

## 1. 项目定位

- **SatNOGS**：开放卫星数据平台——全球地面站网络 + 观测调度 + 遥测数据汇聚（卫星过境自动安排观测）。
- **gr-leo**：卫星-地面站信道仿真器（GNU Radio），仿真多普勒频移、衰落、链路预算。

## 2. 架构拆解

- SatNOGS：调度服务（轨道计算 TLE → 过境时间 → 地面站分配）+ 数据后端 + 开放 API。
- gr-leo：信道模型（多普勒、大气衰减、链路预算）以 GNU Radio 块形式注入信号链。

## 3. 与本仓对照

| 维度 | SatNOGS/gr-leo | 本仓 |
|---|---|---|
| 卫星调度 | 全球网络调度 | IC-705 卫星线（单站）|
| 信道仿真 | 多普勒/衰落/链路预算 | radio_brain 链路建模 |
| 数据 | 开放卫星遥测库 | — |

## 4. 可落地借鉴点（≥3）

1. **TLE 轨道→过境→调度闭环**：借鉴 SatNOGS 的「TLE 计算过境时间自动调度观测」，为 IC-705 卫星
   接收做自动化过境提醒/跟踪。
2. **多普勒/衰落信道仿真**：gr-leo 的信道块可移植为 radio_brain 链路模型的「卫星场景」扩展，
   用于卫星接收链路预算预演（验收项：接入建议）。
3. **开放数据 API 设计**：卫星遥测数据的开放汇聚/查询接口，借鉴给 radio_brain 的观测数据归档。

## 5. 许可裁定

AGPL/GPL——**只参考设计不融合**；轨道计算与信道模型思想可借鉴，代码不并入。

## 6. 结论（验收项：链路预算接入建议）

建议在 radio_brain 加「卫星过境 + 链路预算」模块：TLE 过境计算（借鉴 SatNOGS）+ 多普勒/衰落预算
（借鉴 gr-leo），为 IC-705 卫星接收提供「何时收、信噪比够不够」的预演。
