"""
agent_waf - Coraza WAF Rule Engine Agent
Tests and validates WAF rules, explains rule logic.
Uses coraza-wasmer CLI if available; otherwise provides embedded knowledge.
"""
from .agent_waf import WafAgent

__all__ = ["WafAgent"]
