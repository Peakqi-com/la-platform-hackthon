// 07 輸出、紀錄與部署：釘住的段落，三個階段各換一張「前景」：
//   0 十個檔案從不同景深飛進 zip（跟著捲動一張一張收進去）
//   1 案件的一生：可以按的狀態機，按一下就寫一筆操作紀錄（和系統的 audit 同樣欄位）
//   2 架構：瀏覽器 → EC2（Caddy／Next.js／FastAPI）→ 本機資料層與 Bedrock，封包沿線跑
// 背後一層畫布是往遠處退的地面網格，隨捲動前進（視差）。
import { S, Layer, PAL, rgba, section, clamp, lerp, smooth, rng, centerIn, FONT } from './core.js';

export function initOutput(el) {
  const far = new Layer(el.querySelector('.f-out-far'), { max: 1.25 }), steps = [...el.querySelectorAll('.f-step')], panes = [...el.querySelectorAll('.f-out-pane')];
  const box = el.querySelector('.f-files'), files = [...el.querySelectorAll('.f-file')], zip = el.querySelector('.f-zip'), zn = zip.querySelector('.n');
  let step = -1, spots = [];
  const R = rng(21), seeds = files.map(() => ({ z: .25 + R() * .75, rot: (R() - .5) * .16 }));

  function layoutFiles() {
    const W = box.clientWidth, H = box.clientHeight, fw = files[0].offsetWidth, fh = files[0].offsetHeight, cols = W > 620 ? 4 : 3;
    spots = files.map((f, i) => {
      const c = i % cols, r = (i / cols) | 0, jx = (R() - .5) * 30, jy = (R() - .5) * 26;
      return [clamp(c * (W - fw) / (cols - 1) + jx, 0, W - fw), clamp(r * (H * .72 - fh) / Math.ceil(files.length / cols - 1) + jy, 0, H - fh)];
    });
    zip.style.left = `${W - zip.offsetWidth}px`; zip.style.top = `${H - zip.offsetHeight}px`;
  }
  function drawFiles(p) {
    const W = box.clientWidth, H = box.clientHeight, zx = W - zip.offsetWidth / 2, zy = H - zip.offsetHeight / 2;
    let packed = 0;
    files.forEach((f, i) => {
      const a = S.reduced ? (p > .2 ? 1 : 0) : smooth(.05 + i * .018, .16 + i * .018, p), [sx, sy] = spots[i] || [0, 0], s = seeds[i];
      const mx = S.snx * 26 * s.z * (1 - a), my = S.sny * 18 * s.z * (1 - a);
      const x = lerp(sx, zx - f.offsetWidth / 2, a) + mx, y = lerp(sy, zy - f.offsetHeight / 2, a * a) + my - Math.sin(a * Math.PI) * 60;
      f.style.transform = `translate3d(${x.toFixed(1)}px,${y.toFixed(1)}px,0) rotate(${(s.rot * (1 - a) + a * .4).toFixed(3)}rad) scale(${lerp(.82 + s.z * .18, .18, a).toFixed(3)})`;
      f.style.opacity = (1 - smooth(.85, 1, a)).toFixed(3); f.style.zIndex = String(Math.round(s.z * 10));
      if (a > .97) packed++;
    });
    zn.textContent = packed; zip.style.transform = packed ? `scale(${1 + .04 * Math.sin(S.t * 6) * (packed === files.length ? 0 : 1)})` : 'none';
  }

  // 案件的一生：狀態機
  const states = [...el.querySelectorAll('.f-life-states span')], out = el.querySelector('.f-life-out b'), log = el.querySelector('.f-life-log'), btns = Object.fromEntries([...el.querySelectorAll('.f-life-btns button')].map(b => [b.dataset.a, b]));
  const st = { status: 'review', stale: false, archived: false }; let clock = 14 * 60 + 2;
  function write(action, detail) {
    clock += 1 + Math.round(R() * 3); const hh = String((clock / 60) | 0).padStart(2, '0'), mm = String(clock % 60).padStart(2, '0');
    const li = document.createElement('li'); li.innerHTML = `<span>${hh}:${mm}</span><span>承辦</span><span>${action}・${detail}</span>`;
    log.prepend(li); while (log.children.length > 5) log.lastChild.remove();
  }
  function paint() {
    states.forEach(s => { s.classList.toggle('on', s.dataset.s === st.status); s.classList.toggle('arch', st.archived); });
    out.textContent = st.stale ? '已過期（輸入晚於產出）' : '最新'; out.classList.toggle('stale', st.stale);
    btns.regen.disabled = !st.stale || st.archived; btns.finish.disabled = st.stale || st.status === 'done' || st.archived;
    btns.edit.disabled = btns.decide.disabled = st.archived; btns.archive.textContent = st.archived ? '復原' : '封存';
  }
  const ACT = {
    edit: () => { st.stale = true; if (st.status === 'done') st.status = 'review'; write('修改輸入', '宗地條件變更 2 處'); },
    regen: () => { st.stale = false; write('重新產生書表', '比較價格 212,958；不符 5、需確認 1'); },
    decide: () => write('儲存承辦裁決', '變更 1 處'),
    finish: () => { st.status = 'done'; write('狀態變更', '審查中 → 已完成'); },
    archive: () => { st.archived = !st.archived; write(st.archived ? '封存案件' : '復原案件', st.archived ? '資料與紀錄保留' : '回到案件清單'); }
  };
  Object.entries(btns).forEach(([k, b]) => b.addEventListener('click', () => { ACT[k](); paint(); }));
  write('建立案件', '上傳送審書表 PDF'); write('重新產生書表', '比較價格 212,958；不符 5、需確認 1'); paint();

  // 架構圖
  const arch = el.querySelector('.f-arch'), ac = new Layer(el.querySelector('.f-arch-canvas')), nodes = Object.fromEntries([...el.querySelectorAll('.f-arch-node')].map(n => [n.dataset.n, n]));
  const EDGES = [['user', 'ec2', PAL.gold, 1, 'HTTPS'], ['ec2', 'data', PAL.ok, 1.3, '讀寫'], ['ec2', 'bedrock', PAL.meas, .35, '< 1 RPS']];
  let hot = null;
  Object.values(nodes).forEach(n => { n.addEventListener('pointerenter', () => { hot = n.dataset.n; }); n.addEventListener('pointerleave', () => { hot = null; }); });
  function drawArch() {
    const x = ac.ctx; ac.clear();
    for (const [a, b, col, rate, label] of EDGES) {
      const A = centerIn(nodes[a], arch), B = centerIn(nodes[b], arch), on = !hot || hot === a || hot === b;
      x.strokeStyle = rgba(col, on ? .5 : .12); x.lineWidth = on ? 1.6 : 1; x.setLineDash([4, 5]); x.beginPath(); x.moveTo(A.x, A.y); x.lineTo(B.x, B.y); x.stroke(); x.setLineDash([]);
      if (on) {
        const n = Math.max(1, Math.round(3 * rate));
        for (let k = 0; k < n; k++) {
          const t = ((S.reduced ? .5 : S.t * .35 * rate) + k / n) % 1, back = k % 2;
          const tx = back ? 1 - t : t, px = lerp(A.x, B.x, tx), py = lerp(A.y, B.y, tx);
          x.fillStyle = back ? PAL.fg : col; x.beginPath(); x.arc(px, py, back ? 2.4 : 3.4, 0, 6.283); x.fill();
        }
        x.fillStyle = rgba(col, .9); x.font = `11px ${FONT}`; x.textAlign = 'center'; x.fillText(label, (A.x + B.x) / 2 + 10, (A.y + B.y) / 2 - 8);
      }
    }
  }
  function drawFar(p) {
    const x = far.ctx, W = far.w, H = far.h; far.clear();
    const hz = H * .56, vx = W * .66, shift = (S.reduced ? 0 : p * 900 + S.t * 8) % 60;
    x.strokeStyle = 'rgba(159,211,173,.07)'; x.lineWidth = 1; x.beginPath();
    for (let i = -14; i <= 14; i++) { x.moveTo(vx, hz); x.lineTo(vx + i * W * .12, H + 40); }
    for (let k = 0; k < 14; k++) { const t = (k * 60 + shift) / 840, yy = hz + (H - hz) * t * t; x.moveTo(0, yy); x.lineTo(W, yy); }
    x.stroke();
  }

  return section(el, {
    resize() { far.resize(); ac.resize(); layoutFiles(); },
    enter() { layoutFiles(); },
    update(s) {
      const p = s.ps, next = p < .34 ? 0 : p < .67 ? 1 : 2;
      if (next !== step) { step = next; steps.forEach((x, i) => x.classList.toggle('on', i === step)); panes.forEach((x, i) => x.classList.toggle('on', i === step)); if (step === 2) ac.resize(); }
      drawFar(p);
      if (step === 0) drawFiles(clamp(p / .34, 0, 1));
      if (step === 2) drawArch();
    }
  });
}
