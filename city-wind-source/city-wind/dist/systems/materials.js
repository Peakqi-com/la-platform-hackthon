import * as THREE from '../three.module.min.js';

const PALETTE={
 ivory:0xd8d1be,light:0xf2ead8,concrete:0xa7aea7,roof:0x536d67,glass:0x4c8791,
 darkGlass:0x1f4b55,trim:0x82988e,road:0x313837,stone:0x71877f,curb:0xb8b49e,
 gold:0xd19a58,black:0x172b2d,white:0xe9e3d2,leaf:0x547a62,leaf2:0x8fa477,
 trunk:0x71604e,river:0x245963,brick:0xa75f4c,terracotta:0xc77b57,mustard:0xc6a251,
 blue:0x527b99,teal:0x3f8279,plum:0x76586e,sand:0xc7ae83,slate:0x58687c,
 red:0xb8463c,carBlue:0x3d6783,carGreen:0x4d785e
};

function seededNoise(size,kind='color',seed=8128){
 const data=new Uint8Array(size*size*4);let s=seed>>>0;
 const random=()=>{s=(s*1664525+1013904223)>>>0;return s/4294967296;};
 for(let y=0;y<size;y++)for(let x=0;x<size;x++){
  const i=(y*size+x)*4,n=random(),macro=.5+.5*Math.sin(x*.19+Math.sin(y*.11)*2.1);
  if(kind==='normal'){
   const nx=128+(random()-.5)*22,ny=128+(random()-.5)*22;
   data[i]=nx;data[i+1]=ny;data[i+2]=248;data[i+3]=255;
  }else if(kind==='roughness'){
   const v=Math.round(178+n*58+macro*14);data[i]=data[i+1]=data[i+2]=v;data[i+3]=255;
  }else{
   const aggregate=n>.975?-18:n<.035?14:0,v=Math.round(116+(n-.5)*18+(macro-.5)*8+aggregate);
   data[i]=v;data[i+1]=v+2;data[i+2]=v;data[i+3]=255;
  }
 }
 const texture=new THREE.DataTexture(data,size,size,THREE.RGBAFormat);texture.wrapS=texture.wrapT=THREE.RepeatWrapping;texture.repeat.set(5,5);texture.colorSpace=kind==='color'?THREE.SRGBColorSpace:THREE.NoColorSpace;
 // DataTexture defaults are too sharp for shallow aerial angles. Trilinear mipmaps
 // remove the moving moire bands while anisotropy preserves nearby road detail.
 texture.generateMipmaps=true;texture.minFilter=THREE.LinearMipmapLinearFilter;texture.magFilter=THREE.LinearFilter;texture.needsUpdate=true;return texture;
}

function pbr(color,roughness=.72,metalness=.03,extra={}){
 return new THREE.MeshPhysicalMaterial({color,roughness,metalness,envMapIntensity:.72,...extra});
}

export class MaterialLibrary{
 constructor(){
  this.wind={time:{value:0},strength:{value:.055},direction:{value:new THREE.Vector2(.82,.34)}};
  this.asphaltColor=seededNoise(256,'color',9182);this.asphaltRoughness=seededNoise(256,'roughness',4128);this.asphaltNormal=seededNoise(128,'normal',1298);
  this.materials={
   ivory:pbr(PALETTE.ivory,.78,.02),light:pbr(PALETTE.light,.82,.01),
   concrete:pbr(PALETTE.concrete,.78,.01,{normalMap:this.asphaltNormal,normalScale:new THREE.Vector2(.07,.07)}),
   roof:pbr(PALETTE.roof,.58,.34),glass:pbr(PALETTE.glass,.2,.08,{clearcoat:.32,clearcoatRoughness:.18,envMapIntensity:1.25}),
   darkGlass:pbr(PALETTE.darkGlass,.16,.1,{clearcoat:.45,clearcoatRoughness:.16,envMapIntensity:1.4}),
   trim:pbr(PALETTE.trim,.39,.84),road:pbr(PALETTE.road,.84,0,{map:this.asphaltColor,roughnessMap:this.asphaltRoughness,normalMap:this.asphaltNormal,normalScale:new THREE.Vector2(.28,.28),envMapIntensity:.16}),
   stone:pbr(PALETTE.stone,.88,.01),curb:pbr(PALETTE.curb,.82,.01),gold:pbr(PALETTE.gold,.3,.88),
   black:pbr(PALETTE.black,.68,.08),white:pbr(PALETTE.white,.72,.01),roadMark:pbr(PALETTE.white,.38,.02,{emissive:0xffffff,emissiveIntensity:0}),
   leaf:pbr(PALETTE.leaf,.88,.01),leaf2:pbr(PALETTE.leaf2,.9,.01),trunk:pbr(PALETTE.trunk,.92,.01),
   river:pbr(PALETTE.river,.3,.02),brick:pbr(PALETTE.brick,.84,.01,{normalMap:this.asphaltNormal,normalScale:new THREE.Vector2(.05,.05)}),
   terracotta:pbr(PALETTE.terracotta,.76,.01),mustard:pbr(PALETTE.mustard,.7,.02),blue:pbr(PALETTE.blue,.56,.08),
   teal:pbr(PALETTE.teal,.58,.06),plum:pbr(PALETTE.plum,.64,.04),sand:pbr(PALETTE.sand,.8,.01),slate:pbr(PALETTE.slate,.53,.18),
   red:pbr(PALETTE.red,.31,.25,{clearcoat:.72,clearcoatRoughness:.2}),carBlue:pbr(PALETTE.carBlue,.28,.24,{clearcoat:.78,clearcoatRoughness:.18}),
   carGreen:pbr(PALETTE.carGreen,.3,.23,{clearcoat:.7,clearcoatRoughness:.2}),lamp:pbr(0xf6c783,.35,.15,{emissive:0xffb45b,emissiveIntensity:.15}),
  };
  for(const key of ['ivory','terracotta','mustard','blue','teal','plum','sand'])this.materials[key].normalMap=this.asphaltNormal,this.materials[key].normalScale.set(.035,.035);
  this.windowMaterials=[];const temperatures=[0xffb36b,0xffc783,0xffd79b,0xffe5c7];
  temperatures.forEach((color,t)=>{for(let phase=0;phase<2;phase++){
   const m=pbr(t<2?0x273e43:0x334b50,.18,.08,{emissive:color,emissiveIntensity:.08,envMapIntensity:1.35});
   m.userData={temperature:t,phase:t*.73+phase*.41,toggle:phase===1};this.windowMaterials.push(m);
  }});
  this.patchFoliage(this.materials.leaf);this.patchFoliage(this.materials.leaf2);
 }
 patchFoliage(material){
  const wind=this.wind;material.onBeforeCompile=shader=>{
   shader.uniforms.uWindTime=wind.time;shader.uniforms.uWindStrength=wind.strength;shader.uniforms.uWindDirection=wind.direction;
   shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\nuniform float uWindTime;uniform float uWindStrength;uniform vec2 uWindDirection;').replace('#include <begin_vertex>','#include <begin_vertex>\nfloat windMask=smoothstep(-0.8,1.0,position.y);float gust=sin(uWindTime*0.72+position.x*1.9+position.z*1.3)*uWindStrength*windMask;transformed.xz+=uWindDirection*gust;');
  };material.customProgramCacheKey=()=>`foliage-v2`;
 }
 get(name){return this.materials[name]||name;}
 window(random,litRatio=.35){if(random()>litRatio)return random()>.5?'glass':'darkGlass';return this.windowMaterials[Math.floor(random()*this.windowMaterials.length)];}
 createEnvironment(renderer,scene){
  const w=128,h=64,data=new Uint8Array(w*h*4);
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){const i=(y*w+x)*4,t=y/(h-1),horizon=Math.exp(-Math.pow((t-.52)*7,2));data[i]=Math.round(24+68*horizon+20*(1-t));data[i+1]=Math.round(39+82*horizon+32*(1-t));data[i+2]=Math.round(48+88*horizon+46*(1-t));data[i+3]=255;}
  const source=new THREE.DataTexture(data,w,h,THREE.RGBAFormat);source.mapping=THREE.EquirectangularReflectionMapping;source.colorSpace=THREE.SRGBColorSpace;source.needsUpdate=true;
  const pmrem=new THREE.PMREMGenerator(renderer);const target=pmrem.fromEquirectangular(source);scene.environment=target.texture;source.dispose();pmrem.dispose();this.environmentTarget=target;return target.texture;
 }
 update(elapsed,night){
  this.wind.time.value=elapsed;this.materials.road.roughness=THREE.MathUtils.lerp(.84,.43,night);this.materials.road.envMapIntensity=THREE.MathUtils.lerp(.14,.34,night);
  this.materials.roadMark.emissiveIntensity=night*.19;this.materials.lamp.emissiveIntensity=.12+night*4.8;
  for(const m of this.windowMaterials){const wave=Math.sin(elapsed*.045+m.userData.phase*4.7),slow=m.userData.toggle ? .18+.82*THREE.MathUtils.smoothstep(wave,-.24,.18) : .9+.1*wave;m.emissiveIntensity=night*(1.25+m.userData.temperature*.13)*slow;}
 }
 setAnisotropy(value){for(const t of [this.asphaltColor,this.asphaltRoughness,this.asphaltNormal])t.anisotropy=value;}
}
