"""Accept-Markdown 中间件最小原型（W73-07 · agent 友好 Web 协议）。

依据 docs/accept-markdown-评估.md：用 HTTP `Accept: text/markdown` 请求头，让
服务端给 agent 返回 Markdown 版页面（而非 HTML），降低 agent 抓取的 token 开销。

原型（纯 stdlib，无依赖）：
  - wants_markdown(accept_header)：解析 Accept 头，判断是否要 markdown
  - html_to_markdown(html)：极简 HTML→Markdown 转换（标题/段落/链接/加粗/斜体/列表）
  - serve(accept_header, html)：按 Accept 返回 (content_type, body)

运行：
  python tools/accept_markdown.py
"""
from __future__ import annotations

import re

_MD_TYPE = "text/markdown; charset=utf-8"
_HTML_TYPE = "text/html; charset=utf-8"


def wants_markdown(accept_header: str) -> bool:
    """解析 Accept 头：text/markdown（或 */*）优先于 text/html 时返回 True。"""
    if not accept_header:
        return False
    # 按逗号拆段，取每个媒体类型（忽略 q 权重与参数）
    for part in accept_header.split(","):
        mtype = part.split(";")[0].strip().lower()
        if mtype == "text/markdown":
            return True
        if mtype in ("text/html", "application/xhtml+xml"):
            return False
    return False  # 未显式声明 markdown


def html_to_markdown(html: str) -> str:
    """极简 HTML→Markdown：覆盖标题/段落/链接/加粗/斜体/无序列表。

    诚实降级：只处理常见标签，复杂 HTML 需专业转换器；此处演示协议层转义的核心。
    """
    s = html
    # 链接 <a href="...">text</a> -> [text](href)
    s = re.sub(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r'[\2](\1)', s, flags=re.S)
    # 标题 h1-h6 -> #
    for level in range(6, 0, -1):
        s = re.sub(rf'<h{level}[^>]*>(.*?)</h{level}>', lambda m: '#' * level + ' ' + m.group(1).strip(), s, flags=re.S)
    # 无序列表 <li> -> - 
    s = re.sub(r'<li[^>]*>(.*?)</li>', lambda m: '- ' + m.group(1).strip(), s, flags=re.S)
    # 段落 <p> -> 换行
    s = re.sub(r'<p[^>]*>(.*?)</p>', lambda m: m.group(1).strip() + '\n\n', s, flags=re.S)
    # 加粗/斜体
    s = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', s, flags=re.S)
    s = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', s, flags=re.S)
    s = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', s, flags=re.S)
    s = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', s, flags=re.S)
    # 去剩余标签
    s = re.sub(r'<[^>]+>', '', s)
    return s.strip()


def serve(accept_header: str, html: str) -> tuple[str, str]:
    """按 Accept 头返回 (content_type, body)。"""
    if wants_markdown(accept_header):
        return _MD_TYPE, html_to_markdown(html)
    return _HTML_TYPE, html


if __name__ == "__main__":
    html = "<html><body><h1>标题</h1><p>这是一段 <strong>加粗</strong> 文本，<a href=\"https://x.com\">链接</a>。</p><ul><li>第一项</li><li>第二项</li></ul></body></html>"
    ct, body = serve("text/markdown, text/html;q=0.8", html)
    print(f"[{ct}]\n{body}")
