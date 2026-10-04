# 论文池增量自动 digest cron 配置更新说明（W60-04）

> 来源 docs/paper-pipeline-cron-增量.md（K06）· 只交付文本，不直接改用户 cron

## 触发条件

- 增量 `N` = 上次运行以来新入库论文数。
- `N < 50`：仅趋势摘要（现状行为，不逐篇）。
- `N ≥ 50`：触发全量 digest 轮，按 ≤100 篇/块分块。

## 更新后的 cron prompt（替换 ad17cd9d341f 的 prompt）

代码里 `build_cron_prompt()` 已内嵌该文本，可直接调用获取：

```python
from scripts.pipeline_cron_upgrade import build_cron_prompt
print(build_cron_prompt())
```

其内容（与 docs/paper-pipeline-cron-增量.md 第 2 节一致）：

> 你是论文流水线 cron，每天 2:00 执行：
> 1. 拉取自上次运行以来的 arXiv 增量，计算新论文数 N。
> 2. 若 N < 50：只产出趋势摘要（周度/主题趋势，不逐篇）。
> 3. 若 N ≥ 50：触发全量 digest 轮——按 ≤100 篇/块分块（硬上限 100，>150 必超时）；
>    每块两次调用（先「逐篇一行核心 + Top 模式」，再「最有价值 3 篇 + 跨领域授粉点」）；
>    禁止 digest 前派子代理逐篇预处理；超时块按 100 重切一次，仍超时降级为「仅标题 + ID」摘要行。
> 4. 输出：趋势摘要（每次）+ 增量 digest（仅 N ≥ 50 时）。

## 在 Hermes/Linux 侧的替换步骤（供运维参考，本机不执行）

1. 找到 cron 任务 `ad17cd9d341f` 的 prompt 配置项。
2. 用 `build_cron_prompt()` 输出的文本覆盖其 prompt。
3. 重启 cron 调度（无需改执行频率，仍为每天 2:00）。

## 验收对照

- [x] 触发条件明确（N ≥ 50 触发 digest，N < 50 仅摘要）——见 `scripts/pipeline_cron_upgrade.py` 的 `plan_run`。
- [x] prompt 已更新（阈值 + 分块模式 + 子代理纪律）——见 `build_cron_prompt()`。
- [ ] cron 侧替换：本机无该 cron，仅交付文本（待用户在 Hermes/Linux 侧覆盖 `ad17cd9d341f`）。
