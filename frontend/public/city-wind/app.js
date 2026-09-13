import * as THREE from './three.module.min.js';
import {buildCity,buildSurvey,buildWind} from './city.js';
import {buildDocument,buildAppraiser,buildMagnifier} from './props.js';
import {FireworkSystem} from './systems/fireworks.js';
import {MaterialLibrary} from './systems/materials.js';
import {ScrollController,SceneStateMachine,CameraDirector,smooth} from './systems/state.js';
import {QualityManager} from './systems/quality.js';
import {TimeOfDaySystem,LightingSystem} from './systems/lighting.js';
import {ParcelOverlay,CadastralLayer} from './systems/parcel.js';
import {CrowdSystem,BirdSystem,AircraftSystem,EnvironmentSystem} from './systems/life.js';
import {PostProcessingSystem} from './systems/postprocessing.js';

const clamp=THREE.MathUtils.clamp,lerp=THREE.MathUtils.lerp;
const sections=[...document.querySelectorAll('.scene-section')],chapters=[...document.querySelectorAll('.chapter')],links=[...document.querySelectorAll('nav a')];
const loader=document.querySelector('#loading'),counter=document.querySelector('#counter'),progressBar=document.querySelector('#progress');
const parcelTag=document.querySelector('#parcel-tag'),valuation=document.querySelector('#valuation'),modelNote=document.querySelector('#model-note');
const media=matchMedia('(prefers-reduced-motion: reduce)');let reduced=media.matches,active=-1;

function showChapter(value,pageProgress,mobile){
 const index=Math.min(4,Math.floor(value+.04));if(index!==active){active=index;chapters.forEach((chapter,i)=>{chapter.classList.toggle('active',i===index);chapter.setAttribute('aria-hidden',i===index?'false':'true');chapter.inert=i!==index;});links.forEach((link,i)=>{link.classList.toggle('active',i===index);if(i===index)link.setAttribute('aria-current','step');else link.removeAttribute('aria-current');});counter.textContent=`0${index+1} — 05`;document.documentElement.classList.toggle('at-ending',index===4);}
 const local=value-index,fadeIn=index===0||reduced?1:smooth(-.02,.18,local),fadeOut=index===4||reduced?1:1-smooth(.8,.96,local),alpha=fadeIn*fadeOut,shift=reduced?0:(1-fadeIn)*15-(1-fadeOut)*12;
 chapters.forEach((chapter,i)=>{chapter.style.opacity=i===index?alpha:0;});chapters[index].style.transform=mobile?`translateY(${shift}px)`:`translateY(calc(-46% + ${shift}px))`;progressBar.style.width=`${pageProgress*100}%`;
 const val=smooth(3.05,3.24,value)*(1-smooth(3.76,3.96,value));valuation.style.opacity=val;valuation.style.visibility=val>.01?'visible':'hidden';valuation.style.setProperty('--reveal',smooth(3.18,3.65,value));
}

// 精簡動態只跟隨系統的「減少動態效果」設定；頁首的手動切換鍵已移除。
function applyMotion(value){reduced=value;document.documentElement.style.scrollBehavior=value?'auto':'smooth';}
media.addEventListener('change',event=>applyMotion(event.matches));
// 點導覽或任何錨點時，不要停在區段頂端：那裡 fadeIn 只有 3%，文字幾乎看不見，會被誤會成卡住。
// 落在區段 34% 處，fadeIn（.18 到 1）與 fadeOut（.8 才開始）都在完全不透明的區間。
const CHAPTER_ANCHOR=.34;
function scrollToSection(section,instant){scrollTo({top:section.offsetTop+section.offsetHeight*CHAPTER_ANCHOR,behavior:(instant||reduced)?'instant':'smooth'});}
// 只接管五個故事章節的錨點；系統功能（#f-…）的錨點由 features/main.js 處理，落在段落頂端。
for(const anchor of document.querySelectorAll('a[href^="#"]'))anchor.addEventListener('click',event=>{const section=document.getElementById(anchor.getAttribute('href').slice(1));if(section?.classList.contains('scene-section')){event.preventDefault();scrollToSection(section);history.replaceState(null,'',anchor.getAttribute('href'));}});

// ── 城市轉進系統之前的最後一幕：一陣風 ──
// 固定全螢幕的 2D 畫布（#gust-canvas），畫在 3D 城市之上、系統功能之下。
// 風線是在平滑流場裡前進的點，記住最近的位置畫成頭亮尾暗的尾跡；另有幾條又寬又淡的長帶子，和順風翻滾的落葉。
// 顏色沿用系統功能背景風的金色與淡綠，接到那一段時看起來是同一陣風。捲動越快風越急。
function createGust(cv){
 const ctx=cv.getContext('2d');let W=1,H=1,R=1,shown=false,t=0,lastY=scrollY,boost=0,seed=424242;
 const rnd=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
 const COLS=['227,172,120','255,226,183','198,228,204','169,212,208'],LEAF=['#9aa96f','#c2a055','#b8794a','#7f9a63'];
 const make=(n,hist,wide)=>Array.from({length:n},()=>({hx:new Float32Array(hist),hy:new Float32Array(hist),hn:0,acc:0,hist,wide,x:0,y:0,z:0,c:0,life:0,span:1}));
 const streaks=make(180,16,false),ribbons=make(7,46,true),leaves=Array.from({length:24},()=>({x:0,y:0,r:0,vr:0,z:0,c:0}));
 function resize(){R=Math.min(devicePixelRatio||1,1.5);W=innerWidth;H=innerHeight;const w=Math.round(W*R),h=Math.round(H*R);if(cv.width!==w||cv.height!==h){cv.width=w;cv.height=h;}}
 function spawn(p,anywhere,midLife){p.z=rnd();p.x=anywhere?rnd()*W*.85:-60-rnd()*W*.35;p.y=H*(.06+rnd()*.88);p.hn=0;p.acc=0;p.c=Math.floor(rnd()*COLS.length);p.life=midLife?rnd()*.6:0;p.span=p.wide?5+rnd()*3:2.6+rnd()*3.2;}
 function spawnLeaf(l,anywhere){l.x=anywhere?rnd()*W:-20-rnd()*W*.3;l.y=H*(.15+rnd()*.75);l.r=rnd()*6.28;l.vr=(rnd()-.5)*7;l.z=.6+rnd()*.8;l.c=Math.floor(rnd()*LEAF.length);}
 // 流場：整體由西往東、略往上揚；幾個低頻正弦疊成緩慢翻捲的氣流
 const angle=(x,y)=>-.18+Math.sin(x*.0023+t*.35)*.3+Math.cos(y*.0033-t*.27)*.24+Math.sin((x-y)*.0015+t*.2)*.2;
 function step(p,dt){
  const a=angle(p.x,p.y),v=(p.wide?150:110+p.z*280)*(1+boost);
  p.x+=Math.cos(a)*v*dt;p.y+=Math.sin(a)*v*dt*.75;p.life+=dt/p.span;p.acc+=dt;
  if(p.acc>=.028){p.acc=0;for(let i=p.hist-1;i>0;i--){p.hx[i]=p.hx[i-1];p.hy[i]=p.hy[i-1];}p.hx[0]=p.x;p.hy[0]=p.y;p.hn=Math.min(p.hist,p.hn+1);}
  // 重生時近半數直接出現在畫面中段（從淡入開始），風才會一路吹過整座城市，不會只擠在左半邊
  if(p.x>W+100||p.life>=1||p.y<-100||p.y>H+100)spawn(p,rnd()<.45,false);
 }
 addEventListener('resize',()=>{if(shown)resize();},{passive:true});
 return {update(dt,amt){
  const y=scrollY;boost+=(Math.min(1.4,Math.abs(y-lastY)/Math.max(dt,.001)/1600)-boost)*Math.min(1,dt*5);lastY=y;
  if(amt<.004){if(shown){ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,cv.width,cv.height);cv.style.display='none';shown=false;}return;}
  if(!shown){cv.style.display='block';shown=true;resize();streaks.forEach(p=>spawn(p,true,true));ribbons.forEach(p=>spawn(p,true,true));leaves.forEach(l=>spawnLeaf(l,true));}
  t+=dt;
  ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,cv.width,cv.height);ctx.setTransform(R,0,0,R,0,0);
  ctx.lineCap='round';ctx.lineJoin='round';ctx.globalCompositeOperation='lighter';
  // 長帶子：又寬又淡，像被風拉長的一整片氣流
  for(const p of ribbons){step(p,dt);if(p.hn<4)continue;const f=Math.sin(Math.min(1,p.life)*Math.PI)*amt;
   ctx.strokeStyle=`rgba(${COLS[p.c]},${(.07*f).toFixed(3)})`;ctx.lineWidth=9+p.z*10;ctx.beginPath();ctx.moveTo(p.hx[0],p.hy[0]);for(let i=1;i<p.hn;i++)ctx.lineTo(p.hx[i],p.hy[i]);ctx.stroke();}
  // 風線：頭亮尾暗分三段畫；依顏色、亮度、遠近分組一起描，筆數少
  const groups=new Map();
  for(const p of streaks){step(p,dt);if(p.hn<3)continue;const f=Math.sin(Math.min(1,p.life)*Math.PI)*(.45+p.z*.55),q=f<.33?0:f<.66?1:2,key=p.c*6+q*2+(p.z>.55?1:0);let g=groups.get(key);if(!g)groups.set(key,g=[]);g.push(p);}
  for(const [key,list] of groups){
   const c=COLS[Math.floor(key/6)],q=Math.floor(key%6/2),near=key%2,base=[.2,.42,.66][q]*amt;
   for(let seg=0;seg<3;seg++){
    ctx.strokeStyle=`rgba(${c},${(base*(1-seg*.3)).toFixed(3)})`;ctx.lineWidth=(near?1.7:.9)*(1-seg*.2);ctx.beginPath();
    for(const p of list){const n=p.hn-1,i0=Math.floor(seg*n/3),i1=Math.floor((seg+1)*n/3);if(i1<=i0)continue;ctx.moveTo(p.hx[i0],p.hy[i0]);for(let i=i0+1;i<=i1;i++)ctx.lineTo(p.hx[i],p.hy[i]);}
    ctx.stroke();
   }
  }
  ctx.globalCompositeOperation='source-over';
  // 落葉：順著氣流翻滾
  for(const l of leaves){
   const a=angle(l.x,l.y),v=(170+l.z*170)*(1+boost);l.x+=Math.cos(a)*v*dt;l.y+=Math.sin(a)*v*dt*.75+Math.sin(t*2+l.r)*18*dt;l.r+=l.vr*dt;
   if(l.x>W+30||l.y<-30||l.y>H+30)spawnLeaf(l,false);
   ctx.save();ctx.translate(l.x,l.y);ctx.rotate(l.r);ctx.scale(1,Math.abs(Math.cos(t*3+l.r))*.8+.2);ctx.globalAlpha=.75*amt;ctx.fillStyle=LEAF[l.c];ctx.beginPath();ctx.ellipse(0,0,5.5*l.z,2.6*l.z,0,0,6.283);ctx.fill();ctx.restore();
  }
  ctx.globalAlpha=1;
 }};
}

try{
 const quality=new QualityManager(),renderer=new THREE.WebGLRenderer({canvas:document.querySelector('#world'),antialias:true,alpha:false,powerPreference:'high-performance'});quality.applyRenderer(renderer);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.1;
 const scene=new THREE.Scene();scene.fog=new THREE.FogExp2(0x30484b,.002);const camera=new THREE.PerspectiveCamera(37,innerWidth/innerHeight,.1,650);
 const materials=new MaterialLibrary(),city=buildCity(materials);scene.add(city.root);city.parcels.forEach((parcel,i)=>parcel.id=parcel.selected?'0128':String(201+i).padStart(4,'0'));
 const survey=buildSurvey(city.parcels);city.root.add(survey.root);const cadastral=new CadastralLayer(survey),targetParcel=city.parcels.find(parcel=>parcel.selected),parcelOverlay=new ParcelOverlay(targetParcel);city.root.add(parcelOverlay.root);
 const fireworks=new FireworkSystem(scene,quality);
 const wind=buildWind();scene.add(wind.root);const paper=buildDocument(materials);scene.add(paper.root);paper.root.visible=false;const appraiser=buildAppraiser(materials);scene.add(appraiser);scene.add(appraiser.userData.faceLight);appraiser.visible=false;
 const desk=new THREE.Group(),tabletop=new THREE.Mesh(new THREE.BoxGeometry(34,.6,25),materials.materials.roof);tabletop.position.set(23,-.3,3);tabletop.receiveShadow=true;desk.add(tabletop);for(const x of [8,38])for(const z of [-7,13]){const leg=new THREE.Mesh(new THREE.CylinderGeometry(.2,.2,7,12),materials.materials.trim);leg.position.set(x,-4,z);desk.add(leg);}scene.add(desk);
 // Existing labels remain attached to the cadastral plane and fade with it.
 for(const parcel of city.parcels){const canvas=document.createElement('canvas');canvas.width=512;canvas.height=256;const ctx=canvas.getContext('2d');ctx.fillStyle=parcel.selected?'#ffe2b7':'#c6e4cc';ctx.textAlign='center';ctx.font='500 54px sans-serif';ctx.fillText(parcel.id,256,128);ctx.font='21px sans-serif';ctx.fillText(parcel.selected?'起風段 / 選定宗地':'宗地示意',256,178);const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;const label=new THREE.Mesh(new THREE.PlaneGeometry(6.5,3.25),new THREE.MeshBasicMaterial({map:texture,transparent:true,opacity:0,depthWrite:false}));label.rotation.x=-Math.PI/2;label.position.set(parcel.x,.7,parcel.z);label.renderOrder=802;survey.root.add(label);survey.labels.push(label);}

 const scroll=new ScrollController(sections,{reduced:()=>reduced}),stateMachine=new SceneStateMachine(),cameraDirector=new CameraDirector(camera),timeOfDay=new TimeOfDaySystem();
 // 開場暖機：把之後才會出現的組態全部先編譯、先上傳，完成前載入畫面一直顯示。
 // 第一次捲一遍會卡、第二遍才順，是因為 three.js 第一次畫到某個「光源數量＋物件＋畫到哪裡」組合時
 // 才編譯對應的著色器並快取：
 //  1) 路燈白天隱藏、入夜才亮，光源數量一變，全場有光照的材質都要重編，這是最大的一次停頓；
 //  2) 文件、估價師、碎片、月亮、煙火、地籍圖層、放大鏡開場都是隱藏的，第一次出現才編譯；
 //  3) 畫進離屏目標（後製、放大鏡）時不做色調映射、輸出線性色彩，跟直接畫到畫面是兩個不同的著色器版本。
 //     HIGH／MEDIUM 有後製，主場景每幀都先畫進 post.target，暖機必須綁同一個目標再編譯。
 //     之前沒綁，編好的全是用不到的版本，估價師一出現、路燈一亮就當場重編，第一次捲到「價值」會卡住；
 //  4) compile 只編譯著色器，貼圖要另外 initTexture 才會先上傳；
 //     著色器第一次使用時的檢查、幾何上傳、路燈陰影貼圖，要真的畫過一次才會做掉。
 // 白天與夜晚兩種路燈組態各編譯一次；compileAsync 平行編譯，不卡主執行緒（載入動畫照跑）。
 async function warmup(){
  const saved=[],magSaved=[];
  scene.traverse(o=>saved.push([o,o.visible,o.frustumCulled]));magnifier.scene.traverse(o=>magSaved.push([o,o.visible]));
  scene.traverse(o=>{if(!o.isLight)o.visible=true;});magnifier.scene.traverse(o=>{o.visible=true;});
  const spots=lighting.streetLights.spots,qs=quality.settings;
  // 夜晚的路燈組態要與 StreetLightManager.update 完全一致（數量與投影數），快取鍵才會相同
  const setSpots=on=>spots.forEach((sl,i)=>{sl.light.visible=on&&i<qs.activeLights;sl.light.castShadow=i<qs.shadowLights;});
  // 主場景實際畫進哪裡：有後製是 post.target，沒有就是畫面（null）
  const mainTarget=qs.post?post.target:null;
  const compile=(sc,cam,target)=>{renderer.setRenderTarget(target);const job=renderer.compileAsync?renderer.compileAsync(sc,cam):Promise.resolve(renderer.compile(sc,cam));renderer.setRenderTarget(null);return job;};
  try{
   const jobs=[];
   // compileAsync 在呼叫當下就決定版本並送出編譯，所以可以接著切組態
   setSpots(true);jobs.push(compile(scene,camera,mainTarget));
   setSpots(false);jobs.push(compile(scene,camera,mainTarget));
   // 放大鏡（地籍那一章，白天）把主場景畫進離屏的 source；沒有後製時那是另一個版本
   if(!mainTarget)jobs.push(compile(scene,camera,source));
   jobs.push(compile(magnifier.scene,magnifier.camera,null));
   if(renderer.initTexture){
    const seen=new Set();
    const up=v=>{if(v&&v.isTexture&&!v.isRenderTargetTexture&&!seen.has(v)){seen.add(v);try{renderer.initTexture(v);}catch(e){}}};
    const grab=o=>{const ms=o.material?(Array.isArray(o.material)?o.material:[o.material]):[];for(const m of ms){for(const k in m)up(m[k]);if(m.uniforms)for(const u of Object.values(m.uniforms))up(u&&u.value);}};
    scene.traverse(grab);magnifier.scene.traverse(grab);
   }
   // 最多等 10 秒，少數驅動不回報完成時也不會卡死在載入畫面
   await Promise.race([Promise.all(jobs),new Promise(r=>setTimeout(r,10000))]);
   // 離屏實際畫一次（夜晚、白天各一次），畫面上看不到；關掉視錐剔除，鏡頭外的物件也要真的畫到
   scene.traverse(o=>{o.frustumCulled=false;});
   for(const on of [true,false]){setSpots(on);spots.forEach(sl=>{sl.light.intensity=sl.light.visible?1:0;});renderer.setRenderTarget(mainTarget||source);renderer.render(scene,camera);}
  }catch(e){console.warn('warmup skipped',e);}
  renderer.setRenderTarget(null);
  for(const [o,v,f] of saved){o.visible=v;o.frustumCulled=f;}for(const [o,v] of magSaved)o.visible=v;
 }
 const lighting=new LightingSystem(scene,renderer,materials,city,quality),crowd=new CrowdSystem(city,materials,quality),birds=new BirdSystem(scene,quality),aircraft=new AircraftSystem(scene,materials),environment=new EnvironmentSystem(scene,city,materials),post=new PostProcessingSystem(renderer,quality);
 const source=new THREE.WebGLRenderTarget(1,1,{depthBuffer:true});source.texture.colorSpace=THREE.SRGBColorSpace;const magnifier=buildMagnifier(source.texture);magnifier.lensMat.fragmentShader=magnifier.lensMat.fragmentShader.replace('gl_FragColor=vec4(c,1.);','gl_FragColor=vec4(c,1.);\n#include <colorspace_fragment>\n');
 const gustEl=document.getElementById('gust'),gustCanvas=document.getElementById('gust-canvas'),featuresEl=document.getElementById('features'),gust=gustCanvas?createGust(gustCanvas):null;

 let width=innerWidth,height=innerHeight,mobile=width<=600,dpr=quality.pixelRatio,paused=false,lastFrame=performance.now(),firstFrame=true;
 function resize(){width=innerWidth;height=innerHeight;mobile=width<=600;scroll.measure();quality.applyRenderer(renderer);dpr=quality.pixelRatio;renderer.setSize(width,height,false);camera.aspect=width/height;camera.clearViewOffset();if(mobile)camera.setViewOffset(width,height,0,-height*.17,width,height);else camera.setViewOffset(width,height,-width*.19,0,width,height);cameraDirector.setMobile(mobile);source.setSize(Math.max(1,Math.round(width*dpr)),Math.max(1,Math.round(height*dpr)));magnifier.resize(width,height,dpr);parcelOverlay.resize(width,height,dpr,mobile);post.resize(width,height,dpr);lighting.resizeQuality();camera.updateProjectionMatrix();}
 addEventListener('resize',resize,{passive:true});resize();

 const projectedParcel=new THREE.Vector3();
 function render(now){
  const elapsed=now*.001,dt=clamp((now-lastFrame)/1000,0,.08);lastFrame=now;if(quality.update(dt))resize();/* 改畫布尺寸會清空畫布，必須在繪製之前做，否則那一幀整片黑 */const rawProgress=scroll.update(dt),sceneProgress=reduced?[0,.96,2.5,3.5,4.2][Math.min(4,Math.floor(rawProgress))]:rawProgress,state=stateMachine.sample(sceneProgress);showChapter(rawProgress,scroll.pageProgress,mobile);
  // 最後一幕（#gust）：捲進這段空白時故事文字讓開、風吹過城市；系統那一段蓋上來時淡出
  let gustAmt=0;if(gustEl){const vh=innerHeight,gt=gustEl.getBoundingClientRect().top,ft=featuresEl?featuresEl.getBoundingClientRect().top:gt+gustEl.offsetHeight;gustAmt=reduced?0:(1-smooth(vh*.25,vh*.8,gt))*smooth(-vh*.1,vh*.55,ft);document.documentElement.classList.toggle('at-gust',gt<vh*.5);}
  cameraDirector.update(sceneProgress,state,dt,scroll.velocity,reduced);
  const documentPhase=smooth(1.86,2.23,sceneProgress),valuePhase=smooth(2.88,3.22,sceneProgress),returnPhase=smooth(3.83,4.16,sceneProgress),shrink=lerp(1,.2,documentPhase)*(1-returnPhase)+returnPhase,flatten=1-state.worldOpacity;
  city.root.scale.setScalar(shrink);city.root.position.set(18.5*(1-shrink),lerp(0,.1,documentPhase),2.5*(1-shrink));city.buildings.scale.y=lerp(1,.09,flatten);city.greenery.scale.y=lerp(1,.06,flatten);city.buildingDetails.scale.y=lerp(.72,1,state.buildingLOD);city.buildingDetails.position.y=lerp(-.3,0,state.buildingLOD);city.buildingDetails.visible=quality.level!=='LOW'||state.buildingLOD>.34;scene.updateMatrixWorld();
  const time=timeOfDay.update(sceneProgress),lightingState=lighting.update(elapsed,time,state,camera),{day,night}=lightingState;
  cadastral.update(state,smooth(.72,1.55,sceneProgress));
  // 橘色宗地框只屬於「地籍」這一章：進入地籍時淡入，捲到「紀錄」之前淡出。
  // 各場景狀態原本都把 parcelVisibility 設成 1，所以城市、紀錄、價值、夜景都看得到它。
  // 用 rawProgress 判斷章節：精簡動態模式下 sceneProgress 在第二章被夾成 .96，用它會把框整個藏掉。
  const parcelGate=smooth(.96,1.18,rawProgress)*(1-smooth(1.86,2.04,rawProgress));
  parcelOverlay.update({...state,parcelVisibility:state.parcelVisibility*parcelGate},elapsed);
  paper.root.visible=documentPhase>.002&&returnPhase<.999;paper.root.position.set(18.5,lerp(.7,8.5,documentPhase)-valuePhase*1.5,2.5);paper.root.rotation.x=lerp(-Math.PI/2,-.48,documentPhase)-valuePhase*.35;paper.root.rotation.z=-.035*documentPhase;paper.root.scale.setScalar(lerp(.7,.87,documentPhase)*(reduced?(1-returnPhase):1));if(!reduced)paper.disintegrate(returnPhase,elapsed);paper.draw(smooth(2.08,2.76,sceneProgress));
  const write=smooth(2.16,2.69,sceneProgress),hand=reduced?0:1,lift=smooth(.55,1,Math.sin(elapsed*2.3)),stroke=1-lift*.6;/* 筆在紙上時一直有細小的書寫動作：快的小筆畫、慢慢漂移，每隔一陣子提筆一下；捲動停下來也看得出在寫字 */paper.pencil.position.set(3+Math.sin(write*15)*2.8+hand*(stroke*(Math.sin(elapsed*13.7)*.16+Math.sin(elapsed*31.3)*.05)+Math.sin(elapsed*1.3)*.22),7-write*11+hand*(stroke*Math.sin(elapsed*18.9+.8)*.1+Math.sin(elapsed*.9+2)*.14),.5+hand*lift*.3);paper.pencil.rotation.z=-.6+Math.sin(write*20)*.025+hand*Math.sin(elapsed*9.1)*.035;paper.pencil.rotation.x=hand*Math.sin(elapsed*5.3+.4)*.04;appraiser.visible=valuePhase>.01&&returnPhase<.99;appraiser.scale.setScalar(1.35*valuePhase*(1-returnPhase));appraiser.userData.update?.(elapsed,appraiser.visible&&!reduced&&rawProgress>=2.96&&rawProgress<3.96);desk.visible=documentPhase>.4&&returnPhase<.8;desk.scale.setScalar(documentPhase*(1-returnPhase));
  wind.root.visible=documentPhase<.9||returnPhase>.1;wind.root.children.forEach(object=>{if(object.material?.transparent)object.material.opacity=Math.min(1,(object.geometry.type==='TubeGeometry'?.2:1)*(1-documentPhase+returnPhase)*state.worldOpacity*(1+gustAmt*2.5));});wind.update(elapsed,reduced);
  const animationTime=reduced?sceneProgress*.7:elapsed;city.animate(animationTime,night);crowd.update(animationTime,dt,camera,state,reduced);birds.update(animationTime,time,state,environment.windDirection,reduced);aircraft.update(animationTime,time,state,reduced);environment.update(animationTime,state,reduced);city.waterMaterial.uniforms.uSunX.value=.5+Math.sin(day*Math.PI*1.35-.5)*.3;
  // 河邊煙火，夜晚才放；水面的倒影顏色跟著當下那朵走。
  fireworks.update(dt,night,state.worldOpacity,smooth(3.9,4.1,rawProgress)>.5);   // 只在「連結」發射；天色一亮就全部熄掉
  const wu=city.waterMaterial.uniforms;
  wu.uFire.value.set(fireworks.glow.r,fireworks.glow.g,fireworks.glow.b);
  wu.uFireK.value=fireworks.glow.strength*.85;
  // 水面平面：x 為 -31±9.5 對應 uv.x、z 為 -44..44 對應 uv.y
  wu.uFireAt.value.set(THREE.MathUtils.clamp((fireworks.glow.x+31)/19+.5,-.2,1.2),THREE.MathUtils.clamp((fireworks.glow.z+44)/88,-.2,1.2));post.update(animationTime,state,night);

  const lensIn=smooth(1.02,1.28,sceneProgress),lensOut=smooth(1.8,2.08,sceneProgress),lensAmount=lensIn*(1-lensOut),lensVisible=lensAmount>.015&&!reduced;projectedParcel.set(targetParcel.x,.7,targetParcel.z);city.root.localToWorld(projectedParcel);projectedParcel.project(camera);const px=projectedParcel.x*width/2,py=projectedParcel.y*height/2;
  if(lensVisible){const radius=mobile?clamp(width*.24,75,107):clamp(width*.092,104,149),scale=radius/100,exitX=lensOut*width*.72,exitY=lensOut*height*.22;magnifier.root.scale.setScalar(scale*lensIn*(1-lensOut*.18));magnifier.root.rotation.z=lerp(-.18,.025,lensIn)+lensOut*.32;magnifier.root.position.set(px+exitX,py+exitY,0);magnifier.lensMat.uniforms.center.value.set(.5+(px+(lensOut>.35?exitX:0))/width,.5+(py+(lensOut>.35?exitY:0))/height);renderer.setRenderTarget(source);renderer.clear();renderer.render(scene,camera);renderer.setRenderTarget(null);}
  post.render(scene,camera);if(lensVisible){renderer.autoClear=false;renderer.clearDepth();renderer.render(magnifier.scene,magnifier.camera);renderer.autoClear=true;}if(gust)gust.update(dt,gustAmt);

  const tagOpacity=smooth(1.25,1.45,sceneProgress)*(1-smooth(1.78,2.02,sceneProgress));parcelTag.style.opacity=tagOpacity;parcelTag.style.left=`${clamp((projectedParcel.x*.5+.5)*width+(mobile?-85:70),width*(mobile?.08:.55),width-210)}px`;parcelTag.style.top=`${clamp((-projectedParcel.y*.5+.5)*height+(mobile?110:145),height*.4,height-155)}px`;parcelTag.style.right='auto';
  const timeLabel=day<.2?'清晨':day<.5?'日間':day<.76?'午後':day<.9?'黃昏':'夜晚';modelNote.textContent=`${timeLabel} · ${['河岸街廓','起風段 0128','土地資料紀錄','基地現勘','土地與生活'][active]}`;
  if(firstFrame){firstFrame=false;loader.classList.add('done');}
 }

 renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();paused=true;document.querySelector('#fallback').hidden=false;});renderer.domElement.addEventListener('webglcontextrestored',()=>{paused=false;lastFrame=performance.now();document.querySelector('#fallback').hidden=true;resize();});
 // 捲到系統功能、城市被完全蓋住時（features/main.js 標 city-covered）暫停渲染，把效能讓給那一段。
 document.addEventListener('visibilitychange',()=>{paused=document.hidden;lastFrame=performance.now();});function frame(now){requestAnimationFrame(frame);if(paused||document.documentElement.classList.contains('city-covered')){lastFrame=now;return;}render(now);}warmup().finally(()=>requestAnimationFrame(frame));
}catch(error){
 loader.classList.add('done');document.getElementById('gust')?.remove();document.getElementById('gust-canvas')?.remove();document.querySelector('#fallback').hidden=false;console.error('3D scene unavailable',error);const scroll=new ScrollController(sections,{reduced:()=>true});function fallbackFrame(){showChapter(scroll.target,scroll.pageProgress,innerWidth<=600);requestAnimationFrame(fallbackFrame);}requestAnimationFrame(fallbackFrame);
}

if(location.hash)requestAnimationFrame(()=>{const target=document.getElementById(location.hash.slice(1));if(target?.classList.contains('scene-section'))scrollToSection(target,true);});
