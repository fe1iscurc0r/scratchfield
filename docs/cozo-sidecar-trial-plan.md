# cozo 记忆 sidecar 试路径计划（W65-07）

> 来源 docs/cozo-记忆sidecar-评估.md · 试点结果待用户真机确认，不阻塞其他工单

## 路径 A/C 决策树

```
是否网络可达？
 ├─ 是 → 路径 A：standalone 二进制试点（下载/启动/建库/读写）
 │        └─ 成功 → 路径 C：真机再验
 │        └─ 失败 → 标记阻塞并回报
 └─ 否 → mock（MockCozo）验证流程，等网络恢复再走 A
```

## 下载/启动命令（路径 A）

```bash
# 下载 standalone 二进制
curl -L <cozo-release-url> -o cozo && chmod +x cozo
# 启动 server
./cozo server --path ./cozo_data
# 建库/读写最小流程（见 tools/cozo_trial.py 的 MockCozo 对应步骤）
```

## 结论

- 先 A 后 C；网络不可达走 mock 并显式标注。
- 本工单不阻塞其他工单，试点结果待用户真机确认。
