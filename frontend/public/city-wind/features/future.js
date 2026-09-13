// 08 綜上所述：未來應用。
// 母動畫：釘住一整屏，垂直捲動＝水平前進。三層畫布三種速度——
//   遠層：新北夜間天際線（最慢）；中層：地面、測量樁與沿路的站牌，估價師走在上面（與卡片同速）；
//   前景：風與落葉（最快）。站點卡片沿路經過，走到哪一站、那一站的子動畫就開始。
// 子動畫：每個應用場景一個，畫的就是那一段文字在講的事。
import { S, Layer, PAL, rgba, section, clamp, lerp, smooth, easeOut, easeInOut, rng, roundRect, FONT, MONO } from './core.js';
import { runner } from './case.js';

const R = rng(31);
const txt = (x, s, X, Y, size, col, align = 'center', font = FONT) => { x.font = `${size}px ${font}`; x.fillStyle = col; x.textAlign = align; x.fillText(s, X, Y); };
const box = (x, X, Y, w, h, stroke, fill = 'rgba(9,19,19,.9)') => { x.fillStyle = fill; x.strokeStyle = stroke; x.lineWidth = 1.2; roundRect(x, X - w / 2, Y - h / 2, w, h, 4); x.fill(); x.stroke(); };
const along = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];

/* ── 子動畫 ─────────────────────────────────────────────────── */
// A 開放 API：三個外部系統 → 金鑰驗證的 /v1 閘道 → 規則引擎，回應帶著依據回去
function drawAPI(x, W, H, t) {
  const cl = [['估價師事務所', 'POST /v1/verify', '{ 不符: 5, 依據: "§17" }'], ['地政事務所', 'GET /v1/rules/I14', '{ 項目: 14, 上限: 10% }'], ['需用土地人', 'GET /v1/cases/…/sheets.pdf', 'sheets.pdf ✓']];
  const gx = W * .5, ex = W * .84, cy = H * .42;
  box(x, gx, cy, 70, H * .56, PAL.gold, 'rgba(227,172,120,.08)'); txt(x, 'API', gx, cy - 10, 13, PAL.gold); txt(x, '/v1', gx, cy + 8, 12, PAL.gold, 'center', MONO);
  box(x, ex, cy, W * .2, 58, PAL.meas); txt(x, '規則引擎', ex, cy + 5, 13, PAL.fg);
  cl.forEach(([name, req, res], i) => {
    const cx = W * .15, yy = H * (.16 + i * .26);
    box(x, cx, yy, W * .22, 34, PAL.line); txt(x, name, cx, yy + 4, 12, PAL.ink2);
    const ph = ((t * .22) + i / 3) % 1, a = [cx + W * .11, yy], g = [gx - 35, cy], e = [ex - W * .1, cy];
    let p, lab = req, col = PAL.gold;
    if (ph < .3) p = along(a, g, easeInOut(ph / .3));
    else if (ph < .38) { p = g; x.strokeStyle = PAL.ok; x.lineWidth = 2; x.beginPath(); x.arc(gx, cy - H * .2, 9, 0, 6.283); x.stroke(); txt(x, '✓', gx, cy - H * .2 + 4, 11, PAL.ok); }
    else if (ph < .58) p = along(g, e, easeInOut((ph - .38) / .2));
    else if (ph < .66) p = e;
    else { p = along(e, a, easeInOut((ph - .66) / .34)); lab = res; col = PAL.ok; }
    x.strokeStyle = 'rgba(230,236,225,.1)'; x.setLineDash([3, 4]); x.beginPath(); x.moveTo(a[0], a[1]); x.lineTo(g[0], g[1]); x.lineTo(e[0], e[1]); x.stroke(); x.setLineDash([]);
    x.font = `10.5px ${MONO}`; const w = x.measureText(lab).width + 12;
    x.fillStyle = 'rgba(9,19,19,.92)'; x.strokeStyle = col; roundRect(x, p[0] - w / 2, p[1] - 10, w, 20, 3); x.fill(); x.stroke(); txt(x, lab, p[0], p[1] + 4, 10.5, col, 'center', MONO);
  });
  // 金鑰：閘道上方
  x.strokeStyle = PAL.gold; x.lineWidth = 2; x.beginPath(); x.arc(gx - 6, cy + H * .21, 6, 0, 6.283); x.moveTo(gx, cy + H * .21); x.lineTo(gx + 14, cy + H * .21); x.moveTo(gx + 10, cy + H * .21); x.lineTo(gx + 10, cy + H * .21 + 5); x.stroke();
  // 程式碼：請求與回應逐字打出
  const lines = ['$ curl -H "X-API-Key: ••••" …/v1/verify -d @case.json', '← 200 OK  findings[5]  basis["§17 第3項", "手冊 p.49"]'];
  const k = (t * .6) % 3, y0 = H * .86;
  x.fillStyle = 'rgba(0,0,0,.35)'; x.fillRect(12, y0 - 18, W - 24, 46);
  lines.forEach((s, i) => { const n = Math.floor(clamp(k * 1.4 - i * 1.1, 0, 1) * s.length); txt(x, s.slice(0, n), 22, y0 + i * 18, 11, i ? PAL.ok : PAL.ink2, 'left', MONO); });
}

// B 資訊安全：四圈防線（網路／身分／權限／資料）＋雜湊鏈稽核
const ATTACK = Array.from({ length: 7 }, (_, i) => ({ a: R() * 6.283, bad: i % 3 === 0, off: R() }));
function drawSEC(x, W, H, t) {
  const cx = W * .5, cy = H * .42, M = Math.min(W * .9, H * .8) / 2, rings = [['網路 443／80', 1], ['身分 單一登入', .76], ['權限 角色', .54], ['資料 加密', .33]];
  rings.forEach(([lab, k], i) => {
    x.strokeStyle = rgba(i === 0 ? PAL.meas : PAL.ok, .35 + i * .1); x.lineWidth = 1.4; x.setLineDash([10 + i * 4, 6]); x.lineDashOffset = t * (i % 2 ? -12 : 12);
    x.beginPath(); x.arc(cx, cy, M * k, 0, 6.283); x.stroke(); x.setLineDash([]);
    txt(x, lab, cx, cy - M * k + 13, 10.5, PAL.muted);
  });
  // 核心：未授權時是亂碼，授權封包抵達時解開
  const hit = ATTACK.some(p => !p.bad && ((t * .25 + p.off) % 1) > .92);
  txt(x, hit ? '案件資料' : '▚▞▙▟▚▞', cx, cy + 5, 13, hit ? PAL.fg : PAL.muted);
  for (const p of ATTACK) {
    const ph = (t * .25 + p.off) % 1, far = M * 1.25, rr = p.bad ? (ph < .5 ? lerp(far, M * 1.02, ph / .5) : lerp(M * 1.02, far, (ph - .5) / .5)) : lerp(far, M * .08, ph);
    const px = cx + Math.cos(p.a) * rr, py = cy + Math.sin(p.a) * rr * .9;
    x.fillStyle = p.bad ? PAL.err : PAL.gold; x.beginPath(); x.arc(px, py, 4, 0, 6.283); x.fill();
    if (p.bad && Math.abs(ph - .5) < .06) { x.strokeStyle = PAL.err; x.lineWidth = 2; x.beginPath(); x.arc(cx, cy, M, p.a - .25, p.a + .25); x.stroke(); txt(x, '✕ 阻擋', px, py - 10, 10.5, PAL.err); }
    if (!p.bad && rr < M * .8 && rr > M * .68) {        // 通過身分那一圈：亮出鑰匙
      x.strokeStyle = PAL.gold; x.lineWidth = 1.6; x.beginPath(); x.arc(px + 12, py, 3.5, 0, 6.283);
      x.moveTo(px + 15.5, py); x.lineTo(px + 24, py); x.moveTo(px + 21, py); x.lineTo(px + 21, py + 4); x.stroke();
    }
  }
  // 稽核：每筆操作紀錄帶上一筆的雜湊，串成鏈
  const y = H * .9, bw = W * .2, step = bw + 16, n = 6, shift = (t * 22) % step;
  const hex = k => ((Math.imul(k + 7, 2654435761) >>> 0).toString(16) + '0000').slice(0, 4);
  for (let i = -1; i < n; i++) {
    const k = Math.floor(t * 22 / step) + i, bx = 14 + i * step - shift + step; if (bx > W) continue;
    x.fillStyle = 'rgba(159,211,173,.08)'; x.strokeStyle = rgba(PAL.ok, .5); x.fillRect(bx, y - 16, bw, 30); x.strokeRect(bx, y - 16, bw, 30);
    txt(x, `#${hex(k)}…`, bx + 8, y - 3, 10, PAL.ok, 'left', MONO); txt(x, `prev ${hex(k - 1)}`, bx + 8, y + 9, 9, PAL.muted, 'left', MONO);
    x.strokeStyle = rgba(PAL.ok, .5); x.beginPath(); x.moveTo(bx + bw, y); x.lineTo(bx + step, y); x.stroke();
  }
}

// C 國土測繪中心：五層圖資依序落下疊好，最上層的宗地由「推定」變成「即時地籍」
const NLSC = [['正射影像', '#35524a'], ['國土利用現況', '#4d5a3a'], ['數值地形 20 m', '#3a4a5e'], ['門牌定位', '#2f4a4c'], ['地籍圖 API', '#1f3a3c']];
function drawNLSC(x, W, H, t) {
  const T = t % 9, cx = W * .5, base = H * .78, s = Math.min(W * .26, H * .34), gap = s * .22;
  txt(x, '國土測繪中心', cx, 22, 12.5, PAL.meas); x.strokeStyle = rgba(PAL.meas, .4); x.setLineDash([2, 4]); x.beginPath(); x.moveTo(cx, 30); x.lineTo(cx, base - NLSC.length * gap - s * .5); x.stroke(); x.setLineDash([]);
  NLSC.forEach(([name, col], k) => {
    const d = easeOut(clamp((T - k * .7) / .8, 0, 1)); if (d <= 0) return;
    const yy = lerp(40, base - k * gap, d);
    x.save(); x.translate(cx, yy); x.transform(1, .5, -1, .5, 0, 0); x.globalAlpha = .35 + .65 * d;
    x.fillStyle = col; x.fillRect(-s * .7, -s * .7, s * 1.4, s * 1.4); x.strokeStyle = 'rgba(230,236,225,.25)'; x.strokeRect(-s * .7, -s * .7, s * 1.4, s * 1.4);
    x.strokeStyle = 'rgba(230,236,225,.16)'; x.beginPath();
    if (k === 2) for (let r = 1; r < 5; r++) { x.moveTo(-s * .7, -s * .7 + r * s * .28); x.bezierCurveTo(-s * .2, -s * .5 + r * s * .2, s * .2, -s * .8 + r * s * .3, s * .7, -s * .7 + r * s * .28); }
    else if (k === 1) { x.fillStyle = 'rgba(159,211,173,.2)'; x.fillRect(-s * .6, -s * .6, s * .5, s * .6); x.fillStyle = 'rgba(233,196,106,.2)'; x.fillRect(0, -s * .2, s * .6, s * .7); }
    else if (k === 3) for (let i = 0; i < 9; i++) { x.moveTo(-s * .5 + (i % 3) * s * .5 + 3, -s * .5 + ((i / 3) | 0) * s * .5); x.arc(-s * .5 + (i % 3) * s * .5, -s * .5 + ((i / 3) | 0) * s * .5, 3, 0, 6.283); }
    else if (k === 4) for (let i = -2; i <= 2; i++) { x.moveTo(i * s * .28, -s * .7); x.lineTo(i * s * .28, s * .7); x.moveTo(-s * .7, i * s * .28); x.lineTo(s * .7, i * s * .28); }
    else for (let i = 0; i < 40; i++) { const u = (i * 37 % 100) / 100 - .5, v = (i * 61 % 100) / 100 - .5; x.moveTo(u * s * 1.3, v * s * 1.3); x.lineTo(u * s * 1.3 + 4, v * s * 1.3); }
    x.stroke();
    if (k === 4 && T > 4.2) {                           // 宗地：虛線（推定）→ 實線（即時地籍）
      const solid = smooth(4.4, 5.4, T); x.strokeStyle = PAL.gold; x.lineWidth = 2.2; x.setLineDash(solid > .98 ? [] : [6 * (1 - solid) + .1, 5 * (1 - solid) + .1]);
      x.fillStyle = rgba(PAL.gold, .25 * solid); x.beginPath(); x.rect(-s * .28, -s * .28, s * .56, s * .56); x.fill(); x.stroke(); x.setLineDash([]);
    }
    x.restore();
    txt(x, name, cx + s * 1.05, yy + 4, 11, rgba(PAL.fg, .4 + .6 * d), 'left');
  });
  if (T > 5.4) { const a = smooth(5.4, 6, T); x.globalAlpha = a; txt(x, '推定 → 即時地籍', cx - s * 1.05, base - 4 * gap + 4, 11.5, PAL.gold, 'right'); txt(x, '登記面積 113.21 m² ＝ 圖面面積 113.21 m² ✓', cx, H - 14, 11.5, PAL.ok); x.globalAlpha = 1; }
}

// D 送件前自主檢核：以前補正來回三趟；自檢之後一趟通過
function drawSELF(x, W, H, t) {
  const T = t % 10, before = T < 5.4, L = [W * .2, H * .44], Rt = [W * .8, H * .44];
  box(x, L[0], L[1], W * .24, 50, PAL.meas); txt(x, '估價單位', L[0], L[1] + 5, 13, PAL.fg);
  box(x, Rt[0], Rt[1], W * .24, 50, PAL.gold); txt(x, '地政局審查', Rt[0], Rt[1] + 5, 13, PAL.fg);
  txt(x, before ? '以前：送件 → 補正 → 再送件' : '之後：送件前先自主檢核', W * .5, 24, 12.5, before ? PAL.muted : PAL.ok);
  let trips;
  if (before) {
    const seg = T / 1.8, i = Math.floor(seg), f = seg - i; trips = Math.min(3, i + (f > .5 ? 1 : 0));
    const go = f < .5, p = go ? along([L[0] + W * .12, L[1] - 8], [Rt[0] - W * .12, Rt[1] - 8], easeInOut(f * 2)) : along([Rt[0] - W * .12, Rt[1] + 12], [L[0] + W * .12, L[1] + 12], easeInOut((f - .5) * 2));
    const last = i >= 2 && !go;
    if (!(i >= 2 && !go)) { x.fillStyle = go ? PAL.fg : PAL.err; x.fillRect(p[0] - 9, p[1] - 11, 18, 22); if (!go) txt(x, '補正', p[0], p[1] + 26, 11, PAL.err); }
    if (last) txt(x, '✓ 通過', Rt[0], Rt[1] + 44, 12, PAL.ok);
  } else {
    const U = T - 5.4, spin = clamp(U / 2.2, 0, 1);
    x.strokeStyle = PAL.ok; x.lineWidth = 2; x.beginPath(); x.arc(L[0], L[1] - 52, 16, -1.57, -1.57 + spin * 6.283); x.stroke();
    txt(x, spin < 1 ? '自檢中…' : '自檢：不符 0', L[0], L[1] - 80, 11, PAL.ok);
    if (U > 2.4) { const p = along([L[0] + W * .12, L[1] - 8], [Rt[0] - W * .12, Rt[1] - 8], easeInOut(clamp((U - 2.4) / 1.2, 0, 1))); x.fillStyle = PAL.fg; x.fillRect(p[0] - 9, p[1] - 11, 18, 22); }
    if (U > 3.7) txt(x, '✓ 一次通過', Rt[0], Rt[1] + 44, 12, PAL.ok);
    trips = U > 3.7 ? 1 : 0;
  }
  txt(x, `補正往返 ${before ? trips : 1} 趟`, W * .5, H * .82, 20, before ? PAL.err : PAL.ok, 'center', FONT);
  txt(x, '示意', W - 12, H - 10, 10, PAL.muted, 'right');
}

// E 跨案一致性：一件件案子落進「審查重點 × 批次」熱度格，最常出錯的那一列浮出來
const ROWS = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii'], WEIGHT = [.5, .3, .6, .3, 1, 1.8, 1.5];
function drawDASH(x, W, H, t) {
  const cols = 12, gx = W * .12, gy = H * .16, gw = W * .62, gh = H * .66, cw = gw / cols, rh = gh / ROWS.length;
  const T = t % 12, filled = Math.floor(T * 7), heat = ROWS.map(() => Array(cols).fill(0)), tot = ROWS.map(() => 0);
  for (let n = 0; n < filled; n++) { const c = n % cols, rr = Math.floor(Math.abs(Math.sin(n * 12.9898) * 43758.5453) % 1 * 100) % 100 / 100; let acc = 0, sum = WEIGHT.reduce((a, b) => a + b, 0), row = 0; for (let k = 0; k < 7; k++) { acc += WEIGHT[k] / sum; if (rr < acc) { row = k; break; } } heat[row][c]++; tot[row]++; }
  const max = Math.max(1, ...tot), top = tot.indexOf(max);
  ROWS.forEach((r, i) => {
    txt(x, r, gx - 10, gy + i * rh + rh / 2 + 4, 11, i === top && filled > 20 ? PAL.err : PAL.muted, 'right', MONO);
    for (let c = 0; c < cols; c++) { const v = Math.min(1, heat[i][c] / 3); x.fillStyle = v ? rgba(PAL.err, .15 + .7 * v) : 'rgba(230,236,225,.05)'; x.fillRect(gx + c * cw + 1, gy + i * rh + 1, cw - 2, rh - 2); }
    const bw = (W * .18) * tot[i] / max; x.fillStyle = i === top && filled > 20 ? PAL.err : rgba(PAL.muted, .5); x.fillRect(gx + gw + 14, gy + i * rh + rh * .3, bw, rh * .4);
  });
  if (filled > 20) { x.strokeStyle = PAL.err; x.lineWidth = 1.5; x.strokeRect(gx - 2, gy + top * rh, gw + 4, rh); txt(x, `最常出錯：審查重點 ${ROWS[top]}`, gx, gy + gh + 22, 12, PAL.err, 'left'); }
  const c = filled % cols, dropY = lerp(4, gy - 6, (T * 7) % 1); x.fillStyle = PAL.gold; x.beginPath(); x.arc(gx + c * cw + cw / 2, dropY, 4, 0, 6.283); x.fill();
  txt(x, '批次 →', gx + gw, gy - 8, 10.5, PAL.muted, 'right'); txt(x, '示意資料', W - 12, H - 10, 10, PAL.muted, 'right');
}

// F 換一份基準表：規則卡片插進引擎，吐出對應的書表
const DECKS = [['金山・商業用地', '已內建', PAL.gold], ['樹林・住宅用地', '已內建', PAL.gold], ['區段徵收', '延伸', PAL.meas], ['市地重劃', '延伸', PAL.meas], ['公告土地現值評議', '延伸', PAL.meas]];
function drawRULES(x, W, H, t) {
  const cyc = 2.8, T = t / cyc, i = Math.floor(T) % DECKS.length, f = T % 1, ex = W * .56, ey = H * .52;
  const cx0 = W * .19, bw = W * .3, rowH = Math.min(48, H * .15), y0 = H * .5 - (DECKS.length - 1) * rowH / 2;
  txt(x, '規則 JSON', cx0, y0 - rowH * .8, 11, PAL.muted);
  DECKS.forEach(([n, tag, col], k) => {                // 左側一欄：五份基準表，輪到的那份抽出去
    const yy = y0 + k * rowH, on = k === i; x.globalAlpha = on ? (f < .12 ? 1 : .3) : .75;
    box(x, cx0, yy, bw, rowH - 8, on ? col : PAL.line); txt(x, n, cx0 - bw / 2 + 10, yy + 4, 11, PAL.fg, 'left'); txt(x, tag, cx0 + bw / 2 - 10, yy + 4, 10, col, 'right'); x.globalAlpha = 1;
  });
  const [n, tag, col] = DECKS[i], slide = easeInOut(clamp((f - .12) / .3, 0, 1)), card = along([cx0, y0 + i * rowH], [ex, ey - 44], slide);
  box(x, ex, ey, W * .26, 92, PAL.line, 'rgba(16,38,42,.95)'); txt(x, '規則引擎', ex, ey + 30, 12, PAL.muted); void tag;
  for (let g = 0; g < 2; g++) {                        // 齒輪
    const gx = ex - 28 + g * 56, gy = ey + 6, a = t * (g ? -2 : 2) * (f > .45 && f < .8 ? 1 : .15);
    x.strokeStyle = PAL.gold; x.lineWidth = 2; x.beginPath(); x.arc(gx, gy, 10, 0, 6.283); x.stroke();
    for (let k = 0; k < 8; k++) { const q = a + k * .785; x.beginPath(); x.moveTo(gx + Math.cos(q) * 10, gy + Math.sin(q) * 10); x.lineTo(gx + Math.cos(q) * 15, gy + Math.sin(q) * 15); x.stroke(); }
  }
  box(x, card[0], card[1], bw * .9, rowH - 10, col, 'rgba(16,38,42,.98)'); txt(x, n, card[0], card[1] + 4, 11.5, PAL.fg);
  const out = easeOut(clamp((f - .6) / .28, 0, 1));
  if (out > 0) {
    const ox = lerp(ex, W * .88, out), oy = ey; x.globalAlpha = out;
    x.fillStyle = '#f1eee6'; x.fillRect(ox - 34, oy - 46, 68, 92); x.strokeStyle = 'rgba(9,19,19,.2)'; x.beginPath(); for (let r = 0; r < 8; r++) { x.moveTo(ox - 28, oy - 26 + r * 9); x.lineTo(ox + 28, oy - 26 + r * 9); } x.stroke();
    txt(x, n.split('・')[0], ox, oy - 34, 10, '#1d2624'); txt(x, '查估書表', ox, oy + 60, 11, PAL.fg); x.globalAlpha = 1;
  }
  txt(x, '{ bands, matrix, max_pct }', ex, ey - 78, 10.5, PAL.muted, 'center', MONO);
}
const CHILD = { api: drawAPI, sec: drawSEC, nlsc: drawNLSC, self: drawSELF, dash: drawDASH, rules: drawRULES };

/* ── 母動畫 ─────────────────────────────────────────────────── */
export function initFuture(el) {
  const far = new Layer(el.querySelector('.f-fut-far'), { max: 1.5 }), mid = new Layer(el.querySelector('.f-fut-mid'), { max: 1.75 }), near = new Layer(el.querySelector('.f-fut-near'), { max: 1.5 });
  const track = el.querySelector('.f-fut-track'), stations = [...track.children], dots = [...el.querySelectorAll('.f-fut-dots li')];
  const kids = [...el.querySelectorAll('.f-fut-card')].map(card => ({ card, draw: CHILD[card.dataset.k], layer: new Layer(card.querySelector('canvas')), t0: 0, vis: false }));
  const city = [.26, .42].map((depth, L) => { const b = []; let xx = 0; while (xx < 3200) { const w = 30 + R() * 70, h = (L ? 70 : 120) + R() * (L ? 120 : 200); b.push({ x: xx, w, h, win: Array.from({ length: 10 }, () => [R(), R(), R()]) }); xx += w + 4 + R() * 10; } return { depth, b }; });
  const leaves = Array.from({ length: S.low ? 26 : 46 }, () => ({ x: R(), y: R(), z: .5 + R() * .8, r: R() * 6.28 }));
  let travel = 0, last = -1, walkT = 0, cur = -1;

  function measureTrack() { travel = Math.max(0, track.scrollWidth - S.vw * .9); }
  // 捲動 → 水平位移：每一站停一下（卡片置中、估價師停步、子動畫播放），站與站之間平順移動
  function offsetFor(p) {
    const n = stations.length, u = clamp((p - .03) / .94, 0, 1) * (n - 1), i = Math.min(n - 2, Math.floor(u)), f = u - i;
    const e = S.reduced ? Math.round(f) : smooth(.22, .78, f);
    const c = k => clamp(stations[k].offsetLeft + stations[k].offsetWidth / 2 - S.vw * .5, 0, travel);
    return lerp(c(i), c(i + 1), e);
  }

  function drawFar(off) {
    const x = far.ctx, W = far.w, H = far.h; far.clear();
    const g = x.createLinearGradient(0, 0, 0, H); g.addColorStop(0, '#07100f'); g.addColorStop(.7, '#0b1a1b'); g.addColorStop(1, '#0f2224'); x.fillStyle = g; x.fillRect(0, 0, W, H);
    // 月亮（幾乎不動）；手機版縮小並移到標題上方，不壓字
    const mx = W * .78 - off * .05, my = S.mobile ? H * .11 : H * .2, mr = S.mobile ? 13 : 22;
    const mg = x.createRadialGradient(mx, my, 0, mx, my, mr * 4); mg.addColorStop(0, 'rgba(255,236,200,.18)'); mg.addColorStop(1, 'rgba(255,236,200,0)'); x.fillStyle = mg; x.fillRect(mx - mr * 4, my - mr * 4, mr * 8, mr * 8);
    x.fillStyle = '#efe3c9'; x.beginPath(); x.arc(mx, my, mr, 0, 6.283); x.fill();
    const ground = H * .86;
    city.forEach(({ depth, b }, L) => {
      const oc = (off * depth) % 3200;
      x.fillStyle = L ? '#0d2022' : '#0a1819';
      for (const k of b) for (const rep of [0, 3200]) {
        const bx = k.x - oc + rep; if (bx > W || bx + k.w < 0) continue;
        x.fillRect(bx, ground - k.h, k.w, k.h);
        for (const [u, v, s] of k.win) { const lit = (Math.sin(S.t * .6 + s * 40) > .2 || S.reduced) && s > .35; if (!lit) continue; x.fillStyle = rgba(PAL.gold, L ? .5 : .28); x.fillRect(bx + 4 + u * (k.w - 10), ground - k.h + 8 + v * (k.h - 20), 3, 4); }
        x.fillStyle = L ? '#0d2022' : '#0a1819';
      }
    });
  }
  function drawMid(off) {
    const x = mid.ctx, W = mid.w, H = mid.h; mid.clear();
    const ground = H * .86;
    x.fillStyle = '#0c1b1c'; x.fillRect(0, ground, W, H - ground);
    x.strokeStyle = rgba(PAL.gold, .4); x.lineWidth = 1.5; x.beginPath(); x.moveTo(0, ground); x.lineTo(W, ground); x.stroke();
    x.strokeStyle = 'rgba(230,236,225,.22)'; x.lineWidth = 1; x.beginPath();              // 測量樁：與卡片同速
    const sp = 60, s0 = -(off % sp);
    for (let k = s0; k < W; k += sp) { x.moveTo(k, ground + 3); x.lineTo(k, ground + 12); }
    x.stroke();
    x.font = `10px ${MONO}`; x.fillStyle = 'rgba(174,187,182,.5)'; x.textAlign = 'center';
    for (let k = s0 - sp * 4; k < W; k += sp) { const m = Math.round((k + off) / sp) * 20; if (m % 100 === 0 && m >= 0) x.fillText(`${m} m`, k, ground + 25); }
    stations.forEach((st, i) => {                         // 每一站的站牌：插在卡片中線的地面上
      const cx = st.offsetLeft + st.offsetWidth / 2 - off; if (cx < -40 || cx > W + 40) return;
      x.strokeStyle = rgba(PAL.gold, .7); x.lineWidth = 2; x.beginPath(); x.moveTo(cx, ground); x.lineTo(cx, ground - 22); x.stroke();
      x.fillStyle = i === cur ? PAL.gold : '#1a3032'; x.beginPath(); x.moveTo(cx, ground - 22); x.lineTo(cx + 18, ground - 17); x.lineTo(cx, ground - 12); x.fill();
      txt(x, i ? 'ABCDEF'[i - 1] : '∑', cx + 7, ground - 14, 9, i === cur ? PAL.bg : PAL.gold);
    });
    const moving = Math.abs(off - last) > .3; if (moving) walkT += S.dt; last = off;   // 停在站上時估價師也停步
    runner(x, W * .1, ground, S.reduced ? 0 : (moving ? walkT : S.t), moving && !S.reduced, PAL.gold);
  }
  function drawNear(o) {
    const x = near.ctx, W = near.w, H = near.h; near.clear(); if (S.reduced) return;
    const off = o * 1.45;
    // 前景只在卡片下方的地面帶飄：不壓在卡片與標題的文字上
    const band = track.getBoundingClientRect().bottom - near.c.getBoundingClientRect().top + 14, bh = Math.max(0, H - band);
    if (bh < 8) return;
    for (const l of leaves) {
      const X = ((l.x * W * 1.4 - off * l.z - S.t * 30 * l.z) % (W * 1.4) + W * 1.4) % (W * 1.4) - W * .2, Y = band + l.y * bh * .85 + Math.sin(S.t * .8 + l.r) * 4;
      x.save(); x.translate(X, Y); x.rotate(l.r + S.t * l.z); x.fillStyle = rgba(l.z > 1 ? PAL.gold : '#9fb7a5', .28); x.beginPath(); x.ellipse(0, 0, 5 * l.z, 2 * l.z, 0, 0, 6.283); x.fill(); x.restore();
      x.strokeStyle = rgba(PAL.gold, .08); x.beginPath(); x.moveTo(X + 8, Y); x.lineTo(X + 40 * l.z, Y + 2); x.stroke();
    }
  }

  return section(el, {
    resize() { far.resize(); mid.resize(); near.resize(); kids.forEach(k => k.layer.resize()); measureTrack(); },
    enter() { measureTrack(); },
    update(s) {
      const off = offsetFor(s.ps);
      track.style.transform = `translate3d(${(-off).toFixed(1)}px,0,0)`;
      // 目前這一站＝離畫面中線最近的卡片
      let best = 0, bd = 1e9; const center = S.vw * .5;
      const focus = stations.map((st, i) => { const cx = st.offsetLeft + st.offsetWidth / 2 - off, d = Math.abs(cx - center); if (d < bd) { bd = d; best = i; } return 1 - clamp(d / (st.offsetWidth * .95), 0, 1); });
      if (best !== cur) { cur = best; stations.forEach((st, i) => st.classList.toggle('on', i === cur)); dots.forEach((d, i) => { d.classList.toggle('on', i === cur); d.classList.toggle('past', i < cur); }); }
      drawFar(off); drawMid(off); drawNear(off);
      kids.forEach((k, i) => {
        const f = focus[i + 1], vis = f > .02;
        if (vis && !k.vis) k.t0 = S.t; k.vis = vis; if (!vis) return;
        const x = k.layer.ctx; k.layer.clear(); x.save(); x.globalAlpha = .35 + .65 * smooth(0, .5, f);
        k.draw(x, k.layer.w, k.layer.h, S.reduced ? 4.5 : S.t - k.t0); x.restore();
      });
    }
  });
}
