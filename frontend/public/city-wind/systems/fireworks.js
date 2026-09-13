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

const MAX_PARTICLES=720;

export class FireworkSystem{
 constructor(scene,quality){
  this.quality=quality;
  this.position=new Float32Array(MAX_PARTICLES*3);
  this.color=new Float32Array(MAX_PARTICLES*3);
  this.size=new Float32Array(MAX_PARTICLES);
  this.alpha=new Float32Array(MAX_PARTICLES);
  this.sharp=new Float32Array(MAX_PARTICLES);
  this.linePos=new Float32Array(MAX_PARTICLES*6);this.lineCol=new Float32Array(MAX_PARTICLES*8);
  this.p=[];                                    // 粒子狀態
  for(let i=0;i<MAX_PARTICLES;i++)this.p.push({live:false,vx:0,vy:0,vz:0,age:0,life:1,drag:.96,grav:0,ember:false,baseSize:1,streak:false});

  const geo=new THREE.BufferGeometry();
  geo.setAttribute('position',new THREE.BufferAttribute(this.position,3));
  geo.setAttribute('aColor',new THREE.BufferAttribute(this.color,3));
  geo.setAttribute('aSize',new THREE.BufferAttribute(this.size,1));
  geo.setAttribute('aAlpha',new THREE.BufferAttribute(this.alpha,1));
  geo.setAttribute('aSharp',new THREE.BufferAttribute(this.sharp,1));
  geo.setDrawRange(0,MAX_PARTICLES);
  geo.boundingSphere=new THREE.Sphere(new THREE.Vector3(-31,18,0),120);

  const mat=new THREE.ShaderMaterial({
   transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false,
   uniforms:{uScale:{value:1800}},
   vertexShader:`attribute vec3 aColor;attribute float aSize;attribute float aAlpha;attribute float aSharp;
    uniform float uScale;varying vec3 vColor;varying float vAlpha;varying float vSharp;
    void main(){vColor=aColor;vAlpha=aAlpha;vSharp=aSharp;vec4 mv=modelViewMatrix*vec4(position,1.);
     gl_PointSize=max(1.0,aSize*uScale/max(1.0,-mv.z));gl_Position=projectionMatrix*mv;}`,
   fragmentShader:`varying vec3 vColor;varying float vAlpha;varying float vSharp;
    void main(){vec2 d=gl_PointCoord-.5;float r=dot(d,d);
     if(r>.25)discard;
     // crisp phase: tight bright core; later phase: wide soft glow
     float core=exp(-r*mix(9.0,46.0,vSharp));
     float halo=exp(-r*5.0)*(1.0-vSharp)*.3;
     gl_FragColor=vec4(vColor*(core*mix(1.0,1.9,vSharp)+halo),vAlpha*(core+halo));}`,
  });
  this.points=new THREE.Points(geo,mat);
  this.points.frustumCulled=false;
  this.points.renderOrder=6;
  scene.add(this.points);
  // 剛炸開時的流線拖尾：每顆火花一段線，頭亮尾暗。WebGL 線寬固定 1 像素，所以線條是清楚的
  const lg=new THREE.BufferGeometry();
  lg.setAttribute('position',new THREE.BufferAttribute(this.linePos,3));
  lg.setAttribute('color',new THREE.BufferAttribute(this.lineCol,4));
  lg.boundingSphere=new THREE.Sphere(new THREE.Vector3(-31,18,0),120);
  this.lines=new THREE.LineSegments(lg,new THREE.LineBasicMaterial({vertexColors:true,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false}));
  this.lines.frustumCulled=false;this.lines.renderOrder=6;scene.add(this.lines);

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
  this.size[i]=baseSize;this.alpha[i]=1;this.sharp[i]=1;q.streak=false;
 }
 free(){for(let i=0;i<MAX_PARTICLES;i++)if(!this.p[i].live)return i;return -1;}

 launch(){
  // 河在 x=-31、z 由 -41 到 43。煙火在河面上方隨機位置升空。
  const x=-31+(this.rnd()-.5)*13,z=-34+this.rnd()*74;
  const pair=PALETTES[Math.floor(this.rnd()*PALETTES.length)];
  const a=new THREE.Color(pair[0]),b=new THREE.Color(pair[1]);
  this.rockets.push({x,y:1.6,z,vy:19+this.rnd()*8,t:0,peak:1.05+this.rnd()*.5,a,b});
  const i=this.free();
  if(i>=0)this.spawn(i,x,1.6,z,0,0,0,a.r,a.g,a.b,.05,.8,0,1,false);
 }

 explode(x,y,z,a,b){
  const n=this.quality.settings.post?120:72;
  for(let k=0;k<n;k++){
   const i=this.free();if(i<0)break;
   // 球面均勻取向，速度帶點隨機才不會像標準球
   const u=this.rnd()*2-1,th=this.rnd()*Math.PI*2,s=Math.sqrt(1-u*u);
   const sp=33+this.rnd()*20;
   const c=k%2?a:b;                                   // 兩種顏色一起放
   this.spawn(i,x,y,z,s*Math.cos(th)*sp,u*sp,s*Math.sin(th)*sp,c.r,c.g,c.b,
              2.3+this.rnd()*1.7,.95+this.rnd()*.45,-5.2,.955,false);this.p[i].streak=true;
  }
  this.bursts.push({x,y,z,r:(a.r+b.r)*.5,g:(a.g+b.g)*.5,b:(a.b+b.b)*.5,age:0,life:2.6});
 }

 update(dt,night,worldOpacity,launch=true){
  const dark=night>.25&&worldOpacity>.3;
  // 白天不能有煙火：一回到白天（例如從連結直接點回城市）就全部熄掉，不讓它燒完
  if(!dark){
   if(this.points.visible){for(let i=0;i<MAX_PARTICLES;i++){this.p[i].live=false;this.alpha[i]=0;this.lineCol[i*8+3]=0;this.lineCol[i*8+7]=0;}
    this.rockets.length=0;this.bursts.length=0;this.points.visible=false;this.lines.visible=false;
    this.points.geometry.attributes.aAlpha.needsUpdate=true;this.lines.geometry.attributes.color.needsUpdate=true;}
   this.glow.strength=0;return;
  }
  // 天色還暗但離開了連結：不再發射，空中的讓它自然燒完
  const active=launch;
  // 離開放煙火的範圍就不再發射，但已經在空中的讓它自然燒完，不會一瞬間全部消失
  let anyLive=this.rockets.length>0;
  if(!anyLive)for(let i=0;i<MAX_PARTICLES;i++)if(this.p[i].live){anyLive=true;break;}
  if(!active&&!anyLive){
   this.points.visible=false;this.lines.visible=false;this.bursts.length=0;
   this.glow.strength*=Math.pow(.02,Math.min(dt,.05));
   return;
  }
  this.points.visible=true;this.lines.visible=true;
  const step=Math.min(dt,.05);
  if(active){this.next-=step;if(this.next<=0){this.launch();this.next=1.1+this.rnd()*2.6;}}

  // 升空
  for(let r=this.rockets.length-1;r>=0;r--){
   const k=this.rockets[r];k.t+=step;k.y+=k.vy*step;k.vy-=11*step;
   if(k.t>=k.peak||k.vy<=1.2){this.explode(k.x,k.y,k.z,k.a,k.b);this.rockets.splice(r,1);}
   else{
    const i=this.free();
    if(i>=0)this.spawn(i,k.x+(this.rnd()-.5)*.3,k.y,k.z+(this.rnd()-.5)*.3,0,-1.5,0,1,.82,.5,.4,.55,-2,.9,false);
   }
  }

  // 粒子的三個層次：
  //  1) 剛炸開：清楚的流線，細線拖尾加銳利亮點，像流體被甩出去；
  //  2) 散開：拖尾收掉，亮點變大變柔，成為光暈；
  //  3) 燒完：部分留下很小的火星慢慢下墜。
  const sd=(a,b,v)=>{const t=Math.min(1,Math.max(0,(v-a)/(b-a)));return t*t*(3-2*t);};
  for(let i=0;i<MAX_PARTICLES;i++){
   const q=this.p[i],L=i*6,C=i*8;
   if(!q.live){this.alpha[i]=0;this.lineCol[C+3]=0;this.lineCol[C+7]=0;continue;}
   q.age+=step;
   if(q.age>=q.life){
    if(!q.ember&&this.rnd()<.34){
     q.age=0;q.life=2.2+this.rnd()*1.6;q.ember=true;q.baseSize=.3+this.rnd()*.18;
     q.vx*=.12;q.vy=-.6-this.rnd()*.8;q.vz*=.12;q.grav=-1.5;q.drag=.985;
    }else{q.live=false;this.alpha[i]=0;this.lineCol[C+3]=0;this.lineCol[C+7]=0;continue;}
   }
   q.vy+=q.grav*step;
   const d=Math.pow(q.drag,step*60);
   q.vx*=d;q.vy*=d;q.vz*=d;
   this.position[i*3]+=q.vx*step;this.position[i*3+1]+=q.vy*step;this.position[i*3+2]+=q.vz*step;
   const x=this.position[i*3],y=this.position[i*3+1],z=this.position[i*3+2];
   const t=q.age/q.life;
   const fade=q.ember?(1-t)*(1-t):Math.pow(1-t,1.7)*(.55+.45*Math.exp(-t*2.2));
   this.alpha[i]=fade;
   if(q.ember){this.sharp[i]=.85;this.size[i]=q.baseSize;}
   else{this.sharp[i]=1-sd(.08,.5,t);this.size[i]=q.baseSize*(.45+.85*sd(.04,.55,t))*(1-.2*sd(.6,1,t));}
   const la=(q.streak&&!q.ember)?(1-sd(.1,.34,t))*fade:0;
   if(la>.002){
    this.linePos[L]=x;this.linePos[L+1]=y;this.linePos[L+2]=z;
    this.linePos[L+3]=x-q.vx*.12;this.linePos[L+4]=y-q.vy*.12;this.linePos[L+5]=z-q.vz*.12;
    const cr=this.color[i*3],cg=this.color[i*3+1],cb=this.color[i*3+2];
    this.lineCol[C]=Math.min(1,cr*1.4);this.lineCol[C+1]=Math.min(1,cg*1.4);this.lineCol[C+2]=Math.min(1,cb*1.4);this.lineCol[C+3]=la;
    this.lineCol[C+4]=cr;this.lineCol[C+5]=cg;this.lineCol[C+6]=cb;this.lineCol[C+7]=0;
   }else{this.lineCol[C+3]=0;this.lineCol[C+7]=0;}
   if(y<.3){q.live=false;this.alpha[i]=0;this.lineCol[C+3]=0;this.lineCol[C+7]=0;}
  }

  // 水面倒影參考：取當下最強的一朵
  let best=null;
  for(let b=this.bursts.length-1;b>=0;b--){
   const k=this.bursts[b];k.age+=step;
   if(k.age>=k.life){this.bursts.splice(b,1);continue;}
   const sv=Math.pow(1-k.age/k.life,1.6);
   if(!best||sv>best.s)best={k,s:sv};
  }
  if(best){this.glow.x=best.k.x;this.glow.z=best.k.z;this.glow.r=best.k.r;this.glow.g=best.k.g;this.glow.b=best.k.b;this.glow.strength=best.s;}
  else this.glow.strength*=Math.pow(.02,step);

  const at=this.points.geometry.attributes;
  at.position.needsUpdate=true;at.aColor.needsUpdate=true;at.aSize.needsUpdate=true;at.aAlpha.needsUpdate=true;at.aSharp.needsUpdate=true;
  const lt=this.lines.geometry.attributes;lt.position.needsUpdate=true;lt.color.needsUpdate=true;
 }
}
