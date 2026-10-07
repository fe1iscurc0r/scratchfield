import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

P='LoRaCanary-底板-v0.6'
e=EasyEDAPCB(P)
e.reload()
dmp=e.dump()

TARGETS={('R4','2'),('R5','2'),('C1','1'),('U3','6'),('U3','8')}

def pad_rect(p):
    w,h=p['width'],p['height']
    if int(p.get('rotation',0))%180==90: w,h=h,w
    return (p['x']-w/2,p['y']-h/2,p['x']+w/2,p['y']+h/2)

allc=[{'net':t.get('net'),'x1':t['startX'],'y1':t['startY'],
       'x2':t['endX'],'y2':t['endY'],'w':t['lineWidth']} for t in e.tracks()]

def pt_clear(px,py,rad,gap,net):
    for t in allc:
        if t['net']==net: continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap: return False
    return True

def seg_clear(ax,ay,bx,by,w,gap,net):
    n=max(4,int(math.hypot(bx-ax,by-ay)//3)+1)
    for i in range(n+1):
        px=ax+(bx-ax)*i/n; py=ay+(by-ay)*i/n
        if not pt_clear(px,py,w/2+.01,gap,net): return False
    return True

verts=[]
for t in e.tracks():
    verts+=[{'net':t.get('net'),'x':t['startX'],'y':t['startY']},
            {'net':t.get('net'),'x':t['endX'],'y':t['endY']}]
for v in e.vias():
    verts.append({'net':v['net'],'x':v['x'],'y':v['y']})

placed_ct=0
for c in dmp['components']:
    key=(c['designator'],None)
    for p in c['pads']:
        kk=(c['designator'],p['padNumber'])
        if kk not in TARGETS: continue
        nt=p.get('net'); r=pad_rect(p)
        px=(r[0]+r[2])/2; py=(r[1]+r[3])/2
        placed=False
        for dist in range(24,60,6):
            for ang in range(0,360,15):
                ax=px+dist*math.cos(math.radians(ang)); ay=py+dist*math.sin(math.radians(ang))
                if not pt_clear(ax,ay,12,6,nt): continue
                if not seg_clear(px,py,ax,ay,6,6,nt): continue
                best=None
                for vt in verts:
                    if vt['net']!=nt: continue
                    d=math.hypot(vt['x']-ax,vt['y']-ay)
                    if not 18<d<170: continue
                    s=int(d//3)+2; ok=True
                    for i in range(s+1):
                        mx=ax+(vt['x']-ax)*i/s; my=ay+(vt['y']-ay)*i/s
                        if not pt_clear(mx,my,5,6,nt): ok=False;break
                    if ok and (best is None or d<best[0]): best=(d,vt)
                if best is None: continue
                d,vt=best
                e.create_via(ax,ay,nt)
                e.create_track(px,py,ax,ay,nt,6,1)
                e.create_track(ax,ay,vt['x'],vt['y'],nt,10,15)
                print(f'{kk[0]}.{kk[1]} ({nt}): via@({round(ax)},{round(ay)}) link->{(round(vt["x"]),round(vt["y"]))}')
                placed=True; placed_ct+=1; break
            if placed: break
        if not placed:
            print(f'{kk[0]}.{p["padNumber"]}: no safe spot !!')

print('dogbones placed:',placed_ct)
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
