import json
import os

scratch = r"C:\Users\ASUS\Desktop\scratchpad"
mcpserver = os.path.join(scratch, "mcpserver")

manifests = []
for d in sorted(os.listdir(mcpserver)):
    if d.startswith("agent_") and os.path.isdir(os.path.join(mcpserver, d)):
        mf = os.path.join(mcpserver, d, "agent-manifest.json")
        data = json.load(open(mf, encoding="utf-8"))
        manifests.append(data)
        cls = data["entryPoint"]["class"]
        mod = data["entryPoint"]["module"]
        print(f"OK  {d}: class={cls}  module={mod}")

print(f"\nManifests: {len(manifests)} OK")

# Import test
print()
for d in sorted(os.listdir(mcpserver)):
    if d.startswith("agent_") and os.path.isdir(os.path.join(mcpserver, d)):
        modname = f"mcpserver.{d}.{d}"
        try:
            m = __import__(modname, fromlist=["handle_handoff"])
            has_hh = hasattr(m, "handle_handoff")
            print(f"OK  {d}: import OK, handle_handoff={has_hh}")
        except Exception as e:
            print(f"ERR {d}: {e}")

# Skill check
print()
skills = os.path.join(scratch, "skills")
for d in sorted(os.listdir(skills)):
    sf = os.path.join(skills, d, "SKILL.md")
    if os.path.isfile(sf):
        raw = open(sf, encoding="utf-8").read()
        has_version = "version:" in raw[:200]
        has_tags = "tags:" in raw[:200]
        has_enabled = "enabled:" in raw[:200]
        has_author = "author:" in raw[:200]
        ok = has_version and has_tags and has_enabled and has_author
        status = "OK" if ok else "FIXME"
        print(f"{status} skill/{d}: version={has_version} tags={has_tags} enabled={has_enabled} author={has_author}")
