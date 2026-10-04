# S13 SkillForge 固件模块验证 → OTA 自动回滚

> 来源分组：group3-agent安全（第二批）

【SPEC】LoRaCanary 固件增加模块级验证生态：固件模块运行时通过环境交互（硬件状态反馈）验证自身正确性，失效模块自动回滚而非整体重刷。验收=方案 + 骨架。
【工单】①读 digest-g2-3 SkillForge 授粉点 ②结合 AB 线固件现状 ③设计模块验证/回滚 ④骨架实现。
【提示词】你是固件可靠性 AI。读 digest-g2-3-2026-08-30.md SkillForge 授粉点（技能持续验证生态→固件模块版本共存/热插拔），为 LoRaCanary C3 固件设计模块验证+自动回滚：模块启动自检（硬件状态反馈）+ 运行期健康检查 + 失效回滚到上一版本。输出方案 docs/loracanary-module-ota-方案.md + 骨架代码（firmware/loracanary/module_manager/）。验收：方案含回滚触发条件表 + 骨架可编译。推 trae/agent-s13 分支。
