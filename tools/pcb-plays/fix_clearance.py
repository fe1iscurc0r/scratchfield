import sys

sys.path.insert(0, 'scripts/easyeda')
from clearance_fix import EasyEDAPCB

e = EasyEDAPCB('LoRaCanary-底板-v0.6', doc='PCB2')

# Step 1: reload to get a fresh document, then authorize
print('==> initial reload')
e.reload()
print('==> reauthorize')
e.reauthorize()

# Step 2: delete old/dup primitives
ids = [
    # old 3V3 branch at y=2344
    '20e35943e9df9ddd', '242f81dc97a01794',
    # old CC2 top path and via stub
    '30b490945c8f4c26', 'a7f7a0fb602c20fe', '1b29da7af4f30fa7',
    # old SDA via and its stubs/segments
    'dc2a69f47df68e15', '619027071e6a3123', '9234e302dab95202',
    '826dbd85981e55b1', '914ab5bba2c66878', '62c8f2d9a6385e8a',
]
print('==> delete old primitives')
e.delete(*ids)

# Step 3: reload after delete, then re-authorize
print('==> reload after delete')
e.reload()
print('==> reauthorize after delete')
e.reauthorize()

# Step 4: recreate CC2 via/stubs at lower y
print('==> create CC2 via and tracks')
via1 = e.create_via(4321.474, 2105, 'CC2')
# top path from J1 B5 down? actually pad is at y=2070.7, go up to 2105
e.create_track(4363.9, 2070.7, 4363.9, 2105, 'CC2', 6, 1)
e.create_track(4363.9, 2105, 4321.474, 2105, 'CC2', 6, 1)
# bottom vertical from via down to existing bottom horizontal y=2130
e.create_track(4321.474, 2105, 4321.474, 2130, 'CC2', 10, 2)

# Step 5: reload and check
print('==> reload')
e.reload()
print('==> check')
findings = e.check()
errors = [f for f in findings if f.get('level') == 'ERROR']
print(f'\nRemaining errors: {len(errors)}')
for err in errors:
    print(err['type'], err.get('at'), err.get('nets'))
