// 02 三個入口：分頁切換，右邊的「裝置」用兩層畫布演出每個入口在做什麼。
//   後層：桌面網格與幾張紙（跟滑鼠的景深不同）
//   前層：A 六頁 PDF 逐頁掃描 → 抽出欄位；B 五格輸入 → 地籍、區段、設施、實例依序長出來；C 四個範例發牌
import { S, Layer, PAL, rgba, section, clamp, lerp, easeOut, roundRect, FONT, MONO } from './core.js';

const CAPS = { a: '送審書表 PDF · 逐頁辨識', b: '年期＋地號 · 約 30 秒產生一版', c: '四個範例 · 一鍵開啟' };
const PAGES = ['勘查表', '區域因素分析表', '比較法調查估價表', '地價區段略圖', '使用分區圖', '地價區段圖'];
const RESULT = [['案號', '1140901-99-001', 0], ['估價基準日', '1140901', 0], ['比準地', '金美段489地號', 0], ['比較標的', '1 件', 2], ['缺漏欄位', '0', 5], ['低信心欄位', '0', 5]];
const FIELDS = [['案號', '1140901-99-002'], ['估價基準日', '1140901'], ['鄉鎮市區', '新北市金山區'], ['比準地地號', '金美段489地號'], ['用地別', '商業用地']];
const STAGES = ['地籍界線', '宗地屬性', '區段範圍', '勘查表 28 欄', '設施距離', '比較標的 3 件'];
const CASES = [
  { t: '範例一', s: '金山區 P002-00', b: '相符', c: PAL.ok },
  { t: '範例二', s: '同案含填載錯誤', b: '5 不符・1 需確認', c: PAL.err },
  { t: '範例三', s: '僅有勘查表', b: '圖資推算其餘欄位', c: PAL.meas },
  { t: '範例四', s: '樹林區普通住宅用地', b: '4 區段・3 比較標的', c: PAL.gold }
];

export function initEntry(el) {
  const back = new Layer(el.querySelector('.f-dev-back')), front = new Layer(el.querySelector('.f-dev-front'));
  const tabs = [...el.querySelectorAll('.f-tab')], panes = [...el.querySelectorAll('.f-pane')], cap = el.querySelector('.f-device-cap');
  let k = 'a', t0 = 0;
  function select(nk, focus) {
    k = nk; t0 = S.t;
    tabs.forEach(b => { const on = b.dataset.k === k; b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; if (on && focus) b.focus(); });
    panes.forEach(p => { p.hidden = p.id !== 'f-pane-' + k; });
    cap.textContent = CAPS[k];
  }
  tabs.forEach((b, i) => {
    b.addEventListener('click', () => select(b.dataset.k));
    b.addEventListener('keydown', e => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      e.preventDefault(); select(tabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length].dataset.k, true);
    });
  });

  const txt = (x, s, X, Y, size, col, font = FONT, align = 'left') => { x.font = `${size}px ${font}`; x.fillStyle = col; x.textAlign = align; x.fillText(s, X, Y); };

  function drawBack() {
    const x = back.ctx, W = back.w, H = back.h; back.clear();
    x.strokeStyle = 'rgba(230,236,225,.05)'; x.lineWidth = 1; x.beginPath();
    for (let gx = 0; gx < W; gx += 28) { x.moveTo(gx, 0); x.lineTo(gx, H); }
    for (let gy = 0; gy < H; gy += 28) { x.moveTo(0, gy); x.lineTo(W, gy); }
    x.stroke();
    // 三張紙在不同景深，滑鼠一動就錯開
    [[.78, .2, .5, -.12], [.86, .55, .8, .09], [.1, .78, .3, .05]].forEach(([px, py, z, rot]) => {
      x.save(); x.translate(W * px + S.snx * -22 * z, H * py + S.sny * -16 * z); x.rotate(rot);
      x.fillStyle = 'rgba(242,241,233,.035)'; x.strokeStyle = 'rgba(242,241,233,.08)';
      x.fillRect(-W * .09, -W * .12, W * .18, W * .24); x.strokeRect(-W * .09, -W * .12, W * .18, W * .24); x.restore();
    });
  }

  // A：六頁逐頁掃描
  function drawA(lt) {
    const x = front.ctx, W = front.w, H = front.h, T = lt % 8.4;
    const pw = W * .15, ph = pw * 1.36, gx = W * .045, gy = H * .1;
    for (let i = 0; i < 6; i++) {
      const c = i % 3, r = (i / 3) | 0, px = gx + c * (pw + W * .025), py0 = gy + r * (ph + H * .09);
      const drop = easeOut(clamp((T - i * .08) / .6, 0, 1)), py = py0 - (1 - drop) * 30;
      const s0 = .8 + i * .75, scan = clamp((T - s0) / .75, 0, 1), done = T > s0 + .75;
      x.globalAlpha = drop;
      x.fillStyle = '#e9ece4'; x.fillRect(px, py, pw, ph);
      x.strokeStyle = done ? PAL.meas : 'rgba(0,0,0,.15)'; x.lineWidth = done ? 2 : 1; x.strokeRect(px, py, pw, ph);
      x.fillStyle = 'rgba(9,19,19,.55)'; x.font = `${Math.max(9, pw * .085)}px ${FONT}`; x.textAlign = 'left'; x.fillText(PAGES[i], px + 6, py + 14);
      x.strokeStyle = 'rgba(9,19,19,.18)'; x.lineWidth = 1; x.beginPath();
      if (i < 3) { for (let l = 0; l < 9; l++) { const yy = py + 22 + l * (ph - 30) / 9; x.moveTo(px + 6, yy); x.lineTo(px + pw - 6, yy); } x.moveTo(px + pw * .38, py + 22); x.lineTo(px + pw * .38, py + ph - 8); }
      else { x.moveTo(px + 8, py + ph * .7); x.bezierCurveTo(px + pw * .4, py + ph * .3, px + pw * .6, py + ph * .9, px + pw - 8, py + ph * .4); x.rect(px + pw * .38, py + ph * .42, pw * .2, ph * .14); }
      x.stroke();
      if (scan > 0 && scan < 1) {                         // 掃描光
        const yy = py + scan * ph, g = x.createLinearGradient(0, yy - 18, 0, yy);
        g.addColorStop(0, rgba(PAL.meas, 0)); g.addColorStop(1, rgba(PAL.meas, .45)); x.fillStyle = g; x.fillRect(px, yy - 18, pw, 18);
        x.fillStyle = PAL.meas; x.fillRect(px - 3, yy - 1, pw + 6, 2);
      }
      if (done) txt(x, i < 3 ? '文字讀取' : '圖說', px + pw / 2, py + ph + 15, 11, PAL.meas, FONT, 'center');
      x.globalAlpha = 1;
    }
    // 右側：辨識結果
    const rx = W * .63, rw = W * .33, ry = H * .1;
    x.fillStyle = 'rgba(9,19,19,.72)'; x.strokeStyle = PAL.line; roundRect(x, rx, ry, rw, H * .76, 4); x.fill(); x.stroke();
    txt(x, '辨識結果', rx + 14, ry + 24, 13, PAL.fg);
    // 窄版（手機）欄位名稱與值分兩行，否則會疊字
    const narrow = rw < 200, rowH = narrow ? (H * .76 - 74) / RESULT.length : H * .085;
    RESULT.forEach(([key, val, after], j) => {
      const appear = clamp((T - (.8 + after * .75 + .75) - j * .12) / .35, 0, 1); if (appear <= 0) return;
      const yy = ry + 52 + j * rowH, col = j >= 4 ? PAL.ok : PAL.fg; x.globalAlpha = appear;
      if (narrow) { txt(x, key, rx + 10, yy - 3, 10, PAL.muted); txt(x, val, rx + 10, yy + 10, 11, col, MONO); }
      else { txt(x, key, rx + 14, yy, 11.5, PAL.muted); txt(x, val, rx + rw - 14, yy, 12.5, col, MONO, 'right'); }
      x.fillStyle = PAL.line; x.fillRect(rx + 10, yy + (narrow ? 15 : 8), rw - 20, 1); x.globalAlpha = 1;
    });
    const btn = clamp((T - 6.2) / .4, 0, 1);
    if (btn > 0) { x.globalAlpha = btn; x.fillStyle = PAL.gold; x.fillRect(rx + 10, ry + H * .76 - 46, rw - 20, 32); txt(x, narrow ? '建立案件 →' : '建立案件並開始審查 →', rx + rw / 2, ry + H * .76 - 25, 12, PAL.bg, FONT, 'center'); x.globalAlpha = 1; }
  }

  // B：五格輸入 → 依序長出地籍、區段、勘查表、設施、實例
  function drawB(lt) {
    const x = front.ctx, W = front.w, H = front.h, T = lt % 9.6;
    const fx = W * .05, fw = W * .38, fy = H * .1, fh = H * .1;
    FIELDS.forEach(([label, val], i) => {
      const yy = fy + i * (fh + H * .025), typed = clamp((T - i * .5) / .45, 0, 1), n = Math.round(val.length * typed);
      txt(x, label, fx, yy + 11, 11, PAL.muted);
      x.strokeStyle = typed > 0 && typed < 1 ? PAL.meas : PAL.line; x.lineWidth = 1; x.strokeRect(fx, yy + 17, fw, fh - 12);
      txt(x, val.slice(0, n) + (typed > 0 && typed < 1 && (S.t * 3 | 0) % 2 ? '｜' : ''), fx + 10, yy + 17 + (fh - 12) / 2 + 5, 13, PAL.fg, i < 2 ? MONO : FONT);
    });
    const press = clamp((T - 2.6) / .25, 0, 1), by = fy + 5 * (fh + H * .025) + 6;
    x.fillStyle = press > 0 && press < 1 ? '#f0c190' : PAL.gold; x.fillRect(fx, by, fw, 34); txt(x, '建立並產生 →', fx + fw / 2, by + 22, 13, PAL.bg, FONT, 'center');
    // 右側小地圖
    const mx = W * .5, my = H * .08, mw = W * .45, mh = H * .6, u = mw / 100;
    x.save(); x.beginPath(); x.rect(mx, my, mw, mh); x.clip();
    x.fillStyle = 'rgba(12,26,27,.85)'; x.fillRect(mx, my, mw, mh);
    x.strokeStyle = '#2b4749'; x.lineWidth = 5; x.beginPath(); x.moveTo(mx, my + mh * .72); x.lineTo(mx + mw, my + mh * .3); x.moveTo(mx + mw * .25, my); x.lineTo(mx + mw * .45, my + mh); x.moveTo(mx + mw * .7, my); x.lineTo(mx + mw * .88, my + mh); x.stroke();
    const st = i => clamp((T - (3 + i * .75)) / .6, 0, 1);
    const cxp = mx + mw * .55, cyp = my + mh * .52;
    if (st(2) > 0) {                                     // 區段範圍：沿路網長出街廓
      const g = easeOut(st(2)); x.fillStyle = rgba(PAL.gold, .1 * g); x.strokeStyle = rgba(PAL.gold, .8 * g); x.setLineDash([5, 4]); x.lineWidth = 1.2;
      x.beginPath(); x.moveTo(lerp(cxp, mx + mw * .3, g), lerp(cyp, my + mh * .6, g)); x.lineTo(lerp(cxp, mx + mw * .47, g), lerp(cyp, my + mh * .1, g)); x.lineTo(lerp(cxp, mx + mw * .72, g), lerp(cyp, my + mh * .08, g)); x.lineTo(lerp(cxp, mx + mw * .86, g), lerp(cyp, my + mh * .82, g)); x.lineTo(lerp(cxp, mx + mw * .45, g), lerp(cyp, my + mh * .95, g)); x.closePath(); x.fill(); x.stroke(); x.setLineDash([]);
    }
    if (st(0) > 0) { x.globalAlpha = st(0); x.fillStyle = PAL.gold; x.fillRect(cxp - 3 * u, cyp - 7 * u, 6 * u, 14 * u); x.globalAlpha = 1; }
    if (st(4) > 0) {                                     // 設施距離
      [[.15, .15], [.9, .2], [.2, .9], [.95, .75]].forEach(([ax, ay], j) => {
        const e = easeOut(clamp(st(4) * 1.4 - j * .12, 0, 1)); if (e <= 0) return;
        const tx = mx + mw * ax, ty = my + mh * ay; x.strokeStyle = rgba(PAL.meas, .8); x.lineWidth = 1.2; x.setLineDash([3, 3]);
        x.beginPath(); x.moveTo(cxp, cyp); x.lineTo(lerp(cxp, tx, e), lerp(cyp, ty, e)); x.stroke(); x.setLineDash([]);
        x.fillStyle = PAL.meas; x.beginPath(); x.arc(tx, ty, 4 * e, 0, 6.283); x.fill();
      });
    }
    if (st(5) > 0) [[.3, .3], [.78, .55], [.62, .88]].forEach(([ax, ay], j) => {
      const e = easeOut(clamp(st(5) * 1.5 - j * .2, 0, 1)); if (e <= 0) return;
      x.strokeStyle = PAL.fg; x.lineWidth = 1.5; x.strokeRect(mx + mw * ax - 5 * e, my + mh * ay - 5 * e, 10 * e, 10 * e);
      txt(x, `實例${j + 1}`, mx + mw * ax + 9, my + mh * ay + 4, 10.5, PAL.fg);
    });
    x.restore();
    if (st(3) > 0) {                                     // 勘查表 28 欄
      for (let c = 0; c < 28; c++) { const on = st(3) * 28 > c; x.fillStyle = on ? (c % 9 === 4 ? PAL.warn : PAL.meas) : 'rgba(230,236,225,.08)'; x.fillRect(mx + (c % 14) * (mw / 14) + 1, my + mh + 10 + ((c / 14) | 0) * 9, mw / 14 - 2, 6); }
    }
    // 下方：流程列與計時
    const sy = H * .9, sw = W * .9 / STAGES.length;
    STAGES.forEach((s, i) => {
      const d = st(i) >= 1, a = st(i) > 0;
      txt(x, (d ? '✓ ' : '') + s, W * .05 + i * sw, sy, 11, d ? PAL.meas : a ? PAL.fg : 'rgba(174,187,182,.5)');
    });
    const secs = Math.round(clamp((T - 2.8) / (7.6 - 2.8), 0, 1) * 30);
    txt(x, T > 7.6 ? '約 30 秒完成' : `00:${String(secs).padStart(2, '0')}`, W * .95, H * .08 - 8, 12, PAL.gold, MONO, 'right');
  }

  // C：四個範例發牌
  function drawC(lt) {
    const x = front.ctx, W = front.w, H = front.h;
    CASES.forEach((cs, i) => {
      const c = i % 2, r = (i / 2) | 0, z = .4 + i * .18, e = easeOut(clamp((lt - i * .18) / .7, 0, 1));
      const cw = W * .4, ch = H * .36, tx = W * .07 + c * (cw + W * .06), ty = H * .08 + r * (ch + H * .06);
      const px = lerp(W * .5 - cw / 2, tx, e) + S.snx * 14 * z, py = lerp(H + 40, ty, e) + S.sny * 10 * z + (S.reduced ? 0 : Math.sin(S.t * .9 + i) * 3);
      x.save(); x.translate(px + cw / 2, py + ch / 2); x.rotate((1 - e) * (i % 2 ? .3 : -.3)); x.translate(-cw / 2, -ch / 2);
      x.fillStyle = 'rgba(16,38,42,.95)'; x.strokeStyle = rgba(cs.c, .6); x.lineWidth = 1; roundRect(x, 0, 0, cw, ch, 4); x.fill(); x.stroke();
      x.fillStyle = cs.c; x.fillRect(0, 0, 3, ch);
      txt(x, cs.t, 16, 26, 12, cs.c); txt(x, cs.s, 16, 50, 15, PAL.fg);
      x.font = `11.5px ${FONT}`; const bw = x.measureText(cs.b).width + 16;
      x.strokeStyle = cs.c; x.strokeRect(16, ch - 38, bw, 22); txt(x, cs.b, 24, ch - 23, 11.5, cs.c);
      // 卡片裡的小格：範例二有紅格
      for (let g = 0; g < 12; g++) { x.fillStyle = i === 1 && (g === 3 || g === 7 || g === 8 || g === 10 || g === 11) ? rgba(PAL.err, .7) : i === 1 && g === 5 ? rgba(PAL.warn, .7) : 'rgba(230,236,225,.1)'; x.fillRect(cw - 16 - (6 - (g % 6)) * 12, 20 + ((g / 6) | 0) * 12, 9, 8); }
      x.restore();
    });
  }

  return section(el, {
    resize() { back.resize(); front.resize(); },
    enter() { select('a'); },
    update() {
      const lt = S.reduced ? { a: 7.5, b: 8.5, c: 3 }[k] : S.t - t0;
      drawBack(); front.clear(); ({ a: drawA, b: drawB, c: drawC })[k](lt);
    }
  });
}
