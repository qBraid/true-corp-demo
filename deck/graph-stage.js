// <graph-stage> — 2D conflict-graph diagram, two modes:
//   mode="mis"      (default) nodes -> overlap edge -> full graph -> one MIS resolves (= channel 1)
//   mode="coloring" repeated-MIS extraction painting the graph in channel colors, round by round
(() => {
  const CSS = `
  .gs-wrap { position: absolute; inset: 0; }
  .gs-wrap canvas { display: block; width: 100%; height: 100%; }
  .gs-legend { position: absolute; left: 22px; bottom: 16px; display: flex; flex-wrap: wrap; gap: 18px 30px;
    font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 24px; letter-spacing: 0.08em;
    opacity: 0; transition: opacity 600ms cubic-bezier(0.2,0.7,0.2,1); max-width: 80%; }
  .gs-key { display: flex; align-items: center; gap: 12px; }
  .gs-dot { width: 16px; height: 16px; border-radius: 50%; display: block; }`;

  const hex2rgb = c => [parseInt(c.slice(1,3),16), parseInt(c.slice(3,5),16), parseInt(c.slice(5,7),16)];
  const CREAM = hex2rgb('#ECE9E0');
  const COLS = ['#B389FF','#4ade80','#60a5fa','#f5a35c','#f472b6','#ECE9E0'];
  const clamp01 = v => Math.max(0, Math.min(1, v));
  const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  const seg = (t, a, b) => ease(clamp01((t - a) / (b - a)));

  function mulberry32(a) {
    return function() {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      let t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  class GraphStage extends HTMLElement {
    connectedCallback() {
      if (this._booted) return;
      this._booted = true;
      Object.assign(this.style, { display: 'block', position: 'relative', background: this.getAttribute('bare') ? 'transparent' : '#0a0a0b' });
      if (!this.style.height) this.style.height = '100%';
      const style = document.createElement('style');
      style.textContent = CSS;
      this.appendChild(style);
      this.insertAdjacentHTML('beforeend', '<div class="gs-wrap"><canvas></canvas></div><div class="gs-legend"></div>');
      this._mode = this.getAttribute('mode') === 'coloring' ? 'coloring' : 'mis';
      this._run();
    }

    _graph() {
      if (this._mode === 'mis') {
        // 11 towers; the last one has no conflicts — it always makes the set
        const PTS = [[80,90],[225,140],[360,60],[210,265],[95,255],[420,200],[290,345],[480,320],[160,405],[380,430],[510,80]];
        const EDGES = [[0,1],[1,2],[1,3],[0,4],[2,5],[3,5],[3,4],[4,8],[5,7],[6,7],[3,6],[6,9],[8,6]];
        return { PTS, EDGES, FOCUS: 8 };
      }
      // coloring mode: 26 towers generated like real cell data — min separation, edge within one interference radius
      const rnd = mulberry32(7);
      const PTS = [];
      let guard = 0;
      while (PTS.length < 26 && guard++ < 4000) {
        const x = 40 + rnd() * 480, y = 40 + rnd() * 380;
        if (PTS.every(([px, py]) => Math.hypot(px - x, py - y) > 52)) PTS.push([x, y]);
      }
      const EDGES = [];
      for (let i = 0; i < PTS.length; i++)
        for (let j = i + 1; j < PTS.length; j++)
          if (Math.hypot(PTS[i][0]-PTS[j][0], PTS[i][1]-PTS[j][1]) < 108) EDGES.push([i, j]);
      return { PTS, EDGES, FOCUS: -1 };
    }

    _run() {
      const { PTS, EDGES, FOCUS } = this._graph();
      const N = PTS.length;
      const ADJ = PTS.map(() => new Set());
      EDGES.forEach(([i, j]) => { ADJ[i].add(j); ADJ[j].add(i); });

      // repeated greedy MIS -> roundOf[i] = which channel each tower gets
      const roundOf = Array(N).fill(-1);
      let remaining = new Set(PTS.keys());
      let R = 0;
      while (remaining.size) {
        const deg = i => [...ADJ[i]].filter(n => remaining.has(n)).length;
        const mis = new Set();
        [...remaining].sort((a, b) => deg(a) - deg(b)).forEach(i => {
          for (const n of ADJ[i]) if (mis.has(n)) return;
          mis.add(i);
        });
        mis.forEach(i => { roundOf[i] = R; remaining.delete(i); });
        R++;
      }
      const eRound = EDGES.map(([i, j]) => Math.min(roundOf[i], roundOf[j]));
      const counts = Array(R).fill(0);
      roundOf.forEach(r => counts[r]++);

      const legendEl = this.querySelector('.gs-legend');
      if (this._mode === 'mis') {
        legendEl.innerHTML =
          '<div class="gs-key"><span class="gs-dot" style="background:#B389FF;box-shadow:0 0 14px rgba(159,108,255,0.85)"></span><span style="color:#ECE9E0">CHANNEL 1</span></div>' +
          '<div class="gs-key"><span class="gs-dot" style="background:#4a4750"></span><span style="color:#575450">WAITS FOR ROUND 2</span></div>';
      } else {
        legendEl.innerHTML = counts.map((c, r) =>
          `<div class="gs-key"><span class="gs-dot" style="background:${COLS[r % COLS.length]}"></span><span style="color:#ECE9E0">CH ${r + 1} · ${c}</span></div>`).join('');
      }

      const wrap = this.querySelector('.gs-wrap');
      const canvas = wrap.querySelector('canvas');
      const ctx = canvas.getContext('2d');
      let W = 800, H = 500, sc = 1, ox = 0, oy = 0;
      const self = this;
      const resize = () => {
        W = wrap.clientWidth || 800; H = wrap.clientHeight || 500;
        const dpr = Math.min(devicePixelRatio, 2);
        canvas.width = W * dpr; canvas.height = H * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        const legendH = (self._mode === "coloring" ? 96 : 62);
        sc = Math.min((W - 40) / 560, (H - legendH - 40) / 460);
        ox = (W - 560 * sc) / 2; oy = (H - legendH - 460 * sc) / 2 + 8;
      };
      new ResizeObserver(resize).observe(wrap);
      resize();
      const P = i => [ox + PTS[i][0] * sc, oy + PTS[i][1] * sc];

      const bare = !!this.getAttribute('bare');
      const drawGrid = () => {
        if (bare) { ctx.clearRect(0, 0, W, H); return; }
        ctx.fillStyle = '#0a0a0b'; ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = 'rgba(236,233,224,0.045)'; ctx.lineWidth = 1;
        for (let x = 0; x < W; x += 46) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
        for (let y = 0; y < H; y += 46) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
      };

      let t0 = null;

      const frameMIS = now => {
        if (t0 === null) t0 = now;
        const LOOP = 24;
        const t = ((now - t0) / 1000) % LOOP;
        const appear = seg(t, 0.4, 2.6);
        const cover = seg(t, 3.6, 5.0) * (1 - seg(t, 8.6, 10.0));
        const focus = seg(t, 5.0, 6.4);
        const rest = seg(t, 10.2, 12.8);
        const resolve = seg(t, 14.5, 18.5);
        legendEl.style.opacity = String(resolve);
        drawGrid();
        const [fa, fb] = EDGES[FOCUS];
        if (cover > 0.01) {
          const [ax, ay] = P(fa), [bx, by] = P(fb);
          const Rr = Math.hypot(bx - ax, by - ay) * 0.62;
          for (const [cx, cy] of [[ax, ay], [bx, by]]) {
            const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, Rr);
            g.addColorStop(0, `rgba(159,108,255,${0.13 * cover})`);
            g.addColorStop(1, 'rgba(159,108,255,0)');
            ctx.fillStyle = g;
            ctx.beginPath(); ctx.arc(cx, cy, Rr, 0, 7); ctx.fill();
            ctx.strokeStyle = `rgba(159,108,255,${0.35 * cover})`;
            ctx.setLineDash([5, 7]);
            ctx.beginPath(); ctx.arc(cx, cy, Rr, 0, 7); ctx.stroke();
            ctx.setLineDash([]);
          }
        }
        EDGES.forEach(([i, j], k) => {
          const isFocus = k === FOCUS;
          const grow = isFocus ? focus : clamp01(rest * 1.5 - k * 0.06);
          if (grow < 0.01) return;
          const [ax, ay] = P(i), [bx, by] = P(j);
          const bright = isFocus && rest < 0.5;
          ctx.strokeStyle = bright ? `rgba(214,184,255,${0.95 * grow})` : `rgba(159,108,255,${(0.55 - 0.18 * resolve) * grow})`;
          ctx.lineWidth = bright ? 3 : 2;
          ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(ax + (bx - ax) * grow, ay + (by - ay) * grow); ctx.stroke();
        });
        PTS.forEach((_, i) => {
          const local = clamp01(appear * 1.5 - i * 0.05);
          if (local < 0.01) return;
          const sel = roundOf[i] === 0; // channel-1 set = the MIS
          const res = clamp01(resolve * 1.5 - i * 0.05);
          const [x, y] = P(i);
          const r = (11 + (sel ? 2.6 : -1.6) * res) * local;
          if (sel && res > 0.01) { ctx.shadowColor = 'rgba(159,108,255,0.9)'; ctx.shadowBlur = 22 * res; }
          const lerp = (a, b) => Math.round(a + (b - a) * res);
          const PUR = hex2rgb(COLS[0]);
          ctx.fillStyle = sel
            ? `rgb(${lerp(CREAM[0],PUR[0])},${lerp(CREAM[1],PUR[1])},${lerp(CREAM[2],PUR[2])})`
            : `rgba(${CREAM[0]},${CREAM[1]},${CREAM[2]},${1 - 0.55 * res})`;
          ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
          ctx.shadowBlur = 0;
          if (sel && res > 0.01) {
            ctx.strokeStyle = `rgba(179,137,255,${0.55 * res})`;
            ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(x, y, r + 7 + 2 * res, 0, 7); ctx.stroke();
          }
        });
        requestAnimationFrame(frameMIS);
      };

      const frameColoring = now => {
        if (t0 === null) t0 = now;
        const T_INTRO = 0.3, T_WIRE = 1.8, RD = 3.2, T_R0 = 3.8;
        const LOOP = T_R0 + R * RD + 4.5;
        const t = ((now - t0) / 1000) % LOOP;
        const intro = seg(t, T_INTRO, 1.8);
        const wires = seg(t, T_WIRE, 3.2);
        legendEl.style.opacity = String(seg(t, T_R0 + 0.8, T_R0 + 1.8));
        drawGrid();
        const fillOf = r => seg(t, T_R0 + r * RD + 0.6, T_R0 + r * RD + 1.6);
        const ringOf = r => seg(t, T_R0 + r * RD, T_R0 + r * RD + 0.9);
        EDGES.forEach(([i, j], k) => {
          const gone = seg(t, T_R0 + eRound[k] * RD + 1.0, T_R0 + eRound[k] * RD + 2.0);
          const op = 0.5 * wires * (1 - gone);
          if (op < 0.01) return;
          const [ax, ay] = P(i), [bx, by] = P(j);
          ctx.strokeStyle = `rgba(159,108,255,${op})`;
          ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
        });
        PTS.forEach((_, i) => {
          const local = clamp01(intro * 1.6 - i * 0.02);
          if (local < 0.01) return;
          const r0 = roundOf[i];
          const k = fillOf(r0);
          const ring = ringOf(r0);
          const [x, y] = P(i);
          const col = hex2rgb(COLS[r0 % COLS.length]);
          const lerp = (a, b) => Math.round(a + (b - a) * k);
          const rad = (9 + 2.5 * k) * local;
          if (k > 0.01) {
            ctx.shadowColor = COLS[r0 % COLS.length];
            ctx.shadowBlur = 16 * k;
          }
          ctx.fillStyle = `rgb(${lerp(CREAM[0],col[0])},${lerp(CREAM[1],col[1])},${lerp(CREAM[2],col[2])})`;
          ctx.beginPath(); ctx.arc(x, y, rad, 0, 7); ctx.fill();
          ctx.shadowBlur = 0;
          if (ring > 0.01 && ring < 1) {
            ctx.strokeStyle = `rgba(236,233,224,${0.8 * Math.sin(Math.PI * ring)})`;
            ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(x, y, rad + 6 + 10 * ring, 0, 7); ctx.stroke();
          }
        });
        requestAnimationFrame(frameColoring);
      };

      requestAnimationFrame(this._mode === 'mis' ? frameMIS : frameColoring);
    }
  }
  if (!customElements.get('graph-stage')) customElements.define('graph-stage', GraphStage);
})();
