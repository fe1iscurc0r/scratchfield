"""accept_markdown 测试（W73-07 原型）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from accept_markdown import html_to_markdown, serve, wants_markdown


def test_wants_markdown():
    assert wants_markdown("text/markdown") is True
    assert wants_markdown("text/markdown, text/html;q=0.8") is True
    assert wants_markdown("text/html") is False
    assert wants_markdown("") is False


def test_html_to_markdown_headings_and_link():
    md = html_to_markdown('<h1>标题</h1><p>见 <a href="https://x.com">链接</a></p>')
    assert md.startswith("# 标题")
    assert "[链接](https://x.com)" in md


def test_serve_returns_markdown_when_requested():
    ct, body = serve("text/markdown", "<h1>Hi</h1>")
    assert ct.startswith("text/markdown")
    assert body == "# Hi"


def test_serve_returns_html_by_default():
    html = "<h1>Hi</h1>"
    ct, body = serve("text/html", html)
    assert ct.startswith("text/html")
    assert body == html
