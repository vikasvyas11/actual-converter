const SPECTRUM = ['#ff8705', '#ff8df2', '#6385ff', '#37d7fa'];
const SPARKS = ['#ff8705', '#ff8df2', '#6385ff', '#37d7fa', '#fba647', '#fca6f3', '#92aeff', '#96e7f9'];
const BRICK_TINTS = ['#fba647', '#fca6f3', '#92aeff', '#96e7f9'];

// 8x8 pixel swap-arrows glyph (⇄)
const SWAP_GRID = [
  [0, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 1, 0, 0],
  [0, 1, 1, 1, 1, 1, 1, 0],
  [0, 0, 0, 0, 0, 1, 0, 0],
  [0, 0, 1, 0, 0, 0, 0, 0],
  [0, 1, 1, 1, 1, 1, 1, 0],
  [0, 0, 1, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 0],
];

const SWAP_CELLS = [];
for (let r = 0; r < 8; r++) {
  for (let c = 0; c < 8; c++) {
    if (SWAP_GRID[r][c]) SWAP_CELLS.push({ r, c });
  }
}

const hash = (a, b) => {
  const n = Math.sin(a * 127.1 + b * 311.7) * 43758.5453;
  return n - Math.floor(n);
};

const sizeCanvas = (canvas, w, h) => {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.round(w * dpr));
  canvas.height = Math.max(1, Math.round(h * dpr));
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return ctx;
};

function setupBrandLogo(reducedMotion) {
  const logo = document.getElementById('brand-logo');
  const mark = document.getElementById('brand-mark');
  const fx = document.getElementById('brand-fx');
  if (!logo || !mark || !fx) return;

  const markSize = 32;
  const markCtx = sizeCanvas(mark, markSize, markSize);
  let fxW = logo.offsetWidth + 36;
  let fxH = logo.offsetHeight + 20;
  let fxCtx = sizeCanvas(fx, fxW, fxH);

  let hovered = false;
  let pointer = { x: 16, y: 16 };
  let phase = 0;
  let lastSpawn = 0;
  let raf = 0;
  const sparks = [];

  const drawMark = (now, active) => {
    markCtx.fillStyle = '#000000';
    markCtx.fillRect(0, 0, markSize, markSize);

    const cell = 3;
    const pad = 4;
    for (const { r, c } of SWAP_CELLS) {
      let dx = 0;
      let dy = 0;
      let color = SPECTRUM[Math.min(3, Math.floor((c / 7) * 4))];

      if (active) {
        const cx = pad + c * cell + cell / 2;
        const cy = pad + r * cell + cell / 2;
        const dist = Math.hypot(cx - pointer.x, cy - pointer.y);
        if (dist < 28) {
          const shift = Math.floor((c + phase * 8) % SPECTRUM.length);
          color = SPECTRUM[(shift + SPECTRUM.length) % SPECTRUM.length];
          if (dist < 16 && hash(c + Math.floor(phase * 10), r) > 0.55) {
            dx = r < 4 ? 1 : -1;
            dy = hash(r, c + Math.floor(phase * 10)) > 0.5 ? -1 : 1;
          }
        }
      }

      markCtx.fillStyle = color;
      markCtx.fillRect(pad + (c + dx) * cell, pad + (r + dy) * cell, cell - 0.35, cell - 0.35);
    }
  };

  drawMark(0, false);
  if (reducedMotion) return;

  const tick = (now) => {
    raf = 0;
    phase = (now * 0.004) % 100;
    fxCtx.clearRect(0, 0, fxW, fxH);

    for (let i = sparks.length - 1; i >= 0; i--) {
      const s = sparks[i];
      const age = now - s.t0;
      if (age >= s.life) {
        sparks.splice(i, 1);
        continue;
      }
      fxCtx.globalAlpha = 1 - age / s.life;
      fxCtx.fillStyle = s.color;
      fxCtx.fillRect(s.x, s.y, s.w, s.h);
    }
    fxCtx.globalAlpha = 1;

    drawMark(now, hovered);

    if (hovered || sparks.length > 0) {
      raf = requestAnimationFrame(tick);
    } else {
      drawMark(0, false);
    }
  };

  const ensureLoop = () => {
    if (!raf) raf = requestAnimationFrame(tick);
  };

  const spawn = (lx, ly, now) => {
    if (now - lastSpawn < 32) return;
    lastSpawn = now;
    const count = 2;
    for (let i = 0; i < count; i++) {
      if (sparks.length >= 24) sparks.shift();
      const snapX = Math.round((lx + 18 + (Math.random() - 0.5) * 30) / 4) * 4;
      const snapY = Math.round((ly + 10 + (Math.random() - 0.5) * 22) / 4) * 4;
      const wide = Math.random() > 0.35;
      sparks.push({
        x: snapX,
        y: snapY,
        w: wide ? 6 : 4,
        h: wide ? 3 : 4,
        color: Math.random() > 0.18 ? SPARKS[(Math.random() * SPARKS.length) | 0] : '#000000',
        t0: now,
        life: 180 + Math.random() * 180,
      });
    }
  };

  const resizeFx = () => {
    fxW = logo.offsetWidth + 36;
    fxH = logo.offsetHeight + 20;
    fxCtx = sizeCanvas(fx, fxW, fxH);
  };

  logo.addEventListener('pointerenter', (e) => {
    hovered = true;
    resizeFx();
    const rect = logo.getBoundingClientRect();
    pointer = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    spawn(pointer.x, pointer.y, performance.now());
    ensureLoop();
  });

  logo.addEventListener('pointermove', (e) => {
    const rect = logo.getBoundingClientRect();
    pointer = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    spawn(pointer.x, pointer.y, performance.now());
    ensureLoop();
  });

  logo.addEventListener('pointerleave', () => {
    hovered = false;
    ensureLoop();
  });
}

function setupDropTrail(reducedMotion) {
  const frame = document.querySelector('.drop-frame');
  const canvas = document.getElementById('drop-fx');
  if (!frame || !canvas || reducedMotion) return;

  const CW = 28;
  const CH = 14;
  let w = frame.clientWidth;
  let h = frame.clientHeight;
  let ctx = sizeCanvas(canvas, w, h);
  let lastBucket = '';
  let raf = 0;
  const cells = new Map();

  const resize = () => {
    w = frame.clientWidth;
    h = frame.clientHeight;
    ctx = sizeCanvas(canvas, w, h);
  };
  new ResizeObserver(resize).observe(frame);

  const addCell = (col, row, delay, now) => {
    if (col < 0 || row < 0 || col * CW >= w || row * CH >= h) return;
    const key = `${col},${row}`;
    if (cells.size >= 60 && !cells.has(key)) {
      const oldest = cells.keys().next().value;
      cells.delete(oldest);
    }
    const pastel = Math.random() < 0.45;
    cells.set(key, {
      col,
      row,
      start: now + delay,
      hold: 650 + Math.random() * 650,
      color: pastel ? BRICK_TINTS[(Math.random() * BRICK_TINTS.length) | 0] : '#dedbd4',
      maxAlpha: pastel ? 0.55 : 0.85,
    });
  };

  const tick = (now) => {
    raf = 0;
    ctx.clearRect(0, 0, w, h);
    for (const [key, cell] of cells) {
      const elapsed = now - cell.start;
      if (elapsed < 0) continue;
      const total = 80 + cell.hold + 340;
      if (elapsed >= total) {
        cells.delete(key);
        continue;
      }
      let alpha = 1;
      if (elapsed < 80) alpha = elapsed / 80;
      else if (elapsed > 80 + cell.hold) alpha = 1 - (elapsed - 80 - cell.hold) / 340;
      ctx.globalAlpha = Math.max(0, Math.min(1, alpha)) * cell.maxAlpha;
      ctx.fillStyle = cell.color;
      ctx.fillRect(cell.col * CW + 1, cell.row * CH + 1, CW - 2, CH - 2);
    }
    ctx.globalAlpha = 1;
    if (cells.size > 0) raf = requestAnimationFrame(tick);
  };

  frame.addEventListener('pointermove', (e) => {
    const rect = frame.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const col = Math.floor(x / CW);
    const row = Math.floor(y / CH);
    const bucket = `${col >> 1},${row >> 1}`;
    if (bucket === lastBucket) return;
    lastBucket = bucket;

    const now = performance.now();
    addCell(col, row, 0, now);
    const steps = 2 + ((Math.random() * 2) | 0);
    let cc = col;
    let cr = row;
    for (let i = 0; i < steps; i++) {
      if (Math.random() > 0.5) cc += Math.random() > 0.5 ? 1 : -1;
      else cr += Math.random() > 0.5 ? 1 : -1;
      addCell(cc, cr, 35 + i * 35, now);
    }
    if (!raf) raf = requestAnimationFrame(tick);
  });

  frame.addEventListener('pointerleave', () => {
    lastBucket = '';
  });
}

function setupFootmark(reducedMotion) {
  const zone = document.getElementById('foot-zone');
  const canvas = document.getElementById('foot-canvas');
  if (!zone || !canvas) return;

  let w = 0;
  let h = 0;
  let ctx = null;
  let wordCells = [];
  let glyphCells = [];
  let cellW = 12;
  let cellH = 6;
  let pointer = null;
  let lastSpark = 0;
  let raf = 0;
  const sparks = [];

  const rebuild = () => {
    const cs = getComputedStyle(zone);
    const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    w = Math.max(260, Math.floor(zone.clientWidth - padX));
    cellW = w < 520 ? 4 : w < 880 ? 8 : 12;
    cellH = Math.max(2, Math.round(cellW / 2));
    h = Math.max(64, Math.round(cellH * 14));
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx = sizeCanvas(canvas, w, h);

    const off = document.createElement('canvas');
    off.width = w;
    off.height = h;
    const octx = off.getContext('2d', { willReadFrequently: true });
    const fontSize = Math.min(Math.round(h * 0.72), Math.round(w * 0.095));
    octx.fillStyle = '#000';
    octx.font = `600 ${fontSize}px Geist, system-ui, sans-serif`;
    octx.textBaseline = 'middle';
    const text = 'actual converter';
    const textW = octx.measureText(text).width;
    const glyphSpan = cellW * 8;
    const gap = Math.round(cellW * 1.5);
    const totalW = textW + gap + glyphSpan;
    const startX = Math.max(0, (w - totalW) / 2);
    octx.fillText(text, startX, h * 0.53);

    const data = octx.getImageData(0, 0, w, h).data;
    wordCells = [];
    for (let y = 0; y < h; y += cellH) {
      for (let x = 0; x < w; x += cellW) {
        const sx = Math.min(w - 1, Math.floor(x + cellW / 2));
        const sy = Math.min(h - 1, Math.floor(y + cellH / 2));
        if (data[(sy * w + sx) * 4 + 3] > 108) {
          wordCells.push({ x, y, hitUntil: 0 });
        }
      }
    }

    glyphCells = [];
    const gx0 = Math.round((startX + textW + gap) / cellW) * cellW;
    const gy0 = Math.round((h - cellH * 8) / 2 / cellH) * cellH;
    for (const { r, c } of SWAP_CELLS) {
      glyphCells.push({
        x: gx0 + c * cellW,
        y: gy0 + r * cellH,
        color: SPECTRUM[Math.min(3, Math.floor((c / 7) * 4))],
        hitUntil: 0,
      });
    }
  };

  const draw = (now) => {
    raf = 0;
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);
    const gap = cellW > 8 ? 1 : 0.5;
    let active = false;
    const rx = Math.max(70, w * 0.11);
    const ry = Math.max(55, h * 0.8);

    for (const cell of wordCells) {
      if (pointer) {
        const jitter = 0.75 + 0.5 * hash(cell.x, cell.y);
        const dx = (cell.x + cellW / 2 - pointer.x) / (rx * jitter);
        const dy = ((cell.y + cellH / 2 - pointer.y) * 1.25) / (ry * jitter);
        if (dx * dx + dy * dy <= 1) cell.hitUntil = now + 260;
      }
      const lit = cell.hitUntil > now;
      if (lit) active = true;
      ctx.fillStyle = lit ? '#000000' : '#ededeb';
      ctx.fillRect(cell.x, cell.y, cellW - gap, cellH - gap);
    }

    for (const cell of glyphCells) {
      if (pointer) {
        const jitter = 0.75 + 0.5 * hash(cell.x, cell.y);
        const dx = (cell.x + cellW / 2 - pointer.x) / (rx * jitter);
        const dy = ((cell.y + cellH / 2 - pointer.y) * 1.25) / (ry * jitter);
        if (dx * dx + dy * dy <= 1) cell.hitUntil = now + 260;
      }
      const lit = cell.hitUntil > now;
      if (lit) active = true;
      ctx.fillStyle = lit ? cell.color : '#dcdcd8';
      ctx.fillRect(cell.x, cell.y, cellW - gap, cellH - gap);
    }

    for (let i = sparks.length - 1; i >= 0; i--) {
      const s = sparks[i];
      const age = now - s.t0;
      if (age >= s.life) {
        sparks.splice(i, 1);
        continue;
      }
      active = true;
      ctx.globalAlpha = 1 - age / s.life;
      ctx.fillStyle = s.color;
      ctx.fillRect(s.x, s.y, s.w, s.h);
    }
    ctx.globalAlpha = 1;

    if (pointer || active) raf = requestAnimationFrame(draw);
  };

  rebuild();
  draw(performance.now());
  document.fonts?.ready?.then(() => {
    rebuild();
    draw(performance.now());
  });

  let resizeTimer = 0;
  new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      rebuild();
      draw(performance.now());
    }, 80);
  }).observe(zone);

  if (reducedMotion) return;

  const ensureLoop = () => {
    if (!raf) raf = requestAnimationFrame(draw);
  };

  zone.addEventListener('pointermove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    pointer = { x: px, y: py };

    const now = performance.now();
    if (now - lastSpark > 45) {
      lastSpark = now;
      for (let i = 0; i < 2; i++) {
        if (sparks.length >= 28) sparks.shift();
        const angle = Math.random() * Math.PI * 2;
        const dist = Math.random() * Math.min(110, w * 0.11);
        const sx = Math.round((px + Math.cos(angle) * dist) / cellW) * cellW;
        const sy = Math.round((py + Math.sin(angle) * dist * 0.7) / cellH) * cellH;
        const wide = Math.random() > 0.4 ? 2 : 1;
        sparks.push({
          x: sx,
          y: sy,
          w: cellW * wide - 1,
          h: cellH - 1,
          color: SPARKS[(Math.random() * SPARKS.length) | 0],
          t0: now,
          life: 160 + Math.random() * 300,
        });
      }
    }
    ensureLoop();
  });

  zone.addEventListener('pointerleave', () => {
    pointer = null;
    ensureLoop();
  });
}

export function initPixelEffects() {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  setupBrandLogo(reducedMotion);
  setupDropTrail(reducedMotion);
  setupFootmark(reducedMotion);
}
