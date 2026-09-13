// 05 逐格審查：釘住的段落。
//   前半：一道掃描線逐列掃過，範例二的 5 項不符、1 項需確認依序亮起；
//         背後畫布是兩張表之間的「跨表抄填」連線，掃到那一列時連線斷開變紅。
//   後半：審查意見書從下方滑上來；右邊每列可以改承辦裁決，意見書的結論與逐條意見跟著改。
import { S, Layer, PAL, rgba, section, clamp, smooth, lerp, FONT } from './core.js';

const ROWS = {
  1: { sheet: '比較法調查估價表', cell: '比較標的1／交易日期', filled: '113.05.28', calc: '估價基準日前一年內', why: '交易日期超過估價基準日前一年，逾查估辦法 §17 放寬上限', basis: '查估辦法 §17 第 3 項' },
  2: { sheet: '影響地價區域因素分析明細表', cell: '百分比小計 (2)', filled: '1.00', calc: '0.00', why: '小計加總錯誤', basis: '手冊 p.49 (六)3(3)' },
  3: { sheet: '影響地價區域因素分析明細表', cell: '影響地價區域因素總修正數', filled: '1.00', calc: '0.00', why: '總修正數加總錯誤', basis: '手冊 p.49 (六)3(3)(4)' },
  4: { sheet: '比較法調查估價表', cell: '比較標的1／區域因素調整百分率', filled: '1.00', calc: '0.00', why: '與影響地價區域因素分析明細表之總修正數不符（跨表抄填）', basis: '區域因素分析明細表 總修正數' },
  5: { sheet: '比較法調查估價表', cell: '比較標的1／14 面前道路寬度', filled: '2.50', calc: '5.00', why: '差異率與個別因素基準表矩陣不符', basis: '項目 14 矩陣［稍優］［稍劣］' }
};
const DEC = { accept: '接受填載（經審酌採估價單位之值）', keep: '維持不符，請估價單位補正' };

export function initReview(el) {
  const far = new Layer(el.querySelector('.f-review-far'), { max: 1.5 });
  const table = el.querySelector('.f-rtable'), scan = el.querySelector('.f-scan'), rows = [...el.querySelectorAll('.f-rrow[data-r]')];
  const steps = [...el.querySelectorAll('.f-step')], op = el.querySelector('.f-opinion'), concl = el.querySelector('.f-op-concl'), items = el.querySelector('.f-op-items');
  const nErr = el.querySelector('[data-n="err"]'), nWarn = el.querySelector('[data-n="warn"]');
  // 預設裁決與系統範例相同：交易日期接受填載，其餘維持不符
  const dec = { 1: 'accept', 2: 'keep', 3: 'keep', 4: 'keep', 5: 'keep' };
  let step = -1, seen = new Set(), lastChanged = null;

  for (const row of rows) {
    const r = +row.dataset.r; if (!ROWS[r]) continue;
    const box = row.querySelector('.f-dec');
    box.innerHTML = `<button type="button" data-v="accept">接受填載</button><button type="button" data-v="keep">維持不符</button>`;
    box.querySelectorAll('button').forEach(b => b.addEventListener('click', () => { dec[r] = dec[r] === b.dataset.v ? null : b.dataset.v; lastChanged = r; paintDecisions(); writeOpinion(); }));
  }
  el.querySelector('.f-trace')?.addEventListener('click', e => {
    // 自己處理捲動（置中對齊引擎），不讓 main.js 的錨點處理再捲一次到頂端
    e.preventDefault(); e.stopImmediatePropagation();
    document.dispatchEvent(new CustomEvent('f-engine-focus', { detail: { id: 'I14', s: 18, c: 6 } }));
    document.getElementById('f-engine')?.scrollIntoView({ behavior: S.reduced ? 'auto' : 'smooth', block: 'center' });
  });
  function paintDecisions() {
    for (const row of rows) { const r = +row.dataset.r; row.querySelectorAll('.f-dec button').forEach(b => b.setAttribute('aria-pressed', String(dec[r] === b.dataset.v))); }
  }
  function writeOpinion() {
    const ids = Object.keys(ROWS).map(Number), acc = ids.filter(r => dec[r] === 'accept').length, keep = ids.filter(r => dec[r] === 'keep').length, pend = ids.length - acc - keep;
    concl.textContent = `本案經核算有 ${ids.length} 項與作業手冊及基準明細表不符${acc ? `，其中 ${acc} 項經承辦審酌接受估價單位填載` : ''}${keep ? `，${acc ? '餘 ' : ''}${keep} 項請估價單位補正後再送審` : ''}${pend ? `；${pend} 項待承辦裁決` : ''}；另有 1 項需確認事項。`;
    items.innerHTML = ids.map((r, k) => {
      const d = ROWS[r], v = dec[r], lab = v === 'accept' ? `<b class="ok">承辦裁決：${DEC.accept}</b>` : v === 'keep' ? `<b>承辦裁決：${DEC.keep}</b>` : '<b class="warn">承辦裁決：待處理</b>';
      return `<li data-r="${r}"${r === lastChanged ? ' class="new"' : ''}>[F-00${k + 1}] 不符：${d.sheet}「${d.cell}」：估價師填載 ${d.filled}，依規則核算應為 ${d.calc}，${d.why}（依據：${d.basis}）。${lab}（裁決人 承辦）</li>`;
    }).join('');
    if (lastChanged) { const li = items.querySelector(`li[data-r="${lastChanged}"]`); if (li) op.scrollTop = li.offsetTop - 40; }
  }
  paintDecisions(); writeOpinion();

  function drawFar(p, crossSeen) {
    const x = far.ctx, W = far.w, H = far.h; far.clear();
    const forms = [
      { name: '影響地價區域因素分析明細表', cx: W * .93, cy: H * .22, w: W * .2, h: H * .46, rot: .07, z: .5, cell: [.62, .86] },
      { name: '比較法調查估價表', cx: W * .5, cy: H * .95, w: W * .34, h: H * .34, rot: -.04, z: .8, cell: [.3, .28] }
    ];
    const pts = forms.map(f => {
      const oy = S.reduced ? 0 : (.5 - p) * H * .35 * f.z, ox = S.snx * -14 * f.z;
      x.save(); x.translate(f.cx + ox, f.cy + oy); x.rotate(f.rot); x.globalAlpha = .55;
      x.fillStyle = 'rgba(12,26,27,.8)'; x.fillRect(-f.w / 2, -f.h / 2, f.w, f.h);
      x.strokeStyle = 'rgba(230,236,225,.14)'; x.beginPath();
      for (let r = 1; r < 16; r++) { x.moveTo(-f.w / 2, -f.h / 2 + r * f.h / 16); x.lineTo(f.w / 2, -f.h / 2 + r * f.h / 16); }
      for (let c = 1; c < 5; c++) { x.moveTo(-f.w / 2 + c * f.w / 5, -f.h / 2 + f.h / 16); x.lineTo(-f.w / 2 + c * f.w / 5, f.h / 2); }
      x.stroke(); x.fillStyle = PAL.muted; x.font = `11px ${FONT}`; x.fillText(f.name, -f.w / 2 + 8, -f.h / 2 + 14);
      const cx = -f.w / 2 + f.cell[0] * f.w, cy = -f.h / 2 + f.cell[1] * f.h;
      x.fillStyle = rgba(crossSeen ? PAL.err : PAL.gold, .55); x.fillRect(cx - f.w * .09, cy - f.h / 32, f.w * .18, f.h / 16);
      const m = x.getTransform(); x.restore(); x.globalAlpha = 1;
      const q = new DOMPoint(cx, cy).matrixTransform(m); return [q.x / far.r, q.y / far.r];
    });
    // 跨表抄填連線：資料往下游流；掃到那一列之後斷開變紅，冒出火花
    const [a, b] = pts, mx = (a[0] + b[0]) / 2 + W * .08, my = (a[1] + b[1]) / 2;
    x.lineWidth = 1.6; x.setLineDash([6, 6]); x.lineDashOffset = S.reduced ? 0 : -S.t * 26;
    if (!crossSeen) { x.strokeStyle = rgba(PAL.gold, .7); x.beginPath(); x.moveTo(a[0], a[1]); x.quadraticCurveTo(mx, my, b[0], b[1]); x.stroke(); }
    else {
      x.strokeStyle = rgba(PAL.err, .8);
      const seg = (t0, t1) => { x.beginPath(); for (let k = 0; k <= 20; k++) { const t = t0 + (t1 - t0) * k / 20, u = 1 - t; const px = u * u * a[0] + 2 * u * t * mx + t * t * b[0], py = u * u * a[1] + 2 * u * t * my + t * t * b[1]; k ? x.lineTo(px, py) : x.moveTo(px, py); } x.stroke(); };
      seg(0, .44); seg(.56, 1);
      const u = .5, cx = (1 - u) * (1 - u) * a[0] + 2 * u * (1 - u) * mx + u * u * b[0], cy = (1 - u) * (1 - u) * a[1] + 2 * u * (1 - u) * my + u * u * b[1];
      x.setLineDash([]);
      for (let k = 0; k < 10; k++) { const ang = k * .63 + S.t * 2, r = 6 + ((S.t * 30 + k * 7) % 18); x.fillStyle = rgba(PAL.err, 1 - r / 26); x.beginPath(); x.arc(cx + Math.cos(ang) * r, cy + Math.sin(ang) * r, 1.6, 0, 6.283); x.fill(); }
      x.font = `12px ${FONT}`; x.fillStyle = PAL.err; x.textAlign = 'center'; x.fillText('1.00 ≠ 0.00', cx, cy - 16); x.textAlign = 'left';
    }
    x.setLineDash([]);
  }

  return section(el, {
    resize() { far.resize(); },
    update(s) {
      const p = s.ps, next = p < .5 ? 0 : 1;
      if (next !== step) { step = next; steps.forEach((st, i) => st.classList.toggle('on', i === step)); table.classList.toggle('compact', step === 1); }
      // 掃描：p 從 .06 到 .44 掃過六列
      const sc = S.reduced ? (p > .06 ? 1 : 0) : smooth(.06, .44, p);
      const tb = table.getBoundingClientRect(), first = rows[0].getBoundingClientRect(), last = rows[rows.length - 1].getBoundingClientRect();
      const y = lerp(first.top, last.bottom, sc) - tb.top;
      scan.style.transform = `translate3d(0,${y.toFixed(1)}px,0)`; scan.style.opacity = sc > 0 && sc < 1 ? '1' : '0';
      let e = 0, w = 0;
      rows.forEach(row => {
        const b = row.getBoundingClientRect(), hit = sc >= 1 || (b.top + b.height / 2 - tb.top) <= y;
        if (hit && !seen.has(row)) { seen.add(row); row.classList.add('seen', 'flash'); setTimeout(() => row.classList.remove('flash'), 700); }
        if (!hit && seen.has(row) && sc < 1) { seen.delete(row); row.classList.remove('seen'); }
        if (hit) row.dataset.kind === 'err' ? e++ : w++;
      });
      nErr.textContent = e; nWarn.textContent = w;
      // 意見書滑上來（前景層，比表格快）
      const o = S.reduced ? (p >= .5 ? 1 : 0) : smooth(.5, .64, p);
      op.style.opacity = o.toFixed(3); op.style.transform = `translate3d(0,${((1 - o) * 110).toFixed(1)}%,0) rotate(${((1 - o) * 1.5).toFixed(2)}deg)`;
      op.style.pointerEvents = o > .5 ? 'auto' : 'none';
      drawFar(p, seen.has(rows[4]));
    }
  });
}
