import * as THREE from '../three.module.min.js';

/* 河邊的煙火。
   一朵完整的煙火＝升空 → 炸開（兩種顏色一起）→ 慢慢暗掉 → 掉下很小的餘燼。
   整組用單一 Points 物件，屬性在 CPU 上更新，粒子數不多，每幀成本很低。
   另外把當下最亮那朵的位置與顏色輸出成 glow，給水面著色器做倒影。 */

// 每朵取兩個顏色一起放
const PALETTES=[
 [0xff6b7a,0xffd166],[0x6ee7ff,0xb39bff],[0xffd166,0x8ef6a0],
 [0xff8ad1,0x86e3ff],[0xffe08a,0xff7a3d],[0x9bf6ff,0xfff3a0],
];

const MAX_PARTICLES=560;

export class FireworkSystem{
 constructor(scene,quality){
  this.quality=quality;
  this.position=new Float32Array(MAX_PARTICLES*3);
  this.color=new Float32Array(MAX_PARTICLES*3);
  this.size=new Float32Array(MAX_PARTICLES);
  this.alpha=new Float32Array(MAX_PARTICLES);
  this.p=[];                                    // 粒子狀態
  for(let i=0;i<MAX_PARTICLES;i++)this.p.push({live:false,vx:0,vy:0,vz:0,age:0,life:1,drag:.96,grav:0,ember:false,baseSize:1});

  const geo=new THREE.BufferGeometry();
  geo.setAttribute('position',new THREE.BufferAttribute(this.position,3));
  geo.setAttribute('aColor',new THREE.BufferAttribute(this.color,3));
  geo.setAttribute('aSize',new THREE.BufferAttribute(this.size,1));
  geo.setAttribute('aAlpha',new THREE.BufferAttribute(this.alpha,1));
  geo.setDrawRange(0,MAX_PARTICLES);
  geo.boundingSphere=new THREE.Sphere(new THREE.Vector3(-31,18,0),120);

  const mat=new THREE.ShaderMaterial({
   transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false,
   uniforms:{uScale:{value:1350}},
   vertexShader:`attribute vec3 aColor;attribute float aSize;attribute float aAlpha;
    uniform float uScale;varying vec3 vColor;varying float vAlpha;
    void main(){vColor=aColor;vAlpha=aAlpha;vec4 mv=modelViewMatrix*vec4(position,1.);
     gl_PointSize=max(1.0,aSize*uScale/max(1.0,-mv.z));gl_Position=projectionMatrix*mv;}`,
   fragmentShader:`varying vec3 vColor;varying float vAlpha;
    void main(){vec2 d=gl_PointCoord-.5;float r=dot(d,d);
     if(r>.25)discard;
     float fall=exp(-r*11.0);
     gl_FragColor=vec4(vColor*fall,vAlpha*fall);}`,
  });
  this.points=new THREE.Points(geo,mat);
  this.points.frustumCulled=false;
  this.points.renderOrder=6;
  scene.add(this.points);

  this.rockets=[];
  this.next=1.2;
  this.bursts=[];                               // 供水面倒影參考
  this.glow={x:0,z:0,r:0,g:0,b:0,strength:0};
  this.seed=1337;
 }
 rnd(){this.seed=(this.seed*1664525+1013904223)>>>0;return this.seed/4294967296;}

 spawn(i,x,y,z,vx,vy,vz,cr,cg,cb,life,baseSize,grav,drag,ember){
  const q=this.p[i];q.live=true;q.vx=vx;q.vy=vy;q.vz=vz;q.age=0;q.life=life;q.grav=grav;q.drag=drag;q.ember=ember;q.baseSize=baseSize;
  this.position[i*3]=x;this.position[i*3+1]=y;this.position[i*3+2]=z;
  this.color[i*3]=cr;this.color[i*3+1]=cg;this.color[i*3+2]=cb;
  this.size[i]=baseSize;this.alpha[i]=1;
 }
 free(){for(let i=0;i<MAX_PARTICLES;i++)if(!this.p[i].live)return i;return -1;}

 launch(){
  // 河在 x=-31、z 由 -41 到 43。煙火在河面上方隨機位置升空。
  const x=-31+(this.rnd()-.5)*13,z=-34+this.rnd()*74;
  const pair=PALETTES[Math.floor(this.rnd()*PALETTES.length)];
  const a=new THREE.Color(pair[0]),b=new THREE.Color(pair[1]);
  this.rockets.push({x,y:1.6,z,vy:15+this.rnd()*7,t:0,peak:1.05+this.rnd()*.5,a,b});
  const i=this.free();
  if(i>=0)this.spawn(i,x,1.6,z,0,0,0,a.r,a.g,a.b,.05,.8,0,1,false);
 }

 explode(x,y,z,a,b){
  const n=this.quality.settings.post?96:60;
  for(let k=0;k<n;k++){
   const i=this.free();if(i<0)break;
   // 球面均勻取向，速度帶點隨機才不會像標準球
   const u=this.rnd()*2-1,th=this.rnd()*Math.PI*2,s=Math.sqrt(1-u*u);
   const sp=15+this.rnd()*11;
   const c=k%2?a:b;                                   // 兩種顏色一起放
   this.spawn(i,x,y,z,s*Math.cos(th)*sp,u*sp,s*Math.sin(th)*sp,c.r,c.g,c.b,
              2.3+this.rnd()*1.7,.95+this.rnd()*.45,-5.2,.955,false);
  }
  this.bursts.push({x,y,z,r:(a.r+b.r)*.5,g:(a.g+b.g)*.5,b:(a.b+b.b)*.5,age:0,life:2.6});
 }

 update(dt,night,worldOpacity){
  const active=night>.25&&worldOpacity>.3;
  this.points.visible=active;
  if(!active){
   // 夜晚以外不放，順手把殘留的粒子熄掉
   if(this.glow.strength>0){this.glow.strength=0;}
   for(let i=0;i<MAX_PARTICLES;i++)if(this.p[i].live){this.p[i].live=false;this.alpha[i]=0;}
   this.rockets.length=0;this.bursts.length=0;
   this.points.geometry.attributes.aAlpha.needsUpdate=true;
   return;
  }
  const step=Math.min(dt,.05);
  this.next-=step;
  if(this.next<=0){this.launch();this.next=1.1+this.rnd()*2.6;}      // 隨機間隔

  // 升空
  for(let r=this.rockets.length-1;r>=0;r--){
   const k=this.rockets[r];k.t+=step;k.y+=k.vy*step;k.vy-=11*step;
   if(k.t>=k.peak||k.vy<=1.2){this.explode(k.x,k.y,k.z,k.a,k.b);this.rockets.splice(r,1);}
   else{
    // 升空時的尾焰
    const i=this.free();
    if(i>=0)this.spawn(i,k.x+(this.rnd()-.5)*.3,k.y,k.z+(this.rnd()-.5)*.3,0,-1.5,0,1,.82,.5,.4,.55,-2,.9,false);
   }
  }

  // 粒子
  for(let i=0;i<MAX_PARTICLES;i++){
   const q=this.p[i];if(!q.live){this.alpha[i]=0;continue;}
   q.age+=step;
   if(q.age>=q.life){
    // 火花燒完後，有機會留下一點很小的餘燼慢慢飄落
    if(!q.ember&&this.rnd()<.34){
     q.age=0;q.life=2.2+this.rnd()*1.6;q.ember=true;q.baseSize=.3+this.rnd()*.18;
     q.vx*=.12;q.vy=-.6-this.rnd()*.8;q.vz*=.12;q.grav=-1.5;q.drag=.985;
    }else{q.live=false;this.alpha[i]=0;continue;}
   }
   q.vy+=q.grav*step;
   const d=Math.pow(q.drag,step*60);
   q.vx*=d;q.vy*=d;q.vz*=d;
   this.position[i*3]+=q.vx*step;
   this.position[i*3+1]+=q.vy*step;
   this.position[i*3+2]+=q.vz*step;
   const t=q.age/q.life;
   // 慢慢暗掉：前段幾乎維持亮度，後段才平滑收掉，不是線性直接消失
   const fade=q.ember?(1-t)*(1-t):Math.pow(1-t,1.7)*(.55+.45*Math.exp(-t*2.2));
   this.alpha[i]=fade;
   this.size[i]=q.baseSize*(q.ember?1:(.7+.5*(1-t)));
   if(this.position[i*3+1]<.3){q.live=false;this.alpha[i]=0;}          // 落到水面就熄
  }

  // 水面倒影參考：取當下最強的一朵
  let best=null;
  for(let b=this.bursts.length-1;b>=0;b--){
   const k=this.bursts[b];k.age+=step;
   if(k.age>=k.life){this.bursts.splice(b,1);continue;}
   const s=Math.pow(1-k.age/k.life,1.6);
   if(!best||s>best.s)best={k,s};
  }
  if(best){this.glow.x=best.k.x;this.glow.z=best.k.z;this.glow.r=best.k.r;this.glow.g=best.k.g;this.glow.b=best.k.b;this.glow.strength=best.s;}
  else this.glow.strength*=Math.pow(.02,step);

  const a=this.points.geometry.attributes;
  a.position.needsUpdate=true;a.aColor.needsUpdate=true;a.aSize.needsUpdate=true;a.aAlpha.needsUpdate=true;
 }
}
