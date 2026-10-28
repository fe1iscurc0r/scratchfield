# 授粉 · thermo + fluids（ChEDL 物性计算层）落地报告

> 卷138 · W138-02 | 2026-09-19 | 沈遥签
> 上游：CalebBell/thermo（785★ · MIT ✅）+ CalebBell/fluids（454★ · MIT ✅）· 均 2026-09 活跃
> 前置：超限战轮19 授粉报告 P1-1/P1-2

## 一、上游实地调研结论

**thermo**（ChEDL 热力学件）：纯 Python（依赖 fluids/chemicals/numpy/scipy），
覆盖：状态方程（EOS 族）、活度系数（NRTL/UNIQUAC/UNIFAC/Wilson/Regular Solution）、
闪蒸/相平衡、热容/焓/熵、蒸汽压、粘度/导热/界面张力、介电常数、
基团贡献法（Joback/Fedors/Wilson-Jasperson/Bondi）。
核心 API（官方文档核实）：
- `thermo.chemical_package.ChemicalConstantsPackage` / `PropertyCorrelationsPackage`（现代入口）
- `thermo.flash`（Flash 计算）、`thermo.eos`（PR/SRK/RK 等 EOS）
- legacy 入口 `thermo.chemical.Mixture` / `thermo.chemical.Chemical`

**fluids**（ChEDL 流体件）：thermo 的下游基础件，纯 Python——
密度/粘度/表面张力/导热/两相流/传热/压降（管路、阀门、换热器、填充床等化工单元的
无量纲数与关联式）。

**与既有体系关系**：09-09 生物精炼线的 bioSTEAM（P2）正缺物性层——thermo 是
bioSTEAM 官方依赖链（thermo→fluids→chemicals），授粉即补链。仓里已有
`mcpserver/material_science/`，是天然落点。

## 二、MCP 适配器设计（工单要求的 thermo_adapter）

**落点**：`mcpserver/adapters/thermo_adapter/`（照 hamlog_adapter 样板，agent 目录型）。

**工具面**（3 个工具，最小可用）：

```python
# 1. thermo_props —— 纯物质/混合物物性查询
tool "thermo_props" {
    input:  { chemicals: ["water", "ethanol"],   # 名称/CAS/SMILES
              fractions: [0.7, 0.3],             # 摩尔分率，缺省纯物质
              T: 298.15, P: 101325.0,            # K, Pa（缺省标况）
              props: ["density", "viscosity", "Cp", "thermal_conductivity",
                      "surface_tension", "Hvap"] }
    # 内部：ChemicalConstantsPackage.from_constantsIDs → PropertyCorrelationsPackage
    # 输出：{ok, props: {density: {value: 997.0, unit: "kg/m^3", method: "..."}, ...}}
}

# 2. thermo_flash —— 相平衡/闪蒸
tool "thermo_flash" {
    input:  { chemicals: [...], fractions: [...], T?, P?, VF? }  # TP/HP/VF 任一闪点
    # 输出：{phases: [{phase: "liquid", x: [...], mass_frac: [...]}],
    #        flash_converged: true, method: "..."}
}

# 3. thermo_gc —— 基团贡献法估算（无数据库也能算）
tool "thermo_gc" {
    input:  { smiles: "CCO", method: "joback", props: ["Tb", "Tc", "Hf"] }
    # 输出：{Tb: {value: 351.5, unit: "K", method: "Joback"}}
}
```

**安全边界**：只读计算，无写操作 → 不需要确认门/Scope 闸门（照 hamlog 先例）。
**降级**：包未安装时工具返回 `{ok:false, reason:"thermo_not_installed"}`，
不静默——与 ptz_service 的 no_propagator 先例一致。

## 三、木质素 NPs 水凝胶场景的接线（用户导师方向）

导师方向（邵长惠）：木质素 NPs → 水凝胶/共熔凝胶 → 水下电子/太阳能蒸发。
直接需要的物性计算：

| 环节 | 需要的物性 | thermo/fluids 提供 |
|---|---|---|
| 木质素在共熔溶剂（DES）中的溶解度/稳定性 | 混合物密度、粘度（T 依赖） | `thermo_props`（mixture + PropertyCorrelations） |
| 水凝胶蒸发性能 | 水/DES 混合蒸汽压、汽化焓 | `thermo_flash`（露点/闪蒸）+ Hvap |
| 太阳能蒸发能量核算 | Cp（液态混合物，T 积分得焓差） | `thermo_props` Cp + 手动积分 |
| 喷雾/涂布工艺 | 表面张力、粘度 → 无量纲数（Re/We/Ca） | thermo 表面张力 + fluids 的 `atomization` 模块 |

**注意（如实标注）**：thermo 的数据库覆盖常规小分子；**木质素大分子本身不在其
数据库中**——正确用法是：小分子侧（水/甘油/氯化胆碱/乙二醇等 DES 组分）用 thermo
精确算，木质素大分子侧用基团贡献法（`thermo_gc`，Joback 对大分子误差大，
建议只做量级估算）或留待 RadonPy（见 W138-03 报告）的 MD 路线。

## 四、依赖与许可

- MIT ✅（两件均 LICENSE 原文确认）。纯 Python + numpy/scipy，
  Windows 轮子齐全（本机可装，无 pysqlite3 式坑）。
- 装机成本：`pip install thermo fluids`（连带 chemicals）。
  建议 requirements.txt 追加 `thermo>=0.6`、`fluids>=1.0`（可选组，
  进 pdf2md 同风格的 optional-dependencies `chemprops` 组）。

## 五、结论

- **立即落地**：thermo_adapter 三工具面（props/flash/gc），先服务 DES 混合物
  T 依赖物性查询——导师方向的直接生产力件。
- **进树路径**：`mcpserver/adapters/thermo_adapter/`，照 hamlog 样板 +
  agent-manifest.json + 21 用例级测试（含 mixture/闪蒸收敛/降级三类）。
- **不做**：把 thermo 塞进 material_science 既有模块（语义不符——那是结构/数据，
  这是物性计算）；直接装进根 requirements.txt（保持可选组）。
