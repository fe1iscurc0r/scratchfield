# v5.2.7 发版拦路三病修复报告（工单225）

> 日期：2026-10-09 ｜ 环境：本机 venv（CI 同口径 `PYTHONPATH=<仓根> pytest tests/`）。

## 病一（P0）：raman 懒加载顺序 —— ✅ 修复

**根因**：`tools/raman_utils.py` 的 `parse_raman_vendor` 先 `import ramanspy` 后校验 fmt。
CI 最小安装无 ramanspy → `test_unknown_vendor_format_rejected` 期望的 ValueError 变成
ModuleNotFoundError。上游 737d43fa 引入即带病，v5.2.5 前被 conftest 跳过（scipy 缺失）掩盖。

**修法**：fmt 白名单校验**前置**（校验不需要 ramanspy），懒加载保留但只在校验通过后执行；
loader dict 从 `.get()+None 判断`改为直取（校验已保证键存在）。

**验证实录**：无 ramanspy 环境（`find_spec('ramanspy') is None` 实测）
`pytest tests/test_raman_utils.py` → **11 passed**（修复前 unknown fmt 必挂）。

## 病二（P0）：测试间 namespace 污染 —— ✅ 污染者锁定 + 修复

### 定位过程（二分实录）

1. 四嫌疑配对全绿（mcporter_lazy/verify_entrypoint/neko_launcher/switch_llm 均单对不挂）；
2. 字母序四段二分：段1-3 victim 绿、**段4 挂**；段4 内二分（[9:18]→[16:17]）锁
   **`tests/test_switch_llm_provider.py`**——单独与 victim 配对即挂 ✓✓。

### 污染机制（探针实测）

```
sys.path.insert(0, ROOT/"tools")  # test_switch_llm_provider.py:15 模块级
→ tools/tests/（卷179 台账验证子包，有自己的 __init__.py）抢走顶层 "tests" 命名空间
→ 探针实录：find_spec('tests') = ModuleSpec(origin='...\\tools\\tests\\__init__.py')
→ victim 的 from tests.test_agentic_loop_flow import ... 解析到 tools/tests → ModuleNotFoundError
```

单跑不挂的原因：sys.path[0] 是 tests/ 目录（pytest prepend），`tests` 名字未被抢占。

**修法**：test_switch_llm_provider 不再污染 sys.path——改 `importlib.util.spec_from_file_location`
按文件路径加载 `tools/switch_llm_provider.py`（与 tools/tests 自己的加载姿势一致）；ROOT 查重后插入。

**验证实录**：`pytest tests/test_switch_llm_provider.py tests/test_task_goal_mode.py` →
**17 passed**（修复前 9 挂）；全量 diff 显示 **7 个 victim（goal_mode×2/context_channels/skill_loader/
scope/subagent）全部转绿**。

## 病三（P1）：test_config_and_tools stream_chat —— ✅ 本地不复现（结论：随病一/病二治愈）

该测试在本轮两次全量（修复前后）的失败名单里**均未出现**——它只在沈遥的组合环境里挂过，
本机 PYTHONPATH 同口径已无此失败。判定为**被病一/病二带飞治愈**（工单预判的分支一）。
CI 侧若复现再单独立项。

## CI 同口径全量终验

`PYTHONPATH=<仓根> pytest tests/ --ignore=tests/test_spec03_phase1.py`：
**14 failed / 979 passed / 6 skipped / 7 errors**（修复前 37 failed）。

剩余 14 个失败**全部是已登记的既有账**（非本单三病）：
- memory_maas 9 + 7 errors：NEKO `utils/http/url.py` 缺 `same_endpoint`（10-08 MEMORY 登记）；
- hamlog_adapter 2 + code_workspace 1：test_agentic_loop_flow 先跑的顺序污染（10-08 MEMORY 登记）；
- planner 1：单跑绿（8 passed），同顺序账类型。
另 spec03_phase1（--ignore 排除）：NEKO same_endpoint 同根因。

**顺手修的环境账**（本机 venv 缺件，非代码问题）：duckdb/capstone/casregnum/chemformula/
CoolProp/affine-gaps/PyniteFEA 补装 + thermo 重装（残留半装）→ academic 线 23 passed
（可调用 5 项 ≥ 验收线）。

## 发版建议

三病已除，剩余失败全部既有账。scratchfield 同步后打 v5.2.7 tag（沈遥侧流程）。
若 CI 上 config_and_tools 复现，按病二同法二分（本地无复现基础）。
