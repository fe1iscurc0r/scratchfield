# 工单 262 · 超限战轮 46 设备完整性层授粉落地（6 P0 全部进施工 · 16 候选 / 9 暂缓 / 3 排除 / 4 许可纠正）

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-262 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_262.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-262-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_262.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-19
> **触发**：师傅 10-19 在 QQ 下令"把授粉、论文、日报全部转换成工单"。本单对应**授粉**类（**轮 46**，2026-10-19 15:06 沈遥落盘的最新一期授粉报告）。
> **素材漏斗**：`docs/超限战轮46-设备完整性层-腐蚀回路与损伤机理与剩余寿命-授粉报告-2026-10-19.md`（218 行 / 19 KB）
> **前序**：轮 45 = `docs/超限战轮45-过程安全与工厂语义层-…-2026-10-18.md`（10-18 落盘），对应施工单 #TODO（已合 PR 链上）
> **守卫**：anti_hallucination_guard FAIL=0 / WARN=46（WARN 全部在报告自检命中或已分类）

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 29 候选全部 `gh api` 实核（星数/许可/archived） | ✅ | 见授粉报告 §一 候选清单 |
| 2 | 4 条许可纠正写明 | ✅ | NASA-1.3 / openturns GPL-3.0 / fenics BSD-style / 0 字节 LICENSE |
| 3 | 6 P0 全部给出"落地物 + 验收不变量" | ✅ | 见授粉报告 §六 |
| 4 | 5 项 P0 真正要施工的代码 | ❌ | 本工单任务 A-E |
| 5 | 1 项 P0 只出 SPEC | ❌ | 本工单任务 F |
| 6 | 与 45 轮 P&ID/pyDEXPI 落地线的衔接点 | ⚠ | 见 §6 关联，本工单**不碰** 45 链 |

**核心痛点**：
- 41/43/44/45 四轮把图纸、设备、运行、风险四层都铺到了"图"上，但**图上的设备被假设为永生**——45 在 P&ID 加 `hasStream / hasMaterialOfConstruction` 时，缺一条 `hasDegradation` 边
- `mcpserver/graph_memory_adapter/engine.py:191 ingest_entities` 接受任意 `type` 字符串，**只差节点类型约定**，不需要改引擎
- `device_metrics` 表只有电子设备健康（cpu/mem/status/restart_count），**没有工艺设备退化量**（壁厚/振动/温差/压力循环）
- **RBI（API 580/581）开源侧是荒地**（最高 5★，学生 notebook），定量 PoF×CoF 引擎得自己写

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | 把轮 46 的 6 项 P0 全部进施工（5 立即授粉 + 1 仅 SPEC），16 候选中的 5 项并码入库，9 项暂缓存档，3 项排除归类 |
| **M** Measurable | ① 5 项并码每项 ≥ 1 个验收不变量命中（见 §六）；② SPEC 1 份含三层接口签名 + NASA-1.3 留痕；③ damage-mechanisms.json ≥ 30 条且不含 .owl 原文；④ pytest 全过；⑤ 守卫 FAIL=0 |
| **A** Achievable | 5 项并码每项 ≤ 200 行；轮 46 已写清算法骨架（KMeans 腐蚀回路、POD 曲线、AE 读 pridb）；`vallenae` 6.2 MB、`otpod` 26 MB 可 pip |
| **R** Relevant | 师傅本行（生物质能源/材料/碱法蒸煮 caustic corrosion）直接对上；邵长优惠课题"木质素→水凝胶"短期不触发完整性，但**奖学金/经费材料 / 国家奖 / 论文 Figure 复用**这条线可吃；与 41/43/44/45 形成"图纸→设备→运行→风险→完整性"五层闭环 |
| **T** Time-bound | 1 周（W2 与 WO-263/264 同期 review，**不抢 45 链**） |

## §2 · 任务清单

### 任务 A · P0-3 腐蚀回路聚类（**难度最低 / 收益最高 / 立即**）

`mcpserver/graph_memory_adapter/engine.py` 加 `cluster_corrosion_loops`：

- 输入：`nodes: list[dict]`, `features_categorical: list[str]`, `features_numerical: list[str]`, `max_diff: list[float]`
- 算法骨架（直接照搬授粉报告 §2.3，1★ `andikarachman/Automated-Corrosion-Loop-Development`）：
  ```python
  df = pd.DataFrame([n["attrs"] for n in nodes])
  groups = df.groupby(features_categorical)
  loop_nodes = {}
  for keys, members in groups:
      m = members[features_numerical].values
      for k in range(1, len(members)+1):
          km = KMeans(n_clusters=k, random_state=42).fit(m)
          if max(km.inertia_) < threshold: break
      loop_nodes["-".join(map(str,keys))] = members.index.tolist()
  return loop_nodes
  ```
- 输出：dict[label → node_ids]，调用方把每个 label 挂成 `corrosion_loop` 子图节点
- 验收：`grep -c "def cluster_corrosion_loops" mcpserver/graph_memory_adapter/engine.py` = 1
- 测试：给 5 个 P&ID 节点（碳钢/碱液/150°C × 2、不锈钢/中性/80°C × 2、碳钢/水/40°C），聚类应得 3 个 label

### 任务 B · P0-1 NDE 契约 → inspections 表（**立即 / 最低难度**）

`docs/设备台账-schema-草案-2026-09-11.md` 加第 4 张表：

- 列：`asset_id, method(UT/RT/AE/EC), ts, setup_ref, result, sizing, pod, coverage`
- `pod` 列存检出概率（来自任务 D 的 otpod 计算结果）
- `coverage` 列存检验覆盖率（被检面积/总面积）
- 同时落 `schemas/NDE-FileFormat-Schema-3.3.0.json` 副本（来自 `Evident-Industrial/NDE_Open_File_Format` v3.3）
- 验收：`sqlite3 devices.db ".schema inspections"` 含 `pod` 与 `coverage` 两列；JSON Schema 文件可被 `jsonschema` 包解析
- 关联：与 WO-263/264（同期日报/论文转工单）共用 `devices.db`

### 任务 C · P0-2 vallenae AE 接入（**中难度 / 中高收益**）

`mcpserver/integrity_ae/`：

- 包装 `vallen-systems/vallenae`（MIT，54★），不并码
- 核心函数：`read_pridb(path) -> DataFrame`, `detect_hits(pridb, tradb, threshold_db) -> DataFrame`, `cluster_events(hits, max_dt_us) -> list[EventGroup]`
- 样例：用项目 `examples/` 下的 pridb/tradb 跑通
- 验收：`python -m pytest mcpserver/integrity_ae/ -q` 全过；样例读出的 hit 数 > 0

### 任务 D · P0-4 otpod POD 曲线（**中难度 / 高收益**）

`mcpserver/integrity_pod/`：

- 包装 `openturns/otpod`（LGPL-3.0，10★），不并码
- 核心函数：`hit_miss_pod(df_hit_miss, a) -> PODCurve`、`kriging_pod(signal_data, a) -> PODCurve`、`sobol_indices(model) -> dict`
- 依赖：openturns（GPL-3.0）—— 容器里先用解析式近似（`pod = 1 - exp(-(a/a90)^k)`）跑通，openturns 容器化时再加
- 验收：`python -c "from mcpserver.integrity_pod import pod_curve, sobol_indices"` 无异常；样例 POD 在 a90 处单调

### 任务 E · P0-6 damage-mechanisms.json（**中等难度 / 高收益 / 自写**）

`docs/damage-mechanisms.json`（**自写，不搬运 .owl 原文**）：

- 结构：`{"mechanisms": [{"id": "caustic_corrosion_low_alloy_steel", "name": "Caustic Corrosion (Low Alloy Steel)", "materials": ["low_alloy_steel", "carbon_steel"], "fluids": ["NaOH_2_to_15pct"], "phase": ["liquid"], "temp_range_C": [80, 200], "rate_mm_per_y": [0.1, 1.0], "indicators": ["wall_thickness", "UT_amplitude"], "mitigation": ["MOC upgrade to Ni-Cr", "reduce NaOH conc"]}, ...]}`
- 来源：API 571 标准术语（公开标准）+ 轮 46 报告 §2.1 的 41 类目结构
- **许可红线**：文件内**不允许**出现 `Damage_Mechanism_Identification_Ontology.owl` 的原文片段（哪怕术语也是从标准来的，不是从该仓搬的）
- 验收：`python -c "import json;d=json.load(open('docs/damage-mechanisms.json'));print(len(d['mechanisms']))"` ≥ 30；`grep -c "Damage_Mechanism_Identification_Ontology" docs/damage-mechanisms.json` = 0

### 任务 F · P0-5 RUL SPEC（**仅 SPEC / 不并码**）

`docs/SPEC-integrity-rul-2026-10.md`：

- 退化状态向量：`State = (wall_thickness_mm, fatigue_cycles, corrosion_rate_mm_per_y, last_inspection_ts)`
- 失效阈值：`Thresholds = {wall_thickness_min: float, fatigue_cycles_max: int, ...}`（按设备类型分别定义）
- 观测模型：`Observation = (UT_reading_mm, AE_event_rate, RT_defect_size, EC_noise_mV)`
- 预测接口：`predict_to_eof(state, thresholds) -> ToEPredictionProfile`（照搬 progpy §2.2 的命名）
- **留痕**：文件内必须出现 `NASA-1.3` 至少 1 次（许可留痕）
- 验收：`grep -c "NASA-1.3" docs/SPEC-integrity-rul-2026-10.md` ≥ 1；SPEC 含三段接口签名

### 任务 G · 9 暂缓 / 3 排除 归档

新文件 `docs/pollination/round-46-deferred.md`：

- 9 暂缓清单：10/19/20/22/23/24/25/26/28（无 LICENSE 或 LICENSE 不清）
- 3 排除：27（archived）、28/29（已合并 progpy）
- 每行写明"暂缓原因 + 二次激活路径"（如"`bit628/RapidX-Annotator` 若作者补 LICENSE，可在下一轮 re-eval"）

## §3 · 验收标准

| 项 | 阈值 | 验收命令 |
|---|---|---|
| 1. P0-3 腐蚀回路聚类 | 函数存在 + 测试通过 | `grep -c "def cluster_corrosion_loops" mcpserver/graph_memory_adapter/engine.py` = 1 |
| 2. P0-1 inspections 表 | 含 pod + coverage 列 | `sqlite3 devices.db ".schema inspections"` |
| 3. P0-2 vallenae AE | 样例 hit 数 > 0 | `pytest mcpserver/integrity_ae/ -q` |
| 4. P0-4 otpod POD | import 不异常 + 样例 POD 单调 | 见任务 D 验收 |
| 5. P0-6 damage-mechanisms.json | ≥ 30 条 + 无 .owl 原文 | 见任务 E 验收 |
| 6. P0-5 RUL SPEC | 三段接口签名 + NASA-1.3 留痕 | 见任务 F 验收 |
| 7. pytest 全过 | 0 失败 | `pytest -q` |
| 8. 反幻觉守卫 FAIL=0 | 0 | `python tools/anti_hallucination_guard.py --check-report docs/超限战轮46-…-2026-10-19.md` |
| 9. 不抢 45 链 | `git diff --stat -- apiserver pydexpi` 0 行 | `git diff --stat main -- apiserver pydexpi \| wc -l` = 0 |

## §4 · 关联

- **WO-263**：GitHub 扫货日报 10-19 转化（同期同批 15 项）→ 见姊妹工单
- **WO-264**：论文日报转化（待 `ad17cd9d341f` cron 02:00 跑批后确认是否有新产出）
- **轮 45 P&ID/pyDEXPI 落地线**：不抢，**本工单在 `corrosion_loop` 处汇合**（45 的 `hasDegradation` 边 + 46 的 `cluster_corrosion_loops` 函数 = 图上第一次有"回路"这个管理单元）
- **WO-261（10-18 token 账本审计）**：与本工单独立，不交叉
- **WO-246/247/248（10-19 MCP/状态.db/SSH 收口）**：本工单同期，PR 一起合

## §5 · 风险与边界

| 风险 | 缓解 |
|---|---|
| 任务 D 依赖 openturns 容器化慢 | 用解析式近似先跑通；openturns 单独提 issue 不在本工单 |
| 任务 E 整理 41 类目耗时 | 可拆 2 期（先 30 类 + 后 11 类），任务 G 的验收阈值是 ≥ 30 |
| 任务 A 改 `engine.py` 触及 45 链 | 不改 `ingest_entities` 签名，只加新函数 |
| 任务 C vallenae 样例数据占体积 | 不入仓；放 `tests/fixtures/` 在 `.gitignore` |
| 任务 F 仅 SPEC 引起"为什么不给代码"质疑 | 留痕 NASA-1.3 + §二.2 解释 |

**不在本工单范围**：
- 改 45 链（pyDEXPI / `hasDegradation` 边）
- 9 暂缓项的二次激活（下一轮 sweep 再说）
- 28/29（prog_models/prog_algs）—— 已合并 progpy，单独仓停更，归类

## §6 · 落地物清单（最终交付）

| 类别 | 文件 | 落点 |
|---|---|---|
| P0-3 聚类 | `mcpserver/graph_memory_adapter/engine.py` | 新增 `cluster_corrosion_loops` 函数 |
| P0-1 表 | `docs/设备台账-schema-草案-2026-09-11.md` | 第 4 张表 `inspections` |
| P0-1 契约 | `schemas/NDE-FileFormat-Schema-3.3.0.json` | 副本（来自 Evident-Industrial） |
| P0-2 AE | `mcpserver/integrity_ae/{__init__.py, reader.py, detector.py, tests/}` | 4 文件 |
| P0-4 POD | `mcpserver/integrity_pod/{__init__.py, hit_miss.py, kriging.py, sobol.py, tests/}` | 5 文件 |
| P0-6 JSON | `docs/damage-mechanisms.json` | 1 文件，≥ 30 条 |
| P0-5 SPEC | `docs/SPEC-integrity-rul-2026-10.md` | 1 文件，3 接口签名 |
| 归档 | `docs/pollination/round-46-deferred.md` | 1 文件，9+3=12 行 |

## §7 · 编号防撞

- **指令文件**：`TRAE_WORKORDER_PROMPT_AGENT_262.md`（仓库根，input）
- **施工记录**：本文件 `docs/WO-262-*`（output）
- 与已发的 `TRAE_WORKORDER_PROMPT_AGENT_*` 不撞号（已用 254~261，**262 下一号**）
