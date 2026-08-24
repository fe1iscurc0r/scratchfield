# Scratchpad — QClaw 30 包批量改造工程

## 目录

| 目录 | 内容 | 数量 |
|------|------|------|
| `mcpserver/` | MCP Agent 可执行代码 | 14 个 Agent + 注册表 |
| `skills/` | Skill 工作流定义 | 5 个 SKILL.md |
| `references/` | 第三方框架架构参考笔记 | 11 份 |
| `reports/` | 全流程报告 & 验证脚本 | 审计/构建/验证 |
| `sources/` | 原始源码包 & 工具 | 清单 + 包 + 工具 |

## mcpserver/ — 14 个 MCP Agent

| Agent | 功能 | 底层工具 |
|-------|------|----------|
| agent_nuclei | 漏洞扫描 | nuclei CLI |
| agent_trivy | 容器/文件系统漏洞扫描 | trivy CLI |
| agent_sbom | 软件物料清单生成 | syft CLI |
| agent_signing | 容器镜像签名校验 | cosign CLI |
| agent_osint | 跨社交网络用户名搜索 | sherlock CLI |
| agent_decompile | APK/DEX 反编译 | jadx CLI |
| agent_runtime | 运行时威胁检测 | Falco |
| agent_waf | WAF 规则引擎 | Coraza |
| agent_llm_decompile | LLM 辅助反编译 | LLM4Decompile |
| agent_pentest | 渗透测试原子工具 | nmap/gobuster/searchsploit |
| agent_browser | 浏览器自动化 | Playwright + nanobrowser |
| agent_frida | 动态插桩 | Frida |
| agent_strix | 渗透编排 | nmap/searchsploit/hydra |
| agent_animation | 图表生成 | graphviz/matplotlib |

## skills/ — 5 个 Skill

| Skill | 说明 | 状态 |
|-------|------|------|
| animation | 静态图表生成 (架构/流程/序列/数据流/生命周期) | ✅ 可执行 |
| pentest-chain | 五阶段渗透测试链 | ✅ 可执行 |
| baoyu-comic | 漫画生成 | ⚠️ 概念模板 |
| baoyu-illustrator | 插画生成 | ⚠️ 概念模板 |
| baoyu-infographic | 信息图生成 | ⚠️ 概念模板 |

## references/ — 11 份架构笔记

agent-memory / anything-llm / crewai / dify / esp32-mqtt / flowise / graphiti / lightrag / live2dpet / mastra / pentest-agents

## 状态

✅ 审查完成，7 个 CRITICAL 全部修复  
✅ 14/14 Agent 注册 + 实例化通过  
✅ 28/28 Python 语法通过  
✅ 5/5 Skill YAML 格式正确
