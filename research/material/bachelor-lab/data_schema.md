# 本科实验数据 · 填表格式（data_schema）

> 邵长优惠组快通道（工单213 任务二）。**这是给实验员看的填表说明，不是代码。**
> 配套：`quick_import.py`（入库）· `../lignin-np-regression/`（回归预测）。
> 原则：**一张 CSV 一类实验**；列名必须与下表完全一致（区分大小写）；缺失填 `NA`。

---

## 表 A · 木质素纳米粒子制备与表征（lignin_np）

### 制备参数（特征，实验员可控）

| 列名 | 含义 | 单位/类型 | 典型值 | 必填 |
|---|---|---|---|---|
| `sample_id` | 样品编号 | 文本 | LN-2026-001 | ✅ |
| `date` | 实验日期 | YYYY-MM-DD | 2026-10-08 | ✅ |
| `operator` | 实验员 | 文本 | 张三 | ✅ |
| `lignin_type` | 木质素类型 | 文本（分类） | alkali / kraft / organosolv | ✅ |
| `lignin_conc_mg_ml` | 木质素浓度 | mg/mL | 2.0 | ✅ |
| `solvent_ratio` | 溶剂比（良/不良溶剂） | 体积比，数值 | 1:3 填 `3.0` | ✅ |
| `temp_c` | 沉淀温度 | °C | 25 | ✅ |
| `sonication_min` | 超声时间 | min | 10 | ⬜ |
| `stir_rpm` | 搅拌速率 | rpm | 600 | ⬜ |
| `notes` | 备注 | 文本 | pH=9 | ⬜ |

### 表征结果（观测量 → 可作为回归目标）

| 列名 | 含义 | 单位 | 仪器 | 必填 |
|---|---|---|---|---|
| `diameter_nm` | 粒径（DLS，Z-average） | nm | Malvern Zetasizer | ✅ |
| `pdi` | 多分散指数 PDI | 无量纲 0~1 | 同上 | ✅ |
| `zeta_mv` | Zeta 电位 | mV | 同上 | ⬜ |

## 表 B · 水凝胶性能（hydrogel）

| 列名 | 含义 | 单位 | 必填 |
|---|---|---|---|
| `sample_id` / `date` / `operator` | 同表 A | — | ✅ |
| `np_loading_wt` | 木质素 NPs 掺量 | wt% | ✅ |
| `crosslinker_wt` | 交联剂用量 | wt% | ✅ |
| `swelling_ratio` | 溶胀率（Ws/Wd） | 无量纲 | ✅ |
| `compressive_modulus_kpa` | 压缩模量 | kPa | ✅ |
| `water_content_pct` | 含水率 | % | ⬜ |

## 表 C · 共熔凝胶热学（deep_eutectic）

| 列名 | 含义 | 单位 | 必填 |
|---|---|---|---|
| `sample_id` / `date` / `operator` | 同表 A | — | ✅ |
| `hba` / `hbd` | 氢键受体/供体（如 ChCl/EG） | 文本 | ✅ |
| `molar_ratio` | 摩尔比（数值，1:2 填 2.0） | — | ✅ |
| `t_peak_c` | 相变温度（DSC 峰） | °C | ✅ |
| `dh_j_g` | 相变焓 | J/g | ✅ |
| `cp_j_gk` | 热容 | J/(g·K) | ⬜ |

---

## 填表规则

1. **数值列**：纯数字；检测限以下写实际值并在 notes 注明；缺失写 `NA`（不要留空、不要写 `-`）。
2. **分类列**（如 `lignin_type`）：做回归前会被转成 0/1 哑变量（quick_import 自动处理）。
3. **一张表一个 CSV**，文件名建议 `表名_日期.csv`（如 `lignin_np_2026-10.csv`）。
4. 表 A 的表征结果与表 B 的性能做**关联分析**时，用 `sample_id` 对齐。

## 入库与回归（两条命令）

```bash
# ① 校验 + 入库（SQLite + JSONL 双写，坏行只警告不中断）
python quick_import.py lignin_np_2026-10.csv

# ② 回归（示例：配方 → 粒径；把目标列放最后一列即可）
#    quick_import 会同时导出"回归就绪"CSV：features_<表名>.csv
python ../lignin-np-regression/loo_regression_template.py features_lignin_np.csv
```
