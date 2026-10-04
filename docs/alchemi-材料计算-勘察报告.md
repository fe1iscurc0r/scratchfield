# ALCHEMI 材料计算闭环勘察报告 · ALPHA-01

> 工单：ALPHA-01（NVIDIA ALCHEMI Toolkit 勘察报告）
> 线：ALPHA（A 线 · 材料计算闭环）｜分支：trae/agent-alpha
> 类型：只读勘察，不写码；不把 ALCHEMI 代码拷进主仓
> 上游：https://github.com/NVIDIA/nvalchemi-toolkit
> 对照：docs/SPEC-18-天选7-Lumo科研增强-总纲.md（六模块）+ mcpserver/academic/（MODEL_INTERFACE 模式）
> 完成：2026-08-28

## 〇、一句话结论

NVIDIA ALCHEMI Toolkit 是一个 **GPU-first 的 AI 原子模拟框架**（Apache-2.0，PyPI `nvalchemi-toolkit`，public beta）：吃 **DFT 标注数据**（能量/力/应力标签）→ 训/微调 **MLIP 机器学习势**（MACE / AIMNet2 / UMA）→ 做 **批量分子动力学与结构弛豫** → 产出 **单点能、原子力、应力** 等性质。它不是"DFT 软件"，也不内置 DFT 引擎；它的"材料计算闭环"是 **数据 → 势函数 → 模拟 → 性质** 这条推理/训练链，与 Lumo 当前"表格 ML（maml+RF/BP）预测碳化导电率"（SPEC-18 模块 B）互补，授粉点集中在 **MLFF 推理层 + 数据表示层（Zarr）+ Agent-ready skill 范式** 三处，训练/多卡域分解部分为二期，不否决但标注重依赖。

---

## 一、上游档案卡

| 项 | 值 |
|---|---|
| 仓库 | `NVIDIA/nvalchemi-toolkit` |
| 一句话 | High-throughput AI atomic simulation on NVIDIA GPUs（GPU 优先的 AI 原子模拟框架） |
| Stars | 150（勘察时点 2026-08-28） |
| License | Apache-2.0 |
| 状态 | **public beta**（README 明示"API subject to change"） |
| PyPI | `nvalchemi-toolkit` |
| 主页 | https://nvidia.github.io/nvalchemi-toolkit/ |
| 默认分支 | `main`（最近 push 2026-08-24） |
| Python | `>=3.11,<3.14` |
| 关键子依赖 | `nvalchemi-toolkit-ops`（warp-lang GPU 核）、`torch>=2.8`、`zarr>=3`、`nvidia-physicsnemo>=2.0` |

---

## 二、顶层目录语义定位

勘察用 GitHub API `git/trees` 递归拉取（`truncated=false`，全量树），未 clone、未拷贝源码进主仓。顶层结构：

```
nvalchemi-toolkit/
├─ nvalchemi/            # 包本体（Python 包入口 __init__.py）
│  ├─ data/              # 数据表示 + Zarr 数据管道
│  ├─ models/            # 模型动物园 + 可组合物理项（静电/色散）
│  ├─ training/          # 训练/微调/验证/分布式训练 + CLI
│  ├─ dynamics/          # 积分器 + 弛豫 + hooks（9 个挂点）
│  ├─ distributed/       # 空间域分解多卡
│  ├─ hooks/             # 通用 hook 基类
│  ├─ neighbors.py       # 邻居表（接 ops 的 warp 核）
│  └─ _optional.py/_typing.py/_serialization.py
├─ examples/             # basic / intermediate / advanced / distributed 四级示例
├─ benchmark/            # 分布式前向/NVT 基准
├─ docs/                 # Sphinx userguide（data/models/training/dynamics/…）
├─ test/                 # pytest 全量测试（含 slow/multigpu 标记）
├─ .claude/skills/       # ← Agent-ready 技能（给 AI 编码代理的 API 速查）
├─ AGENTS.md / CLAUDE.md # ← 仓库级代理约定
├─ pyproject.toml        # 依赖与可选 extras
└─ uv.lock / Makefile
```

**语义小结**：`data` 是输入侧（图表示 + 数据管道），`models` 是可组合的能量模型层，`training` 是势函数训练/微调侧，`dynamics` 是消耗势函数产性质的一侧，`distributed` 是规模扩展侧。这与"DFT→特征→MLFF→性质"流水线一一对应（见 §四）。

---

## 三、examples/ 地图（读 examples 即懂流水线）

| 级别 | 目录/文件 | 讲什么 | 对标流水线环节 |
|---|---|---|---|
| basic | `01_data_structures.py` | `AtomicData`/`Batch` 图数据结构 | 特征表示 |
| basic | `02_geometry_optimization.py` | 结构弛豫 + 收敛检测 | 性质（弛豫） |
| basic | `03_ase_integration.py` | ASE 计算器互操作（`ase` extra） | 生态桥接 |
| basic | `04_nve_energy_conservation.py` | NVE 能量守恒验证 | 模拟校验 |
| basic | `05_nvt_langevin.py` | Langevin 恒温 MD | 模拟 |
| intermediate | `01_multistage_pipeline.py` | 弛豫→MD 多阶段（`+` 融合） | 组合 |
| intermediate | `02_trajectory_zarr_io.py` | 轨迹 Zarr 落盘 | 数据 |
| intermediate | `03_npt_barostat_validation.py` | NPT 恒压校验 | 模拟校验 |
| intermediate | `04_inflight_batching.py` | 在飞批处理（GPU 保活） | 推理性能 |
| intermediate | `05_safety_and_monitoring.py` | NaN 检测/监控 hook | 安全 |
| intermediate | `06_ddp_mlp_training.py` / `07_rich_training_reporting.py` | 分布式训练 / 富报告 | 训练 |
| advanced | `10_mace_training.py` + `10_vanilla_mace.yaml` | 完整 MACE 训练生命周期（MatPES r2SCAN） | **训练全链路** |
| advanced | `08_aimnet2_ewald_pipeline.py` | AIMNet2 + Ewald 静电 | 模型组合 |
| advanced | `07_composable_model_composition.py` | 模型组合（势 + 色散 + 静电） | 模型 |
| advanced | `09_uma_nve.py` | UMA 模型 NVE | 模型 |
| advanced | `01_biased_potential.py`/`02_custom_hook.py`/`05_custom_integrator.py` | 偏置势/自定义 hook/自定义积分器 | 扩展 |
| distributed | `01..07` | 域分解多卡 + BYO MPNN/图Transformer | 规模 |

`examples/advanced/10_mace_training.py` 的 docstring 直接点明训练链：**MatPES r2SCAN（DFT 数据集，matpes.ai）→ ALCHEMI 兼容 Zarr 切分 → `AtomicDataZarrReader` → ScaleShiftMACE 基线 → `TrainingStrategy` + cuEquivariance 核 → 能量/力/应力加权 Huber 损失**。

---

## 四、完整流水线（DFT → 特征 → MLFF → 性质）

```
① DFT 标注数据               ② 特征表示/数据管道            ③ MLFF 训练·推理             ④ 分子性质预测
─────────────────          ───────────────────────      ──────────────────────       ─────────────────────
外部 DFT 计算                 nvalchemi.data             nvalchemi.models           nvalchemi.dynamics
(VASP/QE/ORCA/…                AtomicData(Pydantic)      MACE / AIMNet2 / UMA         FIRE 弛豫
 或现成数据集:                 positions+atomic_numbers   + 可组合项:                 Langevin/NVT/NPT/NVE
 MatPES r2SCAN)                forces/velocities/         Ewald/PME 静电、            hooks(9 挂点/步):
     │                        neighbor_list/              DFT-D3(BJ) 色散、LJ           Logging/NaNDetect/
     ▼                        system labels(energy)       BaseModelMixin(BYO)          Convergence/safety/
 Zarr 切分(zarr>=3)      ──►   Batch.from_data_list  ──►   MACEWrapper.                monitoring/profiling/
   │                          datapipes/backends/zarr.py  from_checkpoint("medium-0b2") sampling
   ▼                          transforms + samplers      training.TrainingStrategy  ──►  能量/力/应力
 AtomicDataZarrReader         + inflight batching         (EnergyMSELoss+ForceMSELoss     (+动力学衍生量)
  InMemoryDataset             + CUDA-stream prefetch       +stress, Huber, EMA, DDP)      轨迹 Zarr 落盘
```

**逐步拆解（库 / 格式 / 对标模块）**：

| 环节 | ALCHEMI 用什么库/格式 | 核心类/函数 | 对标 Lumo 模块（SPEC-18） |
|---|---|---|---|
| ① DFT 数据 | 外部 DFT 软件（VASP/QE/ORCA…）或现成 `MatPES r2SCAN`；落 **Zarr**（`zarr>=3`） | `AtomicDataZarrReader`, `InMemoryDataset` | 无对应（Lumo 无原子模拟数据侧）→ 新 |
| ② 特征表示 | PyTorch 张量图：原子=节点、键/半径截断邻居=边；GPU 常驻 | `AtomicData`, `Batch.from_data_list`, `neighbors.py`(warp 核) | 部分对应 E 模块（TGA/DSC/XRD 导入），但非图表示 |
| ③ MLFF 训练/推理 | `torch>=2.8` + `mace-torch==0.3.15`/`aimnet`/`fairchem-core` + `cuequivariance-ops-torch` | `MACEWrapper`, `AIMNet2`, `UMA`, `BaseModelMixin`; `TrainingStrategy`/`ValidationConfig`/`finetune.py` | 对应 B 模块（材料模型算力），但 B 现状是 maml+RF/BP 表格 ML，无势函数 |
| ④ 性质预测 | `dynamics` 积分器族 + hooks | `DemoDynamics`→`NVTLangevin`/`NoseHoover`/`NPT`/`FIRE`, `ConvergenceHook` | 无对应 → 新；产出可回写 ELN（A 模块） |

**诚实标注（性质边界）**：ALCHEMI 直接产出的是 **能量、原子力、应力** 三类物理量（loss 也是这三者的加权），以及经动力学/hook 采样得到的**衍生观测量**（轨迹、RDF 等）。**振动/热力学性质（Hessians、phonons）在官方 Roadmap 中尚未落地**——README Roadmap 明确列了 "Hessians and phonons（解析二阶导）" 为规划项。因此"分子性质预测"这一步在当下是**能量/力/应力级**，不是完整性质谱，授粉 SPEC 要把这个边界写清。

---

## 五、运行依赖标注（只标注，不否决）

| 依赖 | 必要性 | 说明 |
|---|---|---|
| NVIDIA GPU + CUDA 12/13 | **准必需**（GPU-first） | `cu12`/`cu13` extras；warp-lang 核 + cuEquivariance 核针对 CUDA 优化；CPU 可跑但仅限验证性小算例 |
| `torch>=2.8`（CUDA 轮子） | 必需 | 走 `download.pytorch.org/whl/cu12x` + `pypi.nvidia.com` 双索引 |
| `warp-lang`（经 `nvalchemi-toolkit-ops`） | 必需 | 邻居表 + 交互核，GPU kernel 层 |
| `cuequivariance-ops-torch` | MACE 需要 | MACE extra 引入 |
| `cuml` | CUDA extras 引入 | 数据/采样加速 |
| **DFT 软件** | **不需要（关键结论）** | ALCHEMI 只消费 DFT 标注好的数据，不自带 DFT 引擎；训练需外部 DFT 或现成数据集（MatPES） |
| `mace` vs `uma` 互斥 | 注意 | `mace` 钉 `e3nn==0.4.4`，`uma`(fairchem-core) 需 `e3nn>=0.5`，二者不能同环境（pyproject `conflicts` 显式声明） |
| `pymatgen` / `ase` | 可选 extra | 结构 IO（POSCAR/CIF）与计算器互操作；Lumo 侧 SLICES 已钉 `pymatgen`，可复用 |

**对天选7 Pro（RTX 5060 8GB / Windows）的落地判断**：**推理侧（MLFF 单点/弛豫）8GB 显存可跑中小结构，MACE medium-0b2 checkpoint 属边缘可行**；**训练侧（MatPES 全量）不建议本地跑**，属云服/多卡范畴。Windows 原生支持需验证（上游 CI/示例默认 Linux + CUDA），此为设计假设，标注"待真机确认"。

---

## 六、Lumo 差距表（ALCHEMI 提供 → Lumo 缺什么 → 授粉方式）

对照面：SPEC-18 六模块（A ELN / B 材料模型算力 / C 文献 / D 705 / E 数据工具台 / F 语音）+ `mcpserver/academic/` 的 MODEL_INTERFACE 模式（统一契约 `{ok, data, source}`、`AcademicDependencyError` 降级、`_REGISTRY` 注册表、`FUSION_LEVELS` 层级表）。

| # | ALCHEMI 提供 | Lumo 现有/缺什么 | 授粉方式 | 优先级 |
|---|---|---|---|---|
| 1 | MLIP 推理：MACE/AIMNet2/UMA 预训练 checkpoint → 能量/力/应力 | **完全缺失**——无原子模拟/势函数层 | 新增 `MODEL_INTERFACE alchemi`（纯推理入口，`from_checkpoint`） | **一期** |
| 2 | 数据表示：`AtomicData`/`Batch` 图 + Zarr 轨迹存储 | E 模块只有 TGA/DSC/XRD 的 CSV 导入+matplotlib | 授粉"Zarr 作为实验/轨迹数据层"，但仅借鉴格式，不引图结构 | 二期 |
| 3 | MLFF 训练/微调：`TrainingStrategy`+损失组合+checkpoint/EMA/DDP | B 模块是 maml+RF/BP 表格 ML（碳化条件→导电率），无势函数训练 | 授粉"训练策略配置化 + 损失项组合"思想到 B；**不直接引入 ALCHEMI 训练栈（重依赖）** | 二期 |
| 4 | 结构弛豫/MD（FIRE/Langevin/NPT, batched） | 无 | 授粉为 E 模块前处理（XRD 前结构弛豫） | 二期 |
| 5 | Agent-ready 范式：`.claude/skills/` + `AGENTS.md` | Lumo 已有 skills 体系（lumo-hamlog-log 等） | **直接授粉范式**：把"给编码代理的 API 速查 skill"模式复用到 academic 模块 | 一期（低成本） |
| 6 | 可组合物理项（Ewald/PME/DFT-D3 色散） | 无 | 概念授粉（写进 SPEC 的接口扩展位），暂不实现 | 备注 |

---

## 七、给 Lumo 材料计算层的 SPEC 建议（可 grep 验收）

### 7.1 模块名与归属

- 新增接口文件：`mcpserver/academic/alchemi_interface.py`，暴露 `MODEL_INTERFACE`（与现有 `coolprop/chemformula/tespy/slices/indigo/chembl` 六者并列）。
- 注册表追加：`mcpserver/academic/__init__.py` 的 `_REGISTRY` 增加 `"alchemi": ("mcpserver.academic.alchemi_interface", "MODEL_INTERFACE")`。
- 层级表追加：`mcpserver/academic/levels.py` 的 `FUSION_LEVELS` 增加 `"ALCHEMI"` 条目（level=MCP，license=Apache-2.0，pip=`nvalchemi-toolkit`，runtime_deps 标 GPU/CUDA，status 标注"推理可用/训练云服"）。
- 契约文档：`docs/academic/MODEL_INTERFACE.md` 追加 alchemi 章节。

### 7.2 接口签名（一期只做推理，不做训练）

```
MODEL_INTERFACE = {
  "name": "alchemi",
  "package": "ALCHEMI Toolkit",
  "vendor_repo": "https://github.com/NVIDIA/nvalchemi-toolkit",
  "pip": "nvalchemi-toolkit[mace]",           # 或 [cu12,mace]
  "license": "Apache-2.0",
  "fusion_level": "MCP",
  "entrypoints": [
    { "command": "alchemi_singlepoint",
      "params": {"positions": "[N,3] 原子坐标", "atomic_numbers": "[N] 原子序数",
                 "model": "checkpoint 名(默认 mace medium-0b2)", "device": "cuda|cpu"},
      "returns": {"energy_eV": "float(单点能)", "forces": "[N,3] 原子力",
                  "stress": "可选 [3,3] 应力", "source": "model:checkpoint"},
      "example": "alchemi_singlepoint(positions, [6,8,1,1]) -> {energy_eV, forces}" },
    { "command": "alchemi_relax",
      "params": {"positions", "atomic_numbers", "fmax": "收敛阈值(默认 0.05)",
                 "max_steps", "device"},
      "returns": {"relaxed_positions", "energy_eV", "steps"},
      "example": "alchemi_relax(...) -> 弛豫后结构+能量" },
  ],
  "runtime_deps": ["NVIDIA GPU + CUDA12/13(推理 8GB 边缘可行)", "torch>=2.8",
                   "warp-lang(经 nvalchemi-toolkit-ops)", "无 DFT 软件依赖"],
  "degradation": "包缺失→pip install nvalchemi-toolkit[cu12,mace](双索引)；无 GPU→降级 CPU 或抛含恢复提示的 AcademicDependencyError；只标注不否决",
  "verified": "待真机/实测确认(本单只读勘察，未安装运行)",
}
```

### 7.3 依赖与验收 grep 项

验收（施工阶段可 grep 的自检项，含本单与后续施工）：

```bash
# 本报告自检（ALPHA-01 验收）
grep -q "DFT" docs/alchemi-材料计算-勘察报告.md            # 含 DFT→MLFF→性质流水线
grep -q "差距表\|ALCHEMI 提供" docs/alchemi-材料计算-勘察报告.md
grep -q "MODEL_INTERFACE\|alchemi_interface" docs/alchemi-材料计算-勘察报告.md

# 后续施工验收（一期 alchemi 推理接口落码时）
grep -n '"alchemi"' mcpserver/academic/__init__.py          # 注册表含 alchemi
grep -n 'MODEL_INTERFACE' mcpserver/academic/alchemi_interface.py
grep -n 'runtime_deps' mcpserver/academic/alchemi_interface.py
grep -n 'nvalchemi-toolkit' mcpserver/academic/levels.py    # 层级表含上游包名
grep -n 'alchemi_singlepoint' docs/academic/MODEL_INTERFACE.md
```

### 7.4 硬约束回填

- **只读勘察**：本单未 clone、未拷贝任何 ALCHEMI 源码/模型权重进主仓（勘察仅经 GitHub API 读元数据与关键文档/示例片段）。
- **不否决**：重依赖（GPU/CUDA/warp-lang）只标注，不否决；落地优先级由用户拍板。
- **公开 beta**：上游 API 未冻结（README 明示），接口签名以"稳定薄封装"隔离上游变动。

---

## 八、阻塞与假设说明（诚实标注）

1. **round8 授粉报告缺失**：工单标注的上游文档 `github_haul/POLLINATION-2026-08-27-round8.md` 在全仓库（含 `origin/workorders-2026-08-28` 分支）均不存在。本报告以工单内嵌的 round8 结论（"ALCHEMI 是唯一 NVIDIA 开源 AI 化学工具包、Apache-2.0、落地路径为读 examples 写 SPEC"）为判据推进，已在 §一 用上游实际元数据交叉验证（150★/Apache-2.0 一致）。round8 原文到位后，若杂交来源/核心共鸣描述有出入，以原文为准回填本报告。
2. **未真机验证**：本单只读勘察，未 `pip install`、未跑任何 ALCHEMI 代码；§五 的天选7 8GB 显存可行性判断属**设计假设**，标注"待真机确认"。
3. **性质边界**：§四已注明——性质预测当前是能量/力/应力级，phonons/Hessians 在 roadmap。

---

*执行：智能体 ALPHA · 2026-08-28 · 只读勘察线（A 线）*
