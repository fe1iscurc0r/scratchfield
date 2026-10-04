# Task 容器（卷123 W123-01）

把「对话」升级为「可跟踪任务」：一个任务持有 **目标 / 步骤 / 文件引用 / 结果 / git 基线**，
可 pause / resume，每步留轨迹。ZCode 的 Goal Mode 就建在这上面。

## 权威源：SQLite

`apiserver/task_store.py` 用 **与 message_store 同一个库**（`<user_data>/message_store.db`）
里的独立表 `tasks`。不扩建 message_store 的既有三列 schema —— NEKO 侧的
`SQLChatMessageHistory` 只认 `id/session_id/message`，扩建会碰它。

- **任务状态以 SQLite 为权威，内存只是缓存**：进程重启后 `get_task()` 照样读到；
  `status=paused` 的任务可 `resume`
- 写操作全部参数化 SQL；连接用完即关（`WAL` 模式，与 message_store 一致）
- 关联维度是 `session_id`：任务与消息用同一个 session_id，可按会话联合查询
  （`tasks.session_id` 有索引）

## 表结构

| 列 | 说明 |
| --- | --- |
| `task_id` | uuid4 hex（主键） |
| `session_id` | 会话号（与 message_store 对齐，有索引） |
| `goal` | 用户原始目标 |
| `status` | `pending / running / paused / review / done / blocked / failed` |
| `exec_mode` | `explore / code / test / review` |
| `steps_json` | 步骤数组：`{id, desc, status, type, result_ref, ts}` |
| `file_refs_json` | 涉及文件路径（去重保序） |
| `git_state` | 建任务时的 git 基线（`分支@短hash`） |
| `trajectory_json` | 轨迹：`{ts, step_id, tool, summary, status}`，保留最近 200 条 |
| `review_json` | Review 汇总（W123-04 写入） |
| `created_at / updated_at` | 时间戳 |

## 接口

```python
from apiserver import task_store
task = task_store.create_task(session_id, goal, steps=[...], exec_mode="explore",
                              git_state="main@abc1234", status=task_store.STATUS_RUNNING)
task_store.get_task(task_id) / list_tasks(session_id, status=..., limit=...)
task_store.update_step(task_id, "s2", task_store.STEP_DONE, result_ref="calc.py:12")
task_store.pause_task(tid) / resume_task(tid) / set_status(tid, "review")
task_store.add_file_refs(tid, ["calc.py"]) / append_trajectory(tid, tool="test_run", summary="1 passed")
task_store.task_summary(task)   # 给 LLM 看的一句话摘要
```

## 对话侧协议（`apiserver/task_flow.py`）

**用户元指令**（`apiserver/routes/chat.py` 在进 LLM 前处理，命中即短路，无需模型）：

| 指令 | 行为 |
| --- | --- |
| `task:create <目标>` | 建任务（默认四步：探查→实现→测试→验证），回复计划清单 |
| `goal:<目标>` | 目标模式：模型先出 `[PLAN]`，系统按计划建任务（pending 等确认） |
| `task:confirm` | 确认计划，任务转 running 开始逐步执行 |
| `task:list` | 列**可见任务**（本会话 + 同用户其它通道，见 W123-05；不回落到全局列表） |
| `task:continue [id]` | resume 并回任务摘要（含跨通道：会标注「来自会话 xxx」） |
| `task:skip <step_id>` | 跳过某步 |
| `task:replan <新目标>` | 重新计划（回 pending） |
| `task:pause [id]` / `task:resume [id]` | 暂停 / 恢复 |
| `task:review [id]` | 出审查报告（W123-04） |
| `task:accept` / `task:reject <意见>` / `task:skip-review` | Review 裁决三路径 |

**模型 `[TASK]` 段**：模型在回复里写 `[TASK]{json}[/TASK]`，`extract_task_ops()` 抽取、
`apply_task_ops()` 落库，支持 `create / step / complete / pause`。实现类步骤标 done 时会先过
**验证门**（W123-03：跑测试或语法门，fail-closed）。`[TASK]` 段本身会留在正文里
（与 `[PLAN]` 一致），前端按需渲染。

默认步骤模板（`task_flow.DEFAULT_STEP_TEMPLATE`）：
`探查（explore）→ 实现（code）→ 测试（test）→ 验证（verify）`。
可用 `config.json` 的 `task_flow.step_template` 覆盖，每条 `type:描述`。

## 配置（`config.json` 的 `task_flow` 段）

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 是否启用任务流元指令与 `[TASK]` 解析 |
| `step_template` | 空 → 内置四步 | 默认分解模板 |
| `verify_audit_only` | `false` | 验证门只记不拦（W123-03） |
| `verify_max_retries` | `2` | 验证失败允许的修改重试次数（W123-03，fail-closed） |
| `review_dir` | `docs/task-reviews` | Review 报告落盘目录（W123-04） |
| `review_enabled` | `true` | 全步完成是否进 review（false 直接 done） |
| `cross_channel_shared` | `true` | 同用户跨通道任务可见（W123-05）；false 按通道隔离 |
| `idle_advance` | `false` | 空闲任务提示挂到 SCHEDULER_TICK（W123-05） |
| `idle_minutes` | `30` | 多久没动算空闲 |

## 任务级上下文与跨通道（W123-05）

- 注入：每轮把「目标 + 步骤进度 + 当前步 + 相关文件 + 上一步结果」并入 `messages[0]`
- 压缩边界 = 步骤边界：某步完成后 `step_boundary_compact()` 把更早的工具结果收敛成
  「已完成 + 关键结果」一条；goal 与关键结果不压（权威源在 SQLite）
- 跨通道：任务表 `user_id`（老库自动补列）；`bind_task_owner()` 建任务时绑登录用户，
  `channel_visible_tasks()` 决定可见性（不同用户一律不可见）
- 详见 `docs/任务上下文与跨通道-W123-05-2026-09-17.md`

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests -k "task_store or task_goal_mode or task_verify or task_review or task_context_channels" -q
```

覆盖：模板建任务 / 步骤流转与 result_ref / 暂停恢复与状态校验 / 重启后新连接读到状态 /
轨迹追加与统计 / 文件引用去重 / 目标模式（PLAN 解析、确认、fail-closed）/ 验证门（通过、
失败、重试窗口、语法门、audit_only）/ Review（汇总、三种裁决、报告落盘）/ 任务上下文与
步骤边界压缩 / 跨通道可见性与隔离 / 空闲提示；另含与 message_store 同库不同表的校验。

## 回滚

`task_flow.enabled=false` 关闭元指令与 `[TASK]` 解析；彻底回滚删 `task_store.py`、
`task_flow.py` 与 `chat.py` 里的两处短路即可——`tasks` 表留在库里无副作用。
