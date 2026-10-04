# R50 APC-RLNC Mesh 弹性路由

> 来源分组：group1-无线电（第二批）

【SPEC】LoRaCanary 增加分层网络编码弹性路由：承接 SPEC-20 v1.6 弱链路增强（EWMA 分组 + XOR 冗余），APC-RLNC 分层编码到 Mesh。验收=方案 + 原型 + 与单跳对比。
【工单】①读 digest-g8-3a APC-RLNC 授粉点 ②结合 v1.6 link_reliability.py 现状 ③设计分层编码 ④原型模拟。
【提示词】你是网络编码 AI。读 digest-g8-3a-2026-08-30.md APC-RLNC 授粉点 + 现有 tools/link_reliability.py（SPEC-20 v1.6 已验 EWMA+XOR），为 LoRaCanary 设计 Mesh 弹性路由：APC-RLNC 分层网络编码（按链路质量分组编码冗余），断电重同步。输出方案 docs/loracanary-rlnc-mesh-方案.md + numpy 原型。验收：弱链路（PER 30%）下交付率较无编码提升 ≥50%，不破坏 v1/v1.5 帧兼容。推 trae/agent-r50 分支。
