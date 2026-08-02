// <concept-figure kind="language|power|scheduling"> — static, detailed three.js diagrams
// for the "Why towers conflict" cards. Renders one frame, no animation loop.
(() => {
  const PURPLE = 0x9f6cff, LILAC = 0xb389ff, CREAM = 0xece9e0, DIM = 0x575450;
  const TEAL = 0x4ade80, AMBER = 0xf5a35c;

  class ConceptFigure extends HTMLElement {
    connectedCallback() {
      if (this._booted) return;
      this._booted = true;
      Object.assign(this.style, { display: 'block', position: 'relative', background: 'transparent' });
      if (!this.style.height) this.style.height = '100%';
      import('three').then(T => this._run(T));
    }

    _tower(T, color, h = 1.0) {
      const g = new T.Group();
      const mat = new T.MeshStandardMaterial({ name: 'mast', color: 0xd6d2c8, roughness: 0.5, metalness: 0.4 });
      const mast = new T.Mesh(new T.CylinderGeometry(0.028, 0.062, h, 10), mat);
      mast.name = 'mast'; mast.position.y = h / 2; g.add(mast);
      // lattice cross-bracing
      for (let k = 0; k < 4; k++) {
        const y = h * (0.18 + k * 0.19);
        const r = new T.Mesh(new T.TorusGeometry(0.055 - k * 0.007, 0.008, 6, 14), mat);
        r.rotation.x = Math.PI / 2; r.position.y = y; g.add(r);
      }
      // three sector antennas
      for (let k = 0; k < 3; k++) {
        const p = new T.Mesh(new T.BoxGeometry(0.055, 0.17, 0.028),
          new T.MeshStandardMaterial({ name: 'antenna', color, roughness: 0.3, emissive: color, emissiveIntensity: 0.35 }));
        p.name = 'antenna';
        const a = k * Math.PI * 2 / 3;
        p.position.set(Math.cos(a) * 0.1, h + 0.03, Math.sin(a) * 0.1);
        p.lookAt(Math.cos(a) * 3, h + 0.03, Math.sin(a) * 3);
        g.add(p);
      }
      const tip = new T.Mesh(new T.SphereGeometry(0.035, 16, 12),
        new T.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 1.2 }));
      tip.name = 'beacon'; tip.position.y = h + 0.14; g.add(tip);
      return g;
    }

    _phone(T, tone) {
      const g = new T.Group();
      const body = new T.Mesh(new T.BoxGeometry(0.14, 0.26, 0.03),
        new T.MeshStandardMaterial({ color: 0x1a1820, roughness: 0.35, metalness: 0.5 }));
      body.name = 'handset';
      const screen = new T.Mesh(new T.PlaneGeometry(0.11, 0.21),
        new T.MeshBasicMaterial({ color: tone }));
      screen.name = 'screen'; screen.position.z = 0.017;
      g.add(body, screen);
      g.position.y = 0.13;
      return g;
    }

    _rings(T, color, r0, count, y, opacity) {
      const g = new T.Group();
      for (let i = 1; i <= count; i++) {
        const r = r0 * i / count;
        const m = new T.Mesh(new T.RingGeometry(r * 0.985, r, 72),
          new T.MeshBasicMaterial({ color, transparent: true, side: T.DoubleSide,
            opacity: opacity * (1 - 0.55 * (i - 1) / count), depthWrite: false }));
        m.name = 'wavefront'; m.rotation.x = -Math.PI / 2; m.position.y = y + i * 0.001;
        g.add(m);
      }
      return g;
    }

    _run(T) {
      const kind = this.getAttribute('kind') || 'language';
      const renderer = new T.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
      renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
      renderer.setClearColor(0x000000, 0);
      renderer.domElement.style.display = 'block';
      this.appendChild(renderer.domElement);

      const scene = new T.Scene();
      const camera = new T.PerspectiveCamera(34, 1.6, 0.1, 100);
      scene.add(new T.AmbientLight(0xffffff, 1.5));
      const key = new T.DirectionalLight(0xffffff, 1.6); key.position.set(3, 6, 4); scene.add(key);
      const rim = new T.DirectionalLight(PURPLE, 1.4); rim.position.set(-4, 2, -3); scene.add(rim);

      const grid = new T.GridHelper(12, 24, 0x2a2638, 0x1a1822);
      grid.material.transparent = true; grid.material.opacity = 0.5;
      scene.add(grid);

      if (kind === 'language') {
        // two towers, two different channels — no interference, both decodable
        const A = this._tower(T, LILAC); A.position.set(-1.15, 0, 0.1); scene.add(A);
        const B = this._tower(T, TEAL); B.position.set(1.15, 0, -0.1); scene.add(B);
        const wa = this._rings(T, LILAC, 1.0, 5, 0.01, 0.55); wa.position.copy(A.position); scene.add(wa);
        const wb = this._rings(T, TEAL, 1.0, 5, 0.01, 0.55); wb.position.copy(B.position); scene.add(wb);
        const p1 = this._phone(T, LILAC); p1.position.set(-0.55, 0, 0.55); scene.add(p1);
        const p2 = this._phone(T, TEAL); p2.position.set(0.62, 0, 0.6); scene.add(p2);
        camera.position.set(0.7, 1.75, 3.3);
        camera.lookAt(0, 0.42, 0);
      } else if (kind === 'power') {
        // same channel, overlapping — the midpoint is unserviceable at any power
        const A = this._tower(T, LILAC, 1.2); A.position.set(-1.1, 0, 0); scene.add(A);
        const B = this._tower(T, LILAC, 1.2); B.position.set(1.1, 0, 0); scene.add(B);
        [A, B].forEach(t => {
          const w = this._rings(T, LILAC, 1.55, 6, 0.008, 0.5);
          w.position.copy(t.position); scene.add(w);
        });
        // the shared, ruined zone
        const R = 1.55, d = 2.2, th = Math.acos(Math.min(1, d / (2 * R)));
        const shape = new T.Shape();
        shape.absarc(-d / 2, 0, R, -th, th, false);
        shape.absarc(d / 2, 0, R, Math.PI - th, Math.PI + th, false);
        const lens = new T.ShapeGeometry(shape, 40); lens.rotateX(-Math.PI / 2); lens.translate(0, 0.02, 0);
        scene.add(new T.Mesh(lens, new T.MeshBasicMaterial({ name: 'dead-zone', color: AMBER,
          transparent: true, opacity: 0.22, side: T.DoubleSide, depthWrite: false })));
        const p = this._phone(T, 0x3a2f22); p.position.set(0, 0, 0.35); scene.add(p);
        // failure marker over the handset
        const x = new T.Group(); x.name = 'no-decode';
        for (const s of [1, -1]) {
          const bar = new T.Mesh(new T.BoxGeometry(0.19, 0.026, 0.026),
            new T.MeshBasicMaterial({ color: AMBER }));
          bar.rotation.z = s * Math.PI / 4; x.add(bar);
        }
        x.position.set(0, 0.55, 0.35); scene.add(x);
        camera.position.set(0.35, 1.5, 3.4);
        camera.lookAt(0, 0.4, 0);
      } else {
        // reuse-1: the same conflict, moved into the time-frequency scheduler
        const gw = 0.30, gh = 0.20, cols = 7, rows = 5;
        const claimA = new Set(['1,1', '2,1', '1,2', '4,3', '5,3', '4,4']);
        const claimB = new Set(['3,0', '4,0', '5,0', '2,3', '0,4', '6,2', '6,3']);
        const clash = new Set(['3,2']);
        for (let c = 0; c < cols; c++) for (let r = 0; r < rows; r++) {
          const kx = `${c},${r}`;
          const hit = clash.has(kx), a = claimA.has(kx), b = claimB.has(kx);
          const col = hit ? AMBER : a ? LILAC : b ? TEAL : 0x1d1b24;
          const box = new T.Mesh(new T.BoxGeometry(gw * 0.9, (hit || a || b) ? 0.09 : 0.03, gh * 0.9),
            new T.MeshStandardMaterial({ name: 'resource-block', color: col, roughness: 0.4,
              emissive: (hit || a || b) ? col : 0x000000, emissiveIntensity: hit ? 0.9 : 0.45 }));
          box.name = 'resource-block';
          box.position.set((c - (cols - 1) / 2) * gw, 0.02, (r - (rows - 1) / 2) * gh);
          scene.add(box);
        }
        // axis rails: frequency and time
        [[-1, 'freq'], [1, 'time']].forEach(([s, n], i) => {
          const len = i === 0 ? rows * gh : cols * gw;
          const rail = new T.Mesh(new T.CylinderGeometry(0.012, 0.012, len, 8),
            new T.MeshBasicMaterial({ color: DIM }));
          rail.name = n;
          if (i === 0) { rail.rotation.x = Math.PI / 2; rail.position.set(-cols * gw / 2 - 0.11, 0.02, 0); }
          else { rail.rotation.z = Math.PI / 2; rail.position.set(0, 0.02, rows * gh / 2 + 0.11); }
          scene.add(rail);
        });
        // the two cells that cannot share the amber block
        const A = this._tower(T, LILAC, 0.5); A.position.set(-1.4, 0.02, -0.5); scene.add(A);
        const B = this._tower(T, TEAL, 0.5); B.position.set(1.4, 0.02, -0.5); scene.add(B);
        grid.visible = false;
        camera.position.set(0.1, 2.75, 3.05);
        camera.lookAt(0, 0.12, -0.02);
      }

      const resize = () => {
        const w = this.clientWidth || 300, h = this.clientHeight || 170;
        renderer.setSize(w, h);
        camera.aspect = w / h; camera.updateProjectionMatrix();
        renderer.render(scene, camera);
      };
      new ResizeObserver(resize).observe(this);
      resize();
      requestAnimationFrame(resize);
    }
  }
  if (!customElements.get('concept-figure')) customElements.define('concept-figure', ConceptFigure);
})();
