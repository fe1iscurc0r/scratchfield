# A08 RAG ingest-time 编译

> 来源分组：group3-agent安全

【SPEC】固定语料 ingest 时编译替代 query 时解释（摊销成本）；验收=原型+对比。
【工单】①读 G1-2 digest②实现 ingest 编译③对比 chunk RAG。
【提示词】你是 RAG AI。实现 ingest-time 编译：读 digest-g1-2-2026-08-30.md 授粉点 ②，固定语料重复读取摊销为编译索引，对比 chunk RAG 效果。验收：原型 + 32 预算单元对比表。
