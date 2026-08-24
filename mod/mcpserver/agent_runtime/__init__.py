"""
agent_runtime - Falco Runtime Threat Detection Agent
Reads events from a running Falco daemon and provides threat detection tools.
"""
from .agent_runtime import RuntimeAgent

__all__ = ["RuntimeAgent"]
