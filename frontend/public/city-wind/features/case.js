// 06 樹林區實案：
//   流程列：估價師（與首頁載入動畫同一個人）沿著八個站跑過去，跑到哪一站、哪一站就完成；位置跟著捲動，也可以按「重播」。
//   比較法：三筆試算價格 → 權重 → 比較價格 131,529 → 查估辦法 §21 進位成 132,000。
//   容積率：拖動面臨計畫道路寬度，8 m 是土管要點但書的門檻；也可以切成「依現有巷道建築」。
// 數字全部來自系統對樹林區案例的核算結果（fixtures/shulin_case_1110901.json 的單價與期日調整，核算值見 docs/13 講稿）。
import { S, Layer, PAL, rgba, section, clamp, lerp, smooth, centerIn, FONT, MONO } from './core.js';

const TRIAL = [{ n: '樹德段284', v: 137118, w: 30 }, { n: '太平段367、917', v: 124010, w: 50 }, { n: '文林段317', v: 141940, w: 20 }];
const PRICE = 131529, LAND = 132000;

// 估價師：頭、身體、手臂＋板夾、兩條腿（跑步時擺動）；08 未來應用也用同一個人
export function runner(x, X, Y, t, moving, col) {
  const sw = moving ? Math.sin(t * 16) : Math.sin(t * 2) * .15, bob = moving ? Math.abs(Math.sin(t * 16)) * 2 : 0;
  x.save(); x.translate(X, Y - bob); x.strokeStyle = col; x.fillStyle = col; x.lineCap = 'round'; x.lineWidth = 3;
  x.beginPath(); x.arc(0, -30, 4.6, 0, 6.283); x.fill();
  x.beginPath(); x.moveTo(0, -25); x.lineTo(0, -12); x.stroke();
  x.beginPath(); x.moveTo(0, -12); x.lineTo(sw * 6, 0); x.moveTo(0, -12); x.lineTo(-sw * 6, 0); x.stroke();
  x.beginPath(); x.moveTo(0, -22); x.lineTo(6, -18 + sw * 2); x.stroke();
  x.fillStyle = PAL.fg; x.fillRect(6, -25 + sw * 2, 7, 9);
  x.restore();
}

export function initCase(el) {
  const pipe = el.querySelector('.f-pipe'), pc = new Layer(el.querySelector('.f-pipe-canvas')), lis = [...el.querySelectorAll('.f-pipe-steps li')];
  const price = new Layer(el.querySelector('.f-price-canvas')), farC = new Layer(el.querySelector('.f-far-canvas'));
  const comps = [...el.querySelectorAll('.f-far-comps button')], wIn = el.querySelector('.f-far-w'), wOut = el.querySelector('.f-far-ctl output');
  const lane = el.querySelector('.f-far-l'), farB = el.querySelector('.f-far-out b'), farEm = el.querySelector('.f-far-out em');
  let replayT = null, wDraw = 7.3, laneDraw = 0, lastRun = 0, runT = 0;

  el.querySelector('.f-pipe-play').addEventListener('click', () => { replayT = S.t; });
  function updFar() {
    const w = +wIn.value, l = lane.checked, cap = l || w < 8 ? 200 : 260;
    wOut.textContent = l ? '—' : `${w.toFixed(1)} m`; wIn.disabled = l;
    farB.textContent = `${cap}%`;
    farEm.textContent = l ? '依現有巷道建築：但書適用' : w < 8 ? '未達 8 m：但書適用' : '達 8 m：第一種住宅區 260%';
    farEm.classList.toggle('hit', cap === 200);
  }
  comps.forEach(b => b.addEventListener('click', () => {
    comps.forEach(o => o.setAttribute('aria-checked', String(o === b)));
    if (+b.dataset.lane) lane.checked = true; else { lane.checked = false; wIn.value = b.dataset.w; }
    updFar();
  }));
  wIn.addEventListener('input', () => { comps.forEach(o => o.setAttribute('aria-checked', 'false')); updFar(); });
  lane.addEventListener('change', updFar);
  updFar();

  function drawPipe(p) {
    const x = pc.ctx, W = pc.w; pc.clear();
    let prog;
    if (replayT != null) { prog = clamp((S.t - replayT) / 8, 0, 1); if (S.t - replayT > 9) replayT = null; }
    else prog = S.reduced ? (p > .22 ? 1 : 0) : smooth(.1, .4, p);
    const xs = lis.map(li => centerIn(li, pipe).x), y = 44, rx = lerp(xs[0], xs[xs.length - 1], prog);
    x.strokeStyle = PAL.line; x.lineWidth = 2; x.beginPath(); x.moveTo(xs[0], y); x.lineTo(xs[xs.length - 1], y); x.stroke();
    x.strokeStyle = PAL.gold; x.beginPath(); x.moveTo(xs[0], y); x.lineTo(rx, y); x.stroke();
    // 測量樁：與載入動畫同一個意象
    x.strokeStyle = 'rgba(230,236,225,.16)'; x.lineWidth = 1; x.beginPath();
    for (let k = xs[0]; k < xs[xs.length - 1]; k += 22) { x.moveTo(k, y + 4); x.lineTo(k, y + 9); } x.stroke();
    lis.forEach((li, i) => {
      const done = rx >= xs[i] - 1; li.classList.toggle('done', done); li.classList.toggle('cur', done && (i === lis.length - 1 || rx < xs[i + 1] - 1));
      x.fillStyle = done ? PAL.gold : PAL.bg; x.strokeStyle = done ? PAL.gold : 'rgba(230,236,225,.35)'; x.lineWidth = 1.5;
      x.beginPath(); x.arc(xs[i], y, 7, 0, 6.283); x.fill(); x.stroke();
      if (done) { x.strokeStyle = PAL.bg; x.lineWidth = 2; x.beginPath(); x.moveTo(xs[i] - 3, y); x.lineTo(xs[i] - 1, y + 2.6); x.lineTo(xs[i] + 3.4, y - 2.6); x.stroke(); }
    });
    const moving = Math.abs(prog - lastRun) > 1e-4; lastRun = prog; if (moving) runT += S.dt;
    runner(x, rx, y - 8, S.reduced ? 0 : (moving ? runT : S.t), moving && !S.reduced, PAL.gold);
    const secs = prog >= 1 ? '完成' : `約 ${Math.round(prog * 20)} 秒`;
    x.font = `12px ${MONO}`; x.fillStyle = PAL.muted; x.textAlign = 'center'; x.fillText(secs, rx, y - 46);
  }

  function drawPrice(p) {
    const x = price.ctx, W = price.w, H = price.h; price.clear();
    const r = S.reduced ? 1 : smooth(.22, .5, p), r2 = S.reduced ? 1 : smooth(.46, .62, p);
    const lo = 110000, hi = 146000, X = v => 90 + (v - lo) / (hi - lo) * (W - 120);
    x.strokeStyle = PAL.line; x.lineWidth = 1; x.beginPath();
    for (let v = 115000; v <= 145000; v += 5000) { x.moveTo(X(v), 8); x.lineTo(X(v), H - 22); }
    x.stroke(); x.font = `10px ${MONO}`; x.fillStyle = '#7f918a'; x.textAlign = 'center';
    for (let v = 115000; v <= 145000; v += 10000) x.fillText(`${v / 1000}k`, X(v), H - 8);
    TRIAL.forEach((c, i) => {
      const yy = 22 + i * 30, th = 4 + c.w / 5, len = lerp(X(lo), X(c.v), r);
      x.fillStyle = rgba(PAL.meas, .8); x.fillRect(X(lo), yy - th / 2, len - X(lo), th);
      x.textAlign = 'left'; x.fillStyle = PAL.muted; x.font = `11px ${FONT}`; x.fillText(`${c.w}%`, 8, yy + 4);
      if (r > .9) { x.fillStyle = PAL.fg; x.font = `11px ${MONO}`; x.fillText(c.v.toLocaleString('en-US'), len + 6, yy + 4); }
    });
    if (r2 > 0) {                                     // 加權平均線，再依 §21 進位
      const px = X(PRICE), lx = X(LAND);
      x.globalAlpha = r2; x.strokeStyle = PAL.gold; x.lineWidth = 2; x.beginPath(); x.moveTo(px, 6); x.lineTo(px, H - 24); x.stroke();
      x.setLineDash([3, 3]); x.beginPath(); x.moveTo(px, 12); x.lineTo(lerp(px, lx, r2), 12); x.stroke(); x.setLineDash([]);
      x.fillStyle = PAL.gold; x.beginPath(); x.arc(lerp(px, lx, r2), 12, 3.5, 0, 6.283); x.fill(); x.globalAlpha = 1;
    }
  }

  function drawFar() {
    const x = farC.ctx, W = farC.w, H = farC.h; farC.clear();
    wDraw = S.reduced ? +wIn.value : lerp(wDraw, +wIn.value, .18); laneDraw = lerp(laneDraw, lane.checked ? 1 : 0, S.reduced ? 1 : .15);
    const k = Math.min(9, (H - 70) / 12), roadTop = 46, cx = W * .5;
    // 宗地（示意）
    x.fillStyle = rgba(PAL.gold, .22); x.strokeStyle = PAL.gold; x.lineWidth = 1.5;
    x.beginPath(); x.moveTo(cx - 70, 10); x.lineTo(cx + 66, 6); x.lineTo(cx + 74, roadTop); x.lineTo(cx - 76, roadTop); x.closePath(); x.fill(); x.stroke();
    x.fillStyle = PAL.sand; x.font = `11px ${FONT}`; x.textAlign = 'center'; x.fillText('宗地（示意）', cx, 30);
    // 計畫道路用地：寬度＝滑桿；現有巷道時換成窄而不規則的巷道
    const planned = (1 - laneDraw), wpx = wDraw * k;
    if (planned > .02) {
      x.globalAlpha = planned; x.fillStyle = '#56616a'; x.fillRect(0, roadTop, W, wpx);
      x.strokeStyle = 'rgba(242,241,233,.35)'; x.setLineDash([10, 8]); x.beginPath(); x.moveTo(0, roadTop + wpx / 2); x.lineTo(W, roadTop + wpx / 2); x.stroke(); x.setLineDash([]);
      x.strokeStyle = rgba(PAL.warn, .8); x.setLineDash([4, 4]); x.strokeRect(-2, roadTop, W + 4, 8 * k); x.setLineDash([]);   // 8 m 門檻
      x.fillStyle = PAL.warn; x.font = `11px ${FONT}`; x.textAlign = 'right'; x.fillText('8 m 門檻', W - 8, roadTop + 8 * k + 13);
      x.strokeStyle = PAL.fg; x.lineWidth = 1.2; x.beginPath(); x.moveTo(cx + 110, roadTop + 2); x.lineTo(cx + 110, roadTop + wpx - 2); x.stroke();
      [roadTop + 2, roadTop + wpx - 2].forEach((yy, j) => { x.beginPath(); x.moveTo(cx + 105, yy + (j ? -5 : 5)); x.lineTo(cx + 110, yy); x.lineTo(cx + 115, yy + (j ? -5 : 5)); x.stroke(); });
      x.fillStyle = PAL.fg; x.textAlign = 'left'; x.font = `12px ${MONO}`; x.fillText(`${wDraw.toFixed(1)} m`, cx + 120, roadTop + wpx / 2 + 4);
      x.fillStyle = 'rgba(242,241,233,.75)'; x.font = `11px ${FONT}`; x.fillText('都市計畫道路用地', 10, roadTop + wpx / 2 + 4);
      x.globalAlpha = 1;
    }
    if (laneDraw > .02) {
      x.globalAlpha = laneDraw; x.fillStyle = '#3d4a4a'; x.beginPath(); x.moveTo(0, roadTop); x.lineTo(W, roadTop);
      for (let i = 20; i >= 0; i--) { const xx = W * i / 20; x.lineTo(xx, roadTop + 26 + Math.sin(i * 1.7) * 5); } x.closePath(); x.fill();
      x.fillStyle = PAL.fg; x.font = `11px ${FONT}`; x.textAlign = 'left'; x.fillText('現有巷道（1 m 內沒有道路用地）', 10, roadTop + 17); x.globalAlpha = 1;
    }
  }

  return section(el, {
    resize() { pc.resize(); price.resize(); farC.resize(); },
    update(s) { drawPipe(s.p); drawPrice(s.p); drawFar(); }
  });
}
