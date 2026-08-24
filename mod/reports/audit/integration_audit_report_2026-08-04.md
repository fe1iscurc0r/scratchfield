# Scratchpad Integration & Cross-Cutting Audit Report

**Date**: 2026-08-04
**Scope**: Full integration audit of the scratchpad mcpserver, skills, and references

---

## 1. mcp_registry.py Audit

### auto_register_mcp() — PASSES
- Discovers **all 14 agents** correctly
- Resolves entry points via Format A (`entryPoint.module` + `entryPoint.class`)
- Graceful fallback for legacy formats (Format B/C/D)
- All agent-manifest.json files are valid JSON (except agent_browser — see below)

### get_agent() — BROKEN
- **BUG**: `get_agent()` calls `auto_register_mcp()` and returns the raw registry *dict* entry, not an instantiated object.
- Line: `return entry` — returns `{"manifest": ..., "path": ..., "module": ..., "class": ...}`
- Should instantiate: `mod = importlib.import_module(module); cls = getattr(mod, cls_name); return cls()`
- This makes `get_agent()` indistinguishable from just reading the registry dict.

### __init__.py — NEARLY EMPTY
- `mcpserver/__init__.py` contains only `# MCP Server - Agent Registry`
- **No exports**, no imports of `mcp_registry`, no module re-exports
- Users cannot do `from mcpserver import auto_register_mcp`

---

## 2. Manifest vs. Actual Class-Name Mismatches

| Agent Dir | Manifest entryPoint.class | Actual Python Class | Match? |
|-----------|--------------------------|---------------------|--------|
| agent_animation | AgentAnimation | AnimationAgent | **MISMATCH** |
| agent_browser | AgentBrowser | AgentBrowser | OK |
| agent_decompile | AgentDecompile | AgentDecompile | OK |
| agent_frida | AgentFrida | FridaAgent | **MISMATCH** |
| agent_llm_decompile | AgentLLMDecompile | LLMDecompileAgent | **MISMATCH** |
| agent_nuclei | AgentNuclei | AgentNuclei | OK |
| agent_osint | AgentOSINT | AgentOsint | **CASE MISMATCH** |
| agent_pentest | AgentPentest | PentestAgent | **MISMATCH** |
| agent_runtime | AgentRuntime | RuntimeAgent | **MISMATCH** |
| agent_sbom | AgentSBOM | AgentSbom | **CASE MISMATCH** |
| agent_signing | AgentSigning | AgentSigning | OK |
| agent_strix | AgentStrix | StrixAgent | **MISMATCH** |
| agent_trivy | AgentTrivy | AgentTrivy | OK |
| agent_waf | AgentWAF | WafAgent | **MISMATCH** |

**Severity: HIGH** — 8 out of 14 agents have mismatched class names. The registry's `_resolve_entrypoint()` stores the manifest class name, but when `get_agent()` tries `getattr(module, cls_name)`, it will fail to find the class.

**Root cause**: Manifests were auto-generated with "clean" naming (`AgentStrix`, `AgentWAF`) but the actual Python files use different naming conventions (`StrixAgent`, `WafAgent`).

---

## 3. Cross-Cutting Structural Issues

### 3a. Empty __init__.py Files
7 agent directories have **empty or near-empty** `__init__.py` files:
- `agent_browser/__init__.py` — only a comment
- `agent_decompile/__init__.py` — **completely empty**
- `agent_nuclei/__init__.py` — **completely empty**
- `agent_osint/__init__.py` — **completely empty**
- `agent_sbom/__init__.py` — **completely empty**
- `agent_signing/__init__.py` — **completely empty**
- `agent_trivy/__init__.py` — **completely empty**

**Impact**: `from mcpserver.agent_decompile import AgentDecompile` won't work. Users must use the full module path: `from mcpserver.agent_decompile.agent_decompile import AgentDecompile`.

### 3b. agent_browser Manifest JSON
The manifest `agent-manifest.json` has garbled UTF-8 encoded CJK characters (the `description` field contains mojibake like "娴忚" instead of "浏览"). This didn't prevent JSON parsing, but it makes the description unreadable.

### 3c. agent_browser Runtime Dependency
`AgentBrowser.__init__()` raises `RuntimeError` if Playwright is not installed. This is by design for runtime validation, but it means the agent cannot be imported/instantiated in environments without Playwright.

---

## 4. Skill-to-Agent Tool Reference Audit

### 4a. skills/animation → agent_animation
- **Service**: The animation skill references `list_templates`, `generate_diagram`, `export_diagram`
- **Status**: These ARE handled correctly. The agent dispatches them through `handle_handoff()` via a dispatch table:
  ```python
  handlers = {
      "generate_diagram": self._generate_diagram,
      "export_diagram": self._export_diagram,
      "list_templates": self._list_templates,
  }
  ```
- The internal methods are prefixed with `_` (private convention), but the public API through `handle_handoff` works correctly.
- **No breakage** — skill references valid dispatch names.

### 4b. skills/pentest-chain → agent_pentest
- **Status**: All tools referenced by the skill (`port_scan`, `service_detect`, `dir_bruteforce`, `vuln_check`, `exploit_check`) exist as **public methods** on `PentestAgent`.
- The `handle_handoff` dispatcher pattern matches correctly.
- **No breakage** — all 5 tools are present.

### 4c. No dangling skill→agent references
- Both skill files reference only existing agents (`agent_animation`, `agent_pentest`).
- No orphaned or dangling references.

---

## 5. All 14 Agent Directories — Completeness

| # | Directory | manifest | .py | __init__.py | Python Class | handle_handoff |
|---|-----------|----------|-----|-------------|-------------|----------------|
| 1 | agent_animation | ✅ | ✅ | ✅ | AnimationAgent | ✅ |
| 2 | agent_browser | ✅⚠️ | ✅ | ✅(empty) | AgentBrowser | ✅ |
| 3 | agent_decompile | ✅ | ✅ | ✅(empty) | AgentDecompile | ✅ |
| 4 | agent_frida | ✅ | ✅ | ✅ | FridaAgent | ✅ |
| 5 | agent_llm_decompile | ✅ | ✅ | ✅ | LLMDecompileAgent | ✅ |
| 6 | agent_nuclei | ✅ | ✅ | ✅(empty) | AgentNuclei | ✅ |
| 7 | agent_osint | ✅ | ✅ | ✅(empty) | AgentOsint | ✅ |
| 8 | agent_pentest | ✅ | ✅ | ✅ | PentestAgent | ✅ |
| 9 | agent_runtime | ✅ | ✅ | ✅ | RuntimeAgent | ✅ |
| 10 | agent_sbom | ✅ | ✅ | ✅(empty) | AgentSbom | ✅ |
| 11 | agent_signing | ✅ | ✅ | ✅(empty) | AgentSigning | ✅ |
| 12 | agent_strix | ✅ | ✅ | ✅ | StrixAgent | ✅ |
| 13 | agent_trivy | ✅ | ✅ | ✅(empty) | AgentTrivy | ✅ |
| 14 | agent_waf | ✅ | ✅ | ✅ | WafAgent | ✅ |

**All 14 directories are structurally complete** (no missing files, no empty agents, no broken modules).

---

## 6. Summary of Actionable Bugs

| Severity | Issue | Files Affected |
|----------|-------|---------------|
| **HIGH** | 8 manifest class names don't match actual Python classes | 8 agent-manifest.json files |
| **HIGH** | `get_agent()` returns dict instead of instantiated object | `mcp_registry.py` line ~110 |
| **MEDIUM** | `mcpserver/__init__.py` exports nothing | `mcpserver/__init__.py` |
| **MEDIUM** | 7 agent `__init__.py` files are empty (no re-exports) | 7 agent directories |
| **LOW** | agent_browser manifest has garbled CJK text | `agent_browser/agent-manifest.json` |
| **LOW** | agent_browser fails import without Playwright | `agent_browser/agent_browser.py` |
| **INFO** | 2 case-only mismatches (AgentOSINT→AgentOsint, AgentSBOM→AgentSbom) | manifests |

---

## 7. Fix Recommendations

### Priority 1: Fix manifest class names
In each mismatched agent's `agent-manifest.json`, change `entryPoint.class` to match the actual Python class:

```
agent_animation: "AgentAnimation" → "AnimationAgent"
agent_frida:     "AgentFrida" → "FridaAgent"
agent_llm_decompile: "AgentLLMDecompile" → "LLMDecompileAgent"
agent_osint:     "AgentOSINT" → "AgentOsint"
agent_pentest:   "AgentPentest" → "PentestAgent"
agent_runtime:   "AgentRuntime" → "RuntimeAgent"
agent_sbom:      "AgentSBOM" → "AgentSbom"
agent_strix:     "AgentStrix" → "StrixAgent"
agent_waf:       "AgentWAF" → "WafAgent"
```

### Priority 2: Fix get_agent() to actually instantiate
```python
def get_agent(name: str, base_dir: str = None) -> object:
    registry = auto_register_mcp(base_dir)
    if name not in registry:
        return None
    entry = registry[name]
    module = entry["module"]
    cls_name = entry["class"]
    mod = importlib.import_module(module)
    cls = getattr(mod, cls_name)
    return cls()
```

### Priority 3: Add re-exports to __init__.py files
At minimum, add `from .agent_decompile import AgentDecompile` to each agent's `__init__.py`, and add `from .mcp_registry import auto_register_mcp, get_agent` to `mcpserver/__init__.py`.
