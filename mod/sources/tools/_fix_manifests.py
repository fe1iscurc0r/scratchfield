"""
Fix all agent-manifest.json to conform to scratchpad spec:
{ agentType, entryPoint: { module, class } }
"""
import json
import os
from pathlib import Path

MCPSERVER = Path(r"C:\Users\ASUS\Desktop\scratchpad\mcpserver")

# Map agent dir -> (module, class)
AGENT_MAP = {
    "agent_nuclei":     ("mcpserver.agent_nuclei.agent_nuclei", "AgentNuclei"),
    "agent_trivy":      ("mcpserver.agent_trivy.agent_trivy", "AgentTrivy"),
    "agent_sbom":       ("mcpserver.agent_sbom.agent_sbom", "AgentSBOM"),
    "agent_signing":    ("mcpserver.agent_signing.agent_signing", "AgentSigning"),
    "agent_osint":      ("mcpserver.agent_osint.agent_osint", "AgentOSINT"),
    "agent_decompile":  ("mcpserver.agent_decompile.agent_decompile", "AgentDecompile"),
    "agent_runtime":    ("mcpserver.agent_runtime.agent_runtime", "AgentRuntime"),
    "agent_waf":        ("mcpserver.agent_waf.agent_waf", "AgentWAF"),
    "agent_llm_decompile": ("mcpserver.agent_llm_decompile.agent_llm_decompile", "AgentLLMDecompile"),
    "agent_pentest":    ("mcpserver.agent_pentest.agent_pentest", "AgentPentest"),
    "agent_browser":    ("mcpserver.agent_browser.agent_browser", "AgentBrowser"),
    "agent_frida":      ("mcpserver.agent_frida.agent_frida", "AgentFrida"),
    "agent_strix":      ("mcpserver.agent_strix.agent_strix", "AgentStrix"),
    "agent_animation":  ("mcpserver.agent_animation.agent_animation", "AgentAnimation"),
}

for agent_dir_name, (module, cls) in AGENT_MAP.items():
    manifest_path = MCPSERVER / agent_dir_name / "agent-manifest.json"
    if not manifest_path.exists():
        print(f"SKIP {agent_dir_name}: no manifest")
        continue

    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    # Preserve existing fields, add/replace the required ones
    data["agentType"] = "mcp"
    data["entryPoint"] = {
        "module": module,
        "class": cls
    }
    # Ensure version
    if "version" not in data:
        data["version"] = "1.0.0"

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"OK  {agent_dir_name}")

print(f"\nFixed {len(AGENT_MAP)} manifests")
