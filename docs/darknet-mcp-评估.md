# W68-03 darknet-mcp-server 评估（暗网情报 MCP）

> 上游：github.com/badchars/darknet-mcp-server · MIT · 319★ · TypeScript · 2026-09-01 活跃
> 落点：docs/darknet-mcp-评估.md · 评估 +（可选）adapter 骨架

## 1. 项目定位

66-tool 的 MCP server，把暗网/威胁情报统一进单一接口：HIBP 泄露、ThreatFox、勒索软件追踪、Tor .onion 访问、区块链情报、exploit 搜索、stealer logs、恶意软件分析。

## 2. 架构拆解

- **运行时**：Bun（TS），MCP 协议，66 个工具，16 个数据源。
- **定位**：把「16 个浏览器标签 + 手工关联」收敛为「AI agent 按需调用 66 个工具」。
- **Tor 访问**：内置 Tor .onion 访问实现（合规敏感点）。

## 3. 与本仓对照

| 维度 | darknet-mcp-server | 本仓 |
|---|---|---|
| 情报 | 暗网/泄露/勒索/区块链 16 源 | sentinel_intel 实体图谱 + 威胁情报线 |
| 形态 | MCP server（66 tool） | mcpserver 模块 + adapter |

## 4. 可落地借鉴点（≥3）

1. **66-tool 的分类目录**：泄露/勒索/Tor/区块链/exploit/stealer 的数据源清单，可作为我们威胁情报线的数据源扩展清单。
2. **单一 MCP 收敛多数据源**：把异构情报源统一为 MCP tool 的设计，可复用为 sentinel_intel 的 adapter 模式。
3. **Tor 访问的合规封装**：Tor .onion 访问作为「显式标注合规」的受控工具，而非裸暴露。

## 5. 许可裁定 + 结论

- **许可**：MIT → 可借鉴代码。
- **接入 vs 不接入结论**：**谨慎接入（封装为 adapter，不直接启 Tor 抓取）**。合规考量：暗网访问需合法授权 + 明确标注；建议只借鉴「数据源清单 + MCP tool 分类」设计，把合规的数据源（HIBP/ThreatFox 等公开 API）封装成 mcpserver adapter，Tor 访问默认关闭、按需受控开启。
