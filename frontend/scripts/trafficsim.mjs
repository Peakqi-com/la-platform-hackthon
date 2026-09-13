// 首頁 3D 車流模擬：把 city.js 裡 @@traffic-begin～@@traffic-end 那段（車流控制器）原封不動抽出來，
// 用和 city.js 相同的路線、車型、行駛方向跑長時間，量「車身重疊」「最長停車」「平均速度」。
// 改控制器或車的路線之後要跑一次：重疊必須是 0，也不能有車停超過 30 秒，否則以 exit code 1 結束。
// 用法（repo 根目錄）：node frontend/scripts/trafficsim.mjs [每輪秒數=1200] [種子=1,2,3]
import {readFileSync} from 'node:fs';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {dirname,join} from 'node:path';

const here=dirname(fileURLToPath(import.meta.url)),cw=join(here,'..','public','city-wind');
const THREE=await import(pathToFileURL(join(cw,'three.module.min.js')).href);
const src=readFileSync(join(cw,'city.js'),'utf8');
const pick=(re,what)=>{const m=src.match(re);if(!m)throw new Error('city.js 找不到 '+what);return m;};

// 控制器、路線、車型尺寸都直接從 city.js 讀，避免模擬和畫面兩邊不同步
const block=src.slice(src.indexOf('// @@traffic-begin'),src.indexOf('// @@traffic-end'));
if(!block)throw new Error('city.js 找不到 @@traffic 區段');
const createTraffic=new Function(block+'\nreturn createTraffic;')();
const roundedLoop=new Function('THREE',pick(/function roundedLoop\([^)]*\)\{[\s\S]*?return path;\}/,'roundedLoop')[0]+';return roundedLoop;')(THREE);
const routes=[...pick(/const routes=\[(roundedLoop\([^\]]*)\];/,'車的路線')[1].matchAll(/roundedLoop\(([^)]*)\)/g)].map(m=>roundedLoop(...m[1].split(',').map(Number)));
const VEH_W=new Function('return '+pick(/VEH_W=(\[[^\]]*\])/,'VEH_W')[1])(),VEH_L=new Function('return '+pick(/VEH_L=(\[[^\]]*\])/,'VEH_L')[1])();

const SECONDS=+(process.argv[2]||1200),SEEDS=(process.argv[3]||'1,2,3').split(',').map(Number);

// 與 city.js 建車的迴圈相同（27 台；車型、路線、方向依編號決定），速度與起點用固定種子
function specsFor(seed){
 const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
 const cars=[];
 for(let i=0;i<27;i++){
  const type=i%9===0?3:i%7===0?4:i%5===0?2:i%4===0?1:0,ri=i%routes.length,dir=i%3===0?-1:1,L=routes[ri].getLength();
  cars.push({type,ri,dir,L,u:random(),base:.008+random()*.008,key:ri+'|'+dir});
 }
 const groups=new Map();for(const c of cars){if(!groups.has(c.key))groups.set(c.key,[]);groups.get(c.key).push(c);}
 for(const g of groups.values())g.forEach((c,k)=>{c.u=(k/g.length+k*.011)%1;});
 return cars.map(c=>({ri:c.ri,dir:c.dir,len:VEH_L[c.type],w:VEH_W[c.type],vmax:c.base*c.L,s:(c.dir>0?c.u:1-c.u)*c.L}));
}

function run(seed,dt){
 const T=createTraffic(routes,specsFor(seed*7919)),cars=T.cars,P=cars.map(()=>({}));
 let overlapT=0,events=0,minClear=9,speed=0,samples=0;const stopT=cars.map(()=>0),maxStop=cars.map(()=>0);let prev=new Set();
 for(let t=0;t<SECONDS;t+=dt){
  T.update(dt);
  cars.forEach((c,n)=>{const p=T.at(c.ln,c.s,P[n]);p.hl=c.hl;p.hw=c.hw;});
  const now=new Set();
  for(let a=0;a<cars.length;a++)for(let b=a+1;b<cars.length;b++){
   const A=P[a],B=P[b];if(Math.abs(A.x-B.x)+Math.abs(A.z-B.z)>8)continue;
   const clear=T.bodyDist(A,B)-A.hw-B.hw;if(clear<minClear)minClear=clear;
   if(clear<0){overlapT+=dt;const k=a+'-'+b;now.add(k);if(!prev.has(k))events++;}
  }
  prev=now;
  cars.forEach((c,n)=>{speed+=c.v/c.vmax;if(c.v<.02){stopT[n]+=dt;if(stopT[n]>maxStop[n])maxStop[n]=stopT[n];}else stopT[n]=0;});
  samples++;
 }
 return {events,overlapT,minClear,avgSpeed:speed/samples/cars.length,maxStop:Math.max(...maxStop),stuck:maxStop.filter(x=>x>30).length};
}

let pass=true,worst={minClear:9,maxStop:0};
console.log(`車流模擬：${routes.length} 條路線、27 台車，每輪 ${SECONDS} 秒，種子 ${SEEDS.join(',')}`);
for(const dt of [.05,1/60])for(const seed of SEEDS){
 const r=run(seed,dt);
 worst.minClear=Math.min(worst.minClear,r.minClear);worst.maxStop=Math.max(worst.maxStop,r.maxStop);
 if(r.events>0||r.stuck>0)pass=false;
 console.log(`dt=${dt.toFixed(3)} 種子 ${seed}｜重疊 ${r.events} 次（${r.overlapT.toFixed(2)} 車對·秒）｜最小間隙 ${r.minClear.toFixed(2)} m｜平均速度 ${(r.avgSpeed*100).toFixed(0)}%｜最長停車 ${r.maxStop.toFixed(1)} 秒｜停超過 30 秒 ${r.stuck} 台`);
}
console.log(pass?`通過：沒有任何重疊，最小間隙 ${worst.minClear.toFixed(2)} m，最長停車 ${worst.maxStop.toFixed(1)} 秒`:'未通過：有重疊或卡死，見上方各輪');
process.exit(pass?0:1);
