# TB08 本地 main 同步 + 临时分支清理（验证）

> 批次：第十三期 · 专项工单
> 组装：实验田维护者（Hermes）2026-09-01

【SPEC】验证本地 main == 远端 main（6adb4a39a），确认 merge-第九批 临时分支已删；同步各工作线分支。

【验收】git rev-parse main == github/main；git branch 无 merge-* 残留。

【工单】① git fetch github main ② 比对 SHA ③ 清理残留临时分支 ④ 输出状态。
