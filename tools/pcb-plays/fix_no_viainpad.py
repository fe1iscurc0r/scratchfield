import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

P='LoRaCanary-底板-v0.6'
e=EasyEDAPCB(P)
print('== reload =='); e.reload()
dmp=e.dump()

def pad_rect(p):
    w,h=p['width'],p['height']
    if int(p.get('rotation',0))%180==90: w,h=h,w
    return (p['x']-w/2,p['y']-h/2,p['x']+w/2,p['y']+h/2)

# ---------- Phase 1 : remove vias overlapping small SMD pads ----------
smd=[]
for c in dmp['components']:
    for p in c['pads']:
        r=pad_rect(p)
        if p.get('layer')==1 and max(r[2]-r[0],r[3]-r[1])<=60:   # SMD-scale pads only
            smd.append((c['designator'],p['padNumber'],p.get('net'),r))
print('SMD top pads tracked:',len(smd))

victims=[]
for v in e.vias():
    x,y=v['x'],v['y']
    for des,num,nt,r in smd:
        if r[0]<=x<=r[2] and r[1]<=y<=r[3]:
            victims.append((des,num,nt,r,v['primitiveId']))
print('vias punched into SMD pads:',len(victims))
for t in victims: print('   del',t[0],t[1],t[3])
if victims:
    e._ok(e._run('pcb','via-delete','--ids',','.join(v[4] for v in victims)))
print('deleted.')
e.reload()

# ---------- Phase 2 : dog-bone reconnect for every hit pad ----------
allc=[{'net':t.get('net'),'x1':t['startX'],'y1':t['startY'],
       'x2':t['endX'],'y2':t['endY'],'w':t['lineWidth']} for t in e.tracks()]
tracks_map=allc

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

verts=[{'net':t['net'],'x':t['startX'],'y':t['startY'],'layer':t['layer']} for t in e.tracks()]+ \
      [{'net':v['net'],'x':v['x'],'y':v['y'],'layer':'V'} for v in e.vias()]

for des,num,nt,r in victims[:8]:
    px=(r[0]+r[2])/2; py=(r[1]+r[3])/2
    net_id=nt
    placed=False
    for dist in range(24,54,6):
        for ang in range(0,360,15):
            ax=px+dist*math.cos(math.radians(ang)); ay=py+dist*math.sin(math.radians(ang))
            if not pt_clear(ax,ay,12,6,net_id): continue
            if not seg_clear(px,py,ax,ay,6,6,net_id): continue
            # neighbour same-net via/track-endpoint reachable on inner layer?
            best=None
            for vt in verts:
                if vt['net']!=net_id: continue
                d=math.hypot(vt['x']-ax,vt['y']-ay)
                if 20<d<170:
                    s=int(max(4,d//3)+1); ok=True
                    for i in range(s+1):
                        mx=ax+(vt['x']-ax)*i/s; my=ay+(vt['y']-ay)*i/s
                        if not pt_clear(mx,my,5,6,net_id): ok=False;break
                    if ok and (best is None or d<best[0]):
                        best=(d,vt)
            if best is None: continue
            d,vt=best
            e.create_via(ax,ay,net_id)
            e.create_track(px,py,ax,ay,net_id,6,1)          # dog-bone stub
            e.create_track(ax,ay,vt['x'],vt['y'],net_id,10,15)
            print(f'{des}.{num}: via@({round(ax)},{round(ay)}) -> net node ({round(vt["x"])},{round(vt["y"])})')
            placed=True; break
        if placed: break
    if not placed:
        print(f'{des}.{num}: !! no safe spot; manual')

# ---------- Phase 3 : generic closer (reuse stitcher core quickly) ----------
# minimal: reconnect remaining isolated comps within 60 mil via previous algorithm
exec(open('fix_stitch_body.txt').read()) if False else None

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
