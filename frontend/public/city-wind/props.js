import * as THREE from './three.module.min.js';

export function buildDocument(materialLibrary){
 const root=new THREE.Group();root.position.set(18.5,8,2.5);root.rotation.x=-.6;
 const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=1400;const ctx=canvas.getContext('2d');
 const tex=new THREE.CanvasTexture(canvas);tex.colorSpace=THREE.SRGBColorSpace;tex.anisotropy=4;
 // Printed paper stays matte and shadow-free so the city shadow map can never
 // project building/window bands across the document during the transition.
 const paperMat=new THREE.MeshStandardMaterial({map:tex,roughness:.86,side:THREE.DoubleSide});
 const stackMat=new THREE.MeshStandardMaterial({color:0xd4d3c4,roughness:.8,transparent:true});
 for(let i=3;i>=1;i--){const sheet=new THREE.Mesh(new THREE.BoxGeometry(19.8,27,.05),stackMat);sheet.position.set(i*.09,-i*.07,-i*.06);sheet.rotation.z=-i*.009;root.add(sheet);}
 const page=new THREE.Mesh(new THREE.PlaneGeometry(19.8,27),paperMat);page.receiveShadow=false;page.castShadow=false;root.add(page);
 // 退場：整張紙碎成不規則的碎片，順著風的方向翻滾飄走。
 // 碎片是共用同一張貼圖的網格，格點有抖動所以是不規則多邊形，但仍能完整拼回整張紙；
 // 靜止時與原本的紙完全重合，所以切換瞬間看不出來。每一片依位置有不同的放開時間，
 // 從迎風的左上角開始、往下風的右下角一路散開。
 const GX=9,GY=12,W=19.8,H=27;
 let fs=9127;const frnd=()=>{fs=(fs*1664525+1013904223)>>>0;return fs/4294967296;};
 const gp=[];
 for(let j=0;j<=GY;j++)for(let i=0;i<=GX;i++){
  const edge=i===0||j===0||i===GX||j===GY;
  const jx=edge?0:(frnd()-.5)*.55,jy=edge?0:(frnd()-.5)*.55;
  gp.push([(i/GX-.5)*W+jx*W/GX,(j/GY-.5)*H+jy*H/GY,i/GX+jx/GX,j/GY+jy/GY]);
 }
 const NF=GX*GY,fragPos=new Float32Array(NF*12),fragNor=new Float32Array(NF*12),fragUv=new Float32Array(NF*8),fragCol=new Float32Array(NF*16),fragIdx=[],frags=[];
 for(let j=0;j<GY;j++)for(let i=0;i<GX;i++){
  const f=frags.length,ids=[j*(GX+1)+i,j*(GX+1)+i+1,(j+1)*(GX+1)+i+1,(j+1)*(GX+1)+i];
  const corners=ids.map(k=>gp[k]);
  const cx=(corners[0][0]+corners[1][0]+corners[2][0]+corners[3][0])/4,cy=(corners[0][1]+corners[1][1]+corners[2][1]+corners[3][1])/4;
  corners.forEach((c,k)=>{const v=f*4+k;fragUv[v*2]=c[2];fragUv[v*2+1]=c[3];fragPos[v*3]=c[0];fragPos[v*3+1]=c[1];fragPos[v*3+2]=0;fragNor[v*3+2]=1;fragCol.set([1,1,1,1],v*4);});
  fragIdx.push(f*4,f*4+1,f*4+2,f*4,f*4+2,f*4+3);
  const sweep=(i/GX)*.62+(1-j/GY)*.28;
  const ax=frnd()-.5,ay=frnd()-.5,az=frnd()-.5,al=Math.hypot(ax,ay,az)||1;
  frags.push({cx,cy,off:corners.map(c=>[c[0]-cx,c[1]-cy]),release:sweep*.55+frnd()*.08,
   axis:new THREE.Vector3(ax/al,ay/al,az/al),spin:3+frnd()*6,drift:.75+frnd()*.6,lift:.4+frnd()*.9,phase:frnd()*6.28});
 }
 const fragGeo=new THREE.BufferGeometry();
 fragGeo.setAttribute('position',new THREE.BufferAttribute(fragPos,3));
 fragGeo.setAttribute('normal',new THREE.BufferAttribute(fragNor,3));
 fragGeo.setAttribute('uv',new THREE.BufferAttribute(fragUv,2));
 fragGeo.setAttribute('color',new THREE.BufferAttribute(fragCol,4));
 fragGeo.setIndex(fragIdx);
 const fragMat=new THREE.MeshStandardMaterial({map:tex,roughness:.86,side:THREE.DoubleSide,vertexColors:true,transparent:true,depthWrite:false});
 const frag=new THREE.Mesh(fragGeo,fragMat);frag.visible=false;frag.frustumCulled=false;frag.castShadow=false;frag.receiveShadow=false;root.add(frag);
 // 與場景裡的風同方向（往 +x、+z），再帶一點上揚
 const WIND_WORLD=new THREE.Vector3(.86,.34,.38).normalize();
 const _q=new THREE.Quaternion(),_qi=new THREE.Quaternion(),_v=new THREE.Vector3(),_w=new THREE.Vector3(),_n=new THREE.Vector3();
 const sd=(a,b,v)=>{const t=Math.min(1,Math.max(0,(v-a)/(b-a)));return t*t*(3-2*t);};
 // The parcel border uses the same proportions and identity as the scene parcel.
 let lastStep=-1;
 function draw(progress){const step=Math.floor(progress*32);if(step===lastStep)return;lastStep=step;
  ctx.fillStyle='#f3f0e4';ctx.fillRect(0,0,1024,1400);
  ctx.strokeStyle='#b1b2a7';ctx.lineWidth=1.4;ctx.strokeRect(65,65,894,1268);
  ctx.fillStyle='#49655c';ctx.font='18px sans-serif';ctx.fillText('城市起風  /  LAND RECORD',100,112);ctx.textAlign='right';ctx.fillText('NO. 0128',920,112);ctx.textAlign='left';
  ctx.fillStyle='#243c36';ctx.font='bold 49px sans-serif';ctx.fillText('土地資料紀錄',100,198);ctx.font='20px sans-serif';ctx.fillStyle='#768478';ctx.fillText('資料填寫與核對 · 敘事示意',100,245);
  ctx.strokeStyle='#9ea99d';ctx.beginPath();ctx.moveTo(100,283);ctx.lineTo(924,283);ctx.stroke();
  const labels=['土地段名','土地地號','紀錄項目','資料狀態'];const values=['起風段','0128','地籍附圖與土地資料','逐項核對'];
  labels.forEach((label,i)=>{const y=346+i*86;ctx.fillStyle='#758275';ctx.font='21px sans-serif';ctx.fillText(label,100,y);ctx.strokeStyle='#cad0c2';ctx.beginPath();ctx.moveTo(265,y+15);ctx.lineTo(915,y+15);ctx.stroke();const n=Math.floor(Math.max(0,Math.min(1,progress*5-i*.65))*values[i].length);ctx.font='27px sans-serif';ctx.fillStyle='#243c36';ctx.fillText(values[i].slice(0,n),282,y);});
  ctx.font='21px sans-serif';ctx.fillStyle='#768478';ctx.fillText('宗地位置示意',100,724);
  ctx.save();ctx.translate(130,770);ctx.fillStyle='#e6e9dc';ctx.fillRect(0,0,760,340);ctx.strokeStyle='#c0ccbb';ctx.lineWidth=2;
  for(let i=0;i<4;i++){ctx.beginPath();ctx.moveTo(i*252,0);ctx.lineTo(i*252,340);ctx.stroke();}for(let i=0;i<3;i++){ctx.beginPath();ctx.moveTo(0,i*168);ctx.lineTo(760,i*168);ctx.stroke();}
  ctx.fillStyle='#d7dac4';ctx.fillRect(255,50,250,235);ctx.strokeStyle='#b98651';ctx.lineWidth=5;ctx.strokeRect(255,50,250,235);ctx.font='bold 34px sans-serif';ctx.textAlign='center';ctx.fillStyle='#53624d';ctx.fillText('0128',380,186);ctx.textAlign='left';for(const [x,y]of [[255,50],[505,50],[505,285],[255,285]]){ctx.fillStyle='#b98651';ctx.beginPath();ctx.arc(x,y,7,0,Math.PI*2);ctx.fill();}ctx.restore();
  ctx.font='19px sans-serif';ctx.fillStyle='#899083';ctx.fillText('非正式申請書 · 地籍與欄位皆為示意',100,1170);
  if(progress>.78){ctx.save();ctx.translate(786,1238);ctx.rotate(-.1);ctx.strokeStyle='#b38756';ctx.lineWidth=2;ctx.strokeRect(-105,-40,205,63);ctx.font='25px sans-serif';ctx.fillStyle='#9e754a';ctx.fillText('資料已核對',-82,1);ctx.restore();}
  ctx.font='15px monospace';ctx.fillStyle='#889084';ctx.fillText('CITY IN MOTION — EVERY PARCEL TELLS A STORY',100,1295);tex.needsUpdate=true;
 }
 draw(0);
 const pencil=new THREE.Group();
 const barrel=new THREE.Mesh(new THREE.CylinderGeometry(.16,.16,6.2,12),new THREE.MeshStandardMaterial({color:0xb7854f,metalness:.5,roughness:.3}));pencil.add(barrel);
 const tip=new THREE.Mesh(new THREE.ConeGeometry(.17,.8,12),new THREE.MeshStandardMaterial({color:0x1e3431,metalness:.45,roughness:.25}));tip.position.y=-3.5;tip.rotation.z=Math.PI;pencil.add(tip);
 const end=new THREE.Mesh(new THREE.CylinderGeometry(.17,.17,.5,12),new THREE.MeshStandardMaterial({color:0xd1d2c6,metalness:.7,roughness:.3}));end.position.y=3;pencil.add(end);pencil.rotation.z=-.6;pencil.position.set(5,5,.5);root.add(pencil);
 function disintegrate(r,t){
  if(r<=.0005){page.visible=true;frag.visible=false;stackMat.opacity=1;pencil.visible=true;pencil.scale.setScalar(1);return;}
  page.visible=false;frag.visible=r<.999;
  stackMat.opacity=1-sd(0,.3,r);
  pencil.scale.setScalar(Math.max(.001,1-sd(0,.25,r)));pencil.visible=r<.25;
  // 世界座標的風向換算到紙的座標系
  root.getWorldQuaternion(_qi);_qi.invert();_w.copy(WIND_WORLD).applyQuaternion(_qi);
  for(let f=0;f<frags.length;f++){
   const F=frags[f],q=Math.min(1,Math.max(0,(r-F.release)/.42));
   const e=q*q;                               // 先慢後快：被風帶起來的感覺
   const d=e*26*F.drift,wob=Math.sin(t*2.1+F.phase)*e*1.6;
   const px=F.cx+_w.x*d+wob*.4,py=F.cy+_w.y*d+e*F.lift*6,pz=_w.z*d+Math.cos(t*1.7+F.phase)*e*1.2;
   _q.setFromAxisAngle(F.axis,q*F.spin);_n.set(0,0,1).applyQuaternion(_q);
   const a=1-sd(.55,1,q),sc=1-q*.35;
   for(let k=0;k<4;k++){
    _v.set(F.off[k][0]*sc,F.off[k][1]*sc,0).applyQuaternion(_q);
    const v=f*4+k;
    fragPos[v*3]=px+_v.x;fragPos[v*3+1]=py+_v.y;fragPos[v*3+2]=pz+_v.z;
    fragNor[v*3]=_n.x;fragNor[v*3+1]=_n.y;fragNor[v*3+2]=_n.z;
    fragCol[v*4+3]=a;
   }
  }
  fragGeo.attributes.position.needsUpdate=true;fragGeo.attributes.normal.needsUpdate=true;fragGeo.attributes.color.needsUpdate=true;
 }
 return {root,draw,pencil,frag,disintegrate};
}

export function buildAppraiser(materialLibrary){
 const root=new THREE.Group();root.position.set(30,1,8);root.rotation.y=-.5;
 const mat=(c,metalness=0,cloth=false)=>new THREE.MeshPhysicalMaterial({color:c,roughness:cloth?.7:.55,metalness,sheen:cloth?.2:0,sheenRoughness:.78,envMapIntensity:metalness?.9:.48});const coat=mat(0x997a5c,0,true),shirt=mat(0xe9e4ce,0,true),pants=mat(0x344749,0,true),skin=mat(0xceaf8c),hair=mat(0x35403a),shoe=mat(0x223330),gold=mat(0xa6a188,.6);
 function m(g,ma,x,y,z,parent){const o=new THREE.Mesh(g,ma);o.position.set(x,y,z);o.castShadow=true;(parent||root).add(o);return o;}
 function limb(a,b,r,ma,parent){const p=new THREE.Vector3(...a),q=new THREE.Vector3(...b),d=q.clone().sub(p);const o=m(new THREE.CapsuleGeometry(r,Math.max(.05,d.length()-2*r),6,12),ma,...p.clone().add(q).multiplyScalar(.5).toArray(),parent);o.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());return o;}
 for(const side of [-1,1]){limb([side*.44,.7,0],[side*.42,3.15,0],.32,pants);m(new THREE.BoxGeometry(.65,.36,1.1),shoe,side*.44,.3,.24);}
 m(new THREE.CylinderGeometry(.8,.68,2.2,18),coat,0,4,0);m(new THREE.BoxGeometry(.37,1.7,.12),shirt,0,4.12,.7);
 const lapel1=m(new THREE.BoxGeometry(.25,1.35,.09),coat,-.24,4.35,.81);lapel1.rotation.z=.17;const lapel2=m(new THREE.BoxGeometry(.25,1.35,.09),coat,.24,4.35,.81);lapel2.rotation.z=-.17;
 m(new THREE.CylinderGeometry(.24,.27,.5,12),skin,0,5.2,0);const head=m(new THREE.SphereGeometry(.63,24,18),skin,0,5.98,.04);head.scale.set(.85,1.15,.86);
 const cap=m(new THREE.SphereGeometry(.65,20,12,0,Math.PI*2,0,Math.PI*.58),hair,0,6.12,-.06);cap.scale.set(.86,1,.86);
 for(const side of [-1,1]){m(new THREE.TorusGeometry(.16,.022,6,16),gold,side*.23,6.05,.52);m(new THREE.SphereGeometry(.035,8,6),hair,side*.23,6.05,.55);}m(new THREE.BoxGeometry(.13,.035,.035),gold,0,6.05,.55);
 limb([-.72,4.7,0],[-1.1,3.7,.55],.24,coat);limb([-1.1,3.7,.55],[-.65,3.8,1.2],.21,coat);
 m(new THREE.SphereGeometry(.22,12,8),skin,-.62,3.86,1.2);
 // 右臂掛在肩膀的樞紐群組底下，座標改成相對肩膀，這樣整條手臂才能一起舉起來
 const rightArm=new THREE.Group();rightArm.position.set(.72,4.7,0);root.add(rightArm);
 limb([0,0,0],[.33,-.85,.55],.24,coat,rightArm);limb([.33,-.85,.55],[-.14,-.65,1.2],.2,coat,rightArm);
 const rightHand=m(new THREE.SphereGeometry(.22,12,8),skin,-.2,-.62,1.25,rightArm);
 // 大拇指：平時收起，比讚時立起來
 const thumb=m(new THREE.CapsuleGeometry(.075,.2,5,8),skin,-.2,-.38,1.34,rightArm);thumb.rotation.z=.35;thumb.visible=false;
 const tablet=m(new THREE.BoxGeometry(1.75,1.22,.1),pants,0,4.12,1.23);tablet.rotation.x=-.4;
 const screen=m(new THREE.PlaneGeometry(1.52,1.02),mat(0x85aaa2),0,4.13,1.3);screen.rotation.x=-.4;

 // 靈光一閃：燈泡亮起並照到臉 → 比大拇指 → 輕微搖晃。
 // 整段由 update(t) 依時間循環，數值都是平滑函式算出來的，不會抖。
 const bulbPivot=new THREE.Group();bulbPivot.position.set(-2.05,7.55,.25);root.add(bulbPivot);
 const bulbMat=new THREE.MeshBasicMaterial({color:0xffeec0,transparent:true,opacity:0,toneMapped:false});
 const bulb=m(new THREE.SphereGeometry(.36,16,12),bulbMat,0,0,0,bulbPivot);bulb.castShadow=false;
 const haloMat=new THREE.MeshBasicMaterial({color:0xffd98a,transparent:true,opacity:0,toneMapped:false,depthWrite:false,blending:THREE.AdditiveBlending});
 const halo=m(new THREE.SphereGeometry(.86,16,12),haloMat,0,0,0,bulbPivot);halo.castShadow=false;
 const capM=m(new THREE.CylinderGeometry(.15,.17,.22,10),gold,0,-.4,0,bulbPivot);capM.castShadow=false;
 // 打在臉上的光源
 // 光源不能掛在會被 visible=false 的群組底下：three.js 只計算可見物件底下的燈，
 // 燈數一變就會讓場上所有材質重新編譯著色器，畫面就會卡住好幾百毫秒。
 // 改成由 app.js 掛到場景、永遠存在，只調 intensity；位置用 anchor 每幀同步。
 const faceAnchor=new THREE.Object3D();faceAnchor.position.set(-1.5,7.0,.6);root.add(faceAnchor);
 const faceLight=new THREE.PointLight(0xffd79a,0,9,2);

 const sstep=(a,b,v)=>{const t=Math.min(1,Math.max(0,(v-a)/(b-a)));return t*t*(3-2*t);};
 let appearAt=null;
 root.userData.faceLight=faceLight;root.userData.faceAnchor=faceAnchor;
 // 初始狀態：燈泡暗、手放下、不搖晃
 const resetPose=()=>{bulbMat.opacity=0;haloMat.opacity=0;bulbPivot.scale.setScalar(.82);bulbPivot.position.y=7.55;
  rightArm.rotation.set(0,0,0);thumb.visible=false;thumb.rotation.z=.35;
  root.rotation.z=0;root.rotation.y=-.5;root.position.y=1;faceLight.intensity=0;};
 root.userData.update=(t,active)=>{
  faceAnchor.getWorldPosition(faceLight.position);
  // 離開「價值」這一章（往下到連結、往上到紀錄）才回到初始的暗燈狀態；再進來會重新靈光一閃
  if(!active){if(appearAt!==null)resetPose();appearAt=null;return;}
  if(appearAt===null)appearAt=t;
  const c=t-appearAt;
  // 燈泡：出現後 0.25 秒亮起，之後一直亮著，只有很慢的呼吸
  const on=sstep(.25,.6,c);
  const spark=Math.max(0,1-Math.abs(c-.6)/.38);     // 亮起瞬間的「一閃」
  const glow=Math.min(1,on*(.9+.1*Math.sin(t*2.3))+spark*.55);
  bulbMat.opacity=glow*.96;haloMat.opacity=glow*.42;
  bulbPivot.scale.setScalar(.82+glow*.26+spark*.1);
  bulbPivot.position.y=7.55+Math.sin(t*1.7)*.06*on;
  faceLight.intensity=glow*7.5;
  // 比大拇指：0.85 秒舉起，之後一直比著
  const up=sstep(.85,1.4,c);
  rightArm.rotation.x=-up*1.42;rightArm.rotation.z=up*.3;
  thumb.visible=up>.12;thumb.rotation.z=.35-up*.3;
  // 舉起後一直輕微搖晃
  const sway=up*Math.sin(t*3.1)*.055;
  root.rotation.z=sway;root.rotation.y=-.5+sway*.6+Math.sin(t*.8)*.02;
  root.position.y=1+Math.sin(t*1.25)*.035;
 };
 resetPose();

 root.scale.setScalar(1.35);return root;
}

export function buildMagnifier(source){
 const scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-1,1,1,-1,.1,3000);camera.position.z=1000;
 scene.add(new THREE.AmbientLight(0xffffff,2));const light=new THREE.DirectionalLight(0xffedcb,4);light.position.set(-100,300,500);scene.add(light);
 const root=new THREE.Group();scene.add(root);
 const metal=new THREE.MeshStandardMaterial({color:0xd3b589,metalness:.7,roughness:.26});const inner=new THREE.MeshStandardMaterial({color:0x254342,metalness:.55,roughness:.3});
 root.add(new THREE.Mesh(new THREE.TorusGeometry(100,4.6,12,96),metal));const rim=new THREE.Mesh(new THREE.TorusGeometry(94.5,1.4,8,96),inner);rim.position.z=1;root.add(rim);
 const shaft=new THREE.Mesh(new THREE.CylinderGeometry(6.5,8.5,112,18),inner);shaft.position.set(107,-107,-2);shaft.rotation.z=Math.PI/4;root.add(shaft);
 const collar=new THREE.Mesh(new THREE.CylinderGeometry(7,7,21,16),metal);collar.position.set(78,-78,-2);collar.rotation.z=Math.PI/4;root.add(collar);
 const lensMat=new THREE.ShaderMaterial({uniforms:{tScene:{value:source},resolution:{value:new THREE.Vector2(1,1)},center:{value:new THREE.Vector2(.5,.5)},radius:{value:100},power:{value:.53}},vertexShader:'varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',fragmentShader:`uniform sampler2D tScene;uniform vec2 resolution;uniform vec2 center;uniform float radius;uniform float power;varying vec2 vUv;
 void main(){vec2 uv=gl_FragCoord.xy/resolution;vec2 d=uv-center;float r=length(vUv-.5)*2.;vec2 warped=center+d*(power+.11*r*r);vec2 ca=d*.018*r*r;vec3 c=vec3(texture2D(tScene,warped+ca).r,texture2D(tScene,warped).g,texture2D(tScene,warped-ca).b);float rim=pow(smoothstep(.68,1.,r),3.);c=mix(c,vec3(.63,.81,.8),rim*.18);float glint=pow(max(0.,1.-abs(vUv.y-.78-vUv.x*.12)*19.),4.)*.1;c+=glint;gl_FragColor=vec4(c,1.);}`,depthTest:false,depthWrite:false,toneMapped:false});
 const lens=new THREE.Mesh(new THREE.CircleGeometry(94,96),lensMat);lens.position.z=-.5;root.add(lens);
 return {scene,camera,root,lensMat,resize(w,h,pixelRatio){camera.left=-w/2;camera.right=w/2;camera.top=h/2;camera.bottom=-h/2;camera.updateProjectionMatrix();lensMat.uniforms.resolution.value.set(Math.round(w*pixelRatio),Math.round(h*pixelRatio));}};
}
