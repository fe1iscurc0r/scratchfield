# process-sim 双引擎统一 handler SPEC v1 · 2026-10-01（卷170-B）

> 照 SPEC 写作规范 v3：四问 + 不变量验收 + 假设分层。
> 范围：**仅 SPEC**——Aspen 相关不装软件（机房授权依赖，标「待真机」）。

---

## 一、边界（Boundaries）

**做**：`research/process_sim/handler.py` 提供 `Handler(kind)` 统一门面，四方法
`setup / set_stream / run / read_results`；两个后端 adapter（dwsim / aspen）各自把
四方法翻译到上游 API。

**不做**：不实现流程求解器本身（完全委托上游引擎）；不管理授权（Aspen 许可见
「假设分层」）；不做 GUI；不引入新依赖（DWSIM 走其 .NET 桥的本机安装，Aspen 走
COM——均为运行时依赖，非 pip 依赖）。

## 二、层次（Layers）

```
Handler(kind='dwsim'|'aspen')        ← 门面（唯一公共入口）
  ├─ DWSIMAdapter                    ← 桥 dwsim-claude-integration（.NET/Python 桥）
  └─ AspenAdapter                    ← 桥 Aspen-Plus-Automation（COM）
```

Adapter 只翻译不加工；Handler 层做参数校验与统一错误形状。

## 三、关系（Relations）

- 与卷169 的 MCP 模式同构：四方法将来可包成 MCP invocationCommands（本 SPEC 不做）
- 与卷168/170-A 的关系：Bioindustrial-Park（bioSTEAM）是**纯 Python 第三引擎**，
  接口天然可适配同四方法——v2 扩展点，v1 只落 DWSIM/Aspen 两后端

## 四、目的（Purpose）

同一份"流程模拟"语义（加载流程表 → 设流 → 求解 → 读结果）不应因商业/开源引擎
不同而换 API 心智——统一 handler 让 TEA 管线的上游引擎可替换（DWSIM 起步，
Aspen 待授权后切换，**调用方代码零改动**）。

---

## 五、统一接口（v1 签名）

```python
class Handler:
    def __init__(self, kind: str): ...                  # kind ∈ {'dwsim', 'aspen'}
    def setup(self, flowsheet: str) -> None: ...        # 加载/新建流程表（文件路径或模板名）
    def set_stream(self, name: str, T: float, P: float,
                   comp: dict[str, float]) -> None: ... # 组分: 摩尔分数（和为 1 由 adapter 校验）
    def run(self) -> None: ...                          # 求解（同步阻塞；错误抛 SimulationError）
    def read_results(self, stream: str,
                     props: list[str]) -> dict[str, float]: ...  # 如 ['T','P','MOLEFRAC']
```

不变量（全后端成立）：
- `setup` 未调用前调用其余三方法 → `RuntimeError('not initialized')`
- `set_stream` 的 comp 摩尔分数和不等于 1（容差 1e-6）→ `ValueError`
- `run` 后 `read_results` 才有有效数据；失败路径抛 `SimulationError`（统一形状：
  `{engine, stage, detail}`）

## 六、两后端映射表（签名级对照，上游路径引用）

| 统一方法 | Aspen COM（`Aspen-Plus-Automation/script/aspen_utils_v2.py` + `simulation_v2.py`） | DWSIM（`dwsim-claude-integration/src/core/automation.py` + `flowsheet.py`） |
|---|---|---|
| `setup(flowsheet)` | `Aspen_Plus_Interface.load_file(file, visible_state=0, dialog_state=0)` + `re_initialization()`（COM `Application.InitFromArchive2`） | `DWSIMAutomation.initialize()` → `create_flowsheet()` 或 `load_flowsheet(path)`（实测方法清单见上游 `automation.py:88-174`） |
| `set_stream(name, T, P, comp)` | `Application.Tree.FindNode(r"\Data\Streams\<name>\Input\TEMP").Value = T`（同 P/流量——`simulation_v2.py:44-47` 的 FindNode 路径式写入实测） | `FlowsheetManager.add_compound(name)` + 流对象属性设置（`flowsheet.py:103-141`；T/P 经 stream 对象 `Phases[0].Properties` 赋值） |
| `run()` | `Aspen_Plus_Interface.run_simulation()`（`aspen_utils.py:31`，内部 `Engine.Run2`）+ 完成后读 `Run-Status` 检查（`simulation_v2.py:56-57` UOSSTAT 实测） | `DWSIMAutomation.calculate(...)`（`automation.py:192`） |
| `read_results(stream, props)` | `Tree.FindNode(r"\Data\Streams\<s>\Output\MOLEFRAC\MIXED\<c>").Value`（`simulation_v2.py:54-55`：MOLEFRAC/REB_DUTY 实测） | `FlowsheetManager.get_object(stream)`（`flowsheet.py:247`）→ 读流属性字典 |

辅助：Aspen 侧 `KillAspen()`（进程清理，`aspen_utils.py:75`）；DWSIM 侧
`get_available_compounds()` / `get_version()`（`automation.py:242-262`）。

## 七、假设分层

| 层 | 假设 | 验证手段 |
|---|---|---|
| **可自验假设**（本机） | DWSIM 桥可 import（需本机装 DWSIM + pythonnet）；`Handler('dwsim')` 的方法面完整 | `python -c "from research.process_sim.handler import Handler; h=Handler('dwsim'); assert hasattr(h,'set_stream')"` |
| **可自验假设**（本机） | 统一错误形状 / comp 校验 / not-initialized 不变量 | `pytest research/process_sim/ -q`（mock adapter 注入） |
| **待真机假设**（Aspen） | COM 授权可获取；`load_file` 能打开 `.bkp`；FindNode 路径在目标版本稳定 | 机房授权机实测（SPEC 阶段只标注） |
| **待真机假设**（DWSIM 桥） | pythonnet 在 Windows + DWSIM 安装环境下能加载 `DWSIM.Automation` | 装 DWSIM 后跑 `Handler('dwsim').setup('samples')` |

## 八、验收标准（全部可执行）

```bash
# 1. 门面与方法面（无引擎环境即可验——错误形状/校验逻辑）
python -c "from research.process_sim.handler import Handler; h=Handler('dwsim'); assert hasattr(h,'set_stream') and hasattr(h,'read_results')"
# 2. 不变量（未初始化即调 run）
python -c "from research.process_sim.handler import Handler; import pytest; h=Handler('dwsim'); exec(\"try:\\n h.run()\\nexcept RuntimeError as e:\\n assert 'not initialized' in str(e); raise SystemExit(0)\\nraise SystemExit(1)\")"
# 3. comp 校验
python -c "from research.process_sim.handler import Handler; h=Handler('dwsim'); h._initialized=True; exec(\"try:\\n h.set_stream('S1', 300., 101325., {'H2O':0.5})\\nexcept ValueError: raise SystemExit(0)\\nraise SystemExit(1)\")"
# 4. 全量单测
pytest research/process_sim/ -q
```

## 九、验收自检（四问）

- 边界：§一（不实现求解器/不管授权/不引依赖）✓
- 层次：§二（Handler 门面 → 两 adapter，翻译不加工）✓
- 关系：§三（与 MCP 模式/bioSTEAM v2 扩展点）✓
- 目的：§四（引擎可替换，调用方零改动）✓
- 不变量验收：§五（三条不变量）+ §八（四条可执行命令）✓
- 假设分层：§七（2 可自验 + 2 待真机）✓
