// 系統功能段的背景：延續首頁「起風」的流線。
// 兩層畫布＝兩個景深：遠層是地籍網格與細小的風，近層是較長、較亮的風。
// 每條風記住最近幾個位置，畫成順著流場彎曲的尾跡。
//
// 閱讀優先：
//  1) 風的強度跟著捲動走：捲動時明顯（越快越明顯），停下來閱讀就慢慢淡到很低；
//  2) 文字區塊（標題、內文、卡片）底下一律擦掉，風只在留白處流動，不從字後面穿過。
// 捲動時兩層以不同速度往上移（視差）；滑鼠靠近時風會繞開。
import { S, Layer, PAL, clamp, lerp, onFrame, onMeasure, mixRGB, rgbStr, rng, sections } from './core.js';

const HIST = 7, SAMPLE = .085;                     // 尾跡長度：7 個取樣點，每 0.085 秒取一次
const IDLE = .16;                                  // 停止捲動時保留的強度
// 需要保護的閱讀區：各段的文字欄、進場區塊、卡片與面板
const READ_SEL = '.f-copy, .f-rv, .f-fut-head, .f-fut-intro, .f-fut-card, .f-panel, .f-src-uses li';

export function initAmbient(host) {
  const far = new Layer(host.querySelector('.f-amb-far'), { max: 1.5 });
  const mid = new Layer(host.querySelector('.f-amb-mid'), { max: 1.75 });
  const rand = rng(11);
  const N = S.low ? 110 : 200;
  const ps = Array.from({ length: N }, () => ({ hx: new Float32Array(HIST), hy: new Float32Array(HIST), hn: 0, acc: 0 }));
  const readCache = new Map();
  let tint = mixRGB(PAL.gold, PAL.gold, 0), gridShift = 0, seeded = false, energy = IDLE;

  function spawn(p, anywhere) {
    p.z = rand();                                   // 0 遠 … 1 近
    p.x = anywhere ? rand() * far.w : -20 - rand() * 80;
    p.y = rand() * far.h;
    p.life = anywhere ? rand() * .8 : 0; p.span = 6 + rand() * 8; p.hn = 0; p.acc = rand() * SAMPLE;
  }
  // 第一次量到尺寸才撒點；之前畫布寬高都是 1，會全部擠在左上角
  onMeasure(() => { far.resize(); mid.resize(); readCache.clear(); if (!seeded && far.w > 2) { seeded = true; ps.forEach(p => spawn(p, true)); } });

  // 目前畫面上的閱讀區（畫布座標）：只查看得到的段落
  function readingRects() {
    const out = [], top = far.c.getBoundingClientRect().top;
    for (const s of sections()) {
      if (!s.vis) continue;
      let els = readCache.get(s.el); if (!els) { els = [...s.el.querySelectorAll(READ_SEL)]; readCache.set(s.el, els); }
      for (const el of els) {
        const b = el.getBoundingClientRect();
        if (b.width < 1 || b.bottom < 0 || b.top > S.vh) continue;
        out.push([b.left, b.top - top, b.width, b.height]);
      }
    }
    return out;
  }
  // 擦掉閱讀區：外圈半透明（柔邊），內圈全擦
  function erase(x, rects) {
    x.save(); x.globalCompositeOperation = 'destination-out';
    for (const [l, t, w, h] of rects) {
      x.fillStyle = 'rgba(0,0,0,.5)'; x.fillRect(l - 34, t - 26, w + 68, h + 52);
      x.fillStyle = '#000'; x.fillRect(l - 14, t - 10, w + 28, h + 20);
    }
    x.restore();
  }

  // 平滑的流場：幾個不同頻率的正弦疊起來，整體由西往東吹
  const angle = (x, y, t) => Math.sin(x * .0021 + t * .05) * .55 + Math.cos(y * .0029 - t * .04) * .45 + Math.sin((x + y) * .0012 + t * .03) * .35 - .08;

  onFrame(() => {
    if (!seeded) return;
    const t = S.t, dt = S.reduced ? 0 : S.dt, W = far.w, H = far.h;
    const want = S.active?.dataset?.tint || PAL.gold, target = mixRGB(want, want, 0);
    tint = [lerp(tint[0], target[0], .04), lerp(tint[1], target[1], .04), lerp(tint[2], target[2], .04)];
    // 強度：捲動時很快升上來，停下來後約兩秒淡回 IDLE；精簡動態時不畫風
    const goal = S.reduced ? 0 : clamp(IDLE + Math.abs(S.vel) / 900, 0, 1);
    energy = lerp(energy, goal, 1 - Math.exp(-S.dt * (goal > energy ? 7 : 1.4)));
    const gust = clamp(Math.abs(S.vel) / 1400, 0, 1.6);
    far.clear(); mid.clear();

    // 遠層：斜向的地籍網格，捲動時只移動一點點（最遠的一層）
    gridShift = (gridShift + S.dy * .12) % 180;
    const fx = far.ctx; fx.save(); fx.strokeStyle = 'rgba(230,236,225,.04)'; fx.lineWidth = 1;
    fx.translate(W * .5 + S.snx * -10, H * .5 - gridShift + S.sny * -8); fx.rotate(-.42);
    const span = Math.hypot(W, H);
    fx.beginPath();
    for (let gx = -span; gx < span; gx += 90) { fx.moveTo(gx, -span); fx.lineTo(gx, span); }
    for (let gy = -span; gy < span; gy += 60) { fx.moveTo(-span, gy); fx.lineTo(span, gy); }
    fx.stroke(); fx.restore();

    const mxr = S.hasMouse && !S.reduced ? 170 : 0;
    const buckets = [[], [], []];
    for (const p of ps) {
      const shift = S.dy * (.1 + p.z * .55);           // 視差：越近捲得越快
      if (dt > 0) {
        const a = angle(p.x, p.y + S.y * .15, t), sp = (26 + p.z * 64) * (1 + gust * 1.4);
        let vx = Math.cos(a) * sp, vy = Math.sin(a) * sp * .6;
        if (mxr) {                                  // 風繞過游標
          const dx = p.x - S.mx, dy = p.y - S.my, d = Math.hypot(dx, dy);
          if (d < mxr && d > 1) { const f = (1 - d / mxr) ** 2 * 140; vx += (dx / d) * f + (-dy / d) * f * .8; vy += (dy / d) * f + (dx / d) * f * .8; }
        }
        p.x += vx * dt; p.y += vy * dt; p.life += dt / p.span;
        p.acc += dt;
        if (p.acc >= SAMPLE) {
          p.acc = 0;
          for (let i = HIST - 1; i > 0; i--) { p.hx[i] = p.hx[i - 1]; p.hy[i] = p.hy[i - 1]; }
          p.hx[0] = p.x; p.hy[0] = p.y; p.hn = Math.min(HIST, p.hn + 1);
        }
      }
      p.y -= shift; for (let i = 0; i < p.hn; i++) p.hy[i] -= shift;
      if (p.x > W + 60 || p.life >= 1) spawn(p, false);
      else if (p.y < -60 || p.y > H + 60) { p.y = p.y < 0 ? p.y + H + 100 : p.y - H - 100; p.hn = 0; }
      const fade = Math.sin(clamp(p.life, 0, 1) * Math.PI);
      buckets[fade < .35 ? 0 : fade < .7 ? 1 : 2].push(p);
    }
    if (energy < .01) return;
    const draw = (layer, near) => {
      const x = layer.ctx; x.lineCap = 'round'; x.lineJoin = 'round';
      buckets.forEach((list, bi) => {
        x.strokeStyle = rgbStr(tint, (near ? [.1, .22, .36] : [.05, .1, .17])[bi] * energy); x.lineWidth = near ? 1.25 : .8; x.beginPath();
        for (const p of list) {
          if ((p.z > .55) !== near || p.hn < 2) continue;
          x.moveTo(p.x, p.y); for (let i = 0; i < p.hn; i++) x.lineTo(p.hx[i], p.hy[i]);
        }
        x.stroke();
      });
    };
    draw(far, false); draw(mid, true);
    const rects = readingRects();
    erase(far.ctx, rects); erase(mid.ctx, rects);
  });
}
