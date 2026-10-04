# Xtalyst wet-dry loop 机制设计 · 木质素 NPs 水热合成优化 · ALPHA-02

> 工单：ALPHA-02（Xtalyst wet-dry loop 机制设计）
> 线：ALPHA（A 线 · 材料计算闭环）｜分支：trae/agent-alpha
> 类型：只读论文 + 机制设计（不写码、不拉代码、不臆造实验数据）
> 论文：Wang et al. (2026)，"Diagnosing and narrowing the simulation-to-real gap in powder X-ray diffraction with a wet-dry agentic loop"，arXiv:2608.22400v1，cond-mat.mtrl-sci（+ cs.MA），72 页
> 落地课题：木质素纳米颗粒（木质素 NPs）水热合成条件优化
> 完成：2026-08-28

## 〇、一句话结论

Xtalyst 的核心是 **recommend → rescan → reanalyze（推荐 → 重扫 → 再分析）** 的 wet-dry 代理闭环：**"干"**（dry）是分析与推荐——快速粗扫跑过"相识别→精修→标定性质预测"三阶段并过可靠性门，门不过时推荐一个数据驱动的精扫窗口；**"湿"**（wet）是真机重测——操作者按推荐窗口重新扫描；**"校正"**（recalibration）是实测回灌、重新标定并收窄模拟-实测 gap。其决定性发现是**"推荐本身（而非单纯重测）才是把样本带过可靠性门的关键"**。把这条闭环授粉到木质素 NPs 水热合成，映射为：**干 = 合成参数批次设计与推荐器，湿 = 合成 + 表征实测（PXRD/DLS/TEM/收率），校正 = 参数修正规则 + 预测模型回标**——把"靠经验试错"升级为"数据驱动的下一轮条件推荐"。

---

## 一、论文档案卡

| 项 | 值 |
|---|---|
| 标题 | Diagnosing and narrowing the simulation-to-real gap in powder X-ray diffraction with a wet-dry agentic loop |
| 作者 | Shaoguang Wang, Weiyu Guo, Ben Fei（HKUST-Guangzhou），Xiaohong Shao, Zhihui Wang 等 |
| arXiv | 2608.22400v1（2026-08-23），cond-mat.mtrl-sci 主分类 |
| 页数 | 72 页，15 图，7 补充表 |
| 系统 | **Xtalyst**：多智能体编排的 PXRD 相识别 + 精修 + 标定性质预测 |
| 关键词结论 | simulation-to-real gap 是**结构性的**（合成去噪对真实谱无提升，校正峰位漂移使检索相关性中位数翻倍+）|

---

## 二、wet-dry loop 循环结构（提炼自论文）

### 2.1 论文原义（PXRD 场景）

```
            ┌─────────────────────────── 湿 (wet) ───────────────────────────┐
            │  真机/实验室重测：operator 按推荐窗口 re-measure（fine scan）      │
            └──────────────────────────────┬─────────────────────────────────┘
                                           │ fine scan 数据回灌
            ┌──────────────────────────────▼─────────────────────────────────┐
            │  干 (dry)：Xtalyst 分析链 + 可靠性门                              │
            │  ① 快速 coarse survey（粗扫）读入                                 │
            │  ② 三分析阶段（跨阶段可靠性门 cross-stage reliability gate）：     │
            │     [相识别] → [精修 R_wp/R_p profile gate] → [标定性质预测]       │
            │  ③ 门判定：PASS → 输出；FAIL → 推荐器 emit 数据驱动的 fine-scan 窗口 │
            └──────────────────────────────┬─────────────────────────────────┘
                                           │ 推荐（recommend）
                                           ▼
                              operator 执行推荐的 re-scan → 回到"干"再分析
```

### 2.2 三环节的输入输出（论文口径）

| 环节 | 名称 | 输入 | 输出 | 门/判据 |
|---|---|---|---|---|
| 干 | 相识别（phase identification） | 粗扫谱图（raw counts） | 候选相（如 Si, mp-149, Fd-3m #227） | chemistry-aware tiered retrieval |
| 干 | 精修（refinement） | 候选相 + 谱 | R_wp / R_p、晶格参数 | profile gate（R_wp 阈值，如 Si 粗扫 R_wp=22.2 → FAIL） |
| 干 | 标定性质预测（calibrated property prediction） | 精修结果 | 性质 + 标定不确定性 | calibrated-uncertainty 门 |
| 湿 | 重测（rescan） | 推荐器给出的 fine-scan 窗口 | 更高质量谱 | —— |
| 校正 | 重标定/再分析 | fine scan 数据 | 新 R_wp / 新相判定 | 门重新判定 |

### 2.3 关键机制结论（授粉要点）

1. **可靠性门是循环开关**：门 PASS 即终止；FAIL 才触发推荐+重扫。论文的"两扫周期"（coarse → fine）是最小闭环单元。
2. **推荐是 load-bearing，而非重测动作本身**：Si 标样从粗扫 R_wp=22.2（门 FAIL）到推荐精扫后 R_wp=16.4 / R_p=8.8（门 PASS）、晶格 a=5.43198 Å，论文明确强调"起决定作用的是推荐，而不是单纯重测"。
3. **gap 是结构性的，不是加噪声能抹掉的**：合成去噪对真实谱无提升；**校正峰位漂移**使检索相关性中位数翻倍+。→ 对应授粉：木质素 NPs 优化里，瓶颈是"表征质量/漂移校正"与"推荐方向"，不是"多做一轮"。
4. **跨阶段可靠性门**把三个分析阶段串成一个整体判定，而非孤立的工具调用。

---

## 三、映射到木质素 NPs 水热合成（干 / 湿 / 校正）

> 用户课题：木质素纳米颗粒（lignin NPs）水热合成条件优化。下述参数范围与指标均为**领域常识级设计假设**，非实测数据，落地前逐项"待真机/实测确认"。

| Xtalyst 环节 | 木质素 NPs 水热合成的对应物 | 输入 | 输出 |
|---|---|---|---|
| **干（dry）— 批次设计 + 推荐器** | 设计下一批水热条件（温度/时间/浓度/pH/溶剂/来源） | 历史批次结果 + 目标指标 | 下一批条件建议 + 参数修正方向 |
| **湿（wet）— 合成 + 表征实测** | 水热合成 → 表征（PXRD/DLS/TEM/收率） | 设计好的条件 | 实测指标集 |
| **校正（correction）— 参数修正 + 回标** | 实测 vs 目标差距 → 修正规则 → 更新推荐模型 | 实测指标 vs 目标 | 新条件 + 模型回标 |

### 3.1 三环节细化

**干（合成参数批次）**：一次"粗扫"= 一组宽范围条件（如 3-4 个温度点 × 3 个时间点 的正交小批次），由推荐器基于规则/回归给出；一次"精扫"= 在粗扫锁定小区间后做 1-2 个聚焦批次。对应论文的 coarse → fine 两扫结构。

**湿（表征实测，实验室即可覆盖）**：

| 表征 | 测什么 | 门/判据（设计假设） |
|---|---|---|
| **PXRD** | 结晶度、峰位(2θ)、相/无定形程度 | 峰可辨/信噪比足够；峰位漂移对照标准校正（对应论文峰位漂移发现） |
| **DLS** | 水合粒径 Z-average、多分散指数 PDI | PDI ≤ 0.3 视为分布均匀（待确认） |
| **TEM** | 干态形貌、粒径、球形度 | 形态均一/无严重团聚 |
| **收率** | NPs 干重 / 投入木质素 | 达到课题目标下限（待确认） |

**校正（参数修正策略）**：见 §六 规则表。核心是"从差距推导下一轮条件方向"，并把新实测回灌进推荐器（一期为规则表，二期为可拟合的回归模型）。

---

## 四、对比现有工作流 + 闭环收益（量化，诚实标注假设）

**现有工作流（靠经验调参）**：定一批条件 → 合成 → 表征 → 靠经验判断"哪不好、怎么改" → 再试下一批。缺陷：每轮只利用"最后一次结果"的单点反馈，修正方向主观，试错轮次随参数维度上升。

**闭环后（wet-dry 推荐）**：

| 维度 | 现有（经验） | 闭环（推荐器） | 收益（设计假设，待实测） |
|---|---|---|---|
| 反馈利用 | 单点主观判断 | 历史批次全量 + 差距驱动的方向推荐 | —— |
| 试错轮次 | 经验上 10 轮量级 | **估计 4-6 轮**（论文两扫周期类比） | 减半量级，**待真机确认** |
| 表征浪费 | 每轮全表征 | 门不过才触发"精扫/补测"，避免对失败批次做全套 | 节省表征工时 |
| 可复现性 | 靠个人经验 | 规则表 + 推荐日志可追溯 | 可复盘 |

> 诚实标注：上述"10 轮→4-6 轮"是**设计估计**，非实测；论文在 PXRD 的收益（R_wp 22.2→16.4、检索相关性翻倍）是其自身模态的实测，**不能直接外推**到木质素 NPs 合成收率，只能作为"推荐驱动比盲目重测更省轮次"的机制性依据。

---

## 五、闭环伪代码

```python
# 木质素 NPs 水热合成 wet-dry 闭环（设计伪代码，非可执行实现）
# 一期：规则表推荐器；二期：回归模型。不臆造实验数据，缺值标 None=待实测。

def wet_dry_loop(target, max_batches):
    # 目标指标（设计假设，待确认）
    # target = {"yield": 0.30, "pdi_max": 0.30, "d_mean_nm": (100, 300)}

    history = []                       # 历史批次：条件 -> 实测
    conditions = coarse_survey_grid()  # 干：粗扫正交小批次（温度×时间×浓度）

    for batch in range(1, max_batches + 1):
        # ---- 湿（wet）：合成 + 表征 ----
        measured = synthesize_and_measure(conditions)   # PXRD / DLS / TEM / 收率
        history.append({"conditions": conditions, "measured": measured})

        # ---- 干（dry）：可靠性门 + 差距分析 ----
        verdict = reliability_gate(measured, target)
        # verdict 逐指标：PASS / FAIL / DRIFT（漂移需先校正）

        if all(v == "PASS" for v in verdict.values()):
            return {"status": "PASS", "conditions": conditions,
                    "measured": measured, "history": history}

        # ---- 校正（correction）：规则表修正 + 推荐下一轮 ----
        conditions = recommend_next(history, target, verdict)
        # 一期：规则表（见 §六）；二期：拟合回归模型给出方向+幅度

        if conditions is None:
            return {"status": "BLOCKED", "reason": "规则表无法给出下一步，"
                    "需补表征或人工介入", "history": history}

    return {"status": "MAX_BATCHES", "history": history}

def reliability_gate(measured, target):
    verdict = {}
    if measured.get("pdi") is None or measured["pdi"] > target["pdi_max"]:
        verdict["size"] = "FAIL"                 # DLS 分布不均
    if measured.get("yield") is None or measured["yield"] < target["yield"]:
        verdict["yield"] = "FAIL"                # 收率不足
    if measured.get("pxrd_drift") == True:
        verdict["pxrd"] = "DRIFT"                # 峰位漂移：先校正再判定
    # TEM/PXRD 结晶度等逐项补；缺测项标 None 不臆造
    return verdict
```

> 伪代码仅为机制表达，`synthesize_and_measure` 是真实实验步骤，不可被模拟替代；`reliability_gate`/`recommend_next` 的阈值与规则为**设计假设**，落地前逐项标定。

---

## 六、参数表（可调参数 / 实测指标 / 校正规则）

### 6.1 可调参数（干侧设计空间）

| 参数 | 符号 | 设计范围（假设，待确认） | 说明 |
|---|---|---|---|
| 水热温度 | T | 140–220 °C | 影响成核/生长与结晶度 |
| 保温时间 | t | 2–24 h | 影响粒径与收率 |
| 木质素浓度 | C | 1–20 mg/mL | 影响粒径与团聚 |
| 溶剂体系 | S | 纯水 / 乙醇-水混合 | 影响分散与形貌 |
| pH / 碱浓度 | pH | 酸性–碱性（NaOH 等） | 影响溶解/沉淀路径 |
| 木质素来源 | L | 碱木质素 / 酶解木质素 / 其他 | 影响分子量与官能团 |

### 6.2 实测指标（湿侧）

| 指标 | 手段 | 目标方向（假设，待确认） |
|---|---|---|
| 质量收率 | 烘干称重 | 达到课题下限 |
| 粒径 Z-average | DLS | 目标区间（如 100–300 nm） |
| 多分散指数 PDI | DLS | ≤ 0.3（分布均匀） |
| 结晶度/峰位 | PXRD | 峰可辨 + 无异常漂移 |
| 形貌/球形度/团聚 | TEM | 均一、无明显团聚 |

### 6.3 校正规则（湿 → 干）

| 实测现象（门判定） | 校正动作（recommend_next 规则） | 对应论文机理 |
|---|---|---|
| PDI 过大（分布不均） | 提高超声/搅拌强度，或调溶剂比例、降浓度 | gap 收窄靠"校正"而非加数据 |
| 粒径超上限 | 升温度/延时间（促生长）或调 pH | 推荐方向决定成败 |
| 粒径低于下限 | 降温度/缩时间或提浓度（促成核） | —— |
| 收率不足 | 升温度/延时间，检查前驱体投料比 | —— |
| PXRD 峰位漂移 | **先做角度/样品校正再判定**（对照标准样） | 论文"峰位漂移校正使相关性翻倍" |
| PXRD 峰弱/无定形 | 升温度/延退火，或增浓度 | —— |
| TEM 明显团聚 | 调溶剂/表面活性剂/pH | —— |

> 规则表方向为**设计假设**；具体幅度（升多少度、延多久）需一期真机批次标定后再定，不臆造数值。

---

## 七、落地阶段（一期表格 / 二期自动化）

### 一期：表格驱动（人工在环，最快可跑）

- 用 Markdown/CSV 表格记录批次：条件列 × 实测指标列 × 门判定列 × 下一轮条件列（即 §六 三张表实例化）。
- 每轮"干"= 查规则表填下一批条件；"湿"= 实验室合成+表征；"校正"= 手动填规则表并回写。
- 交付物：批次记录模板 + 规则表 + 推荐日志，回写 ELN（对应 SPEC-18 模块 A/B）。

### 二期：自动化（推荐器 + 模型回标）

- `recommend_next` 从规则表升级为数据驱动模型（如贝叶斯优化 / 高斯过程 / 随机森林回归，对接 SPEC-18 模块 B 的 maml+RF/BP 底座）。
- 表征数据（PXRD/DLS/TEM/收率）结构化入库（对应 SPEC-18 模块 E 数据工具台）；PXRD 谱图可后续接入 ALCHEMI/相识别能力（ALPHA-01 授粉点的交叉）。
- 可靠性门做成可配置阈值；漂移校正作为表征前处理步骤固化。

| 阶段 | 推荐器 | 数据记录 | 门判定 | 自动化程度 |
|---|---|---|---|---|
| 一期 | 规则表（人工查表） | 表格/CSV | 人工对照阈值 | 人工在环 |
| 二期 | 回归/贝叶斯模型 | 结构化库 + ELN | 可配置自动判定 | 半自动（真机实验仍需人） |

---

## 八、可考数据源 + 设计假设诚实标注

**可考数据源（是否 PXRD 够用）**：
- **PXRD 实验室即可覆盖**，是闭环的"主表征"：能判结晶度/相/峰位漂移，且与论文模态同源，是可靠性门的首选判据。
- **DLS/TEM 需看设备**：DLS 若实验室有粒度仪即可；TEM 属外送/平台资源，可能成为节拍瓶颈——设计上把 TEM 设为"门 FAIL 时才补测"的精扫项，非每轮必测。
- **收率**：烘干称重即可，零额外设备。
- 结论：**PXRD + 收率 + DLS 足够支撑一期闭环**；TEM 作为二线确认手段。

**设计假设清单（均待真机/实测确认）**：
1. §六 参数范围与阈值（温度/时间/浓度/PDI/收率）为领域常识假设，未实测。
2. §四 试错轮次"10→4-6"为设计估计，非实测。
3. 校正规则方向为假设，幅度需一期标定。
4. 论文 PXRD 收益不可直接外推到合成收率，仅作机制依据。
5. 一期"人工在环"是当前工程现实；真机湿环节不可自动化模拟。

---

## 九、验收 grep 项

```bash
# 本设计自检（ALPHA-02 验收）
grep -q "recommend.*rescan.*reanalyze\|推荐.*重扫.*再分析" docs/xtalyst-wetdry-木质素NPs-设计.md
grep -q "for batch\|for batch in" docs/xtalyst-wetdry-木质素NPs-设计.md   # 闭环伪代码
grep -q "可调参数\|实测指标\|校正规则" docs/xtalyst-wetdry-木质素NPs-设计.md   # 参数表
grep -q "PXRD" docs/xtalyst-wetdry-木质素NPs-设计.md                     # 可考数据源标注
grep -q "待真机\|待确认\|设计假设" docs/xtalyst-wetdry-木质素NPs-设计.md    # 诚实标注
```

---

*执行：智能体 ALPHA · 2026-08-28 · 只读论文 + 机制设计线（A 线）*
