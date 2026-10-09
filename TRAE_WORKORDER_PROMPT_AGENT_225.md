# 工单 225 · v5.2.7 发版拦路三病——raman 懒加载顺序 bug + 测试间 namespace 污染源定位 + 恢复防线入库

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-09
> 背景：v5.2.6 发版 CI 红（run 37890346845）。工单 224（conftest find_spec 容错）只解了第一层。沈遥复盘 v5.2.5 CI 实录 + 本地 CI 同口径复跑（PYTHONPATH=仓根 + 裸 pytest tests/），确认还有三层。展示仓（scratchfield）侧的自有防线恢复已由沈遥完成并推送（scratchfield commit 9ac46fc8）——本单修 **scratchpad 主线代码**，同步自然带走。

## 事故全貌（沈遥实测证据，全部可复现）

本地 CI 同口径全量：**854 passed / 8 skipped / 9 failed**。9 个失败分三病：

### 病一（P0，上游真 bug）：raman 懒加载顺序错误

`tools/raman_utils.py:48-58` `parse_raman_vendor`：

```python
def parse_raman_vendor(data, fmt):
    import ramanspy as rp        # ← 第 54 行：先 import
    loader = {...}               # ← fmt 校验在 import 之后
```

`tests/test_raman_utils.py:98` `test_unknown_vendor_format_rejected` 传 `fmt="unknown"` 期望 ValueError——但函数在触达校验前就 `import ramanspy`，CI 最小安装无此包 → ModuleNotFoundError，测试挂。

**这代码两边仓库同源（737d43fa 引入），上游从第一天就带病**——只是 v5.2.5 CI 时该测试文件被 conftest 跳过（scipy 缺失），病没暴露。10-09 同步后 requirements 变化让 scipy 可用 → 病浮出。

**修法**：把 fmt 白名单校验提到 import 之前（校验不需要 ramanspy）；`import ramanspy` 保留懒加载但只在校验通过后执行。顺手核对同文件其他懒加载点是否有同型问题。

### 病二（P0）：测试间 namespace 污染源（7 个失败同根因）

七个测试**函数内** `from tests.test_agentic_loop_flow import _collect, _FakeLLM, ...`（test_task_goal_mode:195/228、test_task_context_channels:109、test_skill_loader:184、test_scope:215、test_subagent:174）：

- **单文件跑绿**：pytest rootdir 导入机制下 `tests` 可解析
- **全量跑挂**：`ModuleNotFoundError: No module named 'tests.test_agentic_loop_flow'`
- **v5.2.5 CI（686 collected→679 passed）全绿**——10-09 同步进来的 ~185 个新测试里有谁动了 sys.modules/sys.path，把 `tests` 命名空间搞坏了

**任务**：二分定位污染源（嫌疑：test_mcporter_lazy 的 lazy loader、test_verify_entrypoint/test_neko_launcher_wrapper_failfast 的 monkeypatch.setitem(sys.modules,...)、test_switch_llm_provider 的双 sys.path.insert）。方法：`pytest tests/test_agentic_loop_flow_direct_probe.py`（写临时探针文件 import 七处之一）+ 逐半跑全量二分。

**修法原则**：修污染源本身，不动七个受害测试（它们模式没错）；若污染源是合理的 lazy-loader 测试需求，则在其 teardown 里恢复 sys.modules 原状。

### 病三（P1）：test_config_and_tools stream_chat 顺序失败

`McpFuncNameSanitizeTests::test_stream_chat_returns_visible_error_after_empty_stream_retries` 与 raman 同批跑挂、单跑绿。先修病一后回归验证——若仍挂，同病二方法二分。

## 任务清单

1. **（P0）病一修复**：raman_utils fmt 校验前置 + 懒加载顺序修正；本地验证 `pytest tests/test_raman_utils.py` 全绿（无 ramanspy 环境下 unknown fmt 正确抛 ValueError）
2. **（P0）病二定位+修复**：二分出污染源 commit/文件，修复并附探针复现实录（修复前挂/修复后绿的命令输出）
3. **（P1）病三回归**：病一修完后复跑，仍挂则同法处理
4. **（P0）CI 同口径全量验证**：`PYTHONPATH=<仓根> pytest tests/ -q` 在干净 venv 全绿（或 skipped 项全部有 conftest 登记依据）；不接受只修不验
5. 报告落 `docs/ci-v527-blockers-2026-10.md`：三病各一节（根因/修法/复现实录）

## 验收

- [ ] 病一：raman 测试无 ramanspy 环境下绿，校验前置 diff 清晰
- [ ] 病二：污染源定位到具体测试文件 + 修复 + 探针实录
- [ ] 病三：结论明确（被病一带飞治愈 / 独立修复 / 无法本地复现则记录 CI 观察）
- [ ] CI 同口径全量：9 failed → 0
- [ ] 报告落地 + CI 绿

## 发版衔接（沈遥侧备忘）

Trae 合入 → 沈遥同步 scratchfield → bump frontend/package.json 5.2.7 → tag v5.2.7 → CI 全绿出草稿 → 用户过目发布。scratchfield 侧防线已恢复（9ac46fc8），tag 打上去即走完整防线（PYTHONPATH+tag↔版本校验+Lumo 产物名）。

## 坑位沉淀（写给出单人的复盘，已入本单防复发）

**同步误伤模式**：整文件覆盖式同步会抹掉展示仓对**同名文件的私有补丁**（conftest 登记表、workflow 防线、skipif）。后续同步必须先 diff 目标文件在展示仓是否有未带上游的自有改动（`git diff <上次同步基底> <tag> -- <file>`），有则三分法：自有改动保留 + 上游增量叠加 + 冲突人工裁决。本次三处误伤全是这个模式。
