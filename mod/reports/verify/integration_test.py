#!/usr/bin/env python3
"""
INTEGRATION TEST — Validates the entire scratchpad mcpserver structure.

Tests:
  1. mcp_registry auto_register_mcp() for all 14 agents
  2. Manifest class-name vs actual module class-name audit
  3. get_agent() import and instantiation
  4. Skill-to-agent tool reference audit (animation, pentest-chain)
  5. __init__.py export audit
"""

import importlib
import json
import sys
import traceback
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PASS = 0
FAIL = 0
results = []


def check(condition: bool, label: str, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        results.append(f"  ✅ {label}")
    else:
        FAIL += 1
        results.append(f"  ❌ {label}")
        if detail:
            results.append(f"     Detail: {detail}")


def section(title: str):
    results.append(f"\n{'='*60}")
    results.append(f"  {title}")
    results.append(f"{'='*60}")


# ============================================================================
# SECTION 1: mcp_registry.py — auto_register_mcp()
# ============================================================================
section("1. mcp_registry.py — auto_register_mcp()")

from mcpserver.mcp_registry import auto_register_mcp, get_agent

registry = auto_register_mcp()
names = sorted(registry.keys())

check(len(names) == 14, f"14 agents registered (got {len(names)})", f"Got: {names}")

expected_agents = [
    "agent_animation", "agent_browser", "agent_decompile", "agent_frida",
    "agent_llm_decompile", "agent_nuclei", "agent_osint", "agent_pentest",
    "agent_runtime", "agent_sbom", "agent_signing", "agent_strix",
    "agent_trivy", "agent_waf",
]
for agent_name in expected_agents:
    check(agent_name in registry, f"  {agent_name} registered")

# ============================================================================
# SECTION 2: Manifest class-name vs actual module class-name audit
# ============================================================================
section("2. Manifest Class-Name vs Actual Module Class-Name Audit")

# Known mismatches (manifest entryPoint.class -> actual class in file)
MANIFEST_TO_ACTUAL = {
    "agent_animation":   ("AgentAnimation", "AnimationAgent"),    # MISMATCH
    "agent_browser":     ("AgentBrowser", "AgentBrowser"),        # OK
    "agent_decompile":   ("AgentDecompile", "AgentDecompile"),    # OK
    "agent_frida":       ("AgentFrida", "FridaAgent"),            # MISMATCH
    "agent_llm_decompile": ("AgentLLMDecompile", "LLMDecompileAgent"),  # MISMATCH
    "agent_nuclei":      ("AgentNuclei", "AgentNuclei"),          # OK
    "agent_osint":       ("AgentOSINT", "AgentOsint"),            # MISMATCH (case)
    "agent_pentest":     ("AgentPentest", "PentestAgent"),        # MISMATCH
    "agent_runtime":     ("AgentRuntime", "RuntimeAgent"),        # MISMATCH
    "agent_sbom":        ("AgentSBOM", "AgentSbom"),              # MISMATCH (case)
    "agent_signing":     ("AgentSigning", "AgentSigning"),        # OK
    "agent_strix":       ("AgentStrix", "StrixAgent"),           # MISMATCH
    "agent_trivy":       ("AgentTrivy", "AgentTrivy"),            # OK
    "agent_waf":         ("AgentWAF", "WafAgent"),               # MISMATCH
}

mismatch_count = 0
for agent_name in expected_agents:
    manifest_cls = registry[agent_name]["manifest"]["entryPoint"]["class"]
    module_name = registry[agent_name]["module"]
    try:
        mod = importlib.import_module(module_name)
        actual_classes = [k for k in dir(mod)
                          if not k.startswith("_")
                          and isinstance(getattr(mod, k), type)]
        matched = manifest_cls in actual_classes
        if not matched:
            mismatch_count += 1
        check(matched, f"  {agent_name}: {manifest_cls} in module",
              f"Actual classes: {actual_classes}")
    except Exception as e:
        check(False, f"  {agent_name}: unable to import",
              f"Error: {e}")

check(mismatch_count == 0, "Zero class-name mismatches", f"Found {mismatch_count} mismatches")

# ============================================================================
# SECTION 3: get_agent() — import + instantiation
# ============================================================================
section("3. get_agent() — Import and Instantiate 3 Random Agents")

test_agents = ["agent_animation", "agent_pentest", "agent_browser"]

for agent_name in test_agents:
    entry = get_agent(agent_name)

    # Current get_agent() returns a dict (bug), not an instance.
    # Check if we can manually instantiate.
    check(isinstance(entry, dict), f"  {agent_name}: get_agent returns dict",
          "get_agent() should return an instantiated agent object, not a dict")

    manifest_cls = entry["manifest"]["entryPoint"]["class"]
    module_name = entry["module"]
    try:
        mod = importlib.import_module(module_name)
        # Find the actual class (since manifest names may be wrong)
        actual_classes = [k for k in dir(mod)
                          if not k.startswith("_")
                          and isinstance(getattr(mod, k), type)]
        # Try manifest class first, then any available class
        cls = None
        if hasattr(mod, manifest_cls):
            cls = getattr(mod, manifest_cls)
        elif actual_classes:
            cls = getattr(mod, actual_classes[0])

        if cls:
            instance = cls()
            check(True, f"  {agent_name}: instantiated {cls.__name__}")

            # Check for handle_handoff
            has_handoff = hasattr(instance, "handle_handoff")
            check(has_handoff, f"  {agent_name}: has handle_handoff()",
                  f"Class {cls.__name__} has methods: {[m for m in dir(instance) if not m.startswith('_')]}")
        else:
            check(False, f"  {agent_name}: no instantiable class found")
    except Exception as e:
        check(False, f"  {agent_name}: instantiation failed",
              f"{e}\n{traceback.format_exc()}")

# ============================================================================
# SECTION 4: Skill-to-Agent Tool Reference Audit
# ============================================================================
section("4. Skill-to-Agent Tool Reference Audit")

# --- 4a: animation skill → agent_animation tools ---
section("  4a. skills/animation → agent_animation")

# The skill references these tools from agent_animation:
#   - list_templates
#   - generate_diagram
#   - export_diagram

resolved_cls = None
try:
    mod = importlib.import_module("mcpserver.agent_animation.agent_animation")
    # Find the actual class
    for n in dir(mod):
        if not n.startswith("_") and isinstance(getattr(mod, n), type):
            resolved_cls = getattr(mod, n)
            break
    if resolved_cls:
        instance = resolved_cls()
        agent_tools = [m for m in dir(instance) if not m.startswith("_") and callable(getattr(instance, m))]
        # The actual tool methods are: handle_handoff, _generate_diagram, _export_diagram, _list_templates, etc.
        # The skill references them by their dispatch names: generate_diagram, export_diagram, list_templates
        # These ARE available within handle_handoff's dispatch table.
        check("handle_handoff" in agent_tools, "  handle_handoff exists")
        check("_generate_diagram" in agent_tools or "generate_diagram" in agent_tools,
              "  generate_diagram handler exists")
        check("_export_diagram" in agent_tools or "export_diagram" in agent_tools,
              "  export_diagram handler exists")
        check("_list_templates" in agent_tools or "list_templates" in agent_tools,
              "  list_templates handler exists")
except Exception as e:
    check(False, "  animation skill audit failed", str(e))

# --- 4b: pentest-chain skill → agent_pentest tools ---
section("  4b. skills/pentest-chain → agent_pentest")

# The skill references these tools from agent_pentest:
#   - port_scan
#   - service_detect
#   - dir_bruteforce
#   - vuln_check
#   - exploit_check

try:
    # Find actual class in module
    import mcpserver.agent_pentest.agent_pentest as pentest_mod
    for n in dir(pentest_mod):
        if not n.startswith("_") and isinstance(getattr(pentest_mod, n), type):
            instance = getattr(pentest_mod, n)()
            break

    pentest_methods = [m for m in dir(instance) if not m.startswith("_") and callable(getattr(instance, m))]
    skill_refs = ["port_scan", "service_detect", "dir_bruteforce", "vuln_check", "exploit_check"]
    for tool in skill_refs:
        check(tool in pentest_methods, f"  {tool} exists in agent_pentest",
              f"Available: {skill_refs} vs actual methods")
except Exception as e:
    check(False, "  pentest-chain skill audit failed", str(e))

# ============================================================================
# SECTION 5: __init__.py export audit
# ============================================================================
section("5. __init__.py Export Audit")

init_path = Path(__file__).parent / "mcpserver" / "__init__.py"
check(init_path.exists(), "  mcpserver/__init__.py exists")

# Read and check exports
init_content = init_path.read_text()
check("mcp_registry" not in init_content or "import" in init_content,
      "  __init__.py is not empty (has content)", f"Content: {init_content!r}")

# The __init__.py only says "# MCP Server - Agent Registry" with no imports.
# It exports nothing meaningful.
check("from" in init_content or "import" in init_content or len(init_content.strip()) > 1,
      "  __init__.py exports modules/functions",
      f"Current content: {init_content.strip()!r} — only a comment, exports nothing.")

# Check agent __init__.py files
section("  5a. Per-agent __init__.py files")
for agent_name in expected_agents:
    init_f = Path(__file__).parent / "mcpserver" / agent_name / "__init__.py"
    check(init_f.exists(), f"  {agent_name}/__init__.py exists")

    if init_f.exists():
        content = init_f.read_text().strip()
        # Should at least import the agent class
        has_import = "import" in content or ("from" in content and "import" in content)
        check(has_import, f"  {agent_name}/__init__.py has imports", f"Content: {content!r}")

# ============================================================================
# SECTION 6: Cross-Cutting Structural Audit
# ============================================================================
section("6. Cross-Cutting Structural Audit")

mcpserver = Path(__file__).parent / "mcpserver"
agent_dirs = sorted([d for d in mcpserver.iterdir() if d.is_dir() and d.name.startswith("agent_") and not d.name.startswith("__")])
check(len(agent_dirs) == 14, "  14 agent directories exist", f"Got {len(agent_dirs)}")

# Check each agent has all required files
for ad in agent_dirs:
    name = ad.name
    manifest = ad / "agent-manifest.json"
    main_py = ad / f"{name}.py"
    init_py = ad / "__init__.py"

    has_all = manifest.exists() and main_py.exists() and init_py.exists()
    if not has_all:
        missing = []
        if not manifest.exists(): missing.append("agent-manifest.json")
        if not main_py.exists(): missing.append(f"{name}.py")
        if not init_py.exists(): missing.append("__init__.py")
        check(False, f"  {name}: MISSING {missing}")
    else:
        # Check manifest is valid JSON
        try:
            json.loads(manifest.read_text())
        except:
            check(False, f"  {name}: invalid manifest JSON")

# Nested agent lookup (skills referencing nonexistent agents)
section("  6a. Dangling skill references")
skill_dir = Path(__file__).parent / "skills"
if skill_dir.exists():
    for sf in skill_dir.rglob("SKILL.md"):
        content = sf.read_text(encoding="utf-8")
        # Look for agent_ patterns
        import re
        agent_refs = re.findall(r'agent_\w+', content)
        for ref in set(agent_refs):
            if ref.startswith("agent_"):
                exists = (mcpserver / ref).is_dir()
                if not exists:
                    check(False, f"  {sf.parent.name}/SKILL.md references non-existent agent: {ref}")

# ============================================================================
# SECTION 7: Manifest field consistency
# ============================================================================
section("7. Manifest Field Consistency")

for agent_name in expected_agents:
    manifest = registry[agent_name]["manifest"]

    # Check required fields
    check("name" in manifest, f"  {agent_name}: has 'name'")
    check("agentType" in manifest, f"  {agent_name}: has 'agentType'")
    check("entryPoint" in manifest, f"  {agent_name}: has 'entryPoint'")

    ep = manifest.get("entryPoint", {})
    if isinstance(ep, dict):
        check("module" in ep, f"  {agent_name}: entryPoint has 'module'")
        check("class" in ep, f"  {agent_name}: entryPoint has 'class'")
    else:
        check(False, f"  {agent_name}: entryPoint is not a dict", f"Value: {ep}")

# also check legacy fields don't conflict
for agent_name in expected_agents:
    manifest = registry[agent_name]["manifest"]
    legacy_class = manifest.get("agent_class", "")
    legacy_module = manifest.get("module", "")
    legacy_entrypoint = manifest.get("entrypoint", "")
    entrypoint_class = manifest["entryPoint"]["class"]
    entrypoint_module = manifest["entryPoint"]["module"]

    if legacy_class:
        # Doesn't necessarily conflict, but note it
        pass
    if legacy_entrypoint:
        pass

# ============================================================================
# SUMMARY
# ============================================================================
section("SUMMARY")
results.append(f"  Passed: {PASS}")
results.append(f"  Failed: {FAIL}")
results.append(f"  Total:  {PASS + FAIL}")
if FAIL == 0:
    results.append("  ✅ ALL CHECKS PASSED")
else:
    results.append(f"  ❌ {FAIL} checks FAILED")

print("\n".join(results))
sys.exit(0 if FAIL == 0 else 1)
