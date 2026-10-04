# W73-07 Accept-Markdown 协议评估

> 上游：acceptmarkdown.com（HN 176p/108c）· 许可待核（协议/中间件）

## 1. 项目定位

用 HTTP `Accept: text/markdown` 请求头，让服务端给 agent 返回 **Markdown 版页面**（而非 HTML），是「agent 友好 Web」的轻量协议。

## 2. 架构拆解

- **协议**：HTTP content negotiation，`Accept: text/markdown` → 返回 markdown。
- **中间件**：服务端拦截，把 HTML/结构化内容转 markdown 版。
- **定位**：降低 agent 抓取网页的 token 开销与解析成本。

## 3. 与本仓对照

| 维度 | Accept-Markdown | 本仓 |
|---|---|---|
| 网页抓取 | 协议层转 markdown | 知识库/文档站 + MCP 工具链 + 网页抓取 |

## 4. 可落地借鉴点（≥3）

1. **content negotiation 转 markdown**：服务端/中间件支持 `Accept: text/markdown`，让 agent 拿到的就是结构化 markdown，省 token。
2. **agent 友好 Web 协议**：比「抓 HTML → 解析」更省的通用协议，可作为 web_extract 类工具的优化方向。
3. **中间件实现**：一个薄中间件即可让现有文档站对 agent 友好，接入成本低。

## 5. 许可裁定 + 结论

- **许可**：协议/网页无明确开源许可 → **许可待核**；协议本身可参考实现。
- **结论**：**参考设计**，中间件原型（可选）——对文档站加 `Accept: text/markdown` 支持是低成本高收益的 agent 友好改造。
