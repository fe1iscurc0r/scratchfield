# Manifest Fix Task — 2026-08-04

## Objective
Fix two classes of issues in all `agent-manifest.json` files under `mcpserver/agent_*`.

## Problem 1: entryPoint.class mismatch with code class names

Verified each `agent_*.py` to find the actual class name, then fixed the corresponding manifest's `entryPoint.class`.

| Directory | Manifest (before) | Code (actual) | Fixed |
|---|---|---|---|
| agent_frida | AgentFrida | FridaAgent | ✅ |
| agent_llm_decompile | AgentLLMDecompile | LLMDecompileAgent | ✅ |
| agent_pentest | AgentPentest | PentestAgent | ✅ |
| agent_runtime | AgentRuntime | RuntimeAgent | ✅ |
| agent_strix | AgentStrix | StrixAgent | ✅ |
| agent_waf | AgentWaf | WafAgent | ✅ |
| agent_animation | AgentAnimation | AnimationAgent | ✅ |

## Problem 2: Duplicate "entrypoint" (lowercase) + "entryPoint" (camelCase) keys

Removed the erroneous `"entrypoint"` key from 9 manifests, keeping only `"entryPoint"`:

- agent_animation, agent_decompile, agent_frida, agent_nuclei, agent_osint, agent_sbom, agent_signing, agent_strix, agent_trivy

## Verification

- `python -c "..." All manifests parse OK` — all 14 JSON files valid
- Spot-check: all `has_dup_entrypoint=False`, all class names match actual code
