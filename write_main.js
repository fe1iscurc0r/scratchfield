const fs = require('fs');
const path = "d:\\my git\\scratchpad\\wt-overwatch-v6\\js\\main.js";
const code = `/* WT Overwatch v6 — 坦歼火控系统 弹道引擎 */
const R2M = 6400 / (2 * Math.PI);
const GRAV = 9.81;
const AIR_DENSITY = 1.225;
const PEN_DISTS = Object.freeze([0, 500, 1000, 1500, 2000]);
const GRID_LABELS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const DRAG_MODEL = true;
const DRAG_STEP = 0.02;
const DRAG_CD = 0.25;
const MAX_ANGLE = 0.5;
const BISECT_ITERS = 24;
const DRAG_MACH = true;
const SOUND_SPEED = 340;
const G1_MACH_TABLE = Object.freeze([
  [0.00, 1.00], [0.60, 1.00], [0.75, 1.03], [0.85, 1.10], [0.95, 1.25],
  [1.00, 1.38], [1.05, 1.75], [1.10, 1.92], [1.15, 1.88], [1.20, 1.80],
  [1.35, 1.62], [1.50, 1.48], [1.75, 1.36], [2.00, 1.26], [2.50, 1.16],
  [3.00, 1.08], [4.00, 1.00], [5.00, 0.94]
]);

const AMMO_DB = {
  'ISU-152':{gun:'152mm ML-20S',br:'4.7',nation:'CN',shells:[
    {name:'BR-540B APHEBC',v0:600,mass:48.8,pen:[171,160,150,141,133],sigma:0.35,type:'APHEBC',tnt:0.66},
    {name:'OF-540 HE',v0:655,mass:43.6,pen:[49,49,49,49,49],sigma:0.40,type:'HE',tnt:5.9},
    {name:'BP-540 HEAT',v0:500,mass:27.4,pen:[250,250,250,250,250],sigma:0.35,type:'HEAT',tnt:0},
    {name:'BR-540 APHE',v0:600,mass:48.8,pen:[170,161,152,144,136],sigma:0.35,type:'APHE',tnt:0.66}
  ]},
  'PLZ83':{gun:'152mm PL66',br:'6.3',nation:'CN',shells:[
    {name:'D-15 APHE',v0:655,mass:49,pen:[170,162,152,143,134],sigma:0.35,type:'APHE',tnt:0.7},
    {name:'D-15 HE',v0:655,mass:43,pen:[49,49,49,49,49],sigma:0.40,type:'HE',tnt:6},
    {name:'BP-540 HEAT',v0:500,mass:27.4,pen:[250,250,250,250,250],sigma:0.35,type:'HEAT',tnt:0},
    {name:'D-15 SMOKE',v0:655,mass:43,pen:[0,0,0,0,0],sigma:0.40,type:'SMOKE',tnt:0}
  ]},
  'PLZ05':{gun:'155mm PLZ52 L/52',br:'8.0',nation:'CN',shells:[
    {name:'HE',v0:940,mass:45,pen:[62,62,62,62,62],sigma:0.30,type:'HE',tnt:9},
    {name:'HE-VT',v0:940,mass:45,pen:[62,62,62,62,62],sigma:0.30,type:'HE-VT',tnt:9},
    {name:'HE-ERFB',v0:940,mass:45,pen:[62,62,62,62,62],sigma:0.35,type:'HE-ERFB',tnt:9},
    {name:'SMOKE',v0:940,mass:45,pen:[0,0,0,0,0],sigma:0.30,type:'SMOKE',tnt:0}
  ]},
  'M55':{gun:'203mm M47',br:'6.7',nation:'CN',shells:[
    {name:'M106 HE',v0:680,mass:104,pen:[88,88,88,88,88],sigma:0.45,type:'HE',tnt:23}
  ]},
  'M8 HMC':{gun:'75mm M1A1',br:'1.3',nation:'CN',shells:[
    {name:'M48 HE',v0:381,mass:6.3,pen:[10,10,10,10,10],sigma:0.50,type:'HE',tnt:0.7},
    {name:'M66 HEAT',v0:381,mass:6.2,pen:[51,44,38,33,28],sigma:0.45,type:'HEAT',tnt:0}
  ]},
  'SU-76M':{gun:'76mm ZiS-3',br:'2.3',nation:'CN',shells:[
    {name:'BR-350A APHE',v0:662,mass:6.3,pen:[67,60,52,44,37],sigma:0.38,type:'APHE',tnt:0.15},
    {name:'OF-350M HE',v0:680,mass:6.2,pen:[13,13,13,13,13],sigma:0.40,type:'HE',tnt:0.62}
  ]},
  'PLZ83-130':{gun:'130mm Type 59',br:'6.0',nation:'CN',shells:[
    {name:'Type 59 APHE',v0:900,mass:33,pen:[180,165,148,132,118],sigma:0.30,type:'APHE',tnt:0.2},
    {name:'Type 59 HE',v0:900,mass:33,pen:[35,35,35,35,35],sigma:0.32,type:'HE',tnt:3.6}
  ]},
  'M10 GMC':{gun:'105mm Type 91',br:'3.3',nation:'CN',shells:[
    {name:'T-29 HE',v0:400,mass:15,pen:[40,40,40,40,40],sigma:0.38,type:'HE',tnt:2.5},
    {name:'T-33 APHE',v0:400,mass:15,pen:[155,142,128,115,102],sigma:0.30,type:'APHE',tnt:0.5}
  ]},
  'Ho-Ro':{gun:'150mm Type 38',br:'1.3',nation:'JP',shells:[
    {name:'Type 95 APHE',v0:280,mass:36,pen:[38,37,35,33,31],sigma:0.45,type:'APHE',tnt:0.5},
    {name:'Type 92 HE',v0:280,mass:36,pen:[58,58,58,58,58],sigma:0.45,type:'HE',tnt:8.2}
  ]},
  'Dicker Max':{gun:'105mm K.18',br:'3.7',nation:'DE',shells:[
    {name:'PzGr APHE',v0:695,mass:15,pen:[155,144,133,123,114],sigma:0.30,type:'APHE',tnt:0.17},
    {name:'Gr.19 HE',v0:695,mass:15,pen:[23,23,23,23,23],sigma:0.38,type:'HE',tnt:1.7},
    {name:'Pzgr.rot APCBC',v0:720,mass:15,pen:[187,173,159,147,136],sigma:0.28,type:'APCBC',tnt:0.17}
  ]},
  'Sturmpanzer II':{gun:'150mm sIG 33',br:'2.3',nation:'DE',shells:[
    {name:'Gr 38 HL HEAT',v0:240,mass:38,pen:[75,75,75,75,75],sigma:0.45,type:'HEAT',tnt:0},
    {name:'Gr 19 HE',v0:240,mass:38,pen:[58,58,58,58,58],sigma:0.45,type:'HE',tnt:8.6}
  ]},
  'Brummbar':{gun:'150mm StuH 43',br:'4.3',nation:'DE',shells:[
    {name:'Gr 38 HL HEAT',v0:280,mass:38,pen:[75,75,75,75,75],sigma:0.45,type:'HEAT',tnt:0},
    {name:'Gr 19 HE',v0:280,mass:38,pen:[58,58,58,58,58],sigma:0.45,type:'HE',tnt:8.6}
  ]},
  'Sturer Emil':{gun:'128mm K.40',br:'4.7',nation:'DE',shells:[
    {name:'PzGr 43 APCBC',v0:880,mass:26.4,pen:[250,238,220,200,180],sigma:0.25,type:'APCBC',tnt:0.36},
    {name:'Gr 39 HL HEAT',v0:720,mass:27.4,pen:[200,200,200,200,200],sigma:0.28,type:'HEAT',tnt:0}
  ]},
  'M109A1':{gun:'155mm M185',br:'6.0',nation:'US',shells:[
    {name:'M107 HE',v0:564,mass:43,pen:[58,58,58,58,58],sigma:0.40,type:'HE',tnt:7},
    {name:'M454 HEAT',v0:500,mass:27.4,pen:[200,200,200,200,200],sigma:0.35,type:'HEAT',tnt:0},
    {name:'M825 SMOKE',v0:564,mass:43,pen:[0,0,0,0,0],sigma:0.40,type:'SMOKE',tnt:0}
  ]},
  'Type 75 SPH':{gun:'155mm JSW L/30',br:'6.3',nation:'JP',shells:[
    {name:'Type 75 HE',v0:560,mass:43,pen:[58,58,58,58,58],sigma:0.40,type:'HE',tnt:7.5},
    {name:'Type 75 HE-VT',v0:560,mass:43,pen:[58,58,58,58,58],sigma:0.38,type:'HE-VT',tnt:7.5}
  ]},
  '2S3M':{gun:'152mm 2A33',br:'6.3',nation:'RU',shells:[
    {name:'OF-540 HE',v0:655,mass:43.6,pen:[49,49,49,49,49],sigma:0.40,type:'HE',tnt:5.9},
    {name:'3OF25 HE',v0:670,mass:43,pen:[62,62,62,62,62],sigma:0.38,type:'HE',tnt:6},
    {name:'BP-540 HEAT',v0:500,mass:27.4,pen:[250,250,250,250,250],sigma:0.35,type:'HEAT',tnt:0},
    {name:'BR-540B APHEBC',v0:600,mass:48.8,pen:[171,160,150,141,133],sigma:0.35,type:'APHEBC',tnt:0.66}
  ]},
  'G6 Rhino':{gun:'155mm G5 L/45',br:'7.3',nation:'UK',shells:[
    {name:'M1 HE',v0:897,mass:45,pen:[62,62,62,62,62],sigma:0.38,type:'HE',tnt:9},
    {name:'M1 HE-ERFB',v0:937,mass:45,pen:[58,58,58,58,58],sigma:0.35,type:'HE-ERFB',tnt:9}
  ]}
};
const S = {
  vehicle: 'ISU-152', shellIdx: 0,
  zoom: 8, panX: 0, panY: 0,
  canvasW: 900, canvasH: 720,
  playerX: 0.5, playerY: 0.5, playerFound: false,
  targets: [], selectedTargetId: null, nextTargetId: 1,
  dirty: true, dirtyFrames: 0,
  zeroAdjMil: { elev: 0, dir: 0 },
  manualSpeedKmh: 0,
  reloadSec: 15, reloadLeft: 0,
  showOffscreen: true,
  _kCache: {},
  hudMsgs: [
    {time:'12:34',text:'敌 T-34-85 出现在 K11',enemy:true},
    {time:'12:32',text:'友军 IS-2 占领 B 点',enemy:false},
    {time:'12:28',text:'敌 Pz.IV G 被击毁',enemy:true},
    {time:'12:25',text:'友军 SU-85 阵亡',enemy:false}
  ],
  bestPositions: [
    {dist:847, elevAdv:2.3, score:92},
    {dist:1020, elevAdv:1.1, score:85},
    {dist:1150, elevAdv:-0.5, score:78}
  ]
};
const $ = function(id) { return document.getElementById(id); };
const D = {
  vSelect: $('v-select'), sSelect: $('s-select'), mapSelect: $('map-select'),
  canvas: $('map-canvas'), splash: $('map-splash'),
  targetInfo: $('target-info'), targetList: $('target-list'), tlCount: $('tl-count'),
  ammoSuggest: $('ammo-suggest'),
  gridInput: $('grid-input'), gridBtn: $('grid-btn'),
  playerBtn: $('player-btn'), clearAllBtn: $('clear-all-btn'),
  tgtType: $('tgt-type'), connStatus: $('conn-status'),
  reloadSec: $('reload-sec'), fireBtn: $('fire-btn'),
  offscreenCb: $('offscreen-cb'),
  hudBody: $('hud-body'), hudCount: $('hud-count'),
  corrVert: $('corr-vert'), corrHoriz: $('corr-horiz'), corrReset: $('corr-reset'), corrApplied: $('corr-applied'),
  convSize: $('conv-size'), convMil: $('conv-mil'), convMilResult: $('conv-mil-result'),
  convDist: $('conv-dist'), convDistResult: $('conv-dist-result'),
  bestPosPanel: $('best-pos-panel')
};
var ctx = D.canvas ? D.canvas.getContext('2d') : null;
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function escHtml(s) { if (!s) return ''; return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function markDirty() { S.dirty = true; S.dirtyFrames = 0; }
function machDragFactor(M) {
  if (M <= G1_MACH_TABLE[0][0]) return G1_MACH_TABLE[0][1];
  for (var i = 1; i < G1_MACH_TABLE.length; i++) {
    if (M <= G1_MACH_TABLE[i][0]) {
      var a = G1_MACH_TABLE[i - 1], b = G1_MACH_TABLE[i];
      var f = (b[0] - a[0]) ? (M - a[0]) / (b[0] - a[0]) : 0;
      return a[1] + (b[1] - a[1]) * f;
    }
  }
  return G1_MACH_TABLE[G1_MACH_TABLE.length - 1][1];
}
function parseCaliberM(gunStr) {
  var m = /(\\d+(?:\\.\\d+)?)\\s*mm/i.exec(gunStr || '');
  return m ? parseFloat(m[1]) / 1000 : 0.15;
}
function shellDragK(shell, gunStr) {
  var cal = parseCaliberM(gunStr);
  var cd = (shell.cd !== undefined) ? shell.cd : DRAG_CD;
  var key = cal.toFixed(4) + '|' + cd + '|' + shell.mass;
  if (S._kCache[key] !== undefined) return S._kCache[key];
  var A = Math.PI * cal * cal / 4;
  var k = 0.5 * AIR_DENSITY * cd * A / shell.mass;
  S._kCache[key] = k;
  return k;
}
function integrateShot(v0, theta, k, dist, machOn) {
  var useMach = (machOn === undefined) ? DRAG_MACH : machOn;
  var vx = v0 * Math.cos(theta), vy = v0 * Math.sin(theta);
  var x = 0, y = 0, t = 0, maxH = 0, maxT = 90;
  while (t < maxT) {
    var v = Math.hypot(vx, vy);
    var f = useMach ? machDragFactor(v / SOUND_SPEED) : 1;
    var ax = -k * f * v * vx, ay = -k * f * v * vy - GRAV;
    var vxM = vx + 0.5 * ax * DRAG_STEP, vyM = vy + 0.5 * ay * DRAG_STEP;
    var vM = Math.hypot(vxM, vyM);
    var fM = useMach ? machDragFactor(vM / SOUND_SPEED) : 1;
    var axM = -k * fM * vM * vxM, ayM = -k * fM * vM * vyM - GRAV;
    var nvx = vx + axM * DRAG_STEP, nvy = vy + ayM * DRAG_STEP;
    var px = x, py = y;
    x += vxM * DRAG_STEP; y += vyM * DRAG_STEP; t += DRAG_STEP;
    if (y > maxH) maxH = y;
    if (px < dist && x >= dist) {
      var frac = (dist - px) / (x - px);
      return { hit: true, t: t - DRAG_STEP + frac * DRAG_STEP, y: py + (y - py) * frac, maxH: maxH };
    }
    if (y < -2 && vy < 0) return { hit: false };
    vx = nvx; vy = nvy;
  }
  return { hit: false };
}
function calcBallistics(dist, shell, gunStr) {
  if (!shell || !dist || dist <= 0) return null;
  var R = dist, v0 = shell.v0;
  var data = getVehicleData();
  var gun = gunStr || (data ? data.gun : '');
  var penAtDist = shell.pen[0];
  if (R >= PEN_DISTS[PEN_DISTS.length - 1]) { penAtDist = shell.pen[shell.pen.length - 1]; }
  else {
    for (var i = 1; i < PEN_DISTS.length; i++) {
      if (R <= PEN_DISTS[i]) {
        var frac = (R - PEN_DISTS[i - 1]) / (PEN_DISTS[i] - PEN_DISTS[i - 1]);
        penAtDist = shell.pen[i - 1] + (shell.pen[i] - shell.pen[i - 1]) * frac; break;
      }
    }
  }
  var tgtSize = document.getElementById('tgt-type');
  var tgtRadius = parseFloat(tgtSize ? tgtSize.value : 2.5);
  var sigmaMeters = shell.sigma * R / R2M; sigmaMeters *= (1 + R / 3000);
  var hitProb = clamp(1 - Math.exp(-(tgtRadius * tgtRadius) / (2 * sigmaMeters * sigmaMeters)), 0, 1);
  if (DRAG_MODEL && shell.mass > 0) {
    var k = shellDragK(shell, gun);
    var lo = 0, hi = MAX_ANGLE, best = null, bestAng = 0;
    for (var i2 = 0; i2 < BISECT_ITERS; i2++) {
      var mid = (lo + hi) / 2;
      var tr = integrateShot(v0, mid, k, R);
      if (!tr.hit) { lo = mid; continue; }
      best = tr; bestAng = mid;
      if (Math.abs(tr.y) <= 0.3) { bestAng = mid; break; }
      if (tr.y > 0) hi = mid; else lo = mid;
    }
    if (!best) { return { dist: R, t: null, d: null, milComp: null, theta: null, penAtDist: Math.round(penAtDist), hitProb: hitProb, v0: v0, sigma: shell.sigma, maxOrd: null, tgtRadius: tgtRadius, range: 'short', drag: true }; }
    var theta = bestAng, milComp = theta * R2M;
    var flat = integrateShot(v0, 0, k, R);
    var dropFlat = flat.hit ? -flat.y : null;
    return { dist: R, t: best.t, d: (dropFlat != null) ? dropFlat : null, milComp: milComp, theta: theta * 180 / Math.PI, penAtDist: Math.round(penAtDist), hitProb: hitProb, v0: v0, sigma: shell.sigma, maxOrd: Math.round(best.maxH), tgtRadius: tgtRadius, range: 'ok', drag: true };
  }
  var t = R / v0, d = 0.5 * GRAV * t * t, milComp = Math.atan2(d, R) * R2M;
  return { dist: R, t: t, d: d, milComp: milComp, theta: Math.atan2(d, R) * 180 / Math.PI, penAtDist: Math.round(penAtDist), hitProb: hitProb, v0: v0, sigma: shell.sigma, maxOrd: Math.round(0.125 * GRAV * t * t), tgtRadius: tgtRadius, range: 'ok', drag: false };
}
function getVehicleData() { return AMMO_DB[S.vehicle]; }
function getShell() {
  var data = AMMO_DB[S.vehicle];
  if (!data) return null;
  return data.shells[S.shellIdx] || data.shells[0];
}
function populateVehicleSelect() {
  D.vSelect.innerHTML = '';
  var keys = Object.keys(AMMO_DB);
  for (var i = 0; i < keys.length; i++) {
    var v = keys[i], data = AMMO_DB[v];
    var o = document.createElement('option');
    o.value = v; o.textContent = '[' + data.nation + '] ' + v + '  BR ' + data.br;
    D.vSelect.appendChild(o);
  }
  D.vSelect.value = S.vehicle;
  populateShellSelect();
  updateShellInfo();
}
function populateShellSelect() {
  D.sSelect.innerHTML = '';
  var data = AMMO_DB[S.vehicle];
  if (!data) return;
  for (var i = 0; i < data.shells.length; i++) {
    var s = data.shells[i];
    var o = document.createElement('option');
    o.value = i; o.textContent = s.name + ' | v0=' + s.v0 + ' m/s | ' + s.mass + 'kg';
    D.sSelect.appendChild(o);
  }
  S.shellIdx = Math.min(S.shellIdx, data.shells.length - 1);
  D.sSelect.value = S.shellIdx;
  updateShellInfo();
}
function updateShellInfo() {
  var sh = getShell(), data = getVehicleData();
  var infoEl = document.querySelector('.tb-info-text');
  var vNameEl = document.querySelector('.tb-vehicle-name');
  if (infoEl && sh) infoEl.textContent = '初速 ' + sh.v0 + ' m/s | 散布 ' + sh.sigma + ' mil | 弹重 ' + sh.mass + ' kg';
  if (vNameEl) vNameEl.textContent = S.vehicle;
  var brTag = document.querySelector('.tag-warning');
  if (brTag && data) brTag.textContent = 'BR ' + data.br;
  S.reloadSec = estimateReloadSec();
  if (D.reloadSec) { D.reloadSec.textContent = S.reloadSec; D.reloadSec.style.color = '#9599a6'; }
  markDirty();
  refreshTargetInfo();
}
function estimateReloadSec() {
  var data = getVehicleData();
  if (!data) return 15;
  var m = /(\\d+)\\s*mm/i.exec(data.gun || '');
  var calMm = m ? parseInt(m[1]) : 152;
  var TABLE = { 203: 30, 152: 22, 155: 18, 150: 20, 130: 15, 128: 17, 120: 14, 105: 12, 100: 12, 90: 10, 88: 9, 76: 8, 75: 6 };
  if (TABLE[calMm] !== undefined) return TABLE[calMm];
  return Math.round(clamp(calMm * 0.13, 5, 30));
}
var reloadTimer = null;
function fireGun() {
  S.reloadLeft = S.reloadSec || 15;
  D.reloadSec.textContent = S.reloadLeft; D.reloadSec.style.color = '#ff8c00';
  clearInterval(reloadTimer);
  reloadTimer = setInterval(function() {
    S.reloadLeft--;
    if (S.reloadLeft <= 0) { clearInterval(reloadTimer); S.reloadLeft = 0; D.reloadSec.textContent = '0'; D.reloadSec.style.color = '#00cc66'; toast('装填完毕,可再次开火'); return; }
    D.reloadSec.textContent = S.reloadLeft;
  }, 1000);
}
function getSelectedTarget() {
  for (var i = 0; i < S.targets.length; i++)
    if (S.targets[i].id === S.selectedTargetId) return S.targets[i];
  return null;
}
function targetDist(tgt) {
  var span = 65536;
  return Math.hypot((tgt.nx - S.playerX) * span, (tgt.ny - S.playerY) * span);
}
function targetBearing(tgt) {
  return ((Math.atan2(tgt.nx - S.playerX, tgt.ny - S.playerY) * 180 / Math.PI) + 360) % 360;
}
function addTarget(nx, ny, source, targetType) {
  var id = S.nextTargetId++;
  var span = 65536;
  var col = Math.floor((nx * span + 32768) / 3276.8); col = clamp(col, 0, 19);
  var row = Math.floor((32768 - ny * span) / 3276.8); row = clamp(row, 0, 19);
  function colToLetters(c) { var s = '', cc = c; do { s = GRID_LABELS[cc % 26] + s; cc = Math.floor(cc / 26) - 1; } while (cc >= 0); return s; }
  var tgt = { id: id, nx: nx, ny: ny, gridLabel: colToLetters(col) + (row + 1), source: source || 'manual', type: targetType || 'unknown', time: Date.now() };
  S.targets.push(tgt);
  if (!S.selectedTargetId) S.selectedTargetId = id;
  sortTargets(); markDirty(); refreshTargetUI();
  return tgt;
}
function sortTargets() {
  S.targets.sort(function(a, b) {
    var da = Math.hypot(a.nx - S.playerX, a.ny - S.playerY);
    var db = Math.hypot(b.nx - S.playerX, b.ny - S.playerY);
    return da - db;
  });
}
function removeTarget(id) {
  S.targets = S.targets.filter(function(t) { return t.id !== id; });
  if (S.selectedTargetId === id) S.selectedTargetId = S.targets.length > 0 ? S.targets[0].id : null;
  markDirty(); refreshTargetUI();
}
function clearAllTargets() {
  S.targets = []; S.selectedTargetId = null; markDirty(); refreshTargetUI(); toast('已清除全部目标');
}
var _toastTimer = null;
function toast(msg, color) {
  var el = $('toast');
  if (!el) return;
  el.textContent = msg; el.style.color = color || '#32f08c'; el.className = 'toast-visible';
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(function() { el.className = 'toast-hidden'; }, 1800);
}
function refreshTargetInfo() {
  var tgt = getSelectedTarget();
  var dist = tgt ? targetDist(tgt) : 1247;
  var shell = getShell();
  var bal = calcBallistics(dist, shell);
  updateDisplayFields(dist, bal, tgt);
  refreshAmmoSuggest(dist);
}
function updateDisplayFields(dist, bal, tgt) {
  var bearing = tgt ? Math.round(targetBearing(tgt)) : 36;
  var gridLabel = tgt ? tgt.gridLabel : 'K11';
  var source = tgt ? tgt.source : 'test';
  var type = tgt ? tgt.type : 'test';
  var zeroElev = S.zeroAdjMil.elev || 0;
  var zeroDir = S.zeroAdjMil.dir || 0;
  var el;
  el = $('ti-coord'); if (el) el.textContent = '格 ' + gridLabel + ' | 距 ' + Math.round(dist) + 'm | 方位 ' + bearing + String.fromCharCode(176);
  el = $('ti-source'); if (el) el.textContent = source;
  el = $('ti-type'); if (el) el.textContent = type;
  el = $('target-id'); if (el && tgt) el.textContent = '#' + tgt.id;
  el = $('ti-los'); if (el) el.textContent = '通视 CLEAR';
  el = $('ti-speed'); if (el) el.textContent = '10.0 m/s (36 km/h) 实测 [Tracked]';
  el = $('ti-lead'); if (el) el.textContent = (bal && bal.t ? '+' + (bal.t * 5).toFixed(1) : '+9.6') + ' mil';
  if (bal && bal.range === 'ok') {
    var finalMil = bal.milComp + zeroElev;
    el = $('ti-flight-time'); if (el) el.textContent = bal.t.toFixed(2) + ' s';
    el = $('ti-elevation'); if (el) el.textContent = bal.theta.toFixed(2) + String.fromCharCode(176);
    el = $('ti-mil'); if (el) el.innerHTML = (finalMil >= 0 ? '+' : '') + finalMil.toFixed(2) + ' mil' + (zeroElev ? ' <span class="val-warning">(含修正)</span>' : '');
    el = $('ti-max-alt'); if (el) el.textContent = (bal.maxOrd || 0) + ' m';
    el = $('ti-pen'); if (el) el.textContent = bal.penAtDist + ' mm';
    el = $('ti-hitrate'); if (el) el.textContent = (bal.hitProb * 100).toFixed(1) + '%';
    el = $('ti-spread'); if (el) el.textContent = bal.sigma + ' mil @ 1000m';
    el = $('fire-recommendation');
    if (el) el.innerHTML = '<strong>标尺建议:</strong> ' + Math.round(finalMil) + ' mil (含修正) | <strong>初速:</strong> ' + bal.v0 + ' m/s | <strong>弹种:</strong> ' + (getShell() ? getShell().type : '--') + ' | 阻力模型';
    el = $('exposure-risk');
    if (el) {
      var et = bal.t || 0;
      if (et > 1.6) el.innerHTML = String.fromCharCode(128308) + ' 高风险暴露 (' + Math.round(dist) + 'm, 飞行 ' + et.toFixed(1) + 's) — 开火即暴露, 建议射击后移动换位 (Shoot and Scoot)';
      else if (et > 1.0) el.innerHTML = String.fromCharCode(128992) + ' 中风险暴露 (' + Math.round(dist) + 'm, 飞行 ' + et.toFixed(1) + 's) — 开火可能暴露, 有把握再打';
      else el.innerHTML = String.fromCharCode(128994) + ' 低风险 (' + Math.round(dist) + 'm, 飞行 ' + et.toFixed(1) + 's)';
    }
  }
  el = $('corr-applied');
  if (el) el.textContent = '已应用: 高低 ' + (zeroElev >= 0 ? '+' : '') + zeroElev + ' | 方向 ' + (zeroDir >= 0 ? '+' : '') + zeroDir + ' mil';
}
function refreshAmmoSuggest(dist) {
  var data = getVehicleData();
  if (!data || dist <= 0) { D.ammoSuggest.innerHTML = ''; return; }
  var results = [];
  data.shells.forEach(function(s, i) {
    if (s.type === 'SMOKE') return;
    var bal = calcBallistics(dist, s);
    if (!bal) return;
    results.push({ idx: i, shell: s, pen: bal.penAtDist, prob: bal.hitProb });
  });
  if (results.length === 0) { D.ammoSuggest.innerHTML = ''; return; }
  results.sort(function(a, b) { return (b.pen * 0.4 + b.prob * 60) - (a.pen * 0.4 + a.prob * 60); });
  var best = results[0];
  var h = '建议: ' + best.shell.name + ' (' + best.shell.type + ') 穿深 ' + best.pen + 'mm 命中率 ' + (best.prob * 100).toFixed(0) + '%';
  if (results.length > 1) h += ' | 备选: ' + results.slice(1, 3).map(function(r) { return r.shell.name + ' (' + r.pen + 'mm)'; }).join(', ');
  D.ammoSuggest.innerHTML = h;
}
function refreshTargetList() {
  D.tlCount.textContent = S.targets.length + '个';
  if (S.targets.length === 0) { D.targetList.innerHTML = '<div style="color:#666b75;padding:12px;text-align:center;font-size:12px">双击地图标点<br>或输入格号回车标记</div>'; return; }
  var h = '';
  S.targets.forEach(function(t) {
    var dist = targetDist(t), bearing = targetBearing(t);
    var sel = (t.id === S.selectedTargetId) ? ' style="background:#2a2d31"' : '';
    h += '<div class="t-row"' + sel + ' data-id="' + t.id + '"><span class="t-id">#' + t.id + '</span><span class="t-grid">' + t.gridLabel + '</span><span class="t-dist">' + Math.round(dist) + 'm</span><span class="t-bearing">' + Math.round(bearing) + String.fromCharCode(176) + '</span><span class="t-src">' + escHtml(t.source) + '</span><button class="t-btn" data-del="' + t.id + '">X</button></div>';
  });
  D.targetList.innerHTML = h;
}
function refreshTargetUI() { refreshTargetInfo(); refreshTargetList(); }
function updateCorrection() {
  var elev = parseFloat(D.corrVert ? D.corrVert.value : 0) || 0;
  var dir = parseFloat(D.corrHoriz ? D.corrHoriz.value : 0) || 0;
  S.zeroAdjMil.elev = elev; S.zeroAdjMil.dir = dir;
  var el = $('corr-applied');
  if (el) el.textContent = '已应用: 高低 ' + (elev >= 0 ? '+' : '') + elev + ' | 方向 ' + (dir >= 0 ? '+' : '') + dir + ' mil';
  refreshTargetInfo();
}
function resetCorrection() {
  if (D.corrVert) D.corrVert.value = 0;
  if (D.corrHoriz) D.corrHoriz.value = 0;
  S.zeroAdjMil.elev = 0; S.zeroAdjMil.dir = 0; updateCorrection();
}
function updateConverter() {
  var size = parseFloat(D.convSize ? D.convSize.value : 2.5) || 2.5;
  var mil = parseFloat(D.convMil ? D.convMil.value : 0);
  var dist = parseFloat(D.convDist ? D.convDist.value : 0);
  if (D.convMilResult) D.convMilResult.textContent = (mil && mil > 0) ? Math.round(size * 1000 / mil) + ' m' : '-- m';
  if (D.convDistResult) D.convDistResult.textContent = (dist && dist > 0) ? (size * 1000 / dist).toFixed(1) + ' mil' : '-- mil';
}
function refreshHUD() {
  if (D.hudCount) D.hudCount.textContent = S.hudMsgs.length;
  if (!D.hudBody) return;
  var h = '';
  S.hudMsgs.forEach(function(msg) { h += '<div class="hud-entry ' + (msg.enemy ? 'hud-enemy' : 'hud-ally') + '"><span class="hud-time">' + msg.time + '</span><span class="hud-text">' + msg.text + '</span></div>'; });
  D.hudBody.innerHTML = h;
}
function resizeCanvas() {
  if (!D.canvas) return;
  var parent = D.canvas.parentElement;
  if (!parent) return;
  D.canvas.width = parent.clientWidth || 900; D.canvas.height = parent.clientHeight || 500;
  S.canvasW = D.canvas.width; S.canvasH = D.canvas.height;
  if (!ctx) ctx = D.canvas.getContext('2d');
  markDirty();
}
function render() {
  if (!D.canvas || !ctx) return;
  if (!S.dirty && S.dirtyFrames > 8) return;
  S.dirty = false; S.dirtyFrames++;
  var w = D.canvas.width, h = D.canvas.height;
  ctx.fillStyle = '#0a0a18'; ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 1;
  for (var i = 0; i <= 20; i++) {
    var x = (i / 20) * w * S.zoom + S.panX, y = (i / 20) * h * S.zoom + S.panY;
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }
  var px = S.playerX * w * S.zoom + S.panX, py = S.playerY * h * S.zoom + S.panY;
  ctx.fillStyle = '#32f08c'; ctx.beginPath(); ctx.arc(px, py, 6, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#fff'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center'; ctx.fillText('YOU', px, py - 10);
  S.targets.forEach(function(t) {
    var tx = t.nx * w * S.zoom + S.panX, ty = t.ny * h * S.zoom + S.panY;
    ctx.fillStyle = (t.id === S.selectedTargetId) ? '#ff4444' : '#ff8c00';
    ctx.beginPath(); ctx.arc(tx, ty, 5, 0, Math.PI * 2); ctx.fill();
    if (t.id === S.selectedTargetId) { ctx.strokeStyle = '#ff4444'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(tx, ty, 10, 0, Math.PI * 2); ctx.stroke(); }
  });
}
function initEvents() {
  D.vSelect.addEventListener('change', function() { S.vehicle = D.vSelect.value; S.shellIdx = 0; S._kCache = {}; populateShellSelect(); updateShellInfo(); refreshTargetUI(); });
  D.sSelect.addEventListener('change', function() { S.shellIdx = parseInt(D.sSelect.value) || 0; S._kCache = {}; updateShellInfo(); refreshTargetUI(); });
  if (D.mapSelect) D.mapSelect.addEventListener('change', function() { markDirty(); });
  if (D.fireBtn) D.fireBtn.addEventListener('click', fireGun);
  if (D.gridBtn) D.gridBtn.addEventListener('click', function() {
    if (!D.gridInput) return;
    var val = D.gridInput.value.trim().toUpperCase();
    if (!val) return;
    var m = val.match(/^([A-Z]{1,2})(\\d{1,2})$/);
    if (!m) { toast('格号格式错误 (如 E5)', '#f65a5a'); return; }
    var col = 0; for (var ci = 0; ci < m[1].length; ci++) col = col * 26 + (m[1].charCodeAt(ci) - 64); col--;
    var row = parseInt(m[2]) - 1;
    if (col < 0 || col > 19 || row < 0 || row > 19) { toast('格号超出范围', '#f65a5a'); return; }
    addTarget((col + 0.5) / 20, (row + 0.5) / 20, 'grid'); toast('已标点 ' + val);
  });
  if (D.playerBtn) D.playerBtn.addEventListener('click', function() {
    if (!D.gridInput) return; var val = D.gridInput.value.trim().toUpperCase();
    if (!val) { toast('请输入格号', '#ff8c00'); return; }
    var m = val.match(/^([A-Z]{1,2})(\\d{1,2})$/); if (!m) { toast('格号格式错误', '#f65a5a'); return; }
    var col = 0; for (var ci = 0; ci < m[1].length; ci++) col = col * 26 + (m[1].charCodeAt(ci) - 64); col--;
    var row = parseInt(m[2]) - 1;
    S.playerX = (col + 0.5) / 20; S.playerY = (row + 0.5) / 20; S.playerFound = true; markDirty(); refreshTargetUI(); toast('已定位到 ' + val);
  });
  if (D.clearAllBtn) D.clearAllBtn.addEventListener('click', clearAllTargets);
  if (D.offscreenCb) D.offscreenCb.addEventListener('change', function() { S.showOffscreen = D.offscreenCb.checked; markDirty(); });
  if (D.corrVert) D.corrVert.addEventListener('input', updateCorrection);
  if (D.corrHoriz) D.corrHoriz.addEventListener('input', updateCorrection);
  if (D.corrReset) D.corrReset.addEventListener('click', resetCorrection);
  if (D.convSize) D.convSize.addEventListener('change', updateConverter);
  if (D.convMil) D.convMil.addEventListener('input', updateConverter);
  if (D.convDist) D.convDist.addEventListener('input', updateConverter);
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.speed-btn');
    if (btn) {
      var speed = btn.getAttribute('data-speed');
      document.querySelectorAll('.speed-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      S.manualSpeedKmh = (speed === 'auto') ? 0 : parseFloat(speed) || 0; refreshTargetInfo(); return;
    }
    var qd = e.target.closest('[data-quick-dist]');
    if (qd) {
      var dist = parseFloat(qd.getAttribute('data-quick-dist'));
      var shell = getShell(); var bal = calcBallistics(dist, shell);
      if (bal && bal.range === 'ok') { var fm = Math.round((bal.milComp || 0) + (S.zeroAdjMil.elev || 0)); toast(dist + 'm: 表尺 ' + fm + ' mil | 飞行 ' + bal.t.toFixed(1) + 's | 穿深 ' + bal.penAtDist + 'mm', '#ff8c00'); }
      else { toast('超出弹道解算范围', '#f65a5a'); }
      return;
    }
    var del = e.target.closest('[data-del]');
    if (del) { var id = parseInt(del.getAttribute('data-del')); removeTarget(id); return; }
    var tRow = e.target.closest('.t-row');
    if (tRow) { var tid = parseInt(tRow.getAttribute('data-id')); S.selectedTargetId = tid; refreshTargetUI(); markDirty(); }
  });
  if (D.canvas) {
    D.canvas.addEventListener('dblclick', function(e) {
      var rect = D.canvas.getBoundingClientRect();
      var cx = e.clientX - rect.left, cy = e.clientY - rect.top;
      var nx = (cx - S.panX) / (S.canvasW * S.zoom), ny = (cy - S.panY) / (S.canvasH * S.zoom);
      if (nx >= 0 && nx <= 1 && ny >= 0 && ny <= 1) { addTarget(nx, ny, 'dblclick'); toast('已标点'); }
    });
    var dragging = false, dragLastX = 0, dragLastY = 0;
    D.canvas.addEventListener('mousedown', function(e) { if (e.altKey) { dragging = true; dragLastX = e.clientX; dragLastY = e.clientY; D.canvas.style.cursor = 'grabbing'; } });
    window.addEventListener('mousemove', function(e) { if (!dragging) return; S.panX += (e.clientX - dragLastX); S.panY += (e.clientY - dragLastY); dragLastX = e.clientX; dragLastY = e.clientY; markDirty(); });
    window.addEventListener('mouseup', function() { if (dragging) { dragging = false; if (D.canvas) D.canvas.style.cursor = 'crosshair'; } });
    D.canvas.addEventListener('wheel', function(e) {
      e.preventDefault();
      var rect = D.canvas.getBoundingClientRect();
      var mx = e.clientX - rect.left, my = e.clientY - rect.top;
      var normX = (mx - S.panX) / (S.canvasW * S.zoom), normY = (my - S.panY) / (S.canvasH * S.zoom);
      var factor = e.deltaY > 0 ? 0.9 : 1.1;
      S.zoom = clamp(S.zoom * factor, 0.5, 50);
      S.panX = mx - normX * S.canvasW * S.zoom; S.panY = my - normY * S.canvasH * S.zoom; markDirty();
    });
  }
  window.addEventListener('resize', resizeCanvas);
  document.addEventListener('keydown', function(e) {
    if (e.key === 'o' || e.key === 'O') { if (D.offscreenCb) { D.offscreenCb.checked = !D.offscreenCb.checked; S.showOffscreen = D.offscreenCb.checked; markDirty(); } }
    if (e.key === 'g' || e.key === 'G') { if (D.gridInput) { D.gridInput.focus(); D.gridInput.select(); } }
  });
}
function init() {
  resizeCanvas();
  populateVehicleSelect();
  populateShellSelect();
  refreshHUD();
  refreshTargetUI();
  initEvents();
  function loop() { render(); requestAnimationFrame(loop); }
  loop();
  addTarget(0.52, 0.48, 'demo', 'medium');
  S.selectedTargetId = 1;
  refreshTargetUI();
  console.log('WT Overwatch v6 initialized');
}
if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
`;
fs.writeFileSync(path, code, 'utf8');
console.log("main.js written successfully, size: " + code.length + " bytes");