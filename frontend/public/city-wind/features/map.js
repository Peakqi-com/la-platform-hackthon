// 03 每筆距離都有出處：四層畫布＝四層圖資，用 CSS 3D 疊在一起。
// 捲動前段：四層分開懸浮（看得出是哪幾層資料）；中段：疊回一張圖；
// 後段：依序畫出到學校、市場、公園、站牌的步行路線，每條都附資料集、量測方式與起點。
// 區段範圍取自系統推估的 P002-00 街廓（fixtures/sample_geometry_P002-00.json，投影成公尺）；
// 路網為示意重繪，四條路線的長度等於實測步行距離 114／89／201／168 m。
import { S, Layer, PAL, rgba, section, smooth, clamp, lerp, polyLen, pointAt, strokePartial, FONT } from './core.js';

const EXT = { x0: -262, x1: 236, y0: -226, y1: 236 };
const ROADS = [
  { n: '中山路', w: 18, p: [[-260, 205], [-144.9, 105.7], [-114, 77], [-75.9, 43.1], [-46.3, 17.4], [-38.3, 10], [10, -35.6], [16.7, -43.7], [39.3, -74.9], [61.4, -105.5], [103.5, -167.3], [150, -235]] },
  { n: '金包里街', w: 6, p: [[-230, 115], [-157.7, 124.5], [-146.7, 126.9], [-92, 140], [-79.8, 140.3], [-5, 61.7], [27.3, 40.1], [61.3, 17], [65.8, 12.2], [130, -25], [230, -62]] },
  { n: '福德街', w: 8, p: [[80, 110], [65.8, 12.2], [45.6, -10.1], [56.1, -41.2], [87.8, -76.4], [107.2, -96.8], [113.3, -135.4], [114.4, -147.2], [108.5, -160.8], [103.5, -167.3]] },
  { n: '中正路', w: 8, p: [[-178, 190], [-157.7, 124.5], [-144.9, 105.7]] },
  { n: '仁愛路', w: 8, p: [[-38.3, 10], [-78.5, -32.5], [-130, -90], [-190, -150]] },
  { n: '信義路', w: 8, p: [[-114, 77], [-142.9, 44.6], [-185, -3], [-240, -65]] },
  { n: '和平街', w: 6, p: [[39.3, -74.9], [-5.6, -107.4], [-60, -150], [-120, -205]] },
  { n: '慈護街', w: 6, p: [[27.3, 40.1], [70, 110], [110, 200]] },
  { n: '', w: 6, p: [[-79.8, 140.3], [-60, 210], [-40, 262]] },
  { n: '', w: 5, p: [[-185, -3], [-130, -90], [-60, -150]] },
  { n: '', w: 5, p: [[130, -25], [160, 60], [175, 160]] }
];
const SECTION = [[-157.7, 124.5], [-146.7, 126.9], [-92, 140], [-79.8, 140.3], [-5, 61.7], [27.3, 40.1], [32.4, 36.3], [61.3, 17], [64.9, 13.2], [65.8, 12.2], [45.6, -10.1], [56.1, -41.2], [87.8, -76.4], [88.7, -77.4], [102.2, -90.3], [107.2, -96.8], [113.3, -135.4], [114.4, -147.2], [108.5, -160.8], [103.5, -167.3], [61.4, -105.5], [39.3, -74.9], [16.7, -43.7], [10, -35.6], [-38.3, 10], [-46.3, 17.4], [-75.9, 43.1], [-105.7, 70.2], [-114, 77], [-142.6, 102.7], [-144.9, 105.7]];
const C = [-61.1, 30.25], D = [.755, -.656], N = [.656, .755];     // 路網上的起點、道路方向、向區段內的法向
const F = [C[0] + N[0] * 9, C[1] + N[1] * 9];                        // 宗地臨路邊界中點
const FAC = [
  { name: '金山國小', item: '項目 15 接近學校之程度', band: '優（200 m 以內）', filled: 150, meas: 114, glyph: '校', at: [-160, 36], route: [C, [-75.9, 43.1], [-114, 77], [-142.9, 44.6]] },
  { name: '金山市場', item: '項目 16 接近市場之程度', band: '優（500 m 以內）', filled: 30, meas: 89, glyph: '市', at: [-88, -44], route: [C, [-46.3, 17.4], [-38.3, 10], [-78.5, -32.5]] },
  { name: '中山溫泉公園', item: '項目 17 接近公園、廣場之程度', band: '優（300 m 以內）', filled: 190, meas: 201, glyph: '園', at: [-16, -124], route: [C, [-46.3, 17.4], [-38.3, 10], [10, -35.6], [16.7, -43.7], [39.3, -74.9], [-5.6, -107.4]] },
  { name: '金山區公所站', item: '項目 18 接近車站之程度', band: '優（300 m 以內）', filled: 80, meas: 168, glyph: '站', at: [-196, 131], route: [C, [-75.9, 43.1], [-114, 77], [-144.9, 105.7], [-186.7, 141.7]] }
];
const LAYER_INFO = [
  ['底圖', '國土測繪中心通用版電子地圖與段籍圖；金山一帶 z14–18 已快取，離線可用。'],
  ['路網', 'OpenStreetMap 全新北市路網與步行圖；沒有 OSRM 時用內建步行圖（Dijkstra）。'],
  ['地籍與區段', '地籍圖檔匯入或開放地籍查詢；沒有地價區段圖時依路網推估街廓，標「草稿，需確認」。'],
  ['設施與量測', '政府開放資料＋OpenStreetMap；人工標定的設施來源標「人工標定」。']
];

export function initMap(el) {
  const world = el.querySelector('.f-map-world'), stack = el.querySelector('.f-map-stack');
  const layers = [...el.querySelectorAll('.f-map-layer')].map(c => new Layer(c));
  const tags = [...el.querySelectorAll('.f-map-tag')], lis = [...el.querySelectorAll('.f-layer-list li')];
  const steps = [...el.querySelectorAll('.f-step')], btns = [...el.querySelectorAll('.f-fac-btn')], card = el.querySelector('.f-map-card');
  let sx = 1, ox = 0, oy = 0, step = -1, picked = null, active = -1, tAct = 0, shown = '';
  const P = ([mx, my]) => [ox + (mx - EXT.x0) * sx, oy + (EXT.y1 - my) * sx];
  const path = (x, pts, close) => { x.beginPath(); pts.forEach((q, i) => { const [a, b] = P(q); i ? x.lineTo(a, b) : x.moveTo(a, b); }); if (close) x.closePath(); };
  btns.forEach(b => b.addEventListener('click', () => { picked = +b.dataset.f; tAct = S.t; active = picked; }));

  function fit() {
    const L = layers[0], W = L.w, H = L.h;
    sx = Math.min(W / (EXT.x1 - EXT.x0), H / (EXT.y1 - EXT.y0)); ox = (W - (EXT.x1 - EXT.x0) * sx) / 2; oy = (H - (EXT.y1 - EXT.y0) * sx) / 2;
  }
  function drawStatic() {
    fit();
    // 0 底圖：陸地、海、河、段籍名稱
    let x = layers[0].ctx, W = layers[0].w, H = layers[0].h; layers[0].clear();
    x.fillStyle = '#10211f'; x.fillRect(0, 0, W, H);
    x.fillStyle = '#0c2a33'; x.beginPath(); x.moveTo(0, 0); x.lineTo(W, 0); x.lineTo(W, H * .1); x.bezierCurveTo(W * .7, H * .16, W * .45, H * .02, 0, H * .09); x.closePath(); x.fill();
    x.strokeStyle = '#123b48'; x.lineWidth = Math.max(8, 20 * sx); x.lineCap = 'round'; path(x, [[236, 150], [205, 60], [196, -40], [215, -130], [200, -226]]); x.stroke();
    x.strokeStyle = 'rgba(230,236,225,.05)'; x.lineWidth = 1;
    for (let r = 1; r < 6; r++) { x.beginPath(); x.ellipse(W * .15, H * .95, W * .12 * r, H * .09 * r, -.3, 0, 6.283); x.stroke(); }
    x.font = `600 ${Math.max(14, 30 * sx)}px Georgia, serif`; x.fillStyle = 'rgba(96,132,214,.35)'; x.textAlign = 'center';
    [['溫泉段', 40, 120], ['金美段', -200, 70], ['金山二段', -120, -130], ['金山三段', 150, -170]].forEach(([s, a, b]) => { const [u, v] = P([a, b]); x.fillText(s, u, v); });
    // 1 路網
    x = layers[1].ctx; layers[1].clear(); x.lineCap = 'round'; x.lineJoin = 'round';
    for (const r of ROADS) { x.strokeStyle = '#3b5a5a'; x.lineWidth = Math.max(2.5, r.w * sx + 2); path(x, r.p); x.stroke(); }
    for (const r of ROADS) { x.strokeStyle = '#223c3d'; x.lineWidth = Math.max(1.5, r.w * sx); path(x, r.p); x.stroke(); }
    x.font = `${Math.max(10, 12 * sx)}px ${FONT}`; x.fillStyle = 'rgba(205,216,210,.7)'; x.textAlign = 'center';
    for (const r of ROADS) if (r.n) {
      const mid = pointAt(r.p, polyLen(r.p) * .3), [u, v] = P(mid); let a = -mid[2]; if (a > Math.PI / 2) a -= Math.PI; if (a < -Math.PI / 2) a += Math.PI;
      x.save(); x.translate(u, v); x.rotate(a); x.fillText(r.n, 0, -Math.max(6, r.w * sx / 2 + 4)); x.restore();
    }
    // 2 地籍與區段：沿路的宗地切割（裁在區段內）、區段界線、比準地與比較標的
    x = layers[2].ctx; layers[2].clear();
    x.save(); path(x, SECTION, true); x.clip();
    x.strokeStyle = 'rgba(198,228,204,.22)'; x.lineWidth = 1;
    for (let i = 0; i < SECTION.length; i++) {
      const a = SECTION[i], b = SECTION[(i + 1) % SECTION.length], L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L < 12) continue;
      const d = [(b[0] - a[0]) / L, (b[1] - a[1]) / L], n = [d[1], -d[0]];
      for (let s = 0; s < L; s += 6 + ((s * 7) % 4)) { const p0 = [a[0] + d[0] * s, a[1] + d[1] * s]; path(x, [p0, [p0[0] - n[0] * 22, p0[1] - n[1] * 22]]); x.stroke(); }
    }
    x.restore();
    x.fillStyle = rgba(PAL.gold, .09); path(x, SECTION, true); x.fill();
    x.strokeStyle = PAL.gold; x.lineWidth = 1.6; x.setLineDash([6, 4]); path(x, SECTION, true); x.stroke(); x.setLineDash([]);
    const parcel = [[F[0] - D[0] * 2.5, F[1] - D[1] * 2.5], [F[0] + D[0] * 2.5, F[1] + D[1] * 2.5], [F[0] + D[0] * 2.5 + N[0] * 23, F[1] + D[1] * 2.5 + N[1] * 23], [F[0] - D[0] * 2.5 + N[0] * 23, F[1] - D[1] * 2.5 + N[1] * 23]];
    x.fillStyle = PAL.gold; path(x, parcel, true); x.fill();
    const comp = [[44, 80], [49, 75], [60, 86], [55, 91]].map(([a, b]) => [a, b]);
    x.fillStyle = PAL.meas; path(x, [[40, 84], [45, 79], [57, 91], [52, 96]], true); x.fill(); void comp;
    x.font = `${Math.max(10, 12 * sx)}px ${FONT}`; x.textAlign = 'left';
    let [u, v] = P([F[0] + 14, F[1] + 26]); x.fillStyle = PAL.sand; x.fillText('比準地 金美段489地號', u, v);
    [u, v] = P([62, 100]); x.fillStyle = PAL.meas; x.fillText('比較標的1 溫泉段218地號', u, v);
    [u, v] = P([8, -12]); x.fillStyle = rgba(PAL.gold, .9); x.font = `600 ${Math.max(11, 13 * sx)}px ${FONT}`; x.fillText('區段 P002-00', u, v);
  }

  function drawDynamic(stage) {
    const L = layers[3], x = L.ctx; L.clear(); x.lineCap = 'round'; x.lineJoin = 'round';
    // 設施圖示
    FAC.forEach((f, i) => {
      const [u, v] = P(f.at), on = i === active && stage;
      if (f.glyph === '園') { x.fillStyle = rgba(PAL.leaf, .22); x.beginPath(); x.ellipse(u, v, 26 * sx + 8, 18 * sx + 6, -.4, 0, 6.283); x.fill(); }
      if (f.glyph === '校') { x.strokeStyle = rgba(PAL.leaf, .35); x.strokeRect(u - 22 * sx - 6, v - 16 * sx - 4, 44 * sx + 12, 32 * sx + 8); }
      x.fillStyle = on ? PAL.meas : '#1d3a3c'; x.strokeStyle = PAL.meas; x.lineWidth = 1.4;
      x.beginPath(); x.arc(u, v, 11, 0, 6.283); x.fill(); x.stroke();
      x.fillStyle = on ? PAL.bg : PAL.meas; x.font = `600 11px ${FONT}`; x.textAlign = 'center'; x.fillText(f.glyph, u, v + 4);
      // 名稱放在不會壓到路名的一側（每個設施各自的偏移）
      const [lx, ly, al] = { '校': [0, 27, 'center'], '市': [-16, 4, 'right'], '園': [0, 30, 'center'], '站': [0, -17, 'center'] }[f.glyph];
      x.fillStyle = on ? PAL.fg : 'rgba(205,216,210,.8)'; x.font = `${Math.max(10, 11.5 * sx)}px ${FONT}`; x.textAlign = al; x.fillText(f.name, u + lx, v + ly);
    });
    if (!stage) return;
    const [fu, fv] = P(F), [cu, cv] = P(C);
    FAC.forEach((f, i) => {                               // 其他路線淡淡的
      if (i === active) return; const pts = f.route.map(P);
      x.strokeStyle = rgba(PAL.meas, .18); x.lineWidth = 2; x.beginPath(); pts.forEach((q, j) => j ? x.lineTo(q[0], q[1]) : x.moveTo(q[0], q[1])); x.stroke();
    });
    const f = FAC[active]; if (!f) return;
    const pts = f.route.map(P), len = polyLen(pts), grow = S.reduced ? 1 : clamp((S.t - tAct) / 1.1, 0, 1);
    x.strokeStyle = rgba(PAL.meas, .22); x.lineWidth = 9; strokePartial(x, pts, len * grow);
    x.strokeStyle = PAL.meas; x.lineWidth = 2.6; x.setLineDash([7, 5]); x.lineDashOffset = S.reduced ? 0 : -S.t * 24; strokePartial(x, pts, len * grow); x.setLineDash([]);
    if (grow >= 1 && !S.reduced) { const [px, py] = pointAt(pts, (S.t * 60) % len); x.fillStyle = PAL.fg; x.beginPath(); x.arc(px, py, 3.2, 0, 6.283); x.fill(); }
    // 起點：宗地臨路邊界中點 → 吸附到路網
    x.strokeStyle = PAL.sand; x.lineWidth = 1.2; x.setLineDash([2, 3]); x.beginPath(); x.moveTo(fu, fv); x.lineTo(cu, cv); x.stroke(); x.setLineDash([]);
    const pulse = S.reduced ? .5 : (S.t * .9) % 1;
    x.strokeStyle = rgba(PAL.sand, 1 - pulse); x.beginPath(); x.arc(fu, fv, 5 + pulse * 16, 0, 6.283); x.stroke();
    x.fillStyle = PAL.sand; x.beginPath(); x.arc(fu, fv, 4, 0, 6.283); x.fill();
    if (grow >= 1) {                                       // 距離標籤
      const [mx, my] = pointAt(pts, len * .55), s = `步行 ${f.meas} m`;
      x.font = `600 12px ${FONT}`; const w = x.measureText(s).width + 14;
      x.fillStyle = 'rgba(9,19,19,.9)'; x.strokeStyle = PAL.meas; x.fillRect(mx - w / 2, my - 24, w, 20); x.strokeRect(mx - w / 2, my - 24, w, 20);
      x.fillStyle = PAL.meas; x.textAlign = 'center'; x.fillText(s, mx, my - 10);
    }
  }

  function showCard(key, html) { if (key !== shown) { shown = key; card.innerHTML = html; } }

  return section(el, {
    resize() { layers.forEach(l => l.resize()); drawStatic(); },
    update(s) {
      const p = s.ps, next = p < .5 ? 0 : 1;
      if (next !== step) { step = next; steps.forEach((st, i) => st.classList.toggle('on', i === step)); if (!step) picked = null; }
      const explode = S.reduced ? (p < .45 ? 1 : 0) : 1 - smooth(.26, .5, p);
      const tilt = lerp(10, 57, explode) + (S.reduced ? 0 : S.sny * -3), spin = lerp(-3, -26, explode) + (S.reduced ? 0 : S.snx * 4);
      const spread = Math.min(stack.clientWidth, stack.clientHeight) * .15 * explode;
      // 分層懸浮時縮小並往下放：四層疊高之後最上層不會頂到頁首
      world.style.transform = `translateY(${(explode * 9).toFixed(2)}%) rotateX(${tilt.toFixed(2)}deg) rotateZ(${spin.toFixed(2)}deg) scale(${lerp(1, .68, explode).toFixed(3)})`;
      const focus = explode > .05 ? Math.min(3, Math.floor(clamp(p / .26, 0, .999) * 4)) : -1;   // 前段依序點名四層（由上往下）
      layers.forEach((l, i) => { l.c.style.transform = `translateZ(${(i * spread).toFixed(1)}px)`; l.c.style.setProperty('--edge', (explode * (i === 3 - focus ? .9 : .35)).toFixed(2)); l.c.style.opacity = i === 0 ? 1 : lerp(1, .93, explode); });
      tags.forEach((t, i) => { t.style.transform = `translateZ(${(i * spread + 1).toFixed(1)}px)`; t.style.setProperty('--tag', (explode * (i === 3 - focus ? 1 : .55)).toFixed(2)); });
      lis.forEach(li => li.classList.toggle('on', +li.dataset.l === 3 - focus));
      // 後段：依捲動輪流畫四條路線；使用者點過就以點的為準
      if (step === 1) {
        const auto = Math.min(3, Math.floor(smooth(.52, .95, p) * 4 - 1e-3 + (p > .95 ? 1 : 0)));
        const want = picked ?? Math.max(0, auto);
        if (want !== active) { active = want; tAct = S.t; }
        btns.forEach((b, i) => b.classList.toggle('on', i === active));
        const f = FAC[active];
        showCard('f' + active, `<h3>${f.name}　<span class="f-badge ok">相符</span></h3><p><span class="k">送審書表</span>填載 ${f.filled} m　<span class="k">系統實測</span>步行 ${f.meas} m</p><p><span class="k">判定</span>${f.item}：兩者同為${f.band}</p><p><span class="k">出處</span>OpenStreetMap（© OpenStreetMap contributors）· 內建步行路網（OSRM → 內建步行圖 → 直線 × 1.3）· 起點：宗地臨路邊界中點</p>`);
      } else {
        active = -1; btns.forEach(b => b.classList.remove('on'));
        const li = LAYER_INFO[focus < 0 ? 0 : 3 - focus];
        showCard('l' + focus, `<h3>${focus < 0 ? '四層疊合' : li[0]}</h3><p>${focus < 0 ? '四層共用同一個座標系（TWD97），疊回來就是一張可以量距離的圖。' : li[1]}</p>`);
      }
      drawDynamic(step === 1);
    }
  });
}
