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
  this.sun=this.createCelestial(0xffd195,9,44,.58);this.moon=this.createMoon(9,46,.36);scene.add(this.sun,this.moon);
  const starGeo=new THREE.BufferGeometry(),starData=[];let seed=4821;for(let i=0;i<270;i++){seed=(seed*1664525+1013904223)>>>0;const a=seed/4294967296*Math.PI*2;seed=(seed*1664525+1013904223)>>>0;const r=170+seed/4294967296*90;seed=(seed*1664525+1013904223)>>>0;starData.push(Math.cos(a)*r,55+seed/4294967296*145,Math.sin(a)*r);}starGeo.setAttribute('position',new THREE.Float32BufferAttribute(starData,3));this.stars=new THREE.Points(starGeo,new THREE.PointsMaterial({color:0xcfe2e3,size:.7,transparent:true,opacity:0,depthWrite:false,fog:false}));scene.add(this.stars);
  materials.createEnvironment(renderer,scene);materials.setAnisotropy(Math.min(8,renderer.capabilities.getMaxAnisotropy()));this.streetLights=new StreetLightManager(scene,city,quality);
 }
 createCelestial(color,radius,glowSize,glowOpacity){
  const root=new THREE.Group(),core=new THREE.Mesh(new THREE.SphereGeometry(radius,24,16),new THREE.MeshBasicMaterial({color,fog:false,transparent:true}));root.add(core);
  const data=new Uint8Array(64*64*4);for(let y=0;y<64;y++)for(let x=0;x<64;x++){const d=Math.hypot(x-31.5,y-31.5)/31.5,a=Math.max(0,1-d),i=(y*64+x)*4;data[i]=255;data[i+1]=210;data[i+2]=155;data[i+3]=Math.round(a*a*glowOpacity*255);}const tex=new THREE.DataTexture(data,64,64,THREE.RGBAFormat);tex.colorSpace=THREE.SRGBColorSpace;tex.needsUpdate=true;const glow=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,depthWrite:false,fog:false,blending:THREE.AdditiveBlending}));glow.scale.set(glowSize,glowSize,1);root.add(glow);root.userData={core,glow};return root;
 }

 // 月亮：表面有月海與隕石坑，正面站一隻搗藥的兔子（中秋彩蛋）。
 // 兔子與坑都掛在一個朝向鏡頭的群組上，不管相機怎麼動都看得到正面。

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

 createMoon(radius,glowSize,glowOpacity){
  const root=new THREE.Group();
  const body=new THREE.Mesh(new THREE.SphereGeometry(radius,32,24),new THREE.MeshBasicMaterial({color:0xdfe4f0,fog:false,transparent:true}));
  root.add(body);

  const face=new THREE.Group();root.add(face);
  const sea=new THREE.MeshBasicMaterial({color:0xaab3c8,fog:false,transparent:true,opacity:.55,depthWrite:false});
  const crater=new THREE.MeshBasicMaterial({color:0xb9c1d4,fog:false,transparent:true,opacity:.45,depthWrite:false});
  let sd=4711;const rnd=()=>{sd=(sd*1664525+1013904223)>>>0;return sd/4294967296;};
  // 月海：幾塊大的深色區
  for(const [ax,ay,ar] of [[-.34,.28,.40],[.22,.36,.30],[-.10,-.30,.34],[.40,-.14,.22]]){
   const d=new THREE.Mesh(new THREE.CircleGeometry(radius*ar,20),sea);
   d.position.set(ax*radius,ay*radius,radius*.97);face.add(d);
  }
  // 隕石坑：散佈的小圓
  for(let i=0;i<16;i++){
   const a=rnd()*Math.PI*2,r=Math.sqrt(rnd())*.82;
   const d=new THREE.Mesh(new THREE.CircleGeometry(radius*(.035+rnd()*.07),12),crater);
   d.position.set(Math.cos(a)*r*radius,Math.sin(a)*r*radius,radius*.98);face.add(d);
  }

  // 搗藥的兔子（剪影）
  const ink=new THREE.MeshBasicMaterial({color:0x5d6782,fog:false,transparent:true,opacity:.72,depthWrite:false});
  const bunny=new THREE.Group();bunny.position.set(radius*.02,-radius*.42*.7,radius*.99);face.add(bunny);
  const u=radius*.42;
  const part=(w,h,x,y,rot=0)=>{const m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),ink);m.position.set(x,y,0);m.rotation.z=rot;bunny.add(m);return m;};
  part(u*1.15,u*1.5,0,0);                      // 身體
  part(u*.8,u*.8,u*.12,u*1.15);                // 頭
  part(u*.26,u*1.0,-u*.08,u*1.85,.16);         // 耳
  part(u*.26,u*1.0,u*.3,u*1.9,-.12);           // 耳
  const arm=part(u*.24,u*1.0,u*.55,u*1.0,-.5); // 手臂（連著杵）
  const pestle=new THREE.Group();pestle.position.set(u*.62,u*1.15,0);bunny.add(pestle);
  const stick=new THREE.Mesh(new THREE.PlaneGeometry(u*.16,u*1.5),ink);stick.position.set(0,-u*.55,0);pestle.add(stick);
  const headP=new THREE.Mesh(new THREE.PlaneGeometry(u*.42,u*.34),ink);headP.position.set(0,-u*1.25,0);pestle.add(headP);
  part(u*1.0,u*.5,u*.72,-u*.75);               // 臼

  const data=new Uint8Array(64*64*4);
  for(let y=0;y<64;y++)for(let x=0;x<64;x++){const d=Math.hypot(x-31.5,y-31.5)/31.5,a=Math.max(0,1-d),i=(y*64+x)*4;data[i]=205;data[i+1]=220;data[i+2]=255;data[i+3]=Math.round(a*a*glowOpacity*255);}
  const tex=new THREE.DataTexture(data,64,64,THREE.RGBAFormat);tex.colorSpace=THREE.SRGBColorSpace;tex.needsUpdate=true;
  const glow=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,depthWrite:false,fog:false,blending:THREE.AdditiveBlending}));
  glow.scale.set(glowSize,glowSize,1);root.add(glow);
  root.userData={core:body,glow,face,pestle,arm,bunny};
  return root;
 }

 update(elapsed,time,state,camera){
  const {day,night,sunHeight,sunPosition,moonPosition}=time;
  this.sun.visible=sunHeight>-6&&night<.96;this.moon.visible=night>.08;
  this.sun.userData.core.material.opacity=1-smooth(.55,.94,night);
  if(camera){
   // 太陽沿畫面左上往右上走（仍隨 day 移動），月亮固定在左上的空區
   this.placeDisc(this.sun,camera,.40+day*.30,.28-Math.sin(day*Math.PI)*.14,300);
   this.placeDisc(this.moon,camera,.42,.25,260);
  }else{this.sun.position.copy(sunPosition);this.moon.position.copy(moonPosition);}
  if(this.moon.userData.face&&camera){
   // 月面永遠朝向鏡頭，兔子才不會轉到背面去
   this.moon.userData.face.quaternion.copy(camera.quaternion);
   const swing=Math.sin(elapsed*3.2);
   this.moon.userData.pestle.rotation.z=-.35+Math.max(0,swing)*.95;   // 舉起再落下
   this.moon.userData.arm.rotation.z=-.5+Math.max(0,swing)*.5;
  }
  this.sunLight.position.copy(sunPosition);this.sunLight.intensity=state.sunIntensity*lerp(3.4,.25,night)*(1+Math.sin(day*Math.PI)*.36);this.sunLight.color.set(day<.55?0xffe0b2:0xffa36a);
  this.moonLight.intensity=state.moonIntensity*1.85;this.moonLight.color.set(0xa9c2ef);this.fill.intensity=lerp(1.75,.42,night);this.fill.color.set(night>.45?0x668bb7:0x8cb8bd);this.hemi.intensity=lerp(2.55,.68,night);this.hemi.color.set(night>.45?0x6f8fc4:0xd8edf0);this.hemi.groundColor.set(night>.45?0x10192a:0x35524c);
  this.stars.material.opacity=smooth(.7,.97,day)*.82;this.sun.userData.glow.material.opacity=(1-night)*(.58+Math.abs(day-.5)*.26);this.moon.userData.glow.material.opacity=night*.32;
  const sky=new THREE.Color();if(day<.48)sky.lerpColors(new THREE.Color(0x3f5d60),new THREE.Color(0x75999f),day/.48);else if(day<.76)sky.lerpColors(new THREE.Color(0x75999f),new THREE.Color(0x594454),(day-.48)/.28);else sky.lerpColors(new THREE.Color(0x594454),new THREE.Color(0x071319),(day-.76)/.24);
  this.renderer.setClearColor(sky);this.scene.fog.color.copy(sky).multiplyScalar(.58);this.scene.fog.density=state.fogDensity;this.renderer.toneMappingExposure=state.exposure;this.scene.environmentIntensity=lerp(.72,.34,night);this.materials.update(elapsed,night);this.streetLights.update(camera,night,state.worldOpacity);
  return {day,night,sky};
 }
 resizeQuality(){this.sunLight.shadow.mapSize.set(this.quality.settings.shadowMap,this.quality.settings.shadowMap);this.streetLights.resizeQuality();}
}
