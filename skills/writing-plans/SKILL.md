---
name: writing-plans
description: SPEC → 分块施工计划 skill——把已批准的设计转成可执行工单：Phase 分解、每任务带输入/输出/验收三件套、依赖排序、风险与回退。产出格式与本仓 docs/ 工单体系一致。触发：设计已批准要排计划、写工单、拆 SPEC。触发词：写工单、排计划、拆解 SPEC、writing-plans。
version: 1.0.0
author: scratchpad (Agent 3, SPEC-03 Phase4)
license: Apache-2.0
tags: [process, planning, workorder]
enabled: true
---

# writing-plans — SPEC → 分块施工计划

## 何时用
设计已经过 `brainstorming` 批准（或用户直接给了明确 SPEC），进入排期拆解。

## 工单格式（本仓标准）

每个 Phase / 任务块：

```
━━━━━━━━━━━━━━━━━━━━
工单 <ID>｜<名称>
━━━━━━━━━━━━━━━━━━━━
- 优先级：P0/P1/P2｜状态：可启动/被阻塞(依赖谁)
- 输入：<上游产物路径或仓库链接>
- 落点：<产出写到哪里>

任务步骤：
1. ...
2. ...

验收标准：
- <可执行断言，宁少而硬，不多而软>

注意事项：<不做什么 / 已知坑 / license 要求>
━━━━━━━━━━━━━━━━━━━━
```

## 拆解规则
1. **一任务一交付物**：每个任务有明确落盘产物（文件/测试/报告）
2. **验收可执行**：验收标准要能变成 assert/命令，"工作正常"不算验收
3. **依赖显式**：被阻塞的任务写清楚等谁，禁止隐式依赖
4. **风险前置**：最不确定的事放最前面（spike 先行），别把风险埋在最后
5. **license 注记**：借鉴上游代码的任务必须在工单和代码里双注明（MIT/Apache 来源）

## 输出骨架
```
# <项目> 施工计划 v<n>
## Phase 0：<地基/spike>
## Phase 1：<核心链路>
## Phase N：<收尾与验收>
## 硬约束
## 验收清单（汇总）
```

## 衔接
计划落地后每完成一块 → 跑 `verification-before-completion` 过验收门。
