# MatChat Browser Relay — Playwright MCP 定制化预加工

> 架构：实验田维护者 | 实现：Trae (fe1iscurc0r)
> 目标：用已有浏览器登录态做 Relay，让 NagaAgent MCP 通过 DOM/网络桥接调用 MatChat

---

## 一、架构

```
天选7pro
┌─────────────────────────────────────────────┐
│  Chrome / Edge（已登录 MatChat）             │
│  ┌───────────────────────────────────────┐  │
│  │  ai.matchat.cn                        │  │
│  │  session cookie ✓                    │  │
│  │  --remote-debugging-port=9222        │  │
│  └──────────┬────────────────────────────┘  │
│             │ CDP (ws://localhost:9222)      │
│  ┌──────────▼────────────────────────────┐  │
│  │  Playwright (connect_over_cdp)        │  │
│  │  matchat_bridge.py                    │  │
│  └──────────┬────────────────────────────┘  │
│             │ MCP stdio/SSE                 │
│  ┌──────────▼────────────────────────────┐  │
│  │  NagaAgent MCP Server                 │  │
│  │  → 陆墨对话中调用                      │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

**关键设计**：不启动新浏览器。`connect_over_cdp` 接入已有 Chrome，利用现有登录态。零额外认证逻辑。

---

## 二、核心文件

```
mcpserver/material_science/
├── agent-manifest.json          ← 已有，追加 matchat 工具声明
├── materialscience_agent.py     ← 已有
├── matchat_bridge.py            ← 新建：Playwright relay
└── matchat_tools.py             ← 新建：MCP 工具定义
```

---

## 三、matchat_bridge.py 设计

```python
# 核心类：一个连到已有浏览器的 Playwright wrapper
class MatchatBridge:
    def __init__(self, cdp_url="http://localhost:9222"):
        # connect_over_cdp — 不启动新浏览器
        self.browser = sync_playwright().chromium.connect_over_cdp(cdp_url)
        self.page = None  # 懒加载，首次使用时定位 MatChat 标签页
    
    def _ensure_page(self):
        """定位已有 MatChat 标签页，没有则导航到"""
        for page in self.browser.contexts[0].pages:
            if "matchat.cn" in page.url:
                self.page = page
                return
        self.page = self.browser.contexts[0].new_page()
        self.page.goto("https://ai.matchat.cn")
    
    def search_literature(self, query: str) -> dict:
        """在 MatChat 搜索文献"""
        self._ensure_page()
        # 走 DOM 操作：找到输入框 → 输入 → 提交 → 等响应 → 提取
        ...
    
    def chat_with_ai(self, message: str) -> str:
        """与 MatChat AI 对话"""
        ...
```

### 不需要的：
- ❌ 启动新浏览器 / `chromium.launch()`
- ❌ 模拟登录 / 填手机号密码
- ❌ cookie 管理 / token 刷新
- ❌ UA 伪装 / 反检测

---

## 四、MCP 工具定义

```json
{
  "tools": [
    {
      "name": "matchat_search_literature",
      "description": "在 MatChat 2.0 中搜索材料科学文献（28万篇论文知识库）",
      "parameters": {
        "query": {"type": "string", "description": "搜索关键词，如 'lignin carbonization temperature'"}
      }
    },
    {
      "name": "matchat_chat",
      "description": "与 MatChat AI 对话，询问材料合成路径、性能对比等",
      "parameters": {
        "message": {"type": "string", "description": "对话内容"}
      }
    },
    {
      "name": "matchat_extract_page",
      "description": "提取当前 MatChat 页面的文本内容",
      "parameters": {}
    }
  ]
}
```

---

## 五、启动流程

```bash
# 1. 启动 Chrome 时加 CDP 端口（一次性设置）
# Windows: 修改 Chrome 快捷方式 → 目标 → 追加
chrome.exe --remote-debugging-port=9222

# 2. 在 Chrome 里手动登录 https://ai.matchat.cn（一次）

# 3. 启动桥接
python matchat_bridge.py --cdp http://localhost:9222

# 4. NagaAgent MCP 自动发现并注册工具
```

---

## 六、注意事项

| 项 | 说明 |
|----|------|
| CDP 端口 | `--remote-debugging-port=9222`，不要暴露到公网 |
| 页面定位 | 复用已有标签页，不反复创建 |
| 等待策略 | `page.wait_for_selector()` 等 AI 回复加载，不用 `time.sleep()` |
| 错误处理 | AI 回复超时 → 返回错误信息，不崩 |
| 并发 | 单页面单用户，不需要锁 |

---

## 七、验收标准

```
□ Chrome 启动带 --remote-debugging-port=9222
□ Playwright connect_over_cdp 成功
□ 定位到已有 MatChat 标签页
□ matchat_search_literature("木质素碳化温度") 返回结果
□ matchat_chat("对比淀粉基和明胶基生物塑料的力学性能") 返回 AI 回复
□ MCP 工具在陆墨对话中可调用
□ 不需要重新登录
```
