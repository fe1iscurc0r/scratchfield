# 授粉 · pybaselines + RadonPy（光谱与高分子工具）落地报告

> 卷138 · W138-03 | 2026-09-19 | 沈遥签
> 上游：derb12/pybaselines（194★ · BSD-3 ✅）+ RadonPy/RadonPy（282★ · BSD-3 ✅）
> 前置：授粉轮19 授粉报告 P1-3/P1-4

## 一、pybaselines 实地调研结论

**定位**：光谱基线校正库（Python ≥3.9，BSD-3，依赖仅 numpy/scipy）。
**API 形态**（官方文档核实）：单一 `Baseline` 类（1D）/ `Baseline2D`（2D），
按算法族分组为方法；另有 legacy 函数接口。

**算法清单**（8 族，官方文档核实）：

| 族 | 代表算法 |
|---|---|
| Polynomial | poly/modpoly/imin/modpoly, penalized_poly, poly_value_weighting… |
| Whittaker | **asls/airpls/arpls/iarpls/drifted_asls/derpsalsa**（不对称重罚最小二乘族） |
| Morphological | **snip**（峰剥离）, mplp, tophat, mor/morcer… |
| Spline | mixture/pspline_asls/pspline_airpls…（样条版 Whittaker） |
| Smoothing | noise_median, binned_spacing… |
| Classification | **fabc/golotvin/ccd**（基于分类器找非峰区） |
| Optimizers | collabpls（协作优化器，多算法套壳） |
| Miscellaneous | interp_pts, poly_quantile… |

**FTIR/Raman 前处理的直接命中**：水凝胶/木质素样品的红外谱图基线漂移
（溶剂强吸收 + 散射背景）正是 arPLS/airPLS/snip 的教科书场景。

## 二、pybaselines MCP 落地设计

**落点**：`mcpserver/spectra_tools/`（或并入既有光谱线的独立件，与
mcpserver/material_science 平级）。

```python
tool "spectra_baseline" {
    input:  { x?: [...], y: [...],          # 等距采样时 x 可省
              method: "arpls",              # 白名单：asls/airpls/arpls/iarpls/
                                          # pspline_arpls/snip/mplp/tophat/poly…
              params?: {lam: 1e6, max_iter: 50},
              return_baseline: true }       # true=返回基线，false=返回校正后谱
    # 内部：Baseline().arpls(y, lam=…)
    # 输出：{ok, y_corrected: [...], y_baseline?: [...], params_used: {...}}
}

tool "spectra_baseline_compare" {
    # 同一谱跑多算法并排返回（选型工具）：metrics = 每算法的
    # RoughnessBaseline 分数 + 峰保留率（两侧峰区积分变化）
    input:  { y: [...], methods: ["arpls", "airpls", "snip", "mplp"] }
    # 输出：{per_method: {y_corrected, score}, recommended: "arpls"}
}
```

**设计要点**（授粉自 pybaselines 的 `collabpls` 协作优化器思想）：
`_compare` 工具本质是把"算法对比"工具化——与 rf_brain registry 的
"多解码器并排"同构，沿用仓内既有模式。

**降级**：未装 pybaselines 时两工具返回
`{ok:false, reason:"pybaselines_not_installed"}`（不静默）。
**依赖**：`pybaselines>=1.2`（BSD-3，进 optional-dependencies `spectra` 组）。

## 三、RadonPy 实地调研结论

**定位**：全原子 MD 自动化高分子物性计算（BSD-3，2026-08 活跃，npj Comput. Mater. 2022）。
**能力**（README 核实）：给一个聚合物重复单元结构（SMILES），全自动完成
构象搜索→电荷（RESP/ESP/Gasteiger）→力场指派（GAFF/GAFF2/Dreiding/Amber）→
建模（均聚/共聚/嵌段/支化，非晶/溶液/取向）→平衡 MD（自动判收敛/失败重启）→
NEMD→**62 种物性**（密度/Cp/Tg/热导率/介电/折射率/溶解度参数/回转半径等）。
**附赠**：1070 个非晶聚合物的 MD 计算数据库（PI1070.csv）。

**依赖现实（如实标注）**：完整链需要 LAMMPS + psi4 + rdkit + mdtraj
（conda 生态，Windows 无 psi4 官方支持）；**pip 最小安装**（无 LAMMPS/psi4）
仍提供：聚合物结构构建器、力场指派、力场描述符、高分子信息学工具——
即"预处理与描述符层"在 Windows 本机可用，MD 执行层需要 HPC/Linux。

## 四、RadonPy MCP 落地设计

**落点**：`mcpserver/polymer_md/`（分两层，对应依赖现实）：

```python
# 第一层：本机可用（无 LAMMPS/psi4）——立即落地
tool "polymer_describe" {
    input:  { smiles: "*CCOCC*", repeat_count?: 30 }   # 聚合物 SMILES（* 为连接点）
    # 内部：RadonPy 的结构构建 + 力场描述符
    # 输出：{molecular_weight, ff_descriptor: [...], chain_types: [...]}
}
tool "polymer_db_search" {
    # 查 PI1070.csv：按 SMILES 子结构/物性范围筛 1070 种已算聚合物
    input:  { tg_min?: 350, tg_max?: 450, substructure?: "CCOC" }
    # 输出：{matches: [{polymer, Tg, density, source: "PI1070"}]}
}

# 第二层：LAMMPS 存在时（HPC/Linux 侧部署）——模板生成先行
tool "lammps_template" {
    # 生成 RadonPy 式的 LAMMPS 输入脚本（工单指定）：
    # sim/preset 的 eq.py/tg.py/tc.py/sp.py 四预设 → in.lammps 模板
    input:  { polymer_type: "lignin_model",   # 或 SMILES
              properties: ["Tg", "density"],
              preset: "tg",                   # eq/tg/tc/sp 四预设
              temp_range: [300, 500], steps: 1e6 }
    # 输出：{in_lammps: "<完整脚本文本>", data_file_hint, expected_outputs: [...]}
}
```

**分层理由**：`_describe`/`_db_search` 在 Windows 本机即用（pip 最小安装），
`lammps_template` 纯文本生成不依赖本机 LAMMPS——执行拿去 HPC 跑。
这样三层工具**全部**在当前环境可测，不被依赖现实卡死。

## 五、与导师方向的合流

木质素 NPs → 水凝胶力学/热学性能预测的完整链：

```
木质素结构（LigninGraphs 已授粉）→ RadonPy 聚合物建模（本卷）
    → LAMMPS MD（HPC）→ Tg/密度/热导率（RadonPy 62 物性）
    → 与水凝胶实验 FTIR（pybaselines 前处理）互相印证
    → DES 溶剂侧物性由 thermo_adapter（W138-02）补齐
```

三个工单（138-01/02/03）合起来正好覆盖：结构（RadonPy）+ 溶剂（thermo）+
表征数据（pybaselines）——材料线工具链闭环。

## 六、结论

- **立即落地**：pybaselines 双工具（baseline/baseline_compare）——
  零硬件依赖，直接服务 FTIR/Raman 数据清洗；
  RadonPy 第一层双工具（describe/db_search）+ lammps_template 模板生成。
- **许可**：均 BSD-3 ✅（LICENSE 原文确认）。
- **依赖策略**：pybaselines 进可选组 `spectra`；radonpy-pypi 进可选组
  `polymer`（并注明 psi4/lammps 的 conda 现实，Windows 只支持最小安装层）。
- **不做**：在 Windows 本机硬上 psi4/LAMMPS（官方不支持）；照搬 RadonPy 的
  自动执行调度（那属于 HPC 侧，模板生成已够用）。
