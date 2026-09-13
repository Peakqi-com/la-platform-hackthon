// 01 一條鏈：釘住的段落，捲動驅動三個階段。
//   0 痛點：遠層三張表單飄著，錯的格子在閃
//   1 正著算：光沿著十個節點走完價格鏈
//   2 反著審：另一道掃描從地價倒走回事實，逐節點標相符／不符
// 節點是 DOM 按鈕（可 Tab、可點），畫布只畫路徑、光點與表單。
import { S, Layer, PAL, rgba, section, smooth, clamp, lerp, centerIn, polyLen, pointAt, strokePartial, rng, FONT } from './core.js';

const NODES = [
  { d: '送審書表抽取、圖資量測或系統推定；每筆距離都帶資料集、量測方式與起點。', ex: '面前道路寬度　比準地 18 m ／ 比較標的 6 m', b: '作業手冊 p.24 8(2)(3)：需通達者量路線距離，嫌惡設施量直線' },
  { d: '依評價基準明細表的判定條件分級，每一級都指得回基準表的一格。', ex: '18 m → 稍優（15–20 m）；6 m → 稍劣（4–8 m）', b: '評價基準明細表 項目 14；手冊 p.52 (八)2' },
  { d: '比準地與比較標的的等級差，查修正矩陣。', ex: '（稍劣 3 − 稍優 1）× 2.50 ＝ 5.00%', b: '評價基準明細表 項目 14，最大修正率 10%' },
  { d: '各主要項目的細項相加為小計，小計相加為總修正數。', ex: '區域因素總修正數 0.00%（同一區段）', b: '手冊 p.49 (六)3(3)(4)' },
  { d: '區域因素分析明細表的總修正數，抄進比較法調查估價表。', ex: '表5 總修正數 0.00% → 表4 區域因素調整 0.00%', b: '手冊 p.49 (六)3(4)（跨表抄填）' },
  { d: '表4 第 7～25 項逐項查矩陣後加總；免修正以「-」表示，與 0 區分。', ex: '個別因素合計 13.00%', b: '查估辦法 §19、§20；手冊 p.52 (七)2' },
  { d: '正常單價依期日、區域、個別因素連乘調整，不是相加。', ex: '184,763 × 1.02 → 188,459；× 1.00 × 1.13 ＝ 212,958', b: '查估辦法 §17、§19；手冊 p.100–101 官方算例反證連乘' },
  { d: '調整百分率絕對值加總愈小，權重愈大。', ex: '三件 50／30／20；範本只有一件，權重 100%', b: '手冊 p.53 (十)(十一)' },
  { d: 'Σ 試算價格 × 權重，四捨五入至個位。', ex: '比較價格 212,958 元/m²', b: '手冊 p.53 (十二)' },
  { d: '依尾數規則無條件進位：逾 10 萬元者進位至千位。', ex: '212,958 → 213,000 元/m²', b: '查估辦法 §21；手冊 p.10 六(六)' }
];
// 反向審查的示範：範例二（含填載錯誤）在鏈上出錯的三個位置
const BAD = {
  2: '填載 2.50% ≠ 核算 5.00%：差異率與個別因素基準表矩陣不符',
  3: '填載 1.00% ≠ 核算 0.00%：小計、總修正數加總錯誤',
  4: '填載 1.00% ≠ 核算 0.00%：與區域因素分析明細表總修正數不符（跨表抄填）'
};

export function initChain(el) {
  const vis = el.querySelector('.f-chain-vis'), list = el.querySelector('.f-chain-nodes');
  const mid = new Layer(el.querySelector('.f-chain-mid')), far = new Layer(el.querySelector('.f-chain-far'), { max: 1.5 });
  const btns = [...el.querySelectorAll('.f-node')], steps = [...el.querySelectorAll('.f-step')], card = el.querySelector('.f-node-card');
  let pts = [], cum = [], L = 1, sel = null, pinned = null, shownKey = '', step = -1;

  // 表單（遠層）：三張，各自的景深
  const R = rng(5);
  const FORMS = [
    { name: '地價區段勘查表', x: .66, y: .3, w: .2, h: .5, rows: 26, cols: 3, z: .35, rot: -.08 },
    { name: '區域因素分析明細表', x: .86, y: .52, w: .16, h: .42, rows: 30, cols: 5, z: .6, rot: .06 },
    { name: '比較法調查估價表', x: .56, y: .72, w: .3, h: .3, rows: 22, cols: 8, z: .85, rot: -.03 }
  ].map(f => ({ ...f, bad: Array.from({ length: 5 }, () => [Math.floor(R() * f.rows), Math.floor(R() * f.cols), R() * 6]) }));

  function layoutNodes() {
    const mobile = S.mobile;
    btns.forEach((b, i) => {
      const li = b.parentElement; let r, c;
      if (mobile) { r = Math.floor(i / 2) + 1; c = r % 2 ? (i % 2) + 1 : 2 - (i % 2); } else { r = i < 5 ? 1 : 2; c = i < 5 ? i + 1 : 10 - i; }
      li.style.gridRow = String(r); li.style.gridColumn = String(c);
    });
  }
  function measurePath() {
    pts = btns.map(b => { const c = centerIn(b, vis); return [c.x, c.y]; });
    cum = [0]; for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    L = Math.max(1, cum[cum.length - 1]);
  }
  function showCard(i, mode) {
    const key = i + mode; if (key === shownKey) return; shownKey = key;
    if (i == null) { card.innerHTML = `<span class="k">範本案例</span><h3>金山區 P002-00・金美段 489 地號</h3><p>比較標的 1 件（溫泉段 218 地號）。往下捲，看這條鏈怎麼從事實算到地價，再怎麼反過來審。</p>`; return; }
    const n = NODES[i], name = btns[i].querySelector('b').textContent;
    const verdict = mode === 'rev' ? (BAD[i] ? `<span class="f-badge err verdict">不符</span>` : `<span class="f-badge ok verdict">相符</span>`) : '';
    const line = mode === 'rev' && BAD[i] ? `<p style="color:var(--err)">範例二：${BAD[i]}</p>` : `<p class="ex">${n.ex}</p>`;
    card.innerHTML = `${verdict}<span class="k">${String(i + 1).padStart(2, '0')} / 10</span><h3>${name}</h3><p>${n.d}</p>${line}<p class="basis">依據：${n.b}</p>`;
  }
  btns.forEach((b, i) => {
    b.addEventListener('pointerenter', () => { sel = i; }); b.addEventListener('pointerleave', () => { sel = null; });
    b.addEventListener('focus', () => { sel = i; }); b.addEventListener('blur', () => { sel = null; });
    b.addEventListener('click', () => { pinned = pinned === i ? null : i; b.setAttribute('aria-pressed', String(pinned === i)); });
  });

  function drawForms(s, phase0) {
    const x = far.ctx, W = far.w, H = far.h; far.clear();
    const alpha = lerp(.9, .28, smooth(.2, .36, s.ps));
    for (const f of FORMS) {
      const oy = S.reduced ? 0 : (.5 - s.ps) * H * f.z * .5, ox = S.snx * -18 * f.z;
      const w = W * f.w, h = H * f.h, cx = W * f.x + ox, cy = H * f.y + oy + (S.reduced ? 0 : Math.sin(S.t * .4 + f.z * 5) * 6);
      x.save(); x.translate(cx, cy); x.rotate(f.rot); x.globalAlpha = alpha * (.45 + f.z * .55);
      x.fillStyle = 'rgba(12,26,27,.72)'; x.fillRect(-w / 2, -h / 2, w, h);
      x.strokeStyle = 'rgba(230,236,225,.16)'; x.lineWidth = 1; x.beginPath();
      const cw = w / f.cols, rh = (h - 22) / f.rows;
      for (let c = 0; c <= f.cols; c++) { x.moveTo(-w / 2 + c * cw, -h / 2 + 22); x.lineTo(-w / 2 + c * cw, h / 2); }
      for (let r = 0; r <= f.rows; r++) { x.moveTo(-w / 2, -h / 2 + 22 + r * rh); x.lineTo(w / 2, -h / 2 + 22 + r * rh); }
      x.stroke(); x.strokeStyle = 'rgba(230,236,225,.3)'; x.strokeRect(-w / 2, -h / 2, w, h);
      x.fillStyle = PAL.muted; x.font = `11px ${FONT}`; x.fillText(f.name, -w / 2 + 8, -h / 2 + 15);
      // 痛點階段：錯的格子閃紅
      for (const [r, c, ph] of f.bad) {
        const k = phase0 * (S.reduced ? .8 : .5 + .5 * Math.sin(S.t * 2.6 + ph));
        x.fillStyle = rgba(PAL.err, .55 * k); x.fillRect(-w / 2 + c * cw + 1, -h / 2 + 22 + r * rh + 1, cw - 2, rh - 2);
      }
      x.restore();
    }
    // 跨表抄填的虛線：勘查表 → 表5 → 表4
    if (phase0 > .02) {
      x.save(); x.globalAlpha = phase0 * .8; x.setLineDash([5, 6]); x.lineDashOffset = S.reduced ? 0 : -S.t * 20; x.strokeStyle = rgba(PAL.err, .6);
      const P = FORMS.map(f => [W * f.x + S.snx * -18 * f.z, H * f.y + (S.reduced ? 0 : (.5 - s.ps) * H * f.z * .5)]);
      x.beginPath(); x.moveTo(P[0][0], P[0][1]); x.quadraticCurveTo(W * .8, H * .25, P[1][0], P[1][1]); x.quadraticCurveTo(W * .8, H * .8, P[2][0], P[2][1]); x.stroke(); x.restore();
    }
  }

  return section(el, {
    resize() { layoutNodes(); mid.resize(); far.resize(); measurePath(); },
    enter() { layoutNodes(); measurePath(); showCard(null, ''); },
    update(s) {
      // 每一幀重新量節點中心：下方說明卡換內容時高度會變，節點區跟著被壓矮、第二排往上移。
      // 只在進場時量一次的話，線會停在舊位置，下排的線就跑到方塊底邊。
      measurePath();
      const p = s.ps, next = p < .3 ? 0 : p < .66 ? 1 : 2;
      if (next !== step) { step = next; steps.forEach((st, i) => st.classList.toggle('on', i === step)); }
      const phase0 = 1 - smooth(.22, .34, p), fwd = S.reduced ? (p >= .3 ? 1 : 0) : smooth(.3, .6, p), rev = S.reduced ? (p >= .66 ? 1 : 0) : smooth(.68, .93, p);
      drawForms(s, phase0);
      const x = mid.ctx; mid.clear(); if (pts.length < 2) return;
      x.lineCap = 'round'; x.lineJoin = 'round';
      x.strokeStyle = 'rgba(230,236,225,.16)'; x.lineWidth = 1.5; x.beginPath(); pts.forEach((q, i) => i ? x.lineTo(q[0], q[1]) : x.moveTo(q[0], q[1])); x.stroke();
      const head = fwd * L;
      if (fwd > 0) {
        x.strokeStyle = rgba(PAL.gold, .16); x.lineWidth = 9; strokePartial(x, pts, head);
        x.strokeStyle = rgba(PAL.gold, .9); x.lineWidth = 2; strokePartial(x, pts, head);
        // 沿線流動的光點：數字一路往下游帶
        const n = S.low ? 14 : 26;
        for (let k = 0; k < n; k++) {
          const d = ((k / n) * L + (S.reduced ? 0 : S.t * 60)) % L; if (d > head) continue;
          const [px, py] = pointAt(pts, d); x.fillStyle = rgba(PAL.sand, .75); x.beginPath(); x.arc(px, py, 1.8, 0, 6.283); x.fill();
        }
        if (fwd < 1) { const [hx, hy] = pointAt(pts, head); const g = x.createRadialGradient(hx, hy, 0, hx, hy, 26); g.addColorStop(0, rgba(PAL.gold, .85)); g.addColorStop(1, rgba(PAL.gold, 0)); x.fillStyle = g; x.beginPath(); x.arc(hx, hy, 26, 0, 6.283); x.fill(); }
      }
      // 反向掃描：由地價倒走回事實
      const scan = L - rev * L;
      if (rev > 0 && rev < 1) {
        const [sx, sy] = pointAt(pts, scan);
        x.strokeStyle = rgba(PAL.meas, .9); x.lineWidth = 1.5;
        for (let k = 0; k < 2; k++) { const rr = 14 + ((S.t * 22 + k * 12) % 24); x.globalAlpha = 1 - (rr - 14) / 24; x.beginPath(); x.arc(sx, sy, rr, 0, 6.283); x.stroke(); }
        x.globalAlpha = 1;
      }
      let latest = null, latestRev = null;
      btns.forEach((b, i) => {
        const lit = fwd > 0 && head >= cum[i] - 1, checked = rev > 0 && scan <= cum[i] + 1;
        b.classList.toggle('lit', lit); b.classList.toggle('ok', checked && !BAD[i]); b.classList.toggle('bad', checked && !!BAD[i]);
        b.classList.toggle('sel', sel === i || pinned === i);
        if (lit) latest = i; if (checked && latestRev == null) latestRev = i;
        if (checked) {                                  // 節點右上角的相符／不符記號
          const c = pts[i], bw = b.offsetWidth / 2, bh = b.offsetHeight / 2, gx = c[0] + bw - 2, gy = c[1] - bh + 2;
          x.fillStyle = BAD[i] ? PAL.err : PAL.ok; x.beginPath(); x.arc(gx, gy, 8, 0, 6.283); x.fill();
          x.strokeStyle = PAL.bg; x.lineWidth = 2; x.beginPath();
          if (BAD[i]) { x.moveTo(gx - 3, gy - 3); x.lineTo(gx + 3, gy + 3); x.moveTo(gx + 3, gy - 3); x.lineTo(gx - 3, gy + 3); } else { x.moveTo(gx - 3.5, gy); x.lineTo(gx - 1, gy + 2.8); x.lineTo(gx + 3.8, gy - 2.8); }
          x.stroke();
        }
      });
      const focus = sel ?? pinned;
      if (focus != null) showCard(focus, rev > 0 && scan <= cum[focus] + 1 ? 'rev' : 'fwd');
      else if (step === 2 && latestRev != null) showCard(latestRev, 'rev');
      else if (step >= 1 && latest != null) showCard(latest, 'fwd');
      else showCard(null, '');
      void clamp;
    }
  });
}
