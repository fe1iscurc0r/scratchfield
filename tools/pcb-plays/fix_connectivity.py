import sys

sys.path.insert(0, 'scripts/easyeda')
from clearance_fix import EasyEDAPCB

P = 'LoRaCanary-底板-v0.6'
e = EasyEDAPCB(P)

print('==> reauthorize')
e.reauthorize()

# ---------------- CC2 -----------------
print('==> CC2')
e.create_via(4321.474, 2105, 'CC2')
e.create_track(4363.9, 2070.7, 4363.9, 2105, 'CC2', 6, 1)
e.create_track(4363.9, 2105, 4321.474, 2105, 'CC2', 6, 1)
e.create_track(4321.474, 2105, 4321.474, 2130, 'CC2', 10, 2)
e.create_track(4321.474, 2130, 2332.1, 2130, 'CC2', 10, 2)
e.create_track(2332.1, 2130, 2332.1, 2210, 'CC2', 10, 2)
e.create_via(2332.1, 2210, 'CC2')
e.create_track(2332.1, 2210, 2302.1, 2210, 'CC2', 10, 1)

# ---------------- SDA -----------------
print('==> SDA')
# pull-up R1_2 island
e.create_via(619.88, 2584.9988, 'SDA')
e.create_track(584.4, 2585, 619.88, 2584.9988, 'SDA', 10, 1)
e.create_track(619.88, 2584.9988, 632.87, 2597.99, 'SDA', 10, 16)
e.create_track(632.87, 2597.99, 1496.89, 2597.99, 'SDA', 10, 16)
e.create_track(1496.89, 2597.99, 1506.89, 2587.99, 'SDA', 10, 16)
e.create_via(1506.89, 2587.99, 'SDA')
# MCU U1_11
e.create_track(1651.3, 2588, 1506.89, 2587.99, 'SDA', 10, 1)
# main run to sensor
e.create_track(1506.89, 2587.99, 2726.888, 2587.99, 'SDA', 10, 16)
e.create_track(2726.888, 2587.99, 2761.109, 2622.207, 'SDA', 10, 16)
e.create_track(2761.109, 2622.207, 2804.5495, 2622.207, 'SDA', 10, 16)
# hop out of U3 body to bottom, then east to U6_4
e.create_via(2845, 2628.7664, 'SDA')
e.create_track(2804.5495, 2622.207, 2845, 2628.7664, 'SDA', 10, 16)
e.create_track(2804.5495, 2622.207, 2845, 2628.7664, 'SDA', 10, 1)
e.create_track(2845, 2628.7664, 2954.876, 2504.9989, 'SDA', 10, 2)
e.create_track(2954.876, 2504.9989, 3395, 2504.9989, 'SDA', 10, 2)

# ---------------- 3V3 missing U3_6 / U3_8 -----------------
print('==> 3V3 spur')
# inner-l15 tree from existing anchor via (2774.5,2647.8)
e.create_track(2774.5, 2647.8, 2740, 2647.8, '3V3', 10, 15)
e.create_track(2740, 2647.8, 2740, 2622.21, '3V3', 10, 15)
e.create_track(2740, 2647.8, 2712, 2647.8, '3V3', 10, 15)
e.create_track(2712, 2647.8, 2712, 2673.39, '3V3', 10, 15)
e.create_via(2740, 2622.21, '3V3')
e.create_via(2712, 2673.39, '3V3')
# short top stubs into SMD pads
e.create_track(2740, 2622.21, 2705.5, 2622.21, '3V3', 6, 1)
e.create_track(2712, 2673.39, 2705.5, 2673.39, '3V3', 6, 1)

# ---------------- finalize -----------------
print('==> pour-rebuild')
e._ok(e._run('pcb', 'pour-rebuild'))
print('==> reload')
e.reload()
print('==> pcb check (heuristic)')
fnd = e.check()
errs = [f for f in fnd if f.get('level') == 'ERROR']
print(f'\nheuristic errors: {len(errs)}')

print('\n==> direct plugin DRC')
drc_txt = e._run('pcb', 'drc', '--timeout', '180')
try:
    res = drc_txt['result']
except Exception:
    # non-json plain text fallback shouldn't happen; dump head
    print(drc_txt)
    raise
print('passed:', res.get('passed'))
leaves = []
def walk(n):
    if isinstance(n, dict):
        if 'list' in n:
            for s in n['list']:
                walk(s)
        elif 'explanation' in n:
            leaves.append(n['explanation'].get('errData', {}))
for g in res['violations']:
    walk(g)
from collections import Counter

c = Counter(l.get('errorType') for l in leaves)
print('leaf violations:', len(leaves), dict(c))
for l in leaves[:60]:
    pos = l.get('position') or {}
    print(' ', l.get('errorType'),
          l.get('obj1Suffix'), '<->', l.get('obj2Suffix'),
          (round(pos.get('x', 0) * 10, 1), round(pos.get('y', 0) * 10, 1)))
