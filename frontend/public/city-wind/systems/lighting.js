import * as THREE from '../three.module.min.js';

const clamp=THREE.MathUtils.clamp,lerp=THREE.MathUtils.lerp;
const smooth=(a,b,v)=>{const t=clamp((v-a)/(b-a),0,1);return t*t*(3-2*t);};

function radialTexture(size=64){
 const data=new Uint8Array(size*size*4);for(let y=0;y<size;y++)for(let x=0;x<size;x++){const dx=(x/(size-1)-.5)*2,dy=(y/(size-1)-.5)*2,a=Math.max(0,1-Math.sqrt(dx*dx+dy*dy)),i=(y*size+x)*4;data[i]=255;data[i+1]=184;data[i+2]=103;data[i+3]=Math.round(a*a*255);}
 const texture=new THREE.DataTexture(data,size,size,THREE.RGBAFormat);texture.colorSpace=THREE.SRGBColorSpace;texture.needsUpdate=true;return texture;
}

export class TimeOfDaySystem{
 update(sceneProgress){
  const day=clamp(sceneProgress/4.18,0,1),night=smooth(.63,.98,day),sunHeight=Math.sin(clamp((day+.08)/.96,0,1)*Math.PI)*58-4;
  return {day,night,sunHeight,sunPosition:new THREE.Vector3(lerp(-56,104,day),sunHeight,-74+day*44),moonPosition:new THREE.Vector3(-64,6,-88),morning:smooth(0,.2,day)*(1-smooth(.34,.48,day)),sunset:smooth(.63,.8,day)*(1-smooth(.92,1,day))};
 }
}

export class StreetLightManager{
 constructor(scene,city,quality){
  this.scene=scene;this.city=city;this.quality=quality;this.positions=city.streetLamps||[];this.root=new THREE.Group();this.root.name='StreetLighting';scene.add(this.root);
  const footprintMat=new THREE.MeshBasicMaterial({map:radialTexture(),transparent:true,opacity:0,depthWrite:false,depthTest:true,blending:THREE.AdditiveBlending,toneMapped:false});
  this.footprints=new THREE.InstancedMesh(new THREE.PlaneGeometry(8,8),footprintMat,this.positions.length);const q=new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI/2,0,0)),m=new THREE.Matrix4(),s=new THREE.Vector3(1,.55,1);
  this.positions.forEach((p,i)=>{m.compose(new THREE.Vector3(p.x,.3,p.z),q,s);this.footprints.setMatrixAt(i,m);});this.footprints.instanceMatrix.needsUpdate=true;this.footprints.renderOrder=4;this.footprints.frustumCulled=false;city.root.add(this.footprints);
  this.spots=[];for(let i=0;i<8;i++){const light=new THREE.SpotLight(0xffb463,0,15,Math.PI*.31,.75,2);light.position.set(0,3.05,0);light.castShadow=i<4;light.shadow.mapSize.set(384,384);light.shadow.bias=-.001;light.shadow.normalBias=.08;const target=new THREE.Object3D();scene.add(light,target);light.target=target;this.spots.push({light,target,index:-1});}
  this.temp=new THREE.Vector3();this.lastSelection=-1;
 }
 update(camera,night,worldOpacity){
  const intensity=night*worldOpacity;this.footprints.material.opacity=intensity*.13;
  const ranked=this.positions.map((p,i)=>{this.temp.set(p.x,3,p.z);this.city.root.localToWorld(this.temp);return {i,d:this.temp.distanceToSquared(camera.position)};}).sort((a,b)=>a.d-b.d);
  const active=this.quality.settings.activeLights,shadowCount=this.quality.settings.shadowLights;
  for(let i=0;i<this.spots.length;i++){
   const slot=this.spots[i],entry=ranked[i];if(i>=active||!entry||intensity<.03){slot.light.intensity=0;slot.light.visible=false;continue;}
   const local=this.positions[entry.i];this.temp.set(local.x,local.y||2.58,local.z);this.city.root.localToWorld(this.temp);slot.light.position.copy(this.temp);this.temp.set(local.x,.2,local.z);this.city.root.localToWorld(this.temp);slot.target.position.copy(this.temp);slot.light.visible=true;slot.light.intensity=42*intensity;slot.light.castShadow=i<shadowCount;slot.index=entry.i;
  }
 }
 resizeQuality(){for(let i=0;i<this.spots.length;i++){this.spots[i].light.castShadow=i<this.quality.settings.shadowLights;this.spots[i].light.shadow.mapSize.set(this.quality.level==='HIGH'?512:256,this.quality.level==='HIGH'?512:256);}}
}

export class LightingSystem{
 constructor(scene,renderer,materials,city,quality){
  this.scene=scene;this.renderer=renderer;this.materials=materials;this.quality=quality;
  this.hemi=new THREE.HemisphereLight(0xd8e9e4,0x294846,2.5);scene.add(this.hemi);
  this.sunLight=new THREE.DirectionalLight(0xffead0,3.8);this.sunLight.castShadow=true;this.sunLight.shadow.mapSize.set(quality.settings.shadowMap,quality.settings.shadowMap);this.sunLight.shadow.camera.left=-82;this.sunLight.shadow.camera.right=82;this.sunLight.shadow.camera.top=80;this.sunLight.shadow.camera.bottom=-80;this.sunLight.shadow.camera.near=18;this.sunLight.shadow.camera.far=250;this.sunLight.shadow.bias=.00035;this.sunLight.shadow.normalBias=.13;this.sunLight.shadow.radius=quality.level==='HIGH'?2:1;scene.add(this.sunLight);
  this.moonLight=new THREE.DirectionalLight(0x91aee3,.1);this.moonLight.position.set(-64,52,-88);scene.add(this.moonLight);
  this.fill=new THREE.DirectionalLight(0x8cb8bd,1.8);this.fill.position.set(70,35,-40);scene.add(this.fill);
  this.sun=this.createSun(9,44,.58);this.moon=this.createMoon(9,46,.36);scene.add(this.sun,this.moon);
  const starGeo=new THREE.BufferGeometry(),starData=[];let seed=4821;for(let i=0;i<270;i++){seed=(seed*1664525+1013904223)>>>0;const a=seed/4294967296*Math.PI*2;seed=(seed*1664525+1013904223)>>>0;const r=170+seed/4294967296*90;seed=(seed*1664525+1013904223)>>>0;starData.push(Math.cos(a)*r,55+seed/4294967296*145,Math.sin(a)*r);}starGeo.setAttribute('position',new THREE.Float32BufferAttribute(starData,3));this.stars=new THREE.Points(starGeo,new THREE.PointsMaterial({color:0xcfe2e3,size:.7,transparent:true,opacity:0,depthWrite:false,fog:false}));scene.add(this.stars);
  materials.createEnvironment(renderer,scene);materials.setAnisotropy(Math.min(8,renderer.capabilities.getMaxAnisotropy()));this.streetLights=new StreetLightManager(scene,city,quality);
 }
 createCelestial(color,radius,glowSize,glowOpacity){
  const root=new THREE.Group(),core=new THREE.Mesh(new THREE.SphereGeometry(radius,24,16),new THREE.MeshBasicMaterial({color,fog:false,transparent:true}));root.add(core);
  const data=new Uint8Array(64*64*4);for(let y=0;y<64;y++)for(let x=0;x<64;x++){const d=Math.hypot(x-31.5,y-31.5)/31.5,a=Math.max(0,1-d),i=(y*64+x)*4;data[i]=255;data[i+1]=210;data[i+2]=155;data[i+3]=Math.round(a*a*glowOpacity*255);}const tex=new THREE.DataTexture(data,64,64,THREE.RGBAFormat);tex.colorSpace=THREE.SRGBColorSpace;tex.needsUpdate=true;const glow=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,depthWrite:false,fog:false,blending:THREE.AdditiveBlending}));glow.scale.set(glowSize,glowSize,1);root.add(glow);root.userData={core,glow};return root;
 }

 // 太陽：核心不做色調映射，亮度才能超過 1 讓光暈接得住；外加一層大而淡的外暈。
 // 顏色、亮度、光暈大小都依一天的進程在 update() 裡變化（清晨→正午→夕陽）。
 createSun(radius,glowSize,glowOpacity){
  const root=this.createCelestial(0xffd195,radius,glowSize,glowOpacity);
  root.userData.core.material.toneMapped=false;
  const halo=new THREE.Sprite(root.userData.glow.material.clone());
  halo.scale.set(glowSize*2.3,glowSize*2.3,1);root.add(halo);
  root.userData.halo=halo;root.userData.glowBase=glowSize;
  return root;
 }

 // 日月的圓盤改用「相機座標 + 畫面位置」擺放。用世界座標放在天上時，
 // 每一章的鏡頭都不同，很容易跑出畫面或被頁首擋住。
 // sx/sy 是畫面比例（0 左/上，1 右/下），並補償 camera.setViewOffset 的位移。
 placeDisc(obj,camera,sx,sy,distance){
  const f=this._f||(this._f=new THREE.Vector3()),r=this._r||(this._r=new THREE.Vector3()),u=this._u||(this._u=new THREE.Vector3());
  camera.getWorldDirection(f);
  r.crossVectors(f,camera.up).normalize();
  u.crossVectors(r,f).normalize();
  let ox=0,oy=0;const v=camera.view;
  if(v&&v.enabled){ox=v.offsetX/v.fullWidth;oy=v.offsetY/v.fullHeight;}
  const ndcX=2*(sx+ox)-1,ndcY=1-2*(sy+oy);
  const ty=Math.tan(THREE.MathUtils.degToRad(camera.fov*.5)),tx=ty*camera.aspect;
  obj.position.copy(camera.position)
     .addScaledVector(f,distance)
     .addScaledVector(r,ndcX*tx*distance)
     .addScaledVector(u,ndcY*ty*distance);
 }

 // 月亮：整張月面（月海、隕石坑、玉兔）畫在一張 Canvas 上，裁成圓形，貼在正對鏡頭的圓片。
 // 之前是一堆小圓片疊在球的前面、再複製鏡頭朝向去轉；月亮偏離畫面中心時，
 // 那些圓片因透視被往外擠，邊緣看起來像爆開。改成單張貼圖，內容一定在圓內。
 createMoon(radius,glowSize,glowOpacity){
  const root=new THREE.Group(),S=256,C=S/2,R=S/2-2;
  // 靜態層：月面底色（邊緣略暗）、月海、隕石坑，只畫一次
  const base=document.createElement('canvas');base.width=base.height=S;
  const b=base.getContext('2d');
  b.save();b.beginPath();b.arc(C,C,R,0,Math.PI*2);b.clip();
  const g=b.createRadialGradient(C-R*.25,C-R*.28,R*.08,C,C,R);
  g.addColorStop(0,'#f5f7fb');g.addColorStop(.72,'#dde2ee');g.addColorStop(1,'#c2c9da');
  b.fillStyle=g;b.fillRect(0,0,S,S);
  const blob=(x,y,r,a)=>{const gg=b.createRadialGradient(x,y,0,x,y,r);gg.addColorStop(0,'rgba(146,156,184,'+a+')');gg.addColorStop(1,'rgba(146,156,184,0)');b.fillStyle=gg;b.beginPath();b.arc(x,y,r,0,Math.PI*2);b.fill();};
  for(const [x,y,r,a] of [[.34,.32,.30,.40],[.64,.28,.21,.32],[.46,.68,.25,.34],[.72,.60,.17,.28],[.26,.60,.15,.26]])blob(x*S,y*S,r*S,a);
  let sd=4711;const rnd=()=>{sd=(sd*1664525+1013904223)>>>0;return sd/4294967296;};
  for(let i=0;i<22;i++){
   const a=rnd()*Math.PI*2,rr=Math.sqrt(rnd())*R*.8,x=C+Math.cos(a)*rr,y=C+Math.sin(a)*rr,cr=3+rnd()*8;
   b.fillStyle='rgba(160,170,196,.42)';b.beginPath();b.arc(x,y,cr,0,Math.PI*2);b.fill();
   b.fillStyle='rgba(238,241,249,.5)';b.beginPath();b.arc(x-cr*.28,y-cr*.28,cr*.52,0,Math.PI*2);b.fill();
  }
  b.restore();

  const cv=document.createElement('canvas');cv.width=cv.height=S;
  const ctx=cv.getContext('2d');
  const tex=new THREE.CanvasTexture(cv);tex.colorSpace=THREE.SRGBColorSpace;
  const faceMat=new THREE.MeshBasicMaterial({map:tex,transparent:true,fog:false,depthWrite:false,toneMapped:false});
  const face=new THREE.Mesh(new THREE.CircleGeometry(radius,64),faceMat);root.add(face);

  const data=new Uint8Array(64*64*4);
  for(let y=0;y<64;y++)for(let x=0;x<64;x++){const d=Math.hypot(x-31.5,y-31.5)/31.5,a=Math.max(0,1-d),i=(y*64+x)*4;data[i]=205;data[i+1]=220;data[i+2]=255;data[i+3]=Math.round(a*a*glowOpacity*255);}
  const gtex=new THREE.DataTexture(data,64,64,THREE.RGBAFormat);gtex.colorSpace=THREE.SRGBColorSpace;gtex.needsUpdate=true;
  const glow=new THREE.Sprite(new THREE.SpriteMaterial({map:gtex,transparent:true,depthWrite:false,fog:false,blending:THREE.AdditiveBlending}));
  glow.scale.set(glowSize,glowSize,1);root.add(glow);
  root.userData={core:face,glow,face,faceMat,ctx,base,tex,S,lastDraw:-1};
  this.drawMoonFace(root.userData,0);
  return root;
 }

 // 玉兔搗麻糬：用曲線畫的剪影（圓身體、長耳、尾巴），慢慢舉杵、快速落下、停一下；
 // 落下時身體前傾微壓扁、耳朵延遲甩動、濺起麻糬粉，偶爾眨眼。全部裁在月面圓內。
 drawMoonFace(ud,t){
  const {ctx,base,S}=ud,C=S/2;
  ctx.clearRect(0,0,S,S);ctx.drawImage(base,0,0);
  const T=1.15,p=(((t%T)+T)%T)/T;
  const easeOut=x=>1-(1-x)*(1-x),easeIn=x=>x*x;
  const lift=p<.58?easeOut(p/.58):p<.7?1-easeIn((p-.58)/.12):0;
  const hit=p>=.7&&p<.86?1-(p-.7)/.16:0;
  const L=lift*26;
  const ink='rgba(86,96,128,.88)',moon='rgba(242,245,251,.96)';
  const ell=(x,y,rx,ry,rot=0)=>{ctx.beginPath();ctx.ellipse(x,y,rx,ry,rot,0,Math.PI*2);ctx.fill();};
  ctx.save();
  ctx.beginPath();ctx.arc(C,C,C-2,0,Math.PI*2);ctx.clip();
  ctx.translate(C,124);ctx.scale(1.25,1.25);ctx.translate(-C,-124);
  ctx.fillStyle=ink;
  // 臼與麻糬
  ctx.beginPath();ctx.moveTo(150,150);ctx.lineTo(198,150);ctx.lineTo(190,182);ctx.quadraticCurveTo(174,191,158,182);ctx.closePath();ctx.fill();
  ell(174,150,26,6);
  ctx.fillStyle=moon;ell(174,147-hit*1.5,17,6+hit*1.8);ctx.fillStyle=ink;
  // 身體：舉杵時後仰，落下時前傾並微壓扁
  const lean=-.18+lift*.16,squash=1-hit*.07;
  const bx=100,by=172,cl=Math.cos(lean),sl=Math.sin(lean);
  ctx.save();ctx.translate(bx,by);ctx.rotate(lean);ctx.scale(1,squash);
  ell(0,-26,34,30);ell(-20,-6,22,16);ell(4,2,21,6);ell(-35,-30,8.5,8.5);
  ctx.save();ctx.translate(16,-58-hit*2);ctx.rotate(-lift*.08);
  ell(0,0,19,16,-.1);ell(15,4,8,7);
  const flop=Math.sin((p-.1)*Math.PI*2)*.14+hit*.2;
  ctx.save();ctx.translate(-6,-12);ctx.rotate(-.36+flop);ell(0,-20,6,21);ctx.restore();
  ctx.save();ctx.translate(5,-13);ctx.rotate(.05+flop*.8);ell(0,-19,6,19);ctx.restore();
  const blink=((t%3.7)<.12)?.15:1;
  ctx.fillStyle=moon;ell(6,-3,2.6,2.6*blink);ctx.fillStyle=ink;
  ctx.restore();
  ctx.restore();
  // 手臂：從肩膀直接連到杵的握點，永遠接得上
  const sx=bx+18*cl+36*sl,sy=by+18*sl-36*cl,gx=172,gy=104-L;
  ctx.strokeStyle=ink;ctx.lineCap='round';ctx.lineWidth=9;
  ctx.beginPath();ctx.moveTo(sx,sy);ctx.lineTo(gx,gy);ctx.stroke();
  ctx.lineWidth=7;ctx.beginPath();ctx.moveTo(sx-4,sy+6);ctx.lineTo(gx+3,gy+10);ctx.stroke();
  // 杵：以握點為軸，跟著手上下
  ctx.save();ctx.translate(174,104-L);ctx.rotate(.04-lift*.07);
  ctx.fillRect(-3,-20,6,46);
  ctx.beginPath();ctx.moveTo(-10,24);ctx.lineTo(10,24);ctx.lineTo(10,42);ctx.quadraticCurveTo(0,46,-10,42);ctx.closePath();ctx.fill();
  ctx.restore();
  // 打下去時濺起的麻糬粉
  if(hit>0){ctx.fillStyle='rgba(246,248,252,'+(hit*.85)+')';for(let i=0;i<5;i++){const a=-Math.PI/2+(i-2)*.5,r=6+(1-hit)*15;ell(174+Math.cos(a)*r*1.5,141+Math.sin(a)*r,2.3,2.3);}}
  ctx.restore();
  ud.tex.needsUpdate=true;
 }

 update(elapsed,time,state,camera){
  const {day,night,sunHeight,sunPosition,moonPosition}=time;
  // 日月交接：太陽完全落下之後月亮才開始淡入，中間留一小段空檔；往回捲時反過來。
  const sunFade=1-smooth(.78,.88,day),moonFade=smooth(.91,.98,day);
  this.sun.visible=sunFade>.003;this.moon.visible=moonFade>.003;
  // 太陽由晨到夕：清晨偏橘且柔、正午近白最亮、夕陽轉深橘且光暈最大。
  const toNoon=smooth(0,.3,day),toDusk=smooth(.5,.78,day);
  const mix3=(a,b,t)=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t];
  const rgb=mix3(mix3([1,.66,.44],[1,.95,.84],toNoon),[1,.5,.24],toDusk);
  const bright=lerp(lerp(.82,1.6,toNoon),1.25,toDusk);
  const su=this.sun.userData;
  su.core.material.color.setRGB(rgb[0]*bright,rgb[1]*bright,rgb[2]*bright);
  su.core.material.opacity=sunFade;
  // 光暈做很慢的呼吸（週期約 11 秒、幅度 3.5%），是「發光」不是閃爍
  const breathe=1+Math.sin(elapsed*.55)*.035;
  const gsz=su.glowBase*lerp(lerp(.8,1.25,toNoon),1.55,toDusk)*breathe;
  su.glow.scale.set(gsz,gsz,1);su.glow.material.color.setRGB(rgb[0],rgb[1],rgb[2]);
  su.glow.material.opacity=sunFade*lerp(lerp(.5,.92,toNoon),.85,toDusk);
  su.halo.scale.set(gsz*2.3,gsz*2.3,1);su.halo.material.color.setRGB(rgb[0],rgb[1]*.92,rgb[2]*.8);
  su.halo.material.opacity=sunFade*lerp(lerp(.12,.28,toNoon),.34,toDusk);
  const mu=this.moon.userData;
  mu.faceMat.opacity=moonFade;mu.glow.material.opacity=moonFade*.34;
  if(camera){
   // 太陽清晨在左上、正午升到最高、夕陽落回同一塊天空；月亮接著出現在那裡
   this.placeDisc(this.sun,camera,.40+Math.sin(day*Math.PI)*.10,.30-Math.sin(Math.min(1,day/.8)*Math.PI)*.15+smooth(.62,.86,day)*.06,300);
   this.placeDisc(this.moon,camera,.42,.25,260);
  }else{this.sun.position.copy(sunPosition);this.moon.position.copy(moonPosition);}
  if(this.moon.visible&&camera){
   // 正對「鏡頭所在的位置」，不是複製鏡頭朝向；偏離畫面中心時才不會變形外擠
   mu.face.lookAt(camera.position);
   if(elapsed-mu.lastDraw>1/30){mu.lastDraw=elapsed;this.drawMoonFace(mu,elapsed);}
  }
  this.sunLight.position.copy(sunPosition);this.sunLight.intensity=state.sunIntensity*lerp(3.4,.25,night)*(1+Math.sin(day*Math.PI)*.36);this.sunLight.color.set(day<.55?0xffe0b2:0xffa36a);
  this.moonLight.intensity=state.moonIntensity*1.85;this.moonLight.color.set(0xa9c2ef);this.fill.intensity=lerp(1.75,.42,night);this.fill.color.set(night>.45?0x668bb7:0x8cb8bd);this.hemi.intensity=lerp(2.55,.68,night);this.hemi.color.set(night>.45?0x6f8fc4:0xd8edf0);this.hemi.groundColor.set(night>.45?0x10192a:0x35524c);
  this.stars.material.opacity=smooth(.7,.97,day)*.82;
  const sky=new THREE.Color();if(day<.48)sky.lerpColors(new THREE.Color(0x3f5d60),new THREE.Color(0x75999f),day/.48);else if(day<.76)sky.lerpColors(new THREE.Color(0x75999f),new THREE.Color(0x594454),(day-.48)/.28);else sky.lerpColors(new THREE.Color(0x594454),new THREE.Color(0x071319),(day-.76)/.24);
  this.renderer.setClearColor(sky);this.scene.fog.color.copy(sky).multiplyScalar(.58);this.scene.fog.density=state.fogDensity;this.renderer.toneMappingExposure=state.exposure;this.scene.environmentIntensity=lerp(.72,.34,night);this.materials.update(elapsed,night);this.streetLights.update(camera,night,state.worldOpacity);
  return {day,night,sky};
 }
 resizeQuality(){this.sunLight.shadow.mapSize.set(this.quality.settings.shadowMap,this.quality.settings.shadowMap);this.streetLights.resizeQuality();}
}
