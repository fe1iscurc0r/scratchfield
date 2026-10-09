# 工单 209 · 双单：巨石体检 + 融合候选三线扫货

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：用户问三件事——自家有没有巨石要拆、有没有要优化的、有没有好项目可融合。沈遥已做初勘（巨石 LOC 榜 + GitHub 雷达扫描），本单把初勘结果转成可执行任务。**只做列出的改动，不做无关重构。**

## 任务一（P0）：巨石体检报告 + config.py 拆分准备

初勘实况（LOC 排行，本仓代码不含 NEKO/前端/venv）：

| 巨石 | LOC | 风险判读 |
|---|---|---|
| `system/config.py` | 2042 | **最高优**——全系统配置中枢，任何模块改动都要碰它 |
| `coupled/omnilimb-face/omnilimb_face/runtime.py` | 1910 | 耦合线独立子系统，影响面小 |
| `build.py` | 1765 | 构建脚本，低频改动，可容忍 |
| `agentserver/openclaw/openclaw_client.py` + `instance_manager.py` + `embedded_runtime.py` | 1540+1517+1008 | openclaw 三件套合计 4k+，但 1540 行里大部分可能是模板/常量 |
| `apiserver/travel_service.py` | 1305 | 单服务文件 |
| `apiserver/routes/chat.py` | 1268 | 聊天主路由 |

1. 先跑**测量而非猜测**：对上表每个文件出体检数据（`grep -c '^def \|^class \|^async def '` 函数数 / 最长函数行数 / import 出度——被多少文件 import），落 `docs/monolith-audit-2026-10-08.md`
2. 按数据给拆分优先级：只给**论证 + 拆分方案**（新模块边界、迁移顺序、兼容 shim 策略），**本单不动手拆**——等用户拍板哪个先拆再开执行单
3. 例外：若 `system/config.py` 的 import 出度证明它是全系统单点（预计是），在报告里标红"任何执行单第一步先给它加回归测试网再拆"

## 任务二（P1）：前端巨石 renderer.ts 拆分（执行级）

初勘实况：`frontend/src/views/mind/renderer.ts` **1863 行**，是前端最大单文件（第二名 SpectrumPanel.vue 951 行）。

1. 按 mind 视图的渲染职责拆成 composables（画布初始化/节点渲染/连线/交互手势各自独立文件，renderer.ts 降为编排层），目标单文件 ≤500 行
2. 拆分是**纯移动不改逻辑**：拆完 `npm run test` + `npx vue-tsc --noEmit` + `npm run lint` 三闸门全绿，App.vue 状态依赖图（工单 204 产出）如覆盖 mind 视图则同步更新
3. 若拆分中发现 mind 视图有死代码（无引用导出），列入报告但不删——删除另行确认

## 任务三（P1）：融合候选三线调研（调研级，不动手）

初勘雷达（GitHub 实测 2026-10-08，全部真实存在，与已有 63 份授粉报告核对未重复立项）：

| 候选 | ★ | 许可 | 融合落点 |
|---|---|---|---|
| topoteretes/cognee | 31569 | Apache-2.0 | agent 记忆平台——对照 memory_maas SPEC（已落地），借其记忆分层/ECL 检索做升级弹药 |
| MemTensor/MemOS | 11749 | Apache-2.0 | 自进化记忆 OS——与 Mem0/claude-mem 同域，授粉点：记忆调度（MemCube）而非又一个记忆库 |
| moeru-ai/airi | 50138 | MIT | 自托管 AI 伴侣容器（Live2D+语音+记忆）——**与陆墨定位最接近的开源同位素**，重点调研其 stage-web 手游级前端架构与语音管线，标注参考级 |
| netease-youdao/LobsterAI | 6087 | MIT | 网易有道桌面级 agent——中文大厂参考，借其多 agent 会话管理 UI 模式 |
| NanmiCoder/cc-haha | 14899 | MIT | 本地优先桌面工作区（Claude Code GUI）——对 openclaw 桌面化线的参考 |

1. 每个候选落一份调研卡到 `docs/fusion-candidates-2026-10/`（文件名含 owner/repo）：架构一句话 / 与自家对应模块差距 / 可借用的具体设计（非代码）/ 融合优先级（建议 airi 和 cognee 排前）
2. **许可红线**：调研卡必须标注许可证；NOASSERTION 项目（如 Open-LLM-VTuber）只做思想借鉴不引代码；GPL 系（如 Soul-of-Waifu）只读架构不融合
3. 调研完不自动立项——产出汇总表交用户挑，挑中的下轮开融合 SPEC

## 验收
- [ ] 任务一：monolith-audit 报告含每巨石实测数据（函数数/最长函数/import 出度）+ 优先级论证；不执行拆分
- [ ] 任务二：renderer.ts 拆后 ≤500 行，三闸门（test/vue-tsc/lint）全绿；纯移动不改逻辑；死代码只列不删
- [ ] 任务三：5 份调研卡落盘，每份含许可标注 + 落点 + 优先级；汇总表齐；不自动立项
- [ ] 全程 CI 绿（lint/smoke 若闸门未开则本地等价复现，参照 ci.yml 注释的两步法）
