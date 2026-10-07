import sys

sys.path.insert(0, 'scripts/easyeda')
from clearance_fix import EasyEDAPCB

P='LoRaCanary-底板-v0.6'
e=EasyEDAPCB(P)

print('reload'); e.reload()
print('rip 3V3'); e._ok(e._run('pcb','rip-up','--net','3V3')); e.reload()
print('reauthorize'); e.reauthorize()

# ---- reads ----
scl_existing={(round(t['startX'],1),round(t['startY'],1),round(t['endX'],1),round(t['endY'],1)) for t in e.tracks('SCL')}

def T(a,b,c,d,w=10,l=1):
    e.create_track(a,b,c,d,'3V3',w,l)
def V(x,y): e.create_via(x,y,'3V3')

for x,y in [(538.187,2798.787),(518.613,2701.113),(505.6,2555),(608.2,1843),
            (1681.3,2273),(2538.1,2400),(2801.9,2430),(2774.5,2647.8)]:
    V(x,y)

spine=[
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
 ( 610.5145,2543.0264, 610.5145,1815.3035),
 ( 610.5145,1815.3035, 608.2114,1813.0003),
]
for s in spine: T(*s)

T(1651.2605,2273.0269,1695.6305,2273.0269)
T(1695.6305,2273.0269,1745.6304,2323.0268)
T(1745.6304,2323.0268,1822.6027,2399.9991,l=15)
T(1822.6027,2399.9991,2252.6018,2399.9991,l=15)
T(2252.6018,2399.9991,2272.6018,2379.9992,l=15)
T(2272.6018,2379.9992,2548.0697,2379.9992)
T(2548.0697,2379.9992,2568.0697,2399.9991)
T(2568.0697,2399.9991,2801.9275,2399.9991)

# east tail to C3 / U6_2
T(2801.9275,2399.9991,2969.372,2399.9991)
T(2969.372,2399.9991,3030.0018,2460.6289)
T(3030.0018,2460.6289,3030.0018,2356.2199)
T(3030.0018,2356.2199,3041.5295,2344.6921)
T(3041.5295,2344.6921,3041.5295,2340.6921)
T(3041.5295,2340.6921,3355.3083,2340.6921)
T(3355.3083,2340.6921,3395.0011,2304.9993)

# U3 escape branch fed exclusively from anchor via (2774.5,2647.8):
T(2775.3448,2647.7979,2804.5495,2647.7979)     # pin 2 pad
J=(2732.6008,2605.0538)
T(J[0],J[1],2715.4473,2622.2074)               # diag toward pin6
T(2715.4473,2622.2074,2705.4473,2622.2074)
T(2715.4473,2622.2074,J[0],J[1]) if False else None
# path pin8 approach uses left-of-body weave
T(2705.4473,2622.2074,2695.4474,2622.2074)
T(2695.4474,2622.2074,2675.4474,2642.2073)
T(2675.4474,2642.2073,2675.4474,2652.2073)
T(2675.4474,2652.2073,2696.6285,2673.3884)
T(2696.6285,2673.3884,2705.4473,2673.3884)     # pin 8 pad
# feed junction J from below-left body gap using l1 short hop:
T(J[0],J[1],2715.4473,2622.2074)                # duplicate diag keeps both ends warm
# bridge junction northwards into clean interior via l1 gaps:
T(J[0],J[1],2732.6008,2569.9988)
T(2732.6008,2569.9988,2742.6008,2569.9988)

# --- SCL second branch restore (verbatim historical) ---
need=[
 (1681.3,2619.5,1685.6,2619.5),
 (1685.6,2619.5,1705.6,2639.5),
 (1705.6,2639.5,1705.6,2789.5),
 (1705.6,2789.5,1695.6,2799.5),
 (1695.6,2799.5,1605.6,2799.5),
 (1605.6,2799.5,1555.6,2749.5),
 (1555.6,2749.5,955.6,2749.5),
 (955.6,2749.5,875.6,2669.5),
 (875.6,2669.5,586.6,2669.5),
 (586.6,2669.5,576.2,2679.9),
]
for a,b,c,d in need:
    if (a,b,c,d) not in scl_existing and (c,d,a,b) not in scl_existing:
        e.create_track(a,b,c,d,'SCL',10,1)
        print('SCL add',(a,b))

print('pour-rebuild'); e._ok(e._run('pcb','pour-rebuild'))
e.reload()
f=e.check()
errs=[x for x in f if x.get('level')=='ERROR']
print('heur errors:',[(x['type'],x.get('at',{}).get('x'),x.get('at',{}).get('y'),x.get('nets')) for x in errs])
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
ncs=sorted({l.get('obj1Suffix') for l in leaves if l.get('errorType')=='No Connection'})
print('NoConn:',ncs)
