import re
from pathlib import Path

src = Path("apiserver/routes/extensions.py").read_text(encoding="utf-8")
lines = src.splitlines()

routes = []
for i, ln in enumerate(lines):
    m = re.match(r'@router\.(get|post|put|delete|patch)\("([^"]*)"', ln)
    if not m:
        continue
    method, path = m.group(1).upper(), m.group(2)
    # 向下找 def
    fname = ""
    for j in range(i + 1, min(i + 12, len(lines))):
        dm = re.match(r'(?:async )?def (\w+)', lines[j])
        if dm:
            fname = dm.group(1)
            break
    routes.append((i + 1, method, path, fname))

print("=== 路由总数 %d ===" % len(routes))
# 按一级前缀分组
from collections import defaultdict

groups = defaultdict(list)
for ln, method, path, fname in routes:
    seg = [s for s in path.split("/") if s and not s.startswith("{")]
    key = "/" + (seg[0] if seg else "(root)")
    groups[key].append((ln, method, path, fname))

for key in sorted(groups, key=lambda k: -len(groups[k])):
    print("\n## %s  (%d)" % (key, len(groups[key])))
    for ln, method, path, fname in groups[key]:
        print("   L%-5d %-6s %-42s %s" % (ln, method, path, fname))

# 非路由顶层函数（helper）
print("\n\n=== 非路由顶层 def/class ===")
route_lines = {r[0] for r in routes}
for i, ln in enumerate(lines):
    if (i + 1) in route_lines:
        continue
    m = re.match(r'(?:async )?def (\w+)|class (\w+)', ln)
    if m:
        name = m.group(1) or m.group(2)
        print("   L%-5d %s" % (i + 1, name))

# 装饰器前缀（router 定义处）
print("\n=== router 定义 ===")
for i, ln in enumerate(lines):
    if ln.startswith("router ="):
        print("   L%d %s" % (i + 1, ln))
