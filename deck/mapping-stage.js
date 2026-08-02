// <mapping-stage> — cell sites -> coverage graph -> atom register.
// Mounted in the deck document (not an iframe) so slide captures include it.
(() => {
  const CSS = "\n  html, body { margin: 0; height: 100%; overflow: hidden; background: #0a0a0b;\n    font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif; color: #ECE9E0; }\n  .ms-wrap { position: absolute; inset: 0; }\n  .ms-wrap canvas { display: block; }\n  .ms-acts { display: none !important; } .ms-acts-dead { position: absolute; left: 24px; top: 20px; display: flex; flex-direction: column; gap: 12px;\n    font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 15px; letter-spacing: 0.13em; }\n  .ms-act { color: #3a3742; transition: color 500ms cubic-bezier(0.2,0.7,0.2,1), text-shadow 500ms; }\n  .ms-act.ms-on { color: #B389FF; text-shadow: 0 0 22px rgba(159,108,255,0.55); }\n  .ms-place { position: absolute; right: 24px; top: 20px;\n    font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 15px;\n    letter-spacing: 0.14em; color: #8A8580; text-align: right; }\n  .ms-legend { position: absolute; left: 24px; bottom: 18px; display: flex; flex-direction: column; gap: 10px;\n    font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 15px; letter-spacing: 0.1em;\n    opacity: 0; transition: opacity 600ms cubic-bezier(0.2,0.7,0.2,1); }\n  .ms-key { display: flex; align-items: center; gap: 10px; }\n  .ms-dot { width: 11px; height: 11px; border-radius: 50%; display: block; }\n  .ms-scale { position: absolute; right: 24px; bottom: 18px;\n    font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 15px;\n    letter-spacing: 0.12em; color: #575450; }\n  .ms-headline { position: absolute; left: 24px; bottom: 18px;\n    font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 15px;\n    letter-spacing: 0.12em; color: #575450; }\n";
  const MARKUP = "<div class=\"ms-wrap\"></div>\n<div class=\"ms-acts\">\n  <div class=\"ms-act\" data-act=\"0\">01 · SUKHUMVIT CELL SITES</div>\n  <div class=\"ms-act\" data-act=\"1\">02 · COVERAGE GRAPH</div>\n  <div class=\"ms-act\" data-act=\"2\">03 · ATOM REGISTER</div>\n</div>\n<div class=\"ms-legend\">\n  <div class=\"ms-key\"><span class=\"ms-dot\" style=\"background:#B389FF;box-shadow:0 0 12px rgba(159,108,255,0.8)\"></span><span style=\"color:#ECE9E0\">CHANNEL 1</span></div>\n  <div class=\"ms-key\"><span class=\"ms-dot\" style=\"background:#3a3742\"></span><span style=\"color:#575450\">AWAITS A LATER ROUND</span></div>\n</div>\n<div class=\"ms-scale\">1 µm = 60 m · BLOCKADE 8.4 µm ≈ 500 m</div>";

  class MappingStage extends HTMLElement {
    connectedCallback() {
      if (this._booted) return;
      this._booted = true;
      this.style.display = 'block';
      this.style.position = 'relative';
      this.style.background = this.getAttribute('bare') ? 'transparent' : '#0a0a0b';
      if (!this.style.height) this.style.height = '100%';
      const style = document.createElement('style');
      style.textContent = CSS.replace(/html, body \{[^}]*\}/, '');
      this.appendChild(style);
      this.insertAdjacentHTML('beforeend', MARKUP);
      import('three').then(THREE => this._run(THREE, this));
    }
    _run(THREE, root) {


// ---- real site coordinates (Watthana / Khlong Toei) -> local metres -> scene units
const SITES = [
  [100.5480,13.7440],[100.5545,13.7395],[100.5600,13.7365],[100.5665,13.7325],
  [100.5715,13.7300],[100.5780,13.7280],[100.5840,13.7250],[100.5622,13.7420],
  [100.5608,13.7292],[100.5762,13.7344],[100.5560,13.7472],[100.5700,13.7455],
  [100.5798,13.7408],[100.5872,13.7372],[100.5905,13.7318],[100.5742,13.7228],
  [100.5648,13.7208],[100.5560,13.7262],[100.5905,13.7218],[100.5638,13.7508],
  [100.5872,13.7482],[100.5800,13.7168],[100.5495,13.7180],[100.5952,13.7398],
  [100.5588,13.7150]
];
const lon0 = 100.5700, lat0 = 13.7340, M2U = 1 / 540;      // metres -> scene units
const COVER = 500 * M2U;                                    // 500 m coverage radius
const pos = SITES.map(([lon, lat]) => new THREE.Vector3(
  (lon - lon0) * Math.cos(lat0 * Math.PI / 180) * 111320 * M2U, 0,
  -(lat - lat0) * 111111 * M2U));

const centroid = pos.reduce((a, p) => a.add(p), new THREE.Vector3()).multiplyScalar(1 / pos.length);
pos.forEach(p => p.sub(centroid));

const EDGES = [];
for (let i = 0; i < pos.length; i++)
  for (let j = i + 1; j < pos.length; j++)
    if (pos[i].distanceTo(pos[j]) < COVER * 2) EDGES.push([i, j]);

const ADJ = pos.map(() => new Set());
EDGES.forEach(([i, j]) => { ADJ[i].add(j); ADJ[j].add(i); });
// Pure MIS: the largest set of towers that can transmit on one channel.
// Selected (excited) atoms glow; the rest simply wait for a later round.
const MIS = new Set();
[...pos.keys()].sort((a, b) => ADJ[a].size - ADJ[b].size).forEach(i => {
  for (const n of ADJ[i]) if (MIS.has(n)) return;
  MIS.add(i);
});
const AWAKE = MIS;                                                   // channel 1
const SLEEP = new Set([...pos.keys()].filter(i => !MIS.has(i)));     // not selected

// ---- scene
const wrap = root.querySelector('.ms-wrap');
const BARE = !!root.getAttribute('bare');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x0a0a0b, BARE ? 0 : 1);
wrap.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 200);
scene.add(new THREE.AmbientLight(0xffffff, 1.4));
const key = new THREE.DirectionalLight(0xffffff, 1.5); key.position.set(4, 9, 5); scene.add(key);
const rim = new THREE.DirectionalLight(0x9f6cff, 1.1); rim.position.set(-6, 3, -4); scene.add(rim);

const MAT = {
  mast:  new THREE.MeshStandardMaterial({ name: 'mast', color: 0xd6d2c8, roughness: 0.55, metalness: 0.35 }),
  node:  new THREE.MeshStandardMaterial({ name: 'node', color: 0xece9e0, roughness: 0.3, metalness: 0.1,
           emissive: 0x000000 }),
  atom:  new THREE.MeshStandardMaterial({ name: 'atom', color: 0xb389ff, roughness: 0.25, metalness: 0.0,
           emissive: 0x6d28d9, emissiveIntensity: 0.9 }),
  asleep:new THREE.MeshStandardMaterial({ name: 'asleep', color: 0x575450, roughness: 0.7, metalness: 0.0 }),
  disc:  new THREE.MeshBasicMaterial({ name: 'coverage', color: 0x9f6cff, transparent: true, opacity: 0,
           side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }),
  edge:  new THREE.LineBasicMaterial({ name: 'edge', color: 0x9f6cff, transparent: true, opacity: 0 }),
  rim:   new THREE.MeshBasicMaterial({ name: 'radius-rim', color: 0xb389ff, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false })
};

// ground grid — the city plane
const grid = new THREE.GridHelper(18, 18, 0x2a2638, 0x1c1a24);
grid.material.transparent = true; grid.material.opacity = 0.9;
if (BARE) grid.visible = false;
scene.add(grid);

// basemap as a true 3D ground plane, edge-faded so it melts into the background
let mapPlane = null;
if (BARE) {
  const tex = new THREE.TextureLoader().load('assets/sukhumvit-basemap.png');
  if (THREE.SRGBColorSpace) tex.colorSpace = THREE.SRGBColorSpace;
  const ac = document.createElement('canvas'); ac.width = ac.height = 256;
  const actx = ac.getContext('2d');
  const rg = actx.createRadialGradient(128, 128, 30, 128, 128, 127);
  rg.addColorStop(0, '#ffffff'); rg.addColorStop(0.62, '#ffffff'); rg.addColorStop(1, '#000000');
  actx.fillStyle = '#000000'; actx.fillRect(0, 0, 256, 256);
  actx.fillStyle = rg; actx.fillRect(0, 0, 256, 256);
  const alpha = new THREE.CanvasTexture(ac);
  // georeference the plane to the basemap bbox (sukhumvit_basemap.json) using the
  // exact projection used for the tower coordinates — the map is TO SCALE
  const BB = { west: 100.546, east: 100.604, south: 13.7072, north: 13.7478 };
  const kx = Math.cos(lat0 * Math.PI / 180) * 111320 * M2U, kz = 111111 * M2U;
  const bbW = (BB.east - BB.west) * kx;
  const bbH = (BB.north - BB.south) * kz;
  const bbCx = ((BB.west + BB.east) / 2 - lon0) * kx - centroid.x;
  const bbCz = -(((BB.south + BB.north) / 2 - lat0) * kz) - centroid.z;
  mapPlane = new THREE.Mesh(new THREE.PlaneGeometry(bbW, bbH),
    new THREE.MeshBasicMaterial({ map: tex, alphaMap: alpha, transparent: true, depthWrite: false, opacity: 0.95 }));
  mapPlane.position.set(bbCx, -0.02, bbCz);
  mapPlane.name = 'basemap';
  mapPlane.renderOrder = -10; // always paint first, never over the discs/rims of far (northern) towers
  mapPlane.rotation.x = -Math.PI / 2;
  mapPlane.position.y = -0.02;
  scene.add(mapPlane);
}

// towers: mast + crossarms, one per site
const towers = [], nodes = [], discs = [], rims = [];
const mastGeo = new THREE.CylinderGeometry(0.022, 0.045, 0.85, 8);
const armGeo  = new THREE.BoxGeometry(0.26, 0.028, 0.028);
const nodeGeo = new THREE.SphereGeometry(0.10, 24, 16);
const discGeo = new THREE.CircleGeometry(COVER, 96);
const rimGeo = new THREE.RingGeometry(COVER * 0.96, COVER, 96);

pos.forEach((p, i) => {
  const g = new THREE.Group();
  const mast = new THREE.Mesh(mastGeo, MAT.mast); mast.name = 'mast'; mast.position.y = 0.425;
  g.add(mast);
  [0.60, 0.76].forEach((y, k) => {
    const a = new THREE.Mesh(armGeo, MAT.mast); a.name = 'crossarm'; a.position.y = y;
    a.rotation.y = k * Math.PI / 3; g.add(a);
    const b = a.clone(); b.rotation.y = k * Math.PI / 3 + Math.PI / 2; g.add(b);
  });
  g.position.copy(p); scene.add(g); towers.push(g);

  const n = new THREE.Mesh(nodeGeo, MAT.node.clone()); n.name = 'site-node';
  n.position.copy(p); n.position.y = 0.80; n.scale.setScalar(0.001); scene.add(n); nodes.push(n);

  const d = new THREE.Mesh(discGeo, MAT.disc.clone()); d.name = 'coverage';
  d.rotation.x = -Math.PI / 2; d.position.copy(p); d.position.y = 0.012; scene.add(d); discs.push(d);

  const rr = new THREE.Mesh(rimGeo, MAT.rim.clone()); rr.name = 'radius-rim';
  rr.rotation.x = -Math.PI / 2; rr.position.copy(p); rr.position.y = 0.014; scene.add(rr); rims.push(rr);
});

// edges between overlapping sites
// WebGL ignores LineBasicMaterial.linewidth, so edges are thin cylinders.
const EDGE_R = 0.022;
const edgeMat = new THREE.MeshBasicMaterial({ name: 'edge', color: 0x9f6cff,
  transparent: true, opacity: 0, depthWrite: false });
const edgeLines = new THREE.Group(); edgeLines.name = 'coverage-edges';
const tubeGeo = new THREE.CylinderGeometry(EDGE_R, EDGE_R, 1, 6, 1, true);
const up = new THREE.Vector3(0, 1, 0);
EDGES.forEach(([i, j]) => {
  const a = new THREE.Vector3(pos[i].x, 0.80, pos[i].z);
  const b = new THREE.Vector3(pos[j].x, 0.80, pos[j].z);
  const m = new THREE.Mesh(tubeGeo, edgeMat); m.name = 'edge';
  m.position.copy(a).add(b).multiplyScalar(0.5);
  const dir = new THREE.Vector3().subVectors(b, a);
  m.scale.set(1, dir.length(), 1);
  m.quaternion.setFromUnitVectors(up, dir.clone().normalize());
  edgeLines.add(m);
});
scene.add(edgeLines);

// overlap lenses — the region two coverage discs share, i.e. why an edge exists
const lensMat = new THREE.MeshBasicMaterial({ name: 'overlap', color: 0xb389ff,
  transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false,
  blending: THREE.AdditiveBlending });
const lenses = new THREE.Group(); lenses.name = 'overlaps';
EDGES.forEach(([i, j]) => {
  const dx = pos[j].x - pos[i].x, dz = pos[j].z - pos[i].z;
  const d = Math.hypot(dx, dz);
  if (d >= COVER * 2) return;
  const th = Math.acos(Math.min(1, d / (2 * COVER)));
  const shape = new THREE.Shape();
  shape.absarc(-d / 2, 0, COVER, -th, th, false);
  shape.absarc(d / 2, 0, COVER, Math.PI - th, Math.PI + th, false);
  const g = new THREE.ShapeGeometry(shape, 24);
  g.rotateX(-Math.PI / 2);
  g.rotateY(Math.atan2(-dz, dx));
  g.translate((pos[i].x + pos[j].x) / 2, 0.016, (pos[i].z + pos[j].z) / 2);
  const m = new THREE.Mesh(g, lensMat); m.name = 'overlap'; lenses.add(m);
});
scene.add(lenses);

// power-down pulse: a ring collapsing into each cell as it switches off
const pulseMat = new THREE.MeshBasicMaterial({ color: 0x8A8580, transparent: true, opacity: 0,
  side: THREE.DoubleSide, depthWrite: false });
const pulses = [];
pos.forEach(p => {
  const g = new THREE.RingGeometry(COVER * 0.34, COVER * 0.40, 40);
  const m = new THREE.Mesh(g, pulseMat.clone()); m.name = 'power-down';
  m.rotation.x = -Math.PI / 2; m.position.set(p.x, 0.03, p.z);
  scene.add(m); pulses.push(m);
});

// blockade ring, shown in the atom act
const ringGeo = new THREE.RingGeometry(COVER * 0.97, COVER, 64);
const ringMat = new THREE.MeshBasicMaterial({ color: 0xb389ff, transparent: true, opacity: 0, side: THREE.DoubleSide });
const ring = new THREE.Mesh(ringGeo, ringMat); ring.name = 'blockade'; ring.visible = false;
ring.rotation.x = -Math.PI / 2; ring.position.copy(pos[9]); ring.position.y = 0.02; scene.add(ring);

// ---- timeline
const ACTS = [root.querySelector('[data-act="0"]'), root.querySelector('[data-act="1"]'), root.querySelector('[data-act="2"]')];
const legendEl = root.querySelector('.ms-legend');

const clamp01 = v => Math.max(0, Math.min(1, v));
const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
const seg = (t, a, b) => ease(clamp01((t - a) / (b - a)));
const LOOP = 32;
let t0 = null;

function frame(now) {
  if (t0 === null) t0 = now;
  const t = ((now - t0) / 1000) % LOOP;

  // act 1: towers rise (0-4s) · act 2: graph (6-13s) · act 3: register (15-24s)
  const rise   = seg(t, 0.4, 3.0);
  const descend= seg(t, 3.6, 6.6);   // top-down district view -> low hover
  const graph  = seg(t, 9.0, 11.2);   // coverage discs bloom
  const lens   = seg(t, 11.4, 13.2);  // shared ground lights up
  const wire   = seg(t, 13.6, 15.6);  // each overlap becomes an edge
  const reg    = seg(t, 18.0, 21.5);  // register forms
  const sleep  = seg(t, 23.0, 25.0);  // the sleep set resolves

  ACTS[0].classList.toggle('ms-on', t >= 0.4 && t < 9);
  ACTS[1].classList.toggle('ms-on', t >= 9 && t < 18);
  ACTS[2].classList.toggle('ms-on', t >= 18);

  legendEl.style.opacity = String(sleep);

  towers.forEach((g, i) => {
    const local = clamp01(rise * 1.6 - i * 0.02);
    g.scale.set(1, Math.max(0.001, local * (1 - reg)), 1);
    g.visible = local > 0.01 && reg < 0.99;
  });

  const LIT = new THREE.Color(0xece9e0), ON = new THREE.Color(0xb389ff), OFF = new THREE.Color(0x3a3742);
  nodes.forEach((n, i) => {
    const asleep = SLEEP.has(i);
    const base = 0.001 + graph * 1 + reg * 0.5;
    n.scale.setScalar(Math.max(0.001, base * (1 - 0.25 * reg) * (1 - (asleep ? 0.95 : -0.15) * sleep)));
    n.position.y = 0.80 - reg * 0.78;
    const m = n.material;
    m.color.lerpColors(LIT, asleep ? OFF : ON, sleep);
    m.emissive.setHex(asleep ? 0x000000 : 0x6d28d9);
    m.emissiveIntensity = asleep ? 0 : 1.1 * sleep;
    m.transparent = true;
    m.opacity = 1 - sleep * (asleep ? 1 : 0);
  });

  discs.forEach((d, i) => {
    // all radii visible through the node view; in the resolve only channel-1 radii stay
    const held = SLEEP.has(i) ? 0 : 0.22 * sleep;
    d.material.opacity = 0.16 * graph * (1 - 0.30 * wire) * (1 - reg) * (1 - (SLEEP.has(i) ? sleep : 0)) + held;
    d.position.y = 0.012;
    const rr = rims[i];
    rr.material.opacity = 0.5 * graph * (1 - reg) * (SLEEP.has(i) ? (1 - sleep) : 1);
  });
  pulses.forEach((m, i) => {
    m.material.opacity = 0; return;
    const k = seg(t, 22.6 + (i % 5) * 0.12, 24.2 + (i % 5) * 0.12);
    m.material.opacity = 0.9 * Math.sin(Math.PI * k) * (k < 1 ? 1 : 0);
    m.scale.setScalar(1 - 0.82 * k);
    m.position.y = nodes[i].position.y + 0.004;
  });
  lensMat.opacity = 0.42 * lens * (1 - 0.55 * wire) * (1 - reg);
  edgeMat.opacity = 0.55 * wire * (1 + 0.3 * reg) * (1 - sleep);
  edgeLines.position.y = -reg * 0.78;
  ringMat.opacity = 0;
  grid.material.opacity = 0.9 * (1 - 0.75 * reg);
  if (mapPlane) mapPlane.material.opacity = 0.95 * (1 - 0.8 * reg);

  // camera: low across the towers -> tilted -> near top-down on the register
  // opens top-down on the district, drops into a low hover, then lifts to the register
  const a = 1.45 - descend * 1.13 + graph * 0.45 + reg * 0.48;
  const dist = (12.6 + descend * 1.4 - graph * 0.9 - reg * 0.5) * (BARE ? 0.62 : 1);
  const spin = (now - t0) / 32000;
  camera.position.set(Math.sin(spin) * Math.cos(a) * dist,
                      Math.sin(a) * dist,
                      Math.cos(spin) * Math.cos(a) * dist);
  camera.lookAt(0, 0.25 - reg * 0.2, 0);

  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

function resize() {
  const host = wrap.parentElement || wrap;
  const r = host.getBoundingClientRect();
  const w = Math.round(wrap.clientWidth || r.width) || 800;
  const h = Math.round(wrap.clientHeight || r.height) || 500;
  renderer.setSize(w, h);
  camera.aspect = w / h; camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(wrap);
addEventListener('resize', resize);
resize();
requestAnimationFrame(resize);
requestAnimationFrame(frame);

    }
  }
  if (!customElements.get('mapping-stage')) customElements.define('mapping-stage', MappingStage);
})();
