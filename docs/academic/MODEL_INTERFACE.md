# academic MODEL_INTERFACE 定义（W-09）

> 4 个高价值纯库的结构化数据接口。代码位置 `mcpserver/academic/*_interface.py`，
> MCP 调用面 `mcpserver/academic/bridge.py`（AcademicBridge，工具名=下表 command）。
> 统一契约：返回 `{ok, ...data, source}`；参数非法抛 `ValueError`（白名单提示）；
> 依赖缺失抛 `AcademicDependencyError`（message 含 `pip install` 提示，只标注不否决）。

## 1. coolprop（CoolProp · MIT · 真算可用）

| 命令 | 参数 | 返回 |
| --- | --- | --- |
| `coolprop_props` | `output`(D/H/S/T/P/U/Cpmass/V/Q…)、`name1,prop1`、`name2,prop2`（两点定态，SI）、`fluid` | `{value: float, unit_system: "SI", source}` |
| `coolprop_constant` | `output`(Tcrit/Pcrit/M…)、`fluid` | `{value: float}` |

- 混合物语法透传：`HEOS::Water[0.5]&Ethanol[0.5]`。
- 白名单拦截拼错（`Density`→报白名单错误并提示合法键）。
- NaN/Inf（如两相区外）显式报错，不返回脏值。

## 2. chemformula（ChemFormula · MIT · 离线零依赖）

| 命令 | 参数 | 返回 |
| --- | --- | --- |
| `chem_parse` | `formula`(如 `H2O`/`(C6H5)CHCHCOOC2H5`)、`charge=0`、`name`? | `{formula_weight, mass_fraction, element_counts, hill_formula, unicode_formula("H₂O"), latex_formula, is_radioactive}` |

- 底座为已 vendor 的 `mcpserver/adapters/chem_adapter`（上游源码零修改拷贝）。

## 3. tespy（tespy · MIT · 依赖缺失时降级）

| 命令 | 参数 | 返回 |
| --- | --- | --- |
| `tespy_check` | — | `{available: bool, version?}` |
| `tespy_solve_network` | `spec`（见下） | `{solved, mode, results:{连接线:{m,p,h}}}` |

spec 拓扑 JSON（版本适配集中在本接口层，调用方契约不随 tespy 版本漂移）：

```json
{
  "fluids": ["water"],
  "units": {"p": "bar", "T": "C", "h": "kJ/kg"},
  "components": [
    {"type": "Source", "id": "so"},
    {"type": "Pump", "id": "pu"},
    {"type": "Sink", "id": "si"}
  ],
  "connections": [
    {"from": "so", "from_id": "in1", "to": "pu", "to_id": "in1",
     "fluid": {"water": 1}, "state": {"m": 1, "p": 1, "h": 100}}
  ],
  "mode": "design"
}
```

组件白名单：Source/Sink/Pump/HeatExchanger/Pipe/Compressor/Turbine。
缺依赖：`AcademicDependencyError: tespy 未安装：pip install tespy 后可用`。

## 4. slices（SLICES · LGPL-2.1 · 重依赖只标注不否决）

| 命令 | 参数 | 返回 |
| --- | --- | --- |
| `slices_check` | — | `{available, missing: [slices|pymatgen…]}` |
| `slices_encode` | `cif_path` | `{slices: str}` |
| `slices_decode` | `slices_str` | `{formula, energy_per_atom(eV/atom)}` |

运行依赖链：`pip install slices pymatgen`（tensorflow-cpu/m3gnet 由 slices 钉版）。
GPU 非必需（CPU 可跑）；克隆中转库内无包本体，走 PyPI。

## 5. indigo（Indigo · Apache-2.0 · 离线真算可用）

| 命令 | 参数 | 返回 |
| --- | --- | --- |
| `indigo_molinfo` | `smiles`(如 `CC(=O)Oc1ccccc1C(=O)O`) | `{molecular_weight, molecular_formula("C9H8O4"), canonical_smiles, atoms, bonds}` |
| `indigo_substructure` | `query`(子结构 SMILES)、`target`(目标分子 SMILES) | `{match: bool, count: int}` |

- 底座 epam-indigo（Windows 有 wheel），解析后自动 aromatize 再算分子量/公式。
- 分子量非正/NaN 显式报错（脏值拦截）。子结构走 `substructureMatcher.countMatches`。

## 6. chembl（ChEMBL · Apache-2.0 · 在线 REST 可用）

| 命令 | 参数 | 返回 |
| --- | --- | --- |
| `chembl_molecule` | `chembl_id`(如 `CHEMBL25`) | `{pref_name, canonical_smiles, molecular_formula}` |
| `chembl_search_smiles` | `smiles`、`similarity=90`(0-100)、`limit=5`(≤20) | `{hits:[{chembl_id, pref_name, similarity}]}` |

- 底座 chembl-webresource-client（官方纯 Python，requests-cache 自动缓存）。
- 在线不可达/包缺失统一降级为同形错误（message 含 pip install 与 EBI 域名提示）。
- 已实测：CHEMBL25=ASPIRIN，阿司匹林 95% 相似检索 3 hits。

## MCP 注册

`mcpserver/academic/agent-manifest.json`（agentType=mcp，entryPoint→
`AcademicBridge`）——`scan_and_register_mcp_agents` 自动注册，服务名 `academic`，
上表 14 个 command 即 invocationCommands。全部工具经
`mcp_manager.unified_call("academic", {...})` 或 apiserver `/call` 可达。
