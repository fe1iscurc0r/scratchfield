# 工单 238 · 授粉-轮 41 弹药入仓 + RAG 索引 + 6 个授粉落点施工

> **⚠️ 交付状态（2026-10-17 沈遥复核）**：本单要求的交付物**均未落地** —— 全树无 6 个落点目录、无 `coupled/reactor-digital-twin/`。证据与根因见 `docs/workorders/reports/WO-STATUS-2026-10-17.md` §3.2。
> **处置（师傅 2026-10-17「你看着办」授权）**：**复活**为根 `TRAE_WORKORDER_PROMPT_AGENT_259.md`；原单缺的**取料入口**已补齐：弹药包已上传 `fe1iscurc0r/scratchpad-knowledge` Release **`pollination-r41-2026-10-14`**（asset `pollination-r41-biomass-reactor-2026-10-14.zip`，61,512,208 B）。
> 本文件保留为**原始施工记录**，不改内容、不改号。

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-238 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_238.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-238-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_238.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-15
> **触发**：师傅 10-15 13:18 在 QQ 下令"把这三个 cron 产出转成工单"（授粉 / 论文 / 日报），本单负责**授粉**那条
> **素材漏斗**：超限战轮 41 报告 24 原始候选 → 10 可吞（7 MIT + 3 GPL-3 + 1 GPL-3.0/CeCILL-2.1 双许可）+ 11 暂缓 + 3 误判
> **轮 41 报告原文**：`/home/ubuntu/scratchpad/docs/超限战轮41-生物质热化学转化-反应器动力学与神经网络代理弹药-授粉报告-2026-10-14.md`
> **源码包**（59 MB，已瘦）：`/home/ubuntu/http_share/超限战轮41-生物质热化学转化-反应器动力学与神经网络代理-授粉报告-2026-10-14.zip`
> **关联 cron**：`bda7241fa9c3` 授粉流水线-超限战轮（`0 15 * * *`），今天 15:06:32 跑批产出 = 本工单触发源

## §0 · 沈遥已执行动作（物料搬运 + 自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 读轮 41 报告（241 行 / 24.9 KB） | ✅ | 五范式 + 7 轮历史零重复 + 6 个授粉落点 |
| 2 | 读 zip 内部 manifest | ✅ | 10 个仓库完整源码已在包内 |
| 3 | 校验现有 WO 编号 | ✅ | 现有 230-237 占用，新工单起手 **238/239/240** |
| 4 | 跑 `python3 anti_hallucination_guard.py` 程序化守卫 | ⚠️ **未跑**（属 Trae 工作流验收环节） | 验收前必跑（参考日报"防幻觉守卫"铁律 8-23） |

> 物料未上传 GitHub 中转库：轮 41 报告"§八·交付清单"明文写"本轮 push 工作流**待执行**"——这是本工单 §2 的关键目标

---

## §1 · 工单目标（SMART 拆解）

| 维度 | 内容 |
|------|------|
| **S** Specific | 把轮 41 报告里的 **10 个可吞弹药 + 11 个暂缓项** 全部入仓 / 归档，并对其中 **3 个 P0 高价值目标**（vicena-labs/chemical-reactor-digital-twin / DENG-MIT/Biomass.jl / BRGM/ComPASS）完成 RAG 索引与 mcpserver/material_science 接入 |
| **M** Measurable | ① 10 个可吞 100% 入 `fe1iscurc0r/scratchpad-knowledge` 中转库（6 个分类目录）；② 11 个暂缓项落索引 + 激活策略；③ 3 个 P0 完成 schema 提取 + RAG corpus 索引 + pytest；④ 守卫 FAIL=0 |
| **A** Achievable | 全部 10 仓库已瘦身在 zip 内（59MB），不需重新 clone |
| **R** Relevant | 师傅专业线 = 邵长优惠组（轻化工·生物质能源与材料·木质素/共熔凝胶/MIP/水凝胶），轮 41 范式 A/B/C/D/E 全部直接对接反应器/动力学/代理层缺口 |
| **T** Time-bound | 建议 2 周节奏：W1 = 6 落点入仓 + 索引 + 守卫；W2 = 3 个 P0 接入 + pytest |

---

## §2 · 任务清单（按 §六 6 大差距清单分层）

### 任务 A · 6 个授粉落点入仓（最高优先 / W1）

轮 41 报告"§八·交付清单"已规划 6 个 `fe1iscurc0r/scratchpad-knowledge` 落点，本任务全部 push：

| 落点（中转库分类） | 内容 | 仓库 |
|-------------------|------|------|
| `coupled/reactor-digital-twin/` | **P0** vicena-labs/chemical-reactor-digital-twin v0.2.0（数字孪生完整包）| vicena-labs/chemical-reactor-digital-twin |
| `academic/doris-pyrolysis-julia/` | **P0** DENG-MIT/Biomass.jl（CRNN 论文级）| DENG-MIT/Biomass.jl |
| `academic/doris-pyrolysis-cfd/` | Biomass-Autothermal-Pyrolysis/OpenFOAM-bp（NREL 自热式派生）| Biomass-Autothermal-Pyrolysis/OpenFOAM-bp |
| `academic/bfb-pyrolysis/` | puttak/bfb-pyrolyzer（Python 一维两相）| puttak/bfb-pyrolyzer |
| `academic/doris-sindy/` | xk-y/Atmospheric-chemistry-surrogate...SINDy | xk-y/Atmospheric-chemistry-surrogate...SINDy |
| `academic/doris-htl-multiphase/` | **P0** BRGM/ComPASS（GPL-3.0 + CeCILL-2.1 双许可多相多组分水热）| BRGM/ComPASS |

剩余 4 个可吞（lautenberger/gpyro、mptutvt/rotaryPyrolysis、suraj-ad/Cellulose-Pyrolysis-PINN、wigging/kinetic-schemes、twinkle220/DFT-AL-framework-Biomass-Conversion）按"低星小体积"原则单独建 `academic/` 子目录入仓。

**验收 grep/assert**（参考日报 SKILL 568-583 行）：
```bash
# 1. 全部 10 仓已在 GitHub 落盘
gh api repos/fe1iscurc0r/scratchpad-knowledge/contents/academic | jq -r '.[].name'
# 期望包含: doris-pyrolysis-julia/ doris-pyrolysis-cfd/ bfb-pyrolysis/ doris-sindy/ doris-htl-multiphase/ gpyro/ rotaryPyrolysis/ cellulose-pinn/ kinetic-schemes/ dft-al-biomass/

# 2. LICENSE 二次核验全部通过（已阶段 1-2-5 验过的项目）
for d in doris-pyrolysis-julia bfb-pyrolysis doris-sindy; do
  gh api repos/fe1iscurc0r/scratchpad-knowledge/contents/$d/LICENSE --jq '.content // "MISSING"' | head -1
done
```

### 任务 B · 11 个暂缓项落索引 + 激活策略

11 个无 LICENSE 项目（CRECKMODELING/Kinetic-Mechanisms 是 60★ 学术灰色使用 + 只读，**仅作笔记**不激活；其余 10 个走"代发 issue 询问"激活策略）：

| 项目 | ⭐ | 策略 | 话术 |
|------|-----|------|------|
| CRECKMODELING/Kinetic-Mechanisms | 60 | **只读不拉** | 学术灰色使用 + 笔记引用，机械性暂缓 |
| wiggling/batch-cstr-pyrolysis | 6 | 发 issue 询问 | 萌新小白话术（参考日报 SKILL 480 行）|
| HY-Kim-SKKU/1D-CNN-biomass-pyrolysis-kinetics | 2 | 发 issue 询问 | 同上 |
| arsh-k/biomass-pyrolysis | 3 | 发 issue 询问 | 同上 |
| DouglasDivine/GUI-using-Gradio | 2 | 发 issue 询问 | 同上 |
| octorohan/HTL_BioOil_Prediction | 1 | 发 issue 询问（README 写 MIT 但 404）| 问"README 写 MIT 但 LICENSE 404，能补一个吗" |
| Saiful1040/...HHV | 1 | 发 issue 询问 | 同上 |
| dazhaxie666/Biomass-pyrolysis-data | 2 | 发 issue 询问 | 同上 |
| arnab37/Deconvolution-of-TGA-data | 7 | 发 issue 询问 | 同上 |
| sheep0410/CRNN-for-DAEM | 2 | 发 issue 询问 | 同上 |
| pchen-csu/htl-assessment | 1 | 发 issue 询问 | 同上 |

**验收 grep/assert**：
```bash
# issue 草稿落盘检查（参考日报 SKILL 475-487"外部 issue 起草铁律"）
ls /tmp/issue_bodies/  # 期望 10 个 .md 草稿
# 草稿先给用户过目（师傅拍板）才发——**禁止直接 gh issue create**
```

### 任务 C · 3 个 P0 接入 mcpserver/material_science（**W2** 重点）

3 个 P0 全部走"授粉 + 接入"双线：

#### C-1 · vicena-labs/chemical-reactor-digital-twin 接入
- **目标位置**：`mcpserver/material_science/reactor_digital_twin/`
- **接入方式**（参考日报 SKILL 562-583"五层分类"）：
  1. 写 `agent-manifest.json` 描述工具（Batch/CSTR/PFR 求解器 + Arrhenius + 灵敏度 + MC 不确定性）
  2. 提取 v0.2.0 的 6 类反问题（参数估计 / 协方差 / 局部灵敏度 / 全局灵敏度 / 优化 / 蒙特卡洛）为 handler
  3. 对接 Lumo material_science Agent 编排（README 第 9 章 AI agent 集成钩子）

#### C-2 · DENG-MIT/Biomass.jl 接入
- **目标位置**：`mcpserver/material_science/biomass_crnn/`
- **接入方式**：
  1. CRNN 模型结构（`Reaction` 类 + `Arrhenius` 约束 + `NeuralODE` 求解器）抽 3 个核心 schema
  2. TGA 数据反演流程（数据 → 训练 → 参数提取 → CHEMKIN 输出）为 4 步 handler
  3. 接受 Pyomo 风格的反应网络（species × reactions）

#### C-3 · BRGM/ComPASS 接入
- **目标位置**：`mcpserver/material_science/multiphase_htl/`
- **接入方式**：
  1. 多相多组分水热模拟架构（PETSc + MPI + zmesh）抽 5 个核心类
  2. 多孔介质建模（多孔域 + 裂缝域 + 矩阵域）转 schema
  3. 标注"双许可：GPL-3.0 + CeCILL-2.1"——接入需确认非商业用途

**验收 grep/assert**（每个 P0 一组）：
```bash
# 1. manifest 合法 + 测试全过
python3 -m pytest mcpserver/material_science/reactor_digital_twin/ -q       # ≥ 5 passed
grep -c '"license"' mcpserver/material_science/reactor_digital_twin/agent-manifest.json  # = 1
git diff --stat -- NEKO apiserver | wc -l   # = 0（不碰主流程）

# 2. CRNN 接入（Biomass.jl）
python3 -m pytest mcpserver/material_science/biomass_crnn/ -q
# 3. 多相水热接入（ComPASS）
python3 -m pytest mcpserver/material_science/multiphase_htl/ -q
```

### 任务 D · RAG 索引（接 WO-237 索引层）

参考 WO-237 已建的"灵感素材 RAG"模式，对 3 个 P0 写**反应器 / 动力学 / 神经网络代理**三段式 corpus：

| corpus 主题 | 来源 | 文件 |
|------------|------|------|
| `reactor_digital_twin_corpus` | vicena-labs v0.2.0 README + 论文级文档 | `mcpserver/material_science/reactor_digital_twin/corpus/reactor_digital_twin_corpus/index.json` |
| `crnn_biomass_corpus` | DENG-MIT/Biomass.jl Combustion and Flame 2022 论文 + CRNN schema | `mcpserver/material_science/biomass_crnn/corpus/crnn_biomass_corpus/index.json` |
| `multiphase_htl_corpus` | BRGM/ComPASS LICENSE.rst + 多孔介质建模文档 | `mcpserver/material_science/multiphase_htl/corpus/multiphase_htl_corpus/index.json` |

**索引元数据要求**（参考 WO-237 索引规范）：
```json
{
  "meta": {"source": "<上游源>", "method": "schema-extract", "ts": "2026-10-XX",
           "theme": "<theme>", "count": <n>, "note": "轮 41 授粉产物 - RAG 索引层"},
  "items": [
    {"id": "<repo>:<path>:<line>", "category": "schema|example|doc|test",
     "abstract": "<前1k>", "target": "<1句>", "score": <composite>}
  ]
}
```

---

## §3 · 仓库与文件落点（明示）

- **工单 doc**：`scratchpad/docs/WO-238-pollination-r41-ammunition-intake.md`（本文件）
- **中转库**：`fe1iscurc0r/scratchpad-knowledge`（6 个新落点，见任务 A 表）
- **mcpserver**：`scratchpad/mcpserver/material_science/{reactor_digital_twin,biomass_crnn,multiphase_htl}/`
- **RAG corpus**：`scratchpad/mcpserver/material_science/<name>/corpus/<theme>_corpus/index.json`
- **issue 草稿**：`/tmp/issue_bodies/*.md`（10 个草稿，落盘后由师傅过目再发）
- **报告原文**：`scratchpad/docs/超限战轮41-...md`（已存在）
- **源码包**：`http_share/超限战轮41-...zip`（59MB 已在云服）

---

## §4 · 风险与边界

| 风险 | 缓解 |
|------|------|
| 10 个可吞里有 3 个 GPL-3.0（lautenberger/gpyro / Biomass-Autothermal-Pyrolysis/OpenFOAM-bp / mptutvt/rotaryPyrolysis）+ 1 个 GPL-3.0+CeCILL-2.1 双许可（BRGM/ComPASS）| 2026-10-12 纠正口径已"AGPL-3.0 主仓可包含兼容 copyleft"，BRGM 双许可需标注"接入需确认非商业用途" |
| OpenFOAM-bp 的 tutorials 94MB 已剥离 | 验收时 `du -sh academic/doris-pyrolysis-cfd/` 应 < 5MB |
| ComPASS 需 PETSc + MPI + zmesh 运行时 | 标注"运行依赖"（参考日报 SKILL 596 行铁律），不阻塞接入 |
| gpyro 需 Fortran 编译器 | 同上标注 |
| Biomass.jl 需 Julia + DiffEqFlux | 同上标注 |
| 10 个 issue 草稿必须先过用户 | 禁止直接 `gh issue create`（日报 SKILL 479 行铁律）|

**不在本工单范围**：
- 轮 42 候选方向（Cantera 工业仿真 / HTL Kinetics / DiffEqFlux 等）—— 留给轮 42 报告
- 木质素 NPs / 共熔凝胶 / MIP / 水凝胶的"反应器级"端到端 SPEC —— 留给后续生物质科研线工单
- 论文跨域授粉点（4 条）—— 见工单 239
- 今日 11 个新 GitHub 候选 + 4 个排除项 —— 见工单 240

---

## §5 · 验收不变量（grep/assert）

```bash
# 1. 6 个授粉落点全部在远端可见
gh api repos/fe1iscurc0r/scratchpad-knowledge/contents/ | jq -r '.[].name' | grep -E '^(coupled|academic)/' | wc -l  # 期望 ≥ 6 新增

# 2. 11 个暂缓项索引落盘
ls /home/ubuntu/scratchpad/docs/pollination-r41-suspended-11.md
# 期望：1 个索引 md 存在

# 3. 3 个 P0 全部接入
ls scratchpad/mcpserver/material_science/ | grep -E '^(reactor_digital_twin|biomass_crnn|multiphase_htl)$' | wc -l  # = 3

# 4. pytest 全过
python3 -m pytest scratchpad/mcpserver/material_science/{reactor_digital_twin,biomass_crnn,multiphase_htl}/ -q  # ≥ 15 passed

# 5. RAG 索引 3 个 corpus 落盘
find scratchpad/mcpserver/material_science/ -name 'index.json' -path '*corpus*' | wc -l  # ≥ 3

# 6. 防幻觉守卫 FAIL=0
python3 ~/scratchpad/scripts/anti_hallucination_guard.py --check-report /tmp/wo238_final.md --detect-upstream
# 期望输出：FAIL=0
```

---

## §6 · 与已有工单的关系

| 现有工单 | 关系 |
|---------|------|
| WO-237 灵感素材库 RAG | **复用**索引层规范（meta/items 结构）|
| WO-230/231/232/233 biomass A/B/C | **补充**反应器级 + 动力学反演层（轮 30/37 留下的缺口）|
| POLLINATION-FUNNEL-v2-CHANGELOG | **挂入**轮 41 增量（10 可吞 + 11 暂缓 + 3 误判）|
| 法学工单 L1-L11 | 无关 |

---

> 沈遥出单 · 师傅 1 句话确认/调整后转 Trae
