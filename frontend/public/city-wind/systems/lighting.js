import * as THREE from '../three.module.min.js';

const clamp=THREE.MathUtils.clamp,lerp=THREE.MathUtils.lerp;
const smooth=(a,b,v)=>{const t=clamp((v-a)/(b-a),0,1);return t*t*(3-2*t);};

function radialTexture(size=64){
 const data=new Uint8Array(size*size*4);for(let y=0;y<size;y++)for(let x=0;x<size;x++){const dx=(x/(size-1)-.5)*2,dy=(y/(size-1)-.5)*2,a=Math.max(0,1-Math.sqrt(dx*dx+dy*dy)),i=(y*size+x)*4;data[i]=255;data[i+1]=184;data[i+2]=103;data[i+3]=Math.round(a*a*255);}
 const texture=new THREE.DataTexture(data,size,size,THREE.RGBAFormat);texture.colorSpace=THREE.SRGBColorSpace;texture.needsUpdate=true;return texture;
}

export class TimeOfDaySystem{
 update(sceneProgress){
  const day=clamp(sceneProgress/4.18,0,1),night=smooth(.63,.98,day),sunHeight=Math.sin(clamp((day+.08)/.96,0,1)*Math.PI)*106-8;
  return {day,night,sunHeight,sunPosition:new THREE.Vector3(lerp(-102,116,day),sunHeight,-92+day*48),moonPosition:new THREE.Vector3(86,74,-104),morning:smooth(0,.2,day)*(1-smooth(.34,.48,day)),sunset:smooth(.63,.8,day)*(1-smooth(.92,1,day))};
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
  this.moonLight=new THREE.DirectionalLight(0x91aee3,.1);this.moonLight.position.set(86,74,-104);scene.add(this.moonLight);
  this.fill=new THREE.DirectionalLight(0x8cb8bd,1.8);this.fill.position.set(70,35,-40);scene.add(this.fill);
  this.sun=this.createCelestial(0xffd195,4.6,28,.72);this.moon=this.createCelestial(0xb8c9ea,3.2,14,.28);scene.add(this.sun,this.moon);
  const starGeo=new THREE.BufferGeometry(),starData=[];let seed=4821;for(let i=0;i<270;i++){seed=(seed*1664525+1013904223)>>>0;const a=seed/4294967296*Math.PI*2;seed=(seed*1664525+1013904223)>>>0;const r=170+seed/4294967296*90;seed=(seed*1664525+1013904223)>>>0;starData.push(Math.cos(a)*r,55+seed/4294967296*145,Math.sin(a)*r);}starGeo.setAttribute('position',new THREE.Float32BufferAttribute(starData,3));this.stars=new THREE.Points(starGeo,new THREE.PointsMaterial({color:0xcfe2e3,size:.7,transparent:true,opacity:0,depthWrite:false,fog:false}));scene.add(this.stars);
  materials.createEnvironment(renderer,scene);materials.setAnisotropy(Math.min(8,renderer.capabilities.getMaxAnisotropy()));this.streetLights=new StreetLightManager(scene,city,quality);
 }
 createCelestial(color,radius,glowSize,glowOpacity){
  const root=new THREE.Group(),core=new THREE.Mesh(new THREE.SphereGeometry(radius,24,16),new THREE.MeshBasicMaterial({color,fog:false,transparent:true}));root.add(core);
  const data=new Uint8Array(64*64*4);for(let y=0;y<64;y++)for(let x=0;x<64;x++){const d=Math.hypot(x-31.5,y-31.5)/31.5,a=Math.max(0,1-d),i=(y*64+x)*4;data[i]=255;data[i+1]=210;data[i+2]=155;data[i+3]=Math.round(a*a*glowOpacity*255);}const tex=new THREE.DataTexture(data,64,64,THREE.RGBAFormat);tex.colorSpace=THREE.SRGBColorSpace;tex.needsUpdate=true;const glow=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,depthWrite:false,fog:false,blending:THREE.AdditiveBlending}));glow.scale.set(glowSize,glowSize,1);root.add(glow);root.userData={core,glow};return root;
 }
 update(elapsed,time,state,camera){
  const {day,night,sunHeight,sunPosition,moonPosition}=time;this.sun.position.copy(sunPosition);this.sun.visible=sunHeight>-6;this.moon.position.copy(moonPosition);this.moon.visible=night>.08;
  this.sunLight.position.copy(sunPosition);this.sunLight.intensity=state.sunIntensity*lerp(3.4,.25,night)*(1+Math.sin(day*Math.PI)*.36);this.sunLight.color.set(day<.55?0xffe0b2:0xffa36a);
  this.moonLight.intensity=state.moonIntensity*1.05;this.fill.intensity=lerp(1.75,.42,night);this.fill.color.set(night>.45?0x668bb7:0x8cb8bd);this.hemi.intensity=lerp(2.55,.68,night);this.hemi.color.set(night>.45?0x6f8fc4:0xd8edf0);this.hemi.groundColor.set(night>.45?0x10192a:0x35524c);
  this.stars.material.opacity=smooth(.7,.97,day)*.82;this.sun.userData.glow.material.opacity=(1-night)*(.58+Math.abs(day-.5)*.26);this.moon.userData.glow.material.opacity=night*.32;
  const sky=new THREE.Color();if(day<.48)sky.lerpColors(new THREE.Color(0x3f5d60),new THREE.Color(0x75999f),day/.48);else if(day<.76)sky.lerpColors(new THREE.Color(0x75999f),new THREE.Color(0x594454),(day-.48)/.28);else sky.lerpColors(new THREE.Color(0x594454),new THREE.Color(0x071319),(day-.76)/.24);
  this.renderer.setClearColor(sky);this.scene.fog.color.copy(sky).multiplyScalar(.58);this.scene.fog.density=state.fogDensity;this.renderer.toneMappingExposure=state.exposure;this.scene.environmentIntensity=lerp(.72,.34,night);this.materials.update(elapsed,night);this.streetLights.update(camera,night,state.worldOpacity);
  return {day,night,sky};
 }
 resizeQuality(){this.sunLight.shadow.mapSize.set(this.quality.settings.shadowMap,this.quality.settings.shadowMap);this.streetLights.resizeQuality();}
}
