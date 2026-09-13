// 系統功能段的共用引擎：捲動進度、視差、畫布、時間。
// 不依賴 three.js：3D 場景掛掉時，這一段照樣可以讀、可以操作。
// 捲動只改 transform 與 canvas，不改版面屬性。

export const root = document.documentElement;
export const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
export const lerp = (a, b, t) => a + (b - a) * t;
export const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
export const easeOut = t => 1 - Math.pow(1 - clamp(t, 0, 1), 3);
export const easeInOut = t => { t = clamp(t, 0, 1); return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
export const TAU = Math.PI * 2;

export const PAL = {
  bg: '#091313', fg: '#f2f1e9', muted: '#aebbb6', gold: '#e3ac78', line: 'rgba(230,236,225,.18)',
  ok: '#9fd3ad', warn: '#e9c46a', err: '#ef8a6f', meas: '#7fc8cf', panel: '#0c1a1b', ink2: '#cdd8d2', sand: '#ffe2b7', leaf: '#c6e4cc'
};
const hexCache = new Map();
function hex3(h) {
  if (hexCache.has(h)) return hexCache.get(h);
  const n = parseInt(h.slice(1), 16), v = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  hexCache.set(h, v); return v;
}
export const rgba = (h, a) => { const [r, g, b] = hex3(h); return `rgba(${r},${g},${b},${a})`; };
export const mixRGB = (a, b, t) => { const x = hex3(a), y = hex3(b); return [lerp(x[0], y[0], t), lerp(x[1], y[1], t), lerp(x[2], y[2], t)]; };
export const rgbStr = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
export const FONT = "'Noto Sans TC', sans-serif";
export const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

// 小型可重現亂數：同一段每次載入畫面一致，截圖才對得起來
export function rng(seed = 7) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

/* ── 全域狀態 ── */
const media = matchMedia('(prefers-reduced-motion: reduce)');
const motionBtn = document.querySelector('#motion');
const forcedQ = (new URLSearchParams(location.search).get('q') || '').toUpperCase();
export const S = {
  vw: innerWidth, vh: innerHeight, y: scrollY, dy: 0, vel: 0, t: 0, dt: 0,
  mx: innerWidth / 2, my: innerHeight / 2, nx: 0, ny: 0, snx: 0, sny: 0, hasMouse: false,
  reduced: media.matches, mobile: innerWidth <= 900,
  low: forcedQ === 'LOW' || (forcedQ !== 'HIGH' && (matchMedia('(pointer:coarse)').matches || (navigator.hardwareConcurrency || 4) <= 4)),
  active: null
};
function readReduced() { S.reduced = motionBtn ? motionBtn.getAttribute('aria-pressed') === 'true' : media.matches; }
readReduced();
if (motionBtn) new MutationObserver(readReduced).observe(motionBtn, { attributes: true, attributeFilter: ['aria-pressed'] });
media.addEventListener('change', readReduced);
addEventListener('pointermove', e => { if (e.pointerType === 'touch') return; S.mx = e.clientX; S.my = e.clientY; S.nx = S.mx / S.vw * 2 - 1; S.ny = S.my / S.vh * 2 - 1; S.hasMouse = true; }, { passive: true });
document.addEventListener('pointerleave', () => { S.nx = 0; S.ny = 0; S.hasMouse = false; });

/* ── 畫布層：處理 DPR 與尺寸 ── */
export class Layer {
  constructor(canvas, { max = 2, scale = 1 } = {}) { this.c = canvas; this.ctx = canvas.getContext('2d'); this.max = max; this.scale = scale; this.w = 1; this.h = 1; this.r = 1; }
  resize() {
    // 用版面尺寸（offsetWidth/Height），不用 getBoundingClientRect：
    // 圖層套了 3D 旋轉時，後者回傳的是投影後的外框，畫布會被量成歪的尺寸。
    const bw = this.c.offsetWidth, bh = this.c.offsetHeight, r = Math.min(devicePixelRatio || 1, this.max) * this.scale;
    const w = clamp(Math.round(bw * r), 1, 4096), h = clamp(Math.round(bh * r), 1, 4096);
    if (w !== this.c.width || h !== this.c.height) { this.c.width = w; this.c.height = h; }
    this.w = Math.max(1, bw); this.h = Math.max(1, bh); this.r = r; this.ctx.setTransform(r, 0, 0, r, 0, 0); return this;
  }
  clear() { const x = this.ctx; x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, this.c.width, this.c.height); x.setTransform(this.r, 0, 0, this.r, 0, 0); }
}

// 以畫布座標取得某個 DOM 元素的中心（元素與畫布同在一個定位容器內時用）
export function centerIn(el, host) { const a = el.getBoundingClientRect(), b = host.getBoundingClientRect(); return { x: a.left - b.left + a.width / 2, y: a.top - b.top + a.height / 2, w: a.width, h: a.height }; }

/* ── 段落登錄與捲動進度 ──
   pinned：段落黏住期間 0→1；flow：段落從畫面底部進來到頂部離開 0→1 */
const secs = [], frameHooks = [], measureHooks = [];
export function section(el, ctrl = {}) {
  const s = { el, ctrl, id: el.id, top: 0, h: 1, p: 0, ps: 0, vis: false, pinned: el.classList.contains('f-pin'), pars: [...el.querySelectorAll('[data-par],[data-mouse]')], booted: false };
  secs.push(s); return s;
}
export const onFrame = fn => frameHooks.push(fn);
export const onMeasure = fn => measureHooks.push(fn);
export const sections = () => secs;
export function progressOf(s, y = S.y) {
  return s.pinned ? clamp((y - s.top) / Math.max(1, s.h - S.vh), 0, 1) : clamp((y + S.vh - s.top) / Math.max(1, s.h + S.vh), 0, 1);
}
export function measure() {
  S.vw = innerWidth; S.vh = innerHeight; S.mobile = S.vw <= 900;
  for (const s of secs) { const b = s.el.getBoundingClientRect(); s.top = b.top + scrollY; s.h = s.el.offsetHeight; s.p = progressOf(s); if (!s.booted) s.ps = s.p; }
  for (const fn of measureHooks) fn();
  for (const s of secs) s.ctrl.resize?.(s);
}
// 捲到某段：pinned 可指定段內位置（0～1）
export function goTo(el, frac = 0) {
  const s = secs.find(x => x.el === el);
  const top = s ? s.top + (s.pinned ? frac * (s.h - S.vh) : 0) : el.getBoundingClientRect().top + scrollY;
  scrollTo({ top: Math.max(0, top), behavior: S.reduced ? 'instant' : 'smooth' });
}

/* ── 主迴圈：只在系統功能範圍附近才跑 ── */
let running = false, last = performance.now(), nearFeatures = false;
export function setNear(v) { nearFeatures = v; if (v && !running) { running = true; last = performance.now(); requestAnimationFrame(tick); } }
function tick(now) {
  if (!nearFeatures) { running = false; return; }
  requestAnimationFrame(tick);
  if (document.hidden) { last = now; return; }
  const dt = clamp((now - last) / 1000, 0, .05); last = now; S.dt = dt; S.t += dt;
  const y = scrollY; S.dy = y - S.y; S.y = y; S.vel = lerp(S.vel, S.dy / Math.max(dt, 1e-3), 1 - Math.exp(-dt * 6));
  const k = 1 - Math.exp(-dt * 5); S.snx = lerp(S.snx, S.nx, k); S.sny = lerp(S.sny, S.ny, k);
  const kp = S.reduced ? 1 : 1 - Math.exp(-dt * 9);
  for (const s of secs) {
    s.p = progressOf(s, y);
    if (!s.vis) continue;
    s.ps = lerp(s.ps, s.p, kp); if (Math.abs(s.ps - s.p) < 1e-4) s.ps = s.p;
    for (const el of s.pars) {
      const par = +el.dataset.par || 0, m = S.reduced ? 0 : (+el.dataset.mouse || 0);
      const oy = S.reduced ? 0 : (.5 - s.ps) * par * S.vh * (s.pinned ? .8 : 1);
      el.style.transform = `translate3d(${(S.snx * m).toFixed(2)}px,${(oy + S.sny * m).toFixed(2)}px,0)`;
    }
    s.ctrl.update?.(s);
  }
  for (const fn of frameHooks) fn();
}

// 讓各段在第一次進入畫面前就量好尺寸
export function watchVisibility() {
  const io = new IntersectionObserver(entries => {
    for (const e of entries) {
      const s = secs.find(x => x.el === e.target); if (!s) continue;
      s.vis = e.isIntersecting;
      if (s.vis && !s.booted) { s.booted = true; s.p = s.ps = progressOf(s); s.ctrl.enter?.(s); }
      s.ctrl.visible?.(s, s.vis);
    }
  }, { rootMargin: '12% 0px 12% 0px' });
  secs.forEach(s => io.observe(s.el));
}
export function watchReveals(scope) {
  const els = [...scope.querySelectorAll('.f-rv')];
  const io = new IntersectionObserver(entries => { for (const e of entries) if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); } }, { threshold: .12 });
  els.forEach(el => io.observe(el));
}

/* ── 畫圖小工具 ── */
export function roundRect(x, X, Y, w, h, r) { x.beginPath(); x.moveTo(X + r, Y); x.arcTo(X + w, Y, X + w, Y + h, r); x.arcTo(X + w, Y + h, X, Y + h, r); x.arcTo(X, Y + h, X, Y, r); x.arcTo(X, Y, X + w, Y, r); x.closePath(); }
// 沿折線取長度 d 處的點
export function polyLen(pts) { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return L; }
export function pointAt(pts, d) {
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], l = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (d <= l || i === pts.length - 1) { const t = l ? clamp(d / l, 0, 1) : 0; return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, Math.atan2(b[1] - a[1], b[0] - a[0])]; }
    d -= l;
  }
  return [pts[0][0], pts[0][1], 0];
}
// 只畫折線的前 d 段
export function strokePartial(x, pts, d) {
  x.beginPath(); x.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], l = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (d >= l) { x.lineTo(b[0], b[1]); d -= l; } else { const t = d / l; x.lineTo(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t); break; }
  }
  x.stroke();
}
