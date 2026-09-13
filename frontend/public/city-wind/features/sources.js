// 00 資料前提：七份來源 → 四個用途。
// 畫布畫出每份來源連到它用在哪裡的曲線，光點沿線流向用途；
// 游標移到來源卡，只亮它的線；移到用途，亮所有餵給它的來源。
import { S, Layer, PAL, rgba, section, smooth, clamp } from './core.js';

const bez = (a, b, c, d, t) => { const u = 1 - t; return u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d; };

export function initSources(el) {
  const stage = el.querySelector('.f-src-stage');
  const cv = new Layer(el.querySelector('.f-src-canvas'));
  const cards = [...el.querySelectorAll('.f-src')], nodes = [...el.querySelectorAll('.f-src-uses li')];
  const byK = Object.fromEntries(nodes.map(n => [n.dataset.k, n]));
  const links = [];
  cards.forEach((c, ci) => (c.dataset.use || '').split(' ').filter(Boolean).forEach((k, j) => byK[k] && links.push({ c, n: byK[k], k, right: c.classList.contains('r'), seed: (ci * .37 + j * .21) % 1 })));
  let hotCard = null, hotNode = null;

  function setHot(c, n) {
    hotCard = c; hotNode = n; const any = c || n;
    cards.forEach(card => {
      const uses = (card.dataset.use || '').split(' ');
      const on = card === c || (n && uses.includes(n.dataset.k));
      card.classList.toggle('hot', !!on); card.classList.toggle('dim', !!any && !on);
    });
    nodes.forEach(node => node.classList.toggle('hot', node === n || (c && (c.dataset.use || '').split(' ').includes(node.dataset.k))));
  }
  cards.forEach(c => {
    c.tabIndex = 0;
    c.addEventListener('pointerenter', () => setHot(c, null)); c.addEventListener('pointerleave', () => setHot(null, null));
    c.addEventListener('focus', () => setHot(c, null)); c.addEventListener('blur', () => setHot(null, null));
  });
  nodes.forEach(n => { n.addEventListener('pointerenter', () => setHot(null, n)); n.addEventListener('pointerleave', () => setHot(null, null)); });

  return section(el, {
    resize() { cv.resize(); },
    update(s) {
      if (S.mobile) return;
      const x = cv.ctx, host = stage.getBoundingClientRect();
      cv.clear();
      // 線條隨捲動畫出來：段落進到畫面四分之一後開始，一半時畫完
      const grow = S.reduced ? 1 : smooth(.2, .42, s.ps);
      for (const L of links) {
        const a = L.c.getBoundingClientRect(), b = L.n.getBoundingClientRect();
        const ax = (L.right ? a.left : a.right) - host.left, ay = a.top + a.height / 2 - host.top;
        const bx = (L.right ? b.right : b.left) - host.left, by = b.top + b.height / 2 - host.top;
        const mx = (ax + bx) / 2;
        const lit = (hotCard && hotCard === L.c) || (hotNode && hotNode === L.n);
        const faded = (hotCard || hotNode) && !lit;
        const col = L.right ? PAL.meas : PAL.gold;
        // 只畫到 grow 的比例：用 16 段折線近似貝茲曲線
        x.lineWidth = lit ? 1.8 : 1; x.strokeStyle = rgba(col, faded ? .06 : lit ? .75 : .22);
        x.beginPath(); x.moveTo(ax, ay);
        const steps = 22, upto = Math.max(1, Math.round(steps * grow));
        for (let i = 1; i <= upto; i++) { const t = i / steps; x.lineTo(bez(ax, mx, mx, bx, t), bez(ay, ay, by, by, t)); }
        x.stroke();
        if (grow < 1 || faded) continue;
        // 資料往用途流：每條線 3 顆光點
        for (let k = 0; k < 3; k++) {
          const t = ((S.reduced ? .5 : S.t * (lit ? .42 : .2)) + L.seed + k / 3) % 1;
          const px = bez(ax, mx, mx, bx, t), py = bez(ay, ay, by, by, t), r = lit ? 2.6 : 1.7;
          x.fillStyle = rgba(col, lit ? .95 : .55); x.beginPath(); x.arc(px, py, r, 0, Math.PI * 2); x.fill();
          if (lit) { x.fillStyle = rgba(col, .16); x.beginPath(); x.arc(px, py, r * 3.4, 0, Math.PI * 2); x.fill(); }
        }
      }
      // 用途節點外圈：有來源在亮時跟著呼吸
      for (const n of nodes) {
        if (!n.classList.contains('hot')) continue;
        const b = n.getBoundingClientRect(), cx = b.left + b.width / 2 - host.left, cy = b.top + b.height / 2 - host.top;
        const pulse = S.reduced ? .5 : (Math.sin(S.t * 3) + 1) / 2;
        x.strokeStyle = rgba(PAL.gold, .25 * (1 - pulse)); x.lineWidth = 1;
        x.beginPath(); x.ellipse(cx, cy, b.width / 2 + 8 + pulse * 14, b.height / 2 + 6 + pulse * 10, 0, 0, Math.PI * 2); x.stroke();
      }
      x.globalAlpha = 1; void clamp;
    }
  });
}
