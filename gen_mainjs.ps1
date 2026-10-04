$path = "d:\my git\scratchpad\wt-overwatch-v6\js\main.js"
# Remove old file
Remove-Item $path -Force -ErrorAction SilentlyContinue

# Helper to write JS content
function Write-JS {
    param([string]$file)
    Add-Content -Path $file -Value "/* WT Overwatch v6 -- Tank Destroyer Fire Control System */" -Encoding utf8
    Add-Content -Path $file -Value "" -Encoding utf8
    Add-Content -Path $file -Value "// ===== SECTION 1: Physical Constants =====" -Encoding utf8
    Add-Content -Path $file -Value "const R2M = 6400 / (2 * Math.PI);" -Encoding utf8
    Add-Content -Path $file -Value "const GRAV = 9.81;" -Encoding utf8
    Add-Content -Path $file -Value "const AIR_DENSITY = 1.225;" -Encoding utf8
    Add-Content -Path $file -Value "const PEN_DISTS = Object.freeze([0, 500, 1000, 1500, 2000]);" -Encoding utf8
    Add-Content -Path $file -Value "const GRID_LABELS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';" -Encoding utf8
    Add-Content -Path $file -Value "const DRAG_MODEL = true;" -Encoding utf8
    Add-Content -Path $file -Value "const DRAG_STEP = 0.02;" -Encoding utf8
    Add-Content -Path $file -Value "const DRAG_CD = 0.25;" -Encoding utf8
    Add-Content -Path $file -Value "const MAX_ANGLE = 0.5;" -Encoding utf8
    Add-Content -Path $file -Value "const BISECT_ITERS = 24;" -Encoding utf8
    Add-Content -Path $file -Value "const DRAG_MACH = true;" -Encoding utf8
    Add-Content -Path $file -Value "const SOUND_SPEED = 340;" -Encoding utf8
    Add-Content -Path $file -Value "" -Encoding utf8
    Add-Content -Path $file -Value "const G1_MACH_TABLE = Object.freeze([" -Encoding utf8
    Add-Content -Path $file -Value "  [0.00, 1.00], [0.60, 1.00], [0.75, 1.03], [0.85, 1.10], [0.95, 1.25]," -Encoding utf8
    Add-Content -Path $file -Value "  [1.00, 1.38], [1.05, 1.75], [1.10, 1.92], [1.15, 1.88], [1.20, 1.80]," -Encoding utf8
    Add-Content -Path $file -Value "  [1.35, 1.62], [1.50, 1.48], [1.75, 1.36], [2.00, 1.26], [2.50, 1.16]," -Encoding utf8
    Add-Content -Path $file -Value "  [3.00, 1.08], [4.00, 1.00], [5.00, 0.94]" -Encoding utf8
    Add-Content -Path $file -Value "]);" -Encoding utf8
    Add-Content -Path $file -Value "" -Encoding utf8
    Add-Content -Path $file -Value "// ===== SECTION 2: Ammunition Database (17 vehicles) =====" -Encoding utf8
    Add-Content -Path $file -Value "const AMMO_DB = {" -Encoding utf8
    Add-Content -Path $file -Value "  'ISU-152':{gun:'152mm ML-20S',br:'4.7',nation:'CN',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'BR-540B APHEBC',v0:600,mass:48.8,pen:[171,160,150,141,133],sigma:0.35,type:'APHEBC',tnt:0.66}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'OF-540 HE',v0:655,mass:43.6,pen:[49,49,49,49,49],sigma:0.40,type:'HE',tnt:5.9}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'BP-540 HEAT',v0:500,mass:27.4,pen:[250,250,250,250,250],sigma:0.35,type:'HEAT',tnt:0}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'BR-540 APHE',v0:600,mass:48.8,pen:[170,161,152,144,136],sigma:0.35,type:'APHE',tnt:0.66}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'PLZ83':{gun:'152mm PL66',br:'6.3',nation:'CN',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'D-15 APHE',v0:655,mass:49,pen:[170,162,152,143,134],sigma:0.35,type:'APHE',tnt:0.7}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'D-15 HE',v0:655,mass:43,pen:[49,49,49,49,49],sigma:0.40,type:'HE',tnt:6}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'BP-540 HEAT',v0:500,mass:27.4,pen:[250,250,250,250,250],sigma:0.35,type:'HEAT',tnt:0}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'D-15 SMOKE',v0:655,mass:43,pen:[0,0,0,0,0],sigma:0.40,type:'SMOKE',tnt:0}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'PLZ05':{gun:'155mm PLZ52 L/52',br:'8.0',nation:'CN',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'HE',v0:940,mass:45,pen:[62,62,62,62,62],sigma:0.30,type:'HE',tnt:9}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'HE-VT',v0:940,mass:45,pen:[62,62,62,62,62],sigma:0.30,type:'HE-VT',tnt:9}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'HE-ERFB',v0:940,mass:45,pen:[62,62,62,62,62],sigma:0.35,type:'HE-ERFB',tnt:9}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'SMOKE',v0:940,mass:45,pen:[0,0,0,0,0],sigma:0.30,type:'SMOKE',tnt:0}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'M55':{gun:'203mm M47',br:'6.7',nation:'CN',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'M106 HE',v0:680,mass:104,pen:[88,88,88,88,88],sigma:0.45,type:'HE',tnt:23}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'M8 HMC':{gun:'75mm M1A1',br:'1.3',nation:'CN',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'M48 HE',v0:381,mass:6.3,pen:[10,10,10,10,10],sigma:0.50,type:'HE',tnt:0.7}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'M66 HEAT',v0:381,mass:6.2,pen:[51,44,38,33,28],sigma:0.45,type:'HEAT',tnt:0}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'SU-76M':{gun:'76mm ZiS-3',br:'2.3',nation:'CN',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'BR-350A APHE',v0:662,mass:6.3,pen:[67,60,52,44,37],sigma:0.38,type:'APHE',tnt:0.15}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'OF-350M HE',v0:680,mass:6.2,pen:[13,13,13,13,13],sigma:0.40,type:'HE',tnt:0.62}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'PLZ83-130':{gun:'130mm Type 59',br:'6.0',nation:'CN',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Type 59 APHE',v0:900,mass:33,pen:[180,165,148,132,118],sigma:0.30,type:'APHE',tnt:0.2}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Type 59 HE',v0:900,mass:33,pen:[35,35,35,35,35],sigma:0.32,type:'HE',tnt:3.6}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'M10 GMC':{gun:'105mm Type 91',br:'3.3',nation:'CN',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'T-29 HE',v0:400,mass:15,pen:[40,40,40,40,40],sigma:0.38,type:'HE',tnt:2.5}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'T-33 APHE',v0:400,mass:15,pen:[155,142,128,115,102],sigma:0.30,type:'APHE',tnt:0.5}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'Ho-Ro':{gun:'150mm Type 38',br:'1.3',nation:'JP',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Type 95 APHE',v0:280,mass:36,pen:[38,37,35,33,31],sigma:0.45,type:'APHE',tnt:0.5}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Type 92 HE',v0:280,mass:36,pen:[58,58,58,58,58],sigma:0.45,type:'HE',tnt:8.2}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'Dicker Max':{gun:'105mm K.18',br:'3.7',nation:'DE',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'PzGr APHE',v0:695,mass:15,pen:[155,144,133,123,114],sigma:0.30,type:'APHE',tnt:0.17}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Gr.19 HE',v0:695,mass:15,pen:[23,23,23,23,23],sigma:0.38,type:'HE',tnt:1.7}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Pzgr.rot APCBC',v0:720,mass:15,pen:[187,173,159,147,136],sigma:0.28,type:'APCBC',tnt:0.17}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'Sturmpanzer II':{gun:'150mm sIG 33',br:'2.3',nation:'DE',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Gr 38 HL HEAT',v0:240,mass:38,pen:[75,75,75,75,75],sigma:0.45,type:'HEAT',tnt:0}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Gr 19 HE',v0:240,mass:38,pen:[58,58,58,58,58],sigma:0.45,type:'HE',tnt:8.6}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'Brummbar':{gun:'150mm StuH 43',br:'4.3',nation:'DE',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Gr 38 HL HEAT',v0:280,mass:38,pen:[75,75,75,75,75],sigma:0.45,type:'HEAT',tnt:0}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Gr 19 HE',v0:280,mass:38,pen:[58,58,58,58,58],sigma:0.45,type:'HE',tnt:8.6}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'Sturer Emil':{gun:'128mm K.40',br:'4.7',nation:'DE',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'PzGr 43 APCBC',v0:880,mass:26.4,pen:[250,238,220,200,180],sigma:0.25,type:'APCBC',tnt:0.36}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Gr 39 HL HEAT',v0:720,mass:27.4,pen:[200,200,200,200,200],sigma:0.28,type:'HEAT',tnt:0}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'M109A1':{gun:'155mm M185',br:'6.0',nation:'US',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'M107 HE',v0:564,mass:43,pen:[58,58,58,58,58],sigma:0.40,type:'HE',tnt:7}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'M454 HEAT',v0:500,mass:27.4,pen:[200,200,200,200,200],sigma:0.35,type:'HEAT',tnt:0}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'M825 SMOKE',v0:564,mass:43,pen:[0,0,0,0,0],sigma:0.40,type:'SMOKE',tnt:0}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'Type 75 SPH':{gun:'155mm JSW L/30',br:'6.3',nation:'JP',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Type 75 HE',v0:560,mass:43,pen:[58,58,58,58,58],sigma:0.40,type:'HE',tnt:7.5}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'Type 75 HE-VT',v0:560,mass:43,pen:[58,58,58,58,58],sigma:0.38,type:'HE-VT',tnt:7.5}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  '2S3M':{gun:'152mm 2A33',br:'6.3',nation:'RU',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'OF-540 HE',v0:655,mass:43.6,pen:[49,49,49,49,49],sigma:0.40,type:'HE',tnt:5.9}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'3OF25 HE',v0:670,mass:43,pen:[62,62,62,62,62],sigma:0.38,type:'HE',tnt:6}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'BP-540 HEAT',v0:500,mass:27.4,pen:[250,250,250,250,250],sigma:0.35,type:'HEAT',tnt:0}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'BR-540B APHEBC',v0:600,mass:48.8,pen:[171,160,150,141,133],sigma:0.35,type:'APHEBC',tnt:0.66}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}," -Encoding utf8
    Add-Content -Path $file -Value "  'G6 Rhino':{gun:'155mm G5 L/45',br:'7.3',nation:'UK',shells:[" -Encoding utf8
    Add-Content -Path $file -Value "    {name:'M1 HE',v0:897,mass:45,pen:[62,62,62,62,62],sigma:0.38,type:'HE',tnt:9}," -Encoding utf8
    Add-Content -Path $file -Value "    {name:'M1 HE-ERFB',v0:937,mass:45,pen:[58,58,58,58,58],sigma:0.35,type:'HE-ERFB',tnt:9}" -Encoding utf8
    Add-Content -Path $file -Value "  ]}" -Encoding utf8
    Add-Content -Path $file -Value "};" -Encoding utf8
}

Write-JS $path
Write-Host "main.js part 1 written"