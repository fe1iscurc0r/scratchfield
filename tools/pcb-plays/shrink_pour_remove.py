import json
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

e=EasyEDAPCB('LoRaCanary-底板-v0.6')
e.reload()

# 1. remove all pours
print('remove all pours')
e._ok(e._run('pcb','pour-clear'))
e.reload()

# 2. compute bounding box of all component pads
dmp=e.dump()
minx=miny=1e9
maxx=maxy=-1e9
for c in dmp['components']:
    for p in c['pads']:
        x,y=p['x'],p['y']
        minx=min(minx,x); maxx=max(maxx,x)
        miny=min(miny,y); maxy=max(maxy,y)
print('pad bbox:',(minx,miny,maxx,maxy))
print('mm:',(minx*0.0254,miny*0.0254,maxx*0.0254,maxy*0.0254))

# 3. set outline with 3mm (118mil) margin
margin=118
left=minx-margin; right=maxx+margin; bottom=miny-margin; top=maxy+margin
pts=[[left,bottom],[left,top],[right,top],[right,bottom]]
print('new outline pts:',pts)
print('width mil:',right-left,'mm:',(right-left)*0.0254)
print('height mil:',top-bottom,'mm:',(top-bottom)*0.0254)

e._ok(e._run('pcb','outline-set','--points',json.dumps(pts)))
print('outline set')

# 4. check
f=e.check()
errs=[x for x in f if x.get('level')=='ERROR']
print('heur errors:',len(errs))
for x in errs: print(' ',x.get('type'),x.get('at'))
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
