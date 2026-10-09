# 材料线工具盘点（工单213 任务一）

> 日期：2026-10-08 ｜ 范围：`mcpserver/material_science/`（19 工具 / 7488 行）+ `docs/material*` + 授粉报告
> 判定口径：**可否邵长组（木质素 NPs → 水凝胶/共熔凝胶 → 水下电子/太阳能蒸发）实验数据直用**
> —— ✅ 直用 / 🟡 改造后可用 / ⚪ 参考级 / ❌ 不可用

---

## 0. 一句话总结

**工具面宽但"最后一公里"缺**：19 个工具里与邵长组数据**直接对口的只有 BO 优化和（补上的）LOO 回归**；
文献/物性查询类对木质素体系覆盖薄；**本科数据快通道（任务二）正是补的这块**。

---

## 1. mcpserver/material_science 工具全表（19 个，manifest 实测）

### 1.1 文献/知识线（6 个）

| 工具 | 做什么 | 数据格式 | 依赖 | 直用判定 |
|---|---|---|---|---|
| `literature_search` | 文献检索（academic_bridge） | JSON 结果 | academic API | 🟡 检索通用，木质素专项需自建关键词组 |
| `formula_query` | 化学式查询 | JSON | 内置表 | ⚪ 通用 |
| `property_calc` | 物性计算 | JSON | 内置 | ⚪ 通用 |
| `phase_diagram` | 相图 | JSON | 内置 | 🟡 共熔体系**相变温度**或可用，需试 |
| `crystal_info` | 晶体信息 | JSON | 内置 | ⚪ 无机向 |
| `thermal_analysis` | 热分析 | JSON | 内置 | 🟡 DSC/TGA 曲线解析可对接共熔凝胶数据 |

### 1.2 MatChat 桥（3 + 1 登录态）

| 工具 | 做什么 | 依赖 | 直用判定 |
|---|---|---|---|
| `matchat_search` / `matchat_chat` / `matchat_extract` | 浏览器自动化访问 MatChat（材料问答） | **Playwright persistent context** | 🟡 见 §2 专项分析 |
| `matchat_login_check` | 登录态检查 | 同上 | 同上 |

**§2 MatChat 登录/反爬专项（实测代码口径）**

- 机制：`launch_persistent_context(user_data_dir=…)` 复用浏览器配置目录 → **登录态/cookie 跨进程保留**
  （`matchat_bridge.py:152`）；`headless` 默认 **False**（`persistent` 模式刻意有头，便于用户手动登录）；
  `LOGIN_URL_PATTERNS = ["login","passport","account","auth"]` + `ensure_login()` 探测登录按钮（:344-370）。
- **能否绕过登录/反爬：不能也不应**。桥的设计是「**首次人工登录 → 之后自动复用会话**」：
  - ✅ 好消息：登录只需做一次（persistent context 存 cookie），之后的 `matchat_*` 调用全自动；
  - ⚠️ 限制：cookie 过期需**再次人工登录**（无凭证自动续期）；反爬层面依赖 Playwright 指纹，
    无验证码破解（遇验证码需人工）。
  - **结论**：不是"绕过"，是"登录一次、长期复用"。对邵长组可行（配置一次即可），
    但**不保证无人值守长跑**。

### 1.3 生物预测线（2 个）—— 精度账（实测口径）

| 工具 | 做什么 | 依赖 | 直用判定 |
|---|---|---|---|
| `biopred_predict` | 生物性能预测 | **纯 stdlib**（sqlite3 + math + re，无 ML 框架） | ❌ 见 §3 |
| `biopred_suggest` | 实验建议 | 同上 | ❌ |

**§3 biopred 精度账（如实：没有可报的精度）**

`biopred.py` 的实现是**规则/启发式 + SQLite 存储的候选推荐**（`exploration_score` 打分，:245），
**不是统计学习模型** —— 代码里**没有任何 R²/RMSE/交叉验证指标**（grep 实测零命中）。
- 对"预测精度"的诚实回答：**它不做回归预测**，输出的是规则打分的实验建议；
- 对邵长组：木质素 NPs 的粒径→性能**回归**需求它覆盖不了 → 这正是任务二 LOO 模板补的位。

### 1.4 优化/实验记录线（4 个）

| 工具 | 做什么 | 依赖 | 直用判定 |
|---|---|---|---|
| `bo_recommend` / `bo_record` / `bo_get_params` | 贝叶斯优化循环（bo_optim/） | sklearn 级 | ✅ **配方优化直用**（水凝胶 配方→性能 BO 已是现成范式） |
| （`experiment_records_template.csv`） | 实验记录模板 | CSV | ✅ 与任务二 data_schema 对齐 |

### 1.5 合成 RAG 线（4 个）

| 工具 | 做什么 | 依赖 | 直用判定 |
|---|---|---|---|
| `synth_search` / `synth_add` / `synth_validate` | 合成方案检索/入库/校验 | 纯 stdlib | 🟡 结构现成，木质素 NPs 合成条目需自建库 |

---

## 2. docs/ 材料线文档盘点

| 文档 | 内容 | 与邵长组关系 |
|---|---|---|
| `MATERIAL-STAGE5A-SPEC-v1.md` + `TRAE_PROMPT-material-stage5a.md` | 材料线 Stage5A SPEC | 框架文档 |
| `material-symbolic-regression-勘察报告.md` | 符号回归勘察 | 🟡 与 LOO 回归互补（可解释公式 vs 预测精度） |
| `materials-volume-m153-m197-评估.md` / `m38-m129-评估.md` | 两批材料论文评估 | 参考级 |
| `docs/material-pollination/`（2 份） | 2610.06436 稀疏 AFM→宏观力学 / 2610.06155 纳米颗粒分散度过程链 | ⭐ **直接相关**：前者的"稀疏纳米观测→宏观力学分布"正是木质素 NPs→水凝胶缺的桥（候选来源）；后者的 PSD 过程链优化对分散稳定性有借鉴 |

---

## 3. 缺口 → 任务二的落点

| 邵长组数据流 | 现有覆盖 | 缺口 |
|---|---|---|
| 木质素 NPs：粒径(DLS)/PDI/zeta → 分散稳定性预测 | ❌ 无 | **LOO 回归模板 + 字段定义**（本次补） |
| 水凝胶：溶胀率/压缩模量 → 性能-配方回归 | bo_optim ✅（优化向） | **小样本回归向**（本次补）+ BO 可接续 |
| 共熔凝胶：相变温度/热容 → 热力学模拟 | `phase_diagram`/`thermal_analysis` 🟡 | 先实测这两个工具的覆盖面，不够再立项 |

> ⚠️ **依赖声明（重要）**：工单 213 任务二写的"复用工单206 任务三已产出的
> `loo_regression_template.py`、共用水电 `research/material/lignin-np-regression/`" ——
> **实测该产出在 main 上不存在**（远端树 + 本地均无 `research/material/` 目录），
> 工单 206 任务三从未执行。**本单一并补做**（见 `research/material/` 交付）。
