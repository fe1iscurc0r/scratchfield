"""科研写作管线（SPEC-02 Phase 4）。

用法（MCP 工具）：
1. writing_bibtex_add     新增文献条目（references.bib 自动创建于 %APPDATA%/Lumo/writing/）
2. writing_bibtex_search  按关键词检索文献库
3. writing_draft          选题→初稿一条龙（综述→实验设计→数据分析→nature 模板成稿）

正文润色/引用核验交 skills 侧 nature-* 系列（nature-writing / nature-polishing / nature-ref-verifier）。
"""
from . import bibtex, pipeline, templates
from .writing_tools import register_writing_tools

__all__ = ["bibtex", "pipeline", "templates", "register_writing_tools"]
