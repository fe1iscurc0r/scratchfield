import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

e=EasyEDAPCB('LoRaCanary-底板-v0.6')
e.reload()
allc=[{'net':t.get('net'),'x1':t['startX'],'y1':t['startY'],
       'x2':t['endX'],'y2':t['endY'],'w':t['lineWidth'],'layer':t['layer']} for t in e.tracks()]

def pt_all(px,py,rad,gap,net):
    for t in allc:
        if t['net']==net: continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap: return False
    return True

def pt_top(px,py,rad,gap,net):
    for t in allc:
        if t['net']==net or t['layer']!=1: continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap: return False
    return True

def seg(fn,ax,ay,bx,by,w,gap,net):
    n=max(4,int(math.hypot(bx-ax,by-ay)//3)+1)
    for i in range(n+1):
        px=ax+(bx-ax)*i/n; py=ay+(by-ay)*i/n
        if not fn(px,py,w/2+.01,gap,net): return False
    return True

# ---------- U3_8 -> try via hub at (2757,2652) ----------
P=(2705.5,2673.398)
hubs=[(v['x'],v['y']) for v in e.vias('3V3') if abs(v['x']-2757)<3 and abs(v['y']-2652)<3]
print('hubs near 2757,2652:',hubs)
if hubs:
    hx,hy=hubs[0]
    if seg(pt_top,P[0],P[1],hx,hy,6,6,'3V3'):
        e.create_track(P[0],P[1],hx,hy,'3V3',6,1)
        print('U3_8 -> hub OK')
    else:
        # try other nearby via spots for U3_8
        placed=False
        for dist in range(24,70,6):
            for ang in range(0,360,15):
                ax=P[0]+dist*math.cos(math.radians(ang)); ay=P[1]+dist*math.sin(math.radians(ang))
                if not pt_all(ax,ay,12,6,'3V3'): continue
                if not seg(pt_top,P[0],P[1],ax,ay,6,6,'3V3'): continue
                # connect to nearest 3V3 via or endpoint
                best=None
                for t in e.tracks('3V3'):
                    for x,y in [(t['startX'],t['startY']),(t['endX'],t['endY'])]:
                        d=math.hypot(x-ax,y-ay)
                        if 1<d<180:
                            ok=True
                            s=max(4,int(d//3)+1)
                            for i in range(s+1):
                                mx=ax+(x-ax)*i/s; my=ay+(y-ay)*i/s
                                if not pt_all(mx,my,5,6,'3V3'): ok=False; break
                            if ok and (best is None or d<best[0]): best=(d,x,y)
                for v in e.vias('3V3'):
                    d=math.hypot(v['x']-ax,v['y']-ay)
                    if 1<d<180:
                        ok=True
                        s=max(4,int(d//3)+1)
                        for i in range(s+1):
                            mx=ax+(v['x']-ax)*i/s; my=ay+(v['y']-ay)*i/s
                            if not pt_all(mx,my,5,6,'3V3'): ok=False; break
                        if ok and (best is None or d<best[0]): best=(d,v['x'],v['y'])
                if best:
                    d,tx,ty=best
                    e.create_via(ax,ay,'3V3')
                    e.create_track(P[0],P[1],ax,ay,'3V3',6,1)
                    e.create_track(ax,ay,tx,ty,'3V3',10,15)
                    print(f'U3_8 dogbone via@({round(ax)},{round(ay)}) -> ({round(tx)},{round(ty)})')
                    placed=True; break
            if placed: break
        if not placed:
            print('U3_8 FAILED')
else:
    print('no hub found')

# ---------- R5_2 (LED_STDBY_A) ----------
R5x,R5y=2408.3,2421.1
# collect STDBY nodes
nodes=[]
for t in e.tracks('LED_STDBY_A'):
    nodes+=[(t['startX'],t['startY']),(t['endX'],t['endY'])]
for v in e.vias('LED_STDBY_A'): nodes.append((v['x'],v['y']))
print('STDBY nodes',len(nodes))
best=None
for x,y in nodes:
    d=math.hypot(x-R5x,y-R5y)
    if 1<d<250 and (best is None or d<best[0]): best=(d,x,y)
print('R5_2 nearest',best)
if best:
    d,tx,ty=best
    placed=False
    for dist in range(18,70,6):
        for ang in range(0,360,15):
            ax=R5x+dist*math.cos(math.radians(ang)); ay=R5y+dist*math.sin(math.radians(ang))
            if not pt_all(ax,ay,12,6,'LED_STDBY_A'): continue
            if not seg(pt_top,R5x,R5y,ax,ay,6,6,'LED_STDBY_A'): continue
            ok=True; s=max(4,int(d//3)+1)
            for i in range(s+1):
                mx=ax+(tx-ax)*i/s; my=ay+(ty-ay)*i/s
                if not pt_all(mx,my,5,6,'LED_STDBY_A'): ok=False; break
            if ok:
                e.create_via(ax,ay,'LED_STDBY_A')
                e.create_track(R5x,R5y,ax,ay,'LED_STDBY_A',6,1)
                e.create_track(ax,ay,tx,ty,'LED_STDBY_A',10,15)
                print(f'R5_2 dogbone via@({round(ax)},{round(ay)}) -> ({round(tx)},{round(ty)})')
                placed=True; break
        if placed: break
    if not placed: print('R5_2 FAILED')

print('pour-rebuild'); e._ok(e._run('pcb','pour-rebuild'))
e.reload()
f=e.check(); errs=[x for x in f if x.get('level')=='ERROR']
print('heur errors:',[(x['type'],round(x.get('at',{}).get('x',0)),round(x.get('at',{}).get('y',0))) for x in errs])
resp=e._run('pcb','drc','--timeout','180')['result']
leaves=[]
def walk(n):
    if isinstance(n,dict):
        if 'list' in n:
            for s in n['list']: walk(s)
        elif 'explanation' in n: leaves.append(n['explanation'].get('errData',{}))
for g in resp['violations']: walk(g)
from collections import Counter

print('DRC leaf:',len(leaves),dict(Counter(l.get('errorType') for l in leaves)))
ncs=sorted({l.get('obj1Suffix') for l in leaves if l.get('errorType')=='No Connection'})
print('NoConn:', ncs if ncs else 'NONE ✔')
