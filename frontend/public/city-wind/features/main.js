// 系統功能段的進入點。和 app.js（3D 城市）完全分開載入：
// 3D 失敗、WebGL 不支援，這一段照樣能讀、能操作。
// 與 app.js 只透過 <html> 上的 class 溝通：
//   f-near        系統功能快進畫面：故事的固定文字、頁尾 HUD 讓開
//   f-in          正在系統功能範圍：頁首導覽改亮「系統」、左側章節導覽出現
//   city-covered  3D 城市完全被蓋住：app.js 暫停渲染，把效能讓給這一段
import { S, root, clamp, measure, watchVisibility, watchReveals, setNear, onFrame, goTo, sections } from './core.js';
import { initAmbient } from './ambient.js';
import { initSources } from './sources.js';
import { initChain } from './chain.js';
import { initEntry } from './entry.js';
import { initMap } from './map.js';
import { initRules } from './rules.js';
import { initReview } from './review.js';
import { initCase } from './case.js';
import { initOutput } from './output.js';
import { initFuture } from './future.js';
import { initEnd } from './end.js';

const host = document.getElementById('features');
const MODULES = [
  ['f-sources', initSources], ['f-chain', initChain], ['f-entry', initEntry], ['f-map', initMap],
  ['f-rules', initRules], ['f-review', initReview], ['f-case', initCase], ['f-output', initOutput],
  ['f-future', initFuture], ['f-end', initEnd]
];

if (host) {
  root.classList.add('js-f');
  initAmbient(host);
  // 除錯用：?fskip=f-map,f-entry 可略過指定段落的動畫（排查效能或相容性時用）
  const skip = (new URLSearchParams(location.search).get('fskip') || '').split(',');
  for (const [id, init] of MODULES) {
    const el = document.getElementById(id);
    if (!el || skip.includes(id)) continue;
    try { init(el); } catch (err) { console.error('系統功能段載入失敗：', id, err); }
  }
  watchReveals(host);
  watchVisibility();

  let fTop = 0, fBottom = 0;
  function mode() {
    const y = scrollY, vh = innerHeight, rel = fTop - y;
    setNear(rel < vh * 1.1 && fBottom - y > 0);
    root.classList.toggle('f-near', rel < vh * .55);
    root.classList.toggle('f-in', rel < vh * .3 && fBottom - y > vh * .4);
    root.classList.toggle('city-covered', rel <= -vh * .72);
    root.style.setProperty('--f-lift', String(Math.round(clamp(vh * .55 - rel, 0, vh) * .16)));
  }
  function measureAll() {
    const b = host.getBoundingClientRect(); fTop = b.top + scrollY; fBottom = fTop + host.offsetHeight;
    measure(); mode();
  }
  addEventListener('scroll', mode, { passive: true });
  addEventListener('resize', measureAll, { passive: true });
  new ResizeObserver(() => measureAll()).observe(host);
  document.fonts?.ready?.then(measureAll);
  measureAll();

  // 左側章節導覽：目前段落＝畫面中線落在哪一段
  const rail = [...host.querySelectorAll('.f-rail a')], railBar = host.querySelector('.f-rail-line b');
  const railIds = rail.map(a => a.getAttribute('href').slice(1));
  let lastActive = null;
  onFrame(() => {
    const mid = S.y + S.vh * .5; let cur = null;
    for (const s of sections()) if (s.top <= mid) cur = s;
    S.active = cur ? cur.el : null;
    if (cur === lastActive) return; lastActive = cur;
    root.classList.toggle('f-rail-off', cur?.id === 'f-future');
    let idx = cur ? railIds.indexOf(cur.id) : -1;
    if (idx < 0 && cur) idx = railIds.length - 1;       // 結尾段算在最後一格
    rail.forEach((a, i) => { a.classList.toggle('on', i === idx); if (i === idx) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current'); });
    if (railBar) railBar.style.height = `${Math.max(0, idx) / Math.max(1, rail.length - 1) * 100}%`;
  });

  // 系統功能內的錨點：落在段落頂端（釘住的段落從第一個階段開始）
  document.querySelectorAll('a[href^="#f-"]').forEach(a => a.addEventListener('click', e => {
    const el = document.getElementById(a.getAttribute('href').slice(1));
    if (!el) return;
    e.preventDefault(); goTo(el, 0); history.replaceState(null, '', a.getAttribute('href'));
  }));
  // 整段在載入完成後才出現（index.html 內嵌樣式先把 #features 藏起來）：
  // 等 3D 暖機完成（#loading 加上 done）、字型載好，再確認樣式表真的套上了才顯示。
  // 樣式表沒套上（例如新檔案沒重新 npm run build 而 404）就維持隱藏，不讓沒排版的內容露出來或被 3D 蓋住。
  const loader = document.getElementById('loading');
  const loaderDone = new Promise(res => {
    if (!loader || loader.classList.contains('done')) return res();
    const mo = new MutationObserver(() => { if (loader.classList.contains('done')) { mo.disconnect(); res(); } });
    mo.observe(loader, { attributes: true, attributeFilter: ['class'] });
  });
  const wait = ms => new Promise(res => setTimeout(res, ms));
  Promise.race([Promise.all([loaderDone, document.fonts?.ready ?? Promise.resolve()]), wait(15000)]).then(() => {
    if (getComputedStyle(host).position !== 'relative') { console.warn('系統功能段的樣式表沒有載入（新增檔案後需重新 npm run build），先不顯示'); return; }
    measureAll(); root.classList.add('f-ready');
  });

  if (location.hash.startsWith('#f-')) requestAnimationFrame(() => {
    const el = document.getElementById(location.hash.slice(1));
    if (el) scrollTo({ top: el.getBoundingClientRect().top + scrollY, behavior: 'instant' });
  });
}
