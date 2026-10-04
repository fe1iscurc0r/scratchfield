# A31 Agent 自我恢复→无线电参数状态回滚

> 来源分组：group3-agent安全（第四批）

【SPEC】NEKO/IC-705 增加参数状态回滚：EvoUndo 恢复演算→每次参数变更带反向操作日志，干扰消失后精确回滚。验收=方案 + 原型。
【工单】①读 round3 digest-g1b EvoUndo 授粉点 ②设计恢复演算 ③实现 ④评估。
【提示词】你是状态恢复 AI。读 /home/ubuntu/research/papers/round3/digests/digest-g1b-2026-08-31.md 中 EvoUndo（2608.28363）授粉点（恢复语言+精确状态接地，恢复率 99.3%），为 IC-705/NEKO 设计无线电参数状态回滚：频率/功率/调制变更记录反向操作日志，干扰消失后精确恢复。输出方案 + tools/radio_state_undo.py。验收：模拟参数变更回滚正确率 ≥95%。推 trae/agent-a31 分支。
