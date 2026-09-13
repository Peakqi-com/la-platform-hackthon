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
const motion=document.querySelector('#motion'),loader=document.querySelector('#loading'),counter=document.querySelector('#counter'),progressBar=document.querySelector('#progress');
const parcelTag=document.querySelector('#parcel-tag'),valuation=document.querySelector('#valuation'),modelNote=document.querySelector('#model-note');
const media=matchMedia('(prefers-reduced-motion: reduce)');let reduced=media.matches,manualMotion=false,active=-1;

function showChapter(value,pageProgress,mobile){
 const index=Math.min(4,Math.floor(value+.04));if(index!==active){active=index;chapters.forEach((chapter,i)=>{chapter.classList.toggle('active',i===index);chapter.setAttribute('aria-hidden',i===index?'false':'true');chapter.inert=i!==index;});links.forEach((link,i)=>{link.classList.toggle('active',i===index);if(i===index)link.setAttribute('aria-current','step');else link.removeAttribute('aria-current');});counter.textContent=`0${index+1} — 05`;document.documentElement.classList.toggle('at-ending',index===4);}
 const local=value-index,fadeIn=index===0||reduced?1:smooth(-.02,.18,local),fadeOut=index===4||reduced?1:1-smooth(.8,.96,local),alpha=fadeIn*fadeOut,shift=reduced?0:(1-fadeIn)*15-(1-fadeOut)*12;
 chapters.forEach((chapter,i)=>{chapter.style.opacity=i===index?alpha:0;});chapters[index].style.transform=mobile?`translateY(${shift}px)`:`translateY(calc(-46% + ${shift}px))`;progressBar.style.width=`${pageProgress*100}%`;
 const val=smooth(3.05,3.24,value)*(1-smooth(3.76,3.96,value));valuation.style.opacity=val;valuation.style.visibility=val>.01?'visible':'hidden';valuation.style.setProperty('--reveal',smooth(3.18,3.65,value));
}

motion.setAttribute('aria-pressed',String(reduced));motion.textContent=reduced?'恢復動態':'精簡動態';
function applyMotion(value){reduced=value;motion.setAttribute('aria-pressed',String(value));motion.textContent=value?'恢復動態':'精簡動態';document.documentElement.style.scrollBehavior=value?'auto':'smooth';}
motion.addEventListener('click',()=>{manualMotion=true;applyMotion(!reduced);});media.addEventListener('change',event=>{if(!manualMotion)applyMotion(event.matches);});
// 點導覽或任何錨點時，不要停在區段頂端：那裡 fadeIn 只有 3%，文字幾乎看不見，會被誤會成卡住。
// 落在區段 34% 處，fadeIn（.18 到 1）與 fadeOut（.8 才開始）都在完全不透明的區間。
const CHAPTER_ANCHOR=.34;
function scrollToSection(section,instant){scrollTo({top:section.offsetTop+section.offsetHeight*CHAPTER_ANCHOR,behavior:(instant||reduced)?'instant':'smooth'});}
for(const anchor of document.querySelectorAll('a[href^="#"]'))anchor.addEventListener('click',event=>{const section=document.getElementById(anchor.getAttribute('href').slice(1));if(section){event.preventDefault();scrollToSection(section);history.replaceState(null,'',anchor.getAttribute('href'));}});

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
 // 第一次捲一遍會卡、第二遍才順，是因為 three.js 第一次畫到某個「光源數量＋物件」組合時
 // 才編譯對應的著色器並快取：
 //  1) 路燈白天隱藏、入夜才亮，光源數量一變，全場有光照的材質都要重編，這是最大的一次停頓；
 //  2) 文件、估價師、碎片、月亮、煙火、地籍圖層、放大鏡開場都是隱藏的，第一次出現才編譯；
 //  3) compile 只編譯著色器，貼圖要另外 initTexture 才會先上傳。
 // 白天與夜晚兩種路燈組態各編譯一次；compileAsync 平行編譯，不卡主執行緒（載入動畫照跑）。
 async function warmup(){
  const saved=[],magSaved=[];
  scene.traverse(o=>saved.push([o,o.visible]));magnifier.scene.traverse(o=>magSaved.push([o,o.visible]));
  scene.traverse(o=>{if(!o.isLight)o.visible=true;});magnifier.scene.traverse(o=>{o.visible=true;});
  const spots=lighting.streetLights.spots,qs=quality.settings;
  // 夜晚的路燈組態要與 StreetLightManager.update 完全一致（數量與投影數），快取鍵才會相同
  const setSpots=on=>spots.forEach((sl,i)=>{sl.light.visible=on&&i<qs.activeLights;sl.light.castShadow=i<qs.shadowLights;});
  const compile=(sc,cam)=>renderer.compileAsync?renderer.compileAsync(sc,cam):Promise.resolve(renderer.compile(sc,cam));
  try{
   const jobs=[];
   setSpots(true);jobs.push(compile(scene,camera));    // compileAsync 在呼叫當下就列舉材質，所以可以接著切組態
   setSpots(false);jobs.push(compile(scene,camera));
   jobs.push(compile(magnifier.scene,magnifier.camera));
   if(renderer.initTexture){
    const seen=new Set();
    const up=v=>{if(v&&v.isTexture&&!v.isRenderTargetTexture&&!seen.has(v)){seen.add(v);try{renderer.initTexture(v);}catch(e){}}};
    const grab=o=>{const ms=o.material?(Array.isArray(o.material)?o.material:[o.material]):[];for(const m of ms){for(const k in m)up(m[k]);if(m.uniforms)for(const u of Object.values(m.uniforms))up(u&&u.value);}};
    scene.traverse(grab);magnifier.scene.traverse(grab);
   }
   // 最多等 10 秒，少數驅動不回報完成時也不會卡死在載入畫面
   await Promise.race([Promise.all(jobs),new Promise(r=>setTimeout(r,10000))]);
  }catch(e){console.warn('warmup skipped',e);}
  for(const [o,v] of saved)o.visible=v;for(const [o,v] of magSaved)o.visible=v;
 }
 const lighting=new LightingSystem(scene,renderer,materials,city,quality),crowd=new CrowdSystem(city,materials,quality),birds=new BirdSystem(scene,quality),aircraft=new AircraftSystem(scene,materials),environment=new EnvironmentSystem(scene,city,materials),post=new PostProcessingSystem(renderer,quality);
 const source=new THREE.WebGLRenderTarget(1,1,{depthBuffer:true});source.texture.colorSpace=THREE.SRGBColorSpace;const magnifier=buildMagnifier(source.texture);magnifier.lensMat.fragmentShader=magnifier.lensMat.fragmentShader.replace('gl_FragColor=vec4(c,1.);','gl_FragColor=vec4(c,1.);\n#include <colorspace_fragment>\n');

 let width=innerWidth,height=innerHeight,mobile=width<=600,dpr=quality.pixelRatio,paused=false,lastFrame=performance.now(),firstFrame=true;
 function resize(){width=innerWidth;height=innerHeight;mobile=width<=600;scroll.measure();quality.applyRenderer(renderer);dpr=quality.pixelRatio;renderer.setSize(width,height,false);camera.aspect=width/height;camera.clearViewOffset();if(mobile)camera.setViewOffset(width,height,0,-height*.17,width,height);else camera.setViewOffset(width,height,-width*.19,0,width,height);cameraDirector.setMobile(mobile);source.setSize(Math.max(1,Math.round(width*dpr)),Math.max(1,Math.round(height*dpr)));magnifier.resize(width,height,dpr);parcelOverlay.resize(width,height,dpr,mobile);post.resize(width,height,dpr);lighting.resizeQuality();camera.updateProjectionMatrix();}
 addEventListener('resize',resize,{passive:true});resize();

 const projectedParcel=new THREE.Vector3();
 function render(now){
  const elapsed=now*.001,dt=clamp((now-lastFrame)/1000,0,.08);lastFrame=now;if(quality.update(dt))resize();/* 改畫布尺寸會清空畫布，必須在繪製之前做，否則那一幀整片黑 */const rawProgress=scroll.update(dt),sceneProgress=reduced?[0,.96,2.5,3.5,4.2][Math.min(4,Math.floor(rawProgress))]:rawProgress,state=stateMachine.sample(sceneProgress);showChapter(rawProgress,scroll.pageProgress,mobile);
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
  const write=smooth(2.16,2.69,sceneProgress);paper.pencil.position.set(3+Math.sin(write*15)*2.8,7-write*11,.5);paper.pencil.rotation.z=-.6+Math.sin(write*20)*.025;appraiser.visible=valuePhase>.01&&returnPhase<.99;appraiser.scale.setScalar(1.35*valuePhase*(1-returnPhase));appraiser.userData.update?.(elapsed,appraiser.visible&&!reduced&&rawProgress>=2.96&&rawProgress<3.96);desk.visible=documentPhase>.4&&returnPhase<.8;desk.scale.setScalar(documentPhase*(1-returnPhase));
  wind.root.visible=documentPhase<.9||returnPhase>.1;wind.root.children.forEach(object=>{if(object.material?.transparent)object.material.opacity=(object.geometry.type==='TubeGeometry'?.2:1)*(1-documentPhase+returnPhase)*state.worldOpacity;});wind.update(elapsed,reduced);
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
  post.render(scene,camera);if(lensVisible){renderer.autoClear=false;renderer.clearDepth();renderer.render(magnifier.scene,magnifier.camera);renderer.autoClear=true;}

  const tagOpacity=smooth(1.25,1.45,sceneProgress)*(1-smooth(1.78,2.02,sceneProgress));parcelTag.style.opacity=tagOpacity;parcelTag.style.left=`${clamp((projectedParcel.x*.5+.5)*width+(mobile?-85:70),width*(mobile?.08:.55),width-210)}px`;parcelTag.style.top=`${clamp((-projectedParcel.y*.5+.5)*height+(mobile?110:145),height*.4,height-155)}px`;parcelTag.style.right='auto';
  const timeLabel=day<.2?'清晨':day<.5?'日間':day<.76?'午後':day<.9?'黃昏':'夜晚';modelNote.textContent=`${timeLabel} · ${['河岸街廓','起風段 0128','土地資料紀錄','基地現勘','土地與生活'][active]}`;
  if(firstFrame){firstFrame=false;loader.classList.add('done');}
 }

 renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();paused=true;document.querySelector('#fallback').hidden=false;});renderer.domElement.addEventListener('webglcontextrestored',()=>{paused=false;lastFrame=performance.now();document.querySelector('#fallback').hidden=true;resize();});
 document.addEventListener('visibilitychange',()=>{paused=document.hidden;lastFrame=performance.now();});function frame(now){requestAnimationFrame(frame);if(paused)return;render(now);}warmup().finally(()=>requestAnimationFrame(frame));
}catch(error){
 loader.classList.add('done');document.querySelector('#fallback').hidden=false;console.error('3D scene unavailable',error);const scroll=new ScrollController(sections,{reduced:()=>true});function fallbackFrame(){showChapter(scroll.target,scroll.pageProgress,innerWidth<=600);requestAnimationFrame(fallbackFrame);}requestAnimationFrame(fallbackFrame);
}

if(location.hash)requestAnimationFrame(()=>{const target=document.getElementById(location.hash.slice(1));if(target)scrollToSection(target,true);});
