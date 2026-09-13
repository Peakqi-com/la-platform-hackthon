// 04 規則引擎：頁面上就是一個可以動的確定性小引擎。
// 規則數字抄自 rules/jinshan_commercial_individual.json（新北市金山區商業用地影響地價個別因素評價基準明細表，範例），
// 算法與後端相同：修正率 ＝（比較標的等級索引 − 比準地等級索引）× 最大修正率 ÷ 4。
// 背景一層畫布是書表攤開的扇形（勘查表四區段、表5、表4、三張圖說＝樹林區 9 頁），隨捲動展開。
import { S, Layer, PAL, rgba, section, clamp, lerp, smooth, FONT } from './core.js';

const LV = ['優', '稍優', '普通', '稍劣', '劣'];
const ITEMS = {
  I14: { no: 14, name: '面前道路寬度', unit: 'm', max: 10, lo: 0, hi: 30, step: .1, s: 18, c: 6, dec: 1, bands: [['優', 20, null], ['稍優', 15, 20], ['普通', 8, 15], ['稍劣', 4, 8], ['劣', null, 4]] },
  I15: { no: 15, name: '接近學校之程度', unit: 'm', max: 4, lo: 0, hi: 2600, step: 10, s: 150, c: 100, dec: 0, bands: [['優', null, 200], ['稍優', 200, 600], ['普通', 600, 1200], ['稍劣', 1200, 2000], ['劣', 2000, null]] },
  I16: { no: 16, name: '接近市場之程度', unit: 'm', max: 10, lo: 0, hi: 2600, step: 10, s: 30, c: 92, dec: 0, bands: [['優', null, 500], ['稍優', 500, 1000], ['普通', 1000, 1500], ['稍劣', 1500, 2000], ['劣', 2000, null]] },
  I7: { no: 7, name: '面積', unit: 'm²', max: 8, lo: 40, hi: 140, step: .01, s: 113.21, c: 111.85, dec: 2, bands: [['優', 93, null], ['稍優', 83, 93], ['普通', 73, 83], ['稍劣', 63, 73], ['劣', null, 63]] }
};
const SOURCE = '新北市金山區商業用地影響地價個別因素評價基準明細表（範例）';
const SHEETS = ['勘查表 P001-00', '勘查表 P002-00', '勘查表 P003-00', '勘查表 P004-00', '區域因素分析明細表', '比較法調查估價表', '地價區段略圖', '地價使用分區圖', '地價區段圖'];
const TINT = [PAL.gold, '#d8b98c', '#aebbb6', '#8fb3b5', PAL.meas];

// 與後端 rules.grade 相同的區間判定：下限含、上限不含
const grade = (it, v) => { for (const [lv, a, b] of it.bands) if ((a == null || v >= a) && (b == null || v < b)) return lv; return it.bands[it.bands.length - 1][0]; };
const fmt = n => (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(2);

export function initRules(el) {
  const eng = el.querySelector('.f-engine'), radios = [...el.querySelectorAll('.f-eng-items button')];
  const ins = { s: el.querySelector('input[data-who="s"]'), c: el.querySelector('input[data-who="c"]') };
  const outs = { s: el.querySelector('.f-eng-in.s output'), c: el.querySelector('.f-eng-in.c output') };
  const lvs = { s: el.querySelector('.f-eng-in.s .lv'), c: el.querySelector('.f-eng-in.c .lv') };
  const table = el.querySelector('.f-matrix'), rateEl = el.querySelector('.f-eng-rate'), formula = el.querySelector('.f-eng-formula'), src = el.querySelector('.f-eng-src');
  const bands = new Layer(el.querySelector('.f-eng-bands')), sheets = new Layer(el.querySelector('.f-sheets'), { max: 1, scale: .85 });
  let id = 'I14', it = ITEMS[id], mk = { s: 0, c: 0 }, lastHit = '';

  // 矩陣表頭只建一次
  table.tHead.innerHTML = `<tr><th></th>${LV.map(l => `<th scope="col">${l}</th>`).join('')}</tr>`;
  table.tBodies[0].innerHTML = LV.map((r, i) => `<tr><th scope="row">${r}</th>${LV.map((c, j) => `<td data-i="${i}" data-j="${j}"></td>`).join('')}</tr>`).join('');
  const cells = [...table.querySelectorAll('td')];

  function setItem(nid, sv, cv) {
    id = nid; it = ITEMS[id];
    radios.forEach(b => { const on = b.dataset.id === id; b.setAttribute('aria-checked', String(on)); b.tabIndex = on ? 0 : -1; });
    for (const w of ['s', 'c']) { const v = w === 's' ? (sv ?? it.s) : (cv ?? it.c); Object.assign(ins[w], { min: it.lo, max: it.hi, step: it.step }); ins[w].value = v; }
    const step = it.max / 4;
    cells.forEach(td => { td.textContent = ((+td.dataset.j - +td.dataset.i) * step).toFixed(2); });
    compute(true);
  }
  function compute(force) {
    const v = { s: +ins.s.value, c: +ins.c.value }, g = { s: grade(it, v.s), c: grade(it, v.c) };
    for (const w of ['s', 'c']) { outs[w].textContent = `${v[w].toFixed(it.dec)} ${it.unit}`; lvs[w].textContent = g[w]; }
    const i = LV.indexOf(g.s), j = LV.indexOf(g.c), step = it.max / 4, rate = (j - i) * step, key = `${id}${i}${j}`;
    cells.forEach(td => { const a = +td.dataset.i, b = +td.dataset.j; td.classList.toggle('row', a === i && b !== j); td.classList.toggle('col', b === j && a !== i); if (a === i && b === j) { if (key !== lastHit || force) { td.classList.remove('hit'); void td.offsetWidth; } td.classList.add('hit'); } else td.classList.remove('hit'); });
    lastHit = key;
    rateEl.textContent = fmt(rate) + '%';
    formula.textContent = `（${g.c} ${j + 1} − ${g.s} ${i + 1}）× ${step.toFixed(2)} ＝ ${fmt(rate)}%`;
    src.textContent = `${SOURCE}・項目 ${it.no} ${it.name}・最大修正率 ${it.max}%`;
  }
  radios.forEach((b, k) => {
    b.addEventListener('click', () => setItem(b.dataset.id));
    b.addEventListener('keydown', e => { if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return; e.preventDefault(); const n = radios[(k + (e.key === 'ArrowRight' ? 1 : -1) + radios.length) % radios.length]; setItem(n.dataset.id); n.focus(); });
  });
  ins.s.addEventListener('input', () => compute()); ins.c.addEventListener('input', () => compute());
  // 審查那一段按「看基準表格位 →」會丟這個事件過來：把引擎切到那一格並閃一下
  document.addEventListener('f-engine-focus', e => { const d = e.detail || {}; setItem(d.id || 'I14', d.s, d.c); eng.classList.remove('flash'); void eng.offsetWidth; eng.classList.add('flash'); });

  function drawBands() {
    const x = bands.ctx, W = bands.w, H = bands.h; bands.clear();
    const X = v => 8 + (clamp(v, it.lo, it.hi) - it.lo) / (it.hi - it.lo) * (W - 16), y0 = 20, bh = 12;
    it.bands.forEach(([lv, a, b]) => {
      const x0 = X(a ?? it.lo), x1 = X(b ?? it.hi), k = LV.indexOf(lv);
      x.fillStyle = rgba(TINT[k], .32); x.fillRect(x0, y0, Math.max(1, x1 - x0 - 1), bh);
      x.fillStyle = PAL.muted; x.font = `11px ${FONT}`; x.textAlign = 'center'; if (x1 - x0 > 22) x.fillText(lv, (x0 + x1) / 2, y0 + bh + 14);
      if (a != null && a > it.lo) { x.fillStyle = 'rgba(205,216,210,.6)'; x.fillText(String(a), X(a), y0 - 5); }
    });
    for (const w of ['s', 'c']) {
      const target = X(+ins[w].value); mk[w] = S.reduced || !mk[w] ? target : lerp(mk[w], target, .25);
      const col = w === 's' ? PAL.gold : PAL.meas, up = w === 's';
      x.fillStyle = col; x.beginPath();
      if (up) { x.moveTo(mk[w], y0 - 1); x.lineTo(mk[w] - 6, y0 - 11); x.lineTo(mk[w] + 6, y0 - 11); } else { x.moveTo(mk[w], y0 + bh + 1); x.lineTo(mk[w] - 6, y0 + bh + 11); x.lineTo(mk[w] + 6, y0 + bh + 11); }
      x.fill(); x.fillRect(mk[w] - .75, y0, 1.5, bh);
    }
  }
  function drawSheets(p) {
    const x = sheets.ctx, W = sheets.w, H = sheets.h; sheets.clear();
    const open = S.reduced ? 1 : smooth(.12, .5, p), px = W * .5, py = H * 1.02, n = SHEETS.length;
    const sw = Math.min(170, W * .11), sh = sw * 1.38, R = Math.min(H * .78, W * .5);
    SHEETS.forEach((name, i) => {
      const t = i / (n - 1) - .5, ang = t * lerp(.12, 1.5, open), z = .4 + (i % 3) * .2;
      const rise = (S.reduced ? 0 : (.5 - p) * 120 * z);
      x.save(); x.translate(px + Math.sin(ang) * R * open, py - Math.cos(ang) * R * lerp(.5, 1, open) + rise); x.rotate(ang);
      // 只當背景紋理：壓得很淡，不能搶左欄文字
      x.globalAlpha = .05 + .09 * open;
      x.fillStyle = 'rgba(241,238,230,.9)'; x.fillRect(-sw / 2, -sh / 2, sw, sh);
      x.strokeStyle = 'rgba(9,19,19,.25)'; x.lineWidth = 1; x.beginPath();
      if (i < 6) for (let r = 0; r < 12; r++) { const yy = -sh / 2 + 24 + r * (sh - 32) / 12; x.moveTo(-sw / 2 + 6, yy); x.lineTo(sw / 2 - 6, yy); }
      else { x.rect(-sw / 2 + 8, -sh / 2 + 24, sw - 16, sh - 44); x.moveTo(-sw / 2 + 14, sh * .2); x.bezierCurveTo(-sw * .1, -sh * .1, sw * .1, sh * .3, sw / 2 - 14, -sh * .05); }
      x.stroke();
      x.fillStyle = '#1d2624'; x.font = `${Math.max(9, sw * .075)}px ${FONT}`; x.textAlign = 'left'; x.fillText(name, -sw / 2 + 7, -sh / 2 + 15);
      x.restore();
    });
  }

  setItem('I14');
  return section(el, {
    resize() { bands.resize(); sheets.resize(); },
    update(s) { drawBands(); drawSheets(s.ps); }
  });
}
