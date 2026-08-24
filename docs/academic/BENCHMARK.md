# academic 基准用例（BENCHMARK）

> W-09 · 每个 MODEL_INTERFACE 配可复现基准；实测列以本仓 .venv
> （Windows / Python 3.11.15）2026-08-23 结果为准。未跑项标 pending 及原因，
> 不虚标。

| 接口 | 基准用例 | 期望 | 实测 | 状态 |
| --- | --- | --- | --- | --- |
| chemformula | `chem_parse("H2O")` 分子量 | 18.015 ±0.01 g/mol | 18.015 | ✅ 离线真算 |
| chemformula | H 质量分数 | 0.1119 ±0.001 | 0.1119 | ✅ |
| chemformula | `chem_parse("C6H12O6")` 分子量 | 180.156 ±0.05 | 180.156 | ✅ |
| coolprop | 水 @300K, 101325Pa 密度 | 996.56 ±1.0 kg/m³ | 996.56 | ✅ 真算（CoolProp 已装） |
| coolprop | 水临界温度 | 647.096 ±0.5 K | 647.096 | ✅ |
| coolprop | 白名单拦拼错（`Density`） | ValueError 含合法键 | 通过 | ✅ 契约测试 |
| tespy | 依赖探测 | available=False（venv 未装） | False | ✅ 降级契约 |
| tespy | 未装求解 | `AcademicDependencyError` 含 `pip install tespy` | 通过 | ✅ |
| tespy | spec 非法先报参数错（不依赖包） | ValueError 缺字段/白名单 | 通过 | ✅ |
| tespy | 泵水网络 design 解 | 收敛 | — | ⏸ pending：venv 未装 tespy（pip install tespy 后补测） |
| slices | 依赖探测 | missing 含 slices/pymatgen | 通过 | ✅ 降级契约 |
| slices | 未装编/解码 | `AcademicDependencyError` 含 pip 提示 | 通过 | ✅ |
| slices | NdSiRu.cif 往返保真 | 重构结构化学式一致 | — | ⏸ pending：重依赖链未装（GPU 非必需，CPU 可跑；只标注不否决） |

## 回归口径

- `pytest tests/test_academic_interfaces.py` → 13 passed（层级 16 全标注 /
  MODEL_INTERFACE ≥4 grep 断言 / 真算 / 降级 / MCP 注册链路）。
- grep 断言等价命令：`grep -l "MODEL_INTERFACE" mcpserver/academic/*_interface.py | wc -l` ≥ 4。

## 补测指引（解除 pending）

```bash
pip install tespy                 # 后跑 tests 中 tespy 真求解用例
pip install slices pymatgen       # 后跑 SLICES 往返保真用例
```
