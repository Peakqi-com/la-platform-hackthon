// 結尾：一路吹來的風，最後聚成網站的標誌（三棟樓的天際線），接著是進入系統的入口。
// 點聚好之後底下補一條實線，形狀才不會因為點距不均或閃爍而看起來斷掉。
import { S, Layer, PAL, rgba, section, lerp, smooth, rng } from './core.js';

// 與 favicon 同一組三棟樓（M7 24V14h5v10 m3 0V7h5v17 m3 0V12h3），第三棟補上右側那條線成為完整樓形；
// 另加一條地平線（與樓底同高，才接得上）
const GLYPH = [[[7, 24], [7, 14], [12, 14], [12, 24]], [[15, 24], [15, 7], [20, 7], [20, 24]], [[23, 24], [23, 12], [27, 12], [27, 24]], [[4, 24], [30, 24]]];

export function initEnd(el) {
  const cv = new Layer(el.querySelector('.f-end-canvas'), { max: 2 }), R = rng(3);
  const N = S.low ? 180 : 280;
  // 沿路徑等距取點
  const segs = []; let total = 0;
  for (const line of GLYPH) for (let i = 1; i < line.length; i++) { const a = line[i - 1], b = line[i], l = Math.hypot(b[0] - a[0], b[1] - a[1]); segs.push([a, b, l]); total += l; }
  const home = Array.from({ length: N }, (_, k) => {
    let d = (k / N) * total;
    for (const [a, b, l] of segs) { if (d <= l) { const t = d / l; return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]; } d -= l; }
    return GLYPH[0][0];
  });
  const ps = home.map(() => ({ sx: R(), sy: R(), ph: R() * 6.28, sp: .4 + R() * .8 }));
  const inner = el.querySelector('.f-end-inner');

  return section(el, {
    resize() { cv.resize(); },
    update(s) {
      const x = cv.ctx, W = cv.w, H = cv.h; cv.clear();
      // 聚合進度：文字區進到畫面前就完成；接近完成時直接吸附到位，不留下偏移的點
      const a0 = S.reduced ? 1 : smooth(.06, .34, s.ps), a = a0 > .985 ? 1 : a0;
      // 標誌的底線落在文字區塊上方 26 px：不和眉標、標題重疊
      const size = Math.min(W * .24, 180), ox = W / 2 - size / 2;
      const oy = inner.getBoundingClientRect().top - cv.c.getBoundingClientRect().top - 26 - size * .72 * .9;
      const P = ([gx, gy]) => [ox + (gx - 3) / 26 * size, oy + (gy - 6) / 20 * size * .72];
      // 聚好之後的實線
      const solid = smooth(.7, 1, a);
      if (solid > 0) {
        x.save(); x.strokeStyle = rgba(PAL.gold, .8 * solid); x.lineWidth = 2; x.lineCap = 'square'; x.lineJoin = 'miter';
        for (const line of GLYPH) { x.beginPath(); line.forEach((q, i) => { const [X, Y] = P(q); i ? x.lineTo(X, Y) : x.moveTo(X, Y); }); x.stroke(); }
        x.restore();
      }
      // 點：亮度一致；聚好之後只有一道光沿路徑慢慢流過
      const wave = (S.t * .28) % 1;
      ps.forEach((p, i) => {
        const [tx, ty] = P(home[i]);
        const wx = ((p.sx * W + S.t * 40 * p.sp) % (W + 40)) - 20, wy = p.sy * H + Math.sin(S.t * p.sp + p.ph) * 20;
        const px = lerp(wx, tx, a), py = lerp(wy, ty, a);
        const glow = a >= 1 && !S.reduced ? Math.max(0, 1 - Math.abs(i / N - wave) * 14) : 0;
        x.fillStyle = rgba(glow > 0 ? PAL.sand : PAL.gold, Math.min(1, .3 + .6 * a + glow * .35));
        x.beginPath(); x.arc(px, py, lerp(1.2, 1.6, a) + glow * .9, 0, 6.283); x.fill();
      });
    }
  });
}
