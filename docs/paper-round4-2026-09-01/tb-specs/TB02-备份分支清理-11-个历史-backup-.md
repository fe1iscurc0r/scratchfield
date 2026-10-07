# TB02 备份分支清理（11 个历史 backup）

> 批次：第十三期 · 专项工单
> 组装：沈遥（Hermes）2026-09-01

【SPEC】清理 scratchpad 本地 11 个历史 backup 分支（backup-*、scratch-backup-231728）：确认无未合并独有提交后删除，保留主历史。

【验收】git branch 输出仅剩有效分支；删除前确认各分支无 main 缺失提交（git log main..分支 为空）。

【工单】① git log main..备份分支 逐个检查 ② 无独有提交则 git branch -D 删除 ③ 输出删除清单。
