import sys

sys.path.insert(0, 'scripts/easyeda')
from clearance_fix import EasyEDAPCB

P = 'LoRaCanary-底板-v0.6'
e = EasyEDAPCB(P)

print('==> reload')
e.reload()
print('==> rip-up 3V3 only')
e._ok(e._run('pcb', 'rip-up', '--net', '3V3'))
e.reload()
print('==> reauthorize')
e.reauthorize()

def T(a,b,c,d,w=10,l=1):
    e.create_track(a,b,c,d,'3V3',w,l)
def V(x,y):
    e.create_via(x,y,'3V3')

# ---- complete SINGLE-TREE 3V3 (historical layout minus redundant alt-trunk) ----
for x,y in [(538.187,2798.787),(518.613,2701.113),(505.6,2555),(608.2,1843),
            (1681.3,2273),(2538.1,2400),(2801.9,2430),(2774.5,2647.8)]:
    V(x,y)

spine = [
    (1651.2605,2273.0269,1171.9307,2273.0269),
    (1171.9307,2273.0269, 931.9312,2513.0265),
    ( 931.9312,2513.0265, 780.5142,2513.0265),
    ( 780.5142,2513.0265, 770.5142,2523.0264),
    ( 770.5142,2523.0264, 770.5142,2583.0263),
    ( 770.5142,2583.0263, 779.5693,2583.0263),
    ( 779.5693,2583.0263, 825.0417,2628.4987),
    ( 770.5142,2583.0263, 650.5144,2583.0263),
    ( 650.5144,2583.0263, 610.5145,2543.0264),
    ( 610.5145,2543.0264, 547.6013,2543.0264),
    ( 547.6013,2543.0264, 505.6289,2584.9988),
    ( 505.6289,2584.9988, 505.6289,2671.723),
    ( 505.6289,2671.723,  497.4399,2679.912),
    ( 497.4399,2679.912,  497.4399,2758.0693),
    ( 497.4399,2758.0693, 559.369, 2819.9983),
    # down-island C5
    ( 610.5145,2543.0264, 610.5145,1815.3035),
    ( 610.5145,1815.3035, 608.2114,1813.0003),
]
for s in spine: T(*s)

# MCU fan-out
T(1651.2605,2273.0269,1695.6305,2273.0269)
T(1695.6305,2273.0269,1745.6304,2323.0268)
T(1745.6304,2323.0268,1822.6027,2399.9991,l=15)
T(1822.6027,2399.9991,2252.6018,2399.9991,l=15)
T(2252.6018,2399.9991,2272.6018,2379.9992,l=15)
T(2272.6018,2379.9992,2548.0697,2379.9992)
T(2548.0697,2379.9992,2568.0697,2399.9991)
T(2568.0697,2399.9991,2801.9275,2399.9991)

# inner hop down to U3 body junction
T(2568.0697,2399.9991,2568.0697,2430, l=16)   # uses existing via @2801? keep simple new corner none needed actually vertical exits into horizontal later on l1; skip complex: direct connector instead below

# straight link junction point to U3 escape start (clear interior corridor)
T(2732.6008,2605.0538,2775.3448,2647.7979)          # leg toward pin2
T(2775.3448,2647.7979,2804.5495,2647.7979)          # pin2
T(2732.6008,2605.0538,2715.4473,2622.2074)          # diag pin6
T(2715.4473,2622.2074,2705.4473,2622.2074)
T(2732.6008,2605.0538,2732.6008,2569.9988)          # bridge north
T(2732.6008,2569.9988,2742.6008,2569.9988)
T(2742.6008,2569.9988,2801.9275,2569.9988, l=16)     # join upper trunk via inner
T(2801.9275,2569.9988,2801.9275,2399.9991, l=16)
# connect that inner corner to the top horizontal node (via already at 2801.9,2430)
T(2801.9275,2430,2801.9275,2569.9988, l=16)

# missing bridge between fanout corner and junction x2732 region ON TOP cleared zone:
# historical used inner path; replicate small jump:
T(2548.0697,2379.9992,2518.8217,2379.9992, l=16)
T(2518.8217,2379.9992,2708.8214,2569.9988, l=16)
T(2708.8214,2569.9988,2732.6008,2593.7782, l=16)
T(2732.6008,2593.7782,2732.6008,2605.0538)          # hop to top junction

# east rail + C3/U6_2 patched tail
T(2801.9275,2399.9991,2969.372,2399.9991)
T(2969.372,2399.9991,3030.0018,2460.6289)
T(3030.0018,2460.6289,3030.0018,2356.2199)
T(3030.0018,2356.2199,3041.5295,2344.6921)
T(3041.5295,2344.6921,3041.5295,2340.6921)
T(3041.5295,2340.6921,3355.3083,2340.6921)
T(3355.3083,2340.6921,3395.0011,2304.9993)

print('==> validate connectivity in-memory')
verts=set(); edges=[]
for t in e.tracks('3V3'):
    a=(round(t['startX'],2),round(t['startY'],2)); b=(round(t['endX'],2),round(t['endY'],2))
    verts|={a,b}; edges.append((t['primitiveId'],a,b))
pads={}
dmp=e.dump()
for c in dmp['components']:
    for p in c['pads']:
        if p.get('net')=='3V3':
            pads[(c['designator'],p['padNumber'])]=(round(p['x'],2),round(p['y'],2))
parent={v:v for v in verts}
def find(a):
    while parent[a]!=a: parent[a]=parent[parent[a]]; a=parent[a]
    return a
def uni(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: parent[ra]=rb
for _,a,b in edges: uni(a,b)
padroots={find(v) for v in pads.values()}
unrooted=[eid for eid,a,b in edges if find(a) not in padroots]
print('tracks:',len(edges),'unconnected:',len(unrooted))

print('==> pour-rebuild'); e._ok(e._run('pcb','pour-rebuild'))
e.reload()
f=e.check(); print('heur errors:',[x['type'] for x in f if x.get('level')=='ERROR'])
resp=e._run('pcb','drc','--timeout','180')['result']
leaves=[]
def walk(n):
    if isinstance(n,dict):
        if 'list' in n:
            for s in n['list']: walk(s)
        elif 'explanation' in n: leaves.append(n['explanation'].get('errData',{}))
for g in resp['violations']: walk(g)
from collections import Counter

cnt=Counter(l.get('errorType') for l in leaves)
print('DRC leaf:',len(leaves),dict(cnt))
nc=sorted({l.get('obj1Suffix') for l in leaves if l.get('errorType')=='No Connection'})
print('NoConn:',nc)
