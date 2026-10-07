import math
import sys

sys.path.insert(0, 'scripts/easyeda')
from clearance_fix import EasyEDAPCB

P = 'LoRaCanary-底板-v0.6'
NET = '3V3'
TOL = 0.05

e = EasyEDAPCB(P)

def key(p):
    return (round(p[0], 2), round(p[1], 2))

# collect pads of this net
pads = []
dmp = e.dump()
for c in dmp['components']:
    for p in c['pads']:
        if p.get('net') == NET:
            pads.append((c['designator'], p['padNumber'], key((p['x'], p['y']))))
pad_keys = {k for _, _, k in pads}

# union-find over vertices
parent = {}
def find(a):
    parent.setdefault(a, a)
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb

verts = set(pad_keys)
tracks = e.tracks(NET)
edges = []
for t in tracks:
    a = key((t['startX'], t['startY']))
    b = key((t['endX'], t['endY']))
    verts |= {a, b}
    edges.append((t['primitiveId'], a, b))
for v in e.vias(NET):
    k = key((v['x'], v['y']))
    verts.add(k)
    # treat via as a node joining all layers => single vertex
for k in verts:
    find(k)

for eid, a, b in edges:
    union(a, b)
for v in e.vias(NET):
    k = key((v['x'], v['y']))
    union(k, k)  # no-op keeps vertex registered

root_pads = {find(k) for k in pad_keys}

orphans = [eid for eid, a, b in edges if find(a) not in root_pads]
print(f'{NET}: {len(tracks)} tracks, {len(edges)} edges, orphan={len(orphans)}')
for eid in orphans:
    print('  orphan', eid)

if orphans:
    e._ok(e._run('pcb', 'track-delete', '--ids', ','.join(orphans)))
    print('deleted orphans')

# restore SCL second branch to R2 / OLED side
need = [
    (1681.3, 2619.5, 1685.6, 2619.5),
    (1685.6, 2619.5, 1705.6, 2639.5),
    (1705.6, 2639.5, 1705.6, 2789.5),
    (1705.6, 2789.5, 1695.6, 2799.5),
    (1695.6, 2799.5, 1605.6, 2799.5),
    (1605.6, 2799.5, 1555.6, 2749.5),
    (1555.6, 2749.5,  955.6, 2749.5),
    ( 955.6, 2749.5,  875.6, 2669.5),
    ( 875.6, 2669.5,  586.6, 2669.5),
    ( 586.6, 2669.5,  576.2, 2679.9),
]
have = {(a, b) for a, b, _ in [(t['startX'], t['startY'], None) for t in []]}
for a, b, c, d in need:
    exists = False
    for t in e.tracks('SCL'):
        if abs(t['startX']-a)<TOL and abs(t['startY']-b)<TOL and abs(t['endX']-c)<TOL and abs(t['endY']-d)<TOL:
            exists = True
            break
        if abs(t['endX']-a)<TOL and abs(t['endY']-b)<TOL and abs(t['startX']-c)<TOL and abs(t['startY']-d)<TOL:
            exists = True
            break
    if not exists:
        e.create_track(a, b, c, d, 'SCL', 10, 1)
        print('SCL restored seg', (a, b, c, d))

print('pour-rebuild'); e._ok(e._run('pcb', 'pour-rebuild'))
e.reload()

f = e.check()
errs = [x for x in f if x.get('level') == 'ERROR']
print('heur errors:', len(errs))

resp = e._run('pcb', 'drc', '--timeout', '180')['result']
leaves = []
def walk(n):
    if isinstance(n, dict):
        if 'list' in n:
            for s in n['list']: walk(s)
        elif 'explanation' in n:
            leaves.append(n['explanation'].get('errData', {}))
for g in resp['violations']: walk(g)
from collections import Counter

cnt = Counter(l.get('errorType') for l in leaves)
print('DRC leaf:', len(leaves), dict(cnt))
print('NoConn:', sorted({l.get('obj1Suffix') for l in leaves if l.get('errorType') == 'No Connection'}))
