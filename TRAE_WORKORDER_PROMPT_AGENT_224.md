# 工单 224 · CI 收集炸点修复——find_spec 对缺失父包抛异常炸掉全量测试收集

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-09
> 事故实录：scratchfield v5.2.6 发版 CI 红（run 37890346845，2026-10-09 05:51Z）。test job 在**收集阶段**即崩，build/release 连跑都没跑。v5.2.6 tag 已被保护规则锁死，修复后版本顺延 v5.2.7。

## 事故链（实测证据）

```
tests/conftest.py:27  importlib.util.find_spec(module_name)
→ ModuleNotFoundError: No module named 'mcpserver'
```

1. conftest 用 `find_spec("mcpserver.antenna_rotator")` 判断可选依赖是否存在——设计意图正确（w129 硬件分支的模块，主线缺失时跳过收集）。
2. **坑点**：`find_spec` 查找 `a.b` 时若**父包 `a` 本身不在 sys.path**，不返回 None 而是直接抛 `ModuleNotFoundError`（Python 文档明文行为）。
3. scratchpad 本地/云服跑不炸：cwd 在仓根，`''` 恰好在 sys.path 里，`mcpserver` 可导入——**本地绿纯属巧合**。
4. scratchfield CI 干净环境（pytest tests/ -v，无 cwd 注入路径）裸奔：炸。`mcpserver` 在 scratchfield 是**存在**的（有 __init__.py），但 CI 里 cwd 不进 sys.path（pytest rootdir 处理差异），父包照样找不到。

**同病双仓**：scratchpad 与 scratchfield 的 tests/conftest.py:27 完全同源（本单修 scratchpad 主线，scratchfield 走既有同步管线自然带走；发版 v5.2.7 前需同步+重打 tag）。

## 任务一（P0）：conftest 容错修复

1. `tests/conftest.py` 的 `collect_ignore` 推导式改为安全探测：
   ```python
   def _spec_missing(module_name: str) -> bool:
       try:
           return importlib.util.find_spec(module_name) is None
       except (ImportError, ValueError):  # 父包缺失/命名空间异常 → 视为缺失
           return True

   collect_ignore = [
       test_file
       for test_file, module_name in _OPTIONAL_MODULE_TESTS
       if _spec_missing(module_name)
   ]
   ```
2. 注释写明本次事故根因（父包不可导入时 find_spec 抛异常而非返 None），引用本工单号。
3. **同步修语义**：CI 里 `mcpserver` 不可导入时 4 个 ptz 测试会被跳过收集——这是**预期行为**（它们本来就是 w129 分支专属），但要在 conftest 注释里说清"主线 CI 跳过属正常"，防止后人误判覆盖缩水。

## 任务二（P0）：验证双环境

1. **干净环境复现验证**：`python3 -X importtime -c` 或直接 `cd /tmp && python3 -m pytest <仓>/tests/ --collect-only`——确认修复前炸、修复后收集成功（ptz 四件跳过、其余全收集）。
2. **仓根环境回归**：正常 `pytest tests/ -v` 全绿，ptz 四件行为不变（本地仓根可导入 mcpserver 时照常收集）。
3. 若任务二的收集结果里出现其他因路径导致的假绿/假红，一并记录进报告（不接受只修不验）。

## 任务三（P1）：防复发

1. 全仓 grep `find_spec`，其他调用点若同样裸调无兜底，逐个加同样的 try/except 包装（报告列出位置清单，无则写"全查无遗漏"）。
2. CI 侧不动闸门（ENABLE_FULL_BUILD 开着是 scratchfield 的事，scratchpad 的 CI 变量不在本单范围）。

## 验收

- [ ] 任务一：conftest 修复落地，含事故根因注释 + 工单号引用
- [ ] 任务二：双环境验证记录（/tmp 下裸 pytest 修复前炸/修复后收集成功 的实录输出贴报告）
- [ ] 任务三：find_spec 全仓排查清单
- [ ] 全程 CI 绿（本仓 CI 闸门若关，以本地双环境实录为准）

## 发版衔接（沈遥侧备忘，非 Trae 任务）

- scratchpad 合入 → 同步到 scratchfield → bump frontend/package.json 5.2.7 → 打 tag v5.2.7 → CI 全绿出草稿 → 用户过目发布。v5.2.6 的 tag 留着指红提交，无害（坑②惯例）。
