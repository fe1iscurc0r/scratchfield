"""
MCP Registry - auto-discovers and registers MCP Agents.

Scans mcpserver/ directory for agent-manifest.json files,
validates them, and provides a registry of available MCP services.

Supports both strict spec format (agentType + entryPoint) and
legacy format (agent_class + module + entrypoint).
"""
import importlib
import json
import sys
from pathlib import Path


def _resolve_entrypoint(manifest: dict, agent_dir: Path) -> tuple:
    """Resolve (module, class) from manifest, supporting multiple formats.

    Format A (spec): {"entryPoint": {"module": "...", "class": "..."}}
    Format B (legacy): {"agent_class": "...", "module": "...", "entrypoint": "..."}
    Format C (minimal): name only -> derives module/class from dir name
    """
    name = str(manifest.get("name") or "")

    # Format A: spec entryPoint
    ep = manifest.get("entryPoint")
    if isinstance(ep, dict):
        module = ep.get("module", "")
        cls = ep.get("class", "")
        if module and cls:
            return module, cls

    # Format B: legacy flat fields
    cls = manifest.get("agent_class") or manifest.get("class") or ""
    module = manifest.get("module") or ""

    if module and cls:
        return module, cls

    # Format C: entrypoint string like "agent_nuclei.handle_handoff"
    entrypoint = manifest.get("entrypoint") or ""
    if entrypoint:
        parts = entrypoint.split(".")
        if len(parts) >= 2:
            module = ".".join(parts[:-1])
            return module, "handle_handoff"  # function, not class

    # Format D: derive from directory name
    if name:
        module = f"mcpserver.{name}.{name}"
        # Try to detect class name by reading the module
        try:
            mod = importlib.import_module(module)
            if hasattr(mod, "handle_handoff"):
                return module, "handle_handoff"
        except Exception:
            pass
        return module, ""

    return "", ""


def auto_register_mcp(base_dir: str = None) -> dict:
    """
    Scan mcpserver/ for agent-manifest.json and register all agents.

    Returns: {"agent_key": {"manifest": ..., "module": ..., "class": ...}, ...}
    """
    if base_dir is None:
        base_dir = Path(__file__).parent

    base_dir = Path(base_dir)
    registry = {}

    for manifest_path in base_dir.rglob("agent-manifest.json"):
        # Skip __pycache__ and other hidden dirs
        parts = manifest_path.parts
        if any(p.startswith("__") and p != "__init__.py" for p in parts):
            continue
        parent = manifest_path.parent
        if parent.name.startswith("__"):
            continue

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[MCP Registry] Warning: Failed to parse {manifest_path}: {e}", file=sys.stderr)
            continue

        name = str(manifest.get("name") or "")
        if not name:
            name = parent.name
            manifest["name"] = name

        # Auto-fill missing fields
        if "agentType" not in manifest:
            manifest["agentType"] = "mcp"
        if "version" not in manifest:
            manifest["version"] = "1.0.0"

        module, cls = _resolve_entrypoint(manifest, parent)
        if not module:
            print(f"[MCP Registry] Warning: {manifest_path}: could not resolve entryPoint", file=sys.stderr)
            continue

        registry[name] = {
            "manifest": manifest,
            "path": str(parent),
            "module": module,
            "class": cls or "handle_handoff",
        }

        display = manifest.get("displayName") or manifest.get("description") or name
        print(f"[MCP Registry] Registered: {name} ({display})")

    return registry


def get_agent(name: str, base_dir: str = None) -> object:
    """Dynamically import and instantiate an MCP Agent by registered name."""
    registry = auto_register_mcp(base_dir)
    if name not in registry:
        return None
    entry = registry[name]
    import importlib
    mod = importlib.import_module(entry["module"])
    cls = getattr(mod, entry["class"])
    return cls()


# ----- CLI helper -----
if __name__ == "__main__":
    base = Path(__file__).parent
    registry = auto_register_mcp(str(base))
    names = list(registry.keys())
    print(f"\nRegistered {len(names)} MCP services: {names}")
