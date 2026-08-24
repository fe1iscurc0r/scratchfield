# MatChat 2.0 安全基线检查

> 目标：`https://ai.matchat.cn/login`
> 身份：中国科学院 · 松山湖材料实验室 — 28 万篇材料论文 AI 知识库
> 检查时间：2026-07-30
> 对陆墨的关系：外部知识源 M6，通过 MCP 工具或浏览器自动化对接

---

## 基础设施

| 项目 | 值 |
|------|-----|
| IP | 8.138.190.146（阿里云） |
| 框架 | Next.js + Turbopack + React Server Components |
| 构建 ID | `tkuPjuwoHjcA07Nh_2RL4` |
| SSL | sslTrus DV CA，*.matchat.cn，2027-02-23 到期 |
| 开放端口 | 22 / 80 / 443（干净） |
| 统计 | 自建 Umami (`/stats`) |

---

## 🔴 高危

### 1. 安全响应头全面缺失

只有 `Strict-Transport-Security`，其余全军覆没：

| 头部 | 状态 | 风险 |
|------|------|------|
| Content-Security-Policy | ❌ | XSS 无最后防线 |
| X-Frame-Options | ❌ | 登录页可被 iframe 钓鱼 |
| X-Content-Type-Options | ❌ | MIME 嗅探风险 |
| Referrer-Policy | ❌ | 跳转时泄露 URL 中的 token |
| Permissions-Policy | ❌ | 无 |
| Strict-Transport-Security | ✅ | max-age=1年 |

### 2. 无点击劫持防护

登录页面可被任意第三方 iframe 嵌入。攻击者可以做一个高仿壳，iframe 套真实登录页，中间截获手机号+密码。

---

## 🟡 中危

### 3. Turbopack 生产部署

Turbopack 是 Next.js 的实验性打包器，生产环境通常用标准 webpack。响应头中未见标准的 Next.js 生产印记，可能是快速迭代中省了构建切换。不影响功能但属不规范。

### 4. 未见速率限制

`POST /api/auth/login` 返回 `{"success":false,"message":"手机号和密码不能为空"}` —— API 存在且校验参数，但没有 `429 Too Many Requests` / `Retry-After` 等限流信号。暴力破解面存在。

---

## 🟢 无问题

- 端口仅 22/80/443，无意外服务暴露
- `.env` 未暴露 → 404
- 登录 API 正确校验，错误信息不泄露内部细节（"手机号和密码不能为空"而非"用户不存在"）
- 登录页是 React Server Component，客户端看不到预渲染的敏感状态
- 自建 Umami 分析，非第三方 CDN 注入

---

## 🔍 API 发现

| 端点 | 方法 | 状态 | 响应 |
|------|------|------|------|
| `/api/auth/login` | POST | 400 | `{"success":false,"message":"手机号和密码不能为空"}` |
| `/api/health` | GET | 404 | — |
| `/api/v1` | GET | 404 | — |
| `/.env` | GET | 404 | — |
| `/robots.txt` | GET | 404 | Next.js 默认 404 页 |

登录 API 校验 `手机号` + `密码` 两个字段。

---

## 对陆墨的影响

| 接入方式 | 是否受影响 | 说明 |
|----------|-----------|------|
| 网页对话（浏览器自动化） | 否 | Playwright 直接操控，不依赖安全头 |
| API 对接 | 否 | 目前没有公开 API 端点，走网页 |
| 直接嵌入 iframe | ⚠️ | X-Frame-Options 缺失反而是"好事"——你可以 iframe 嵌入，但别人也可以钓鱼你 |

---

## 建议（如果以后跟他们沟通）

1. **至少加 X-Frame-Options: DENY** — 最廉价的安全感
2. **CSP 至少 `default-src 'self'`** — 防 XSS 注入的最后一道墙
3. **登录接口加 rate limit** — 即使只是简单的内存计数器也好过裸奔
4. **切换到 Next.js 标准生产构建** — Turbopack 不是给生产用的
