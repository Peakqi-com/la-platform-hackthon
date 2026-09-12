import * as THREE from './three.module.min.js';

export function buildDocument(materialLibrary){
 const root=new THREE.Group();root.position.set(18.5,8,2.5);root.rotation.x=-.6;
 const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=1400;const ctx=canvas.getContext('2d');
 const tex=new THREE.CanvasTexture(canvas);tex.colorSpace=THREE.SRGBColorSpace;tex.anisotropy=4;
 // Printed paper stays matte and shadow-free so the city shadow map can never
 // project building/window bands across the document during the transition.
 const paperMat=new THREE.MeshStandardMaterial({map:tex,roughness:.86,side:THREE.DoubleSide});
 const stackMat=new THREE.MeshStandardMaterial({color:0xd4d3c4,roughness:.8});
 for(let i=3;i>=1;i--){const sheet=new THREE.Mesh(new THREE.BoxGeometry(19.8,27,.05),stackMat);sheet.position.set(i*.09,-i*.07,-i*.06);sheet.rotation.z=-i*.009;root.add(sheet);}
 const page=new THREE.Mesh(new THREE.PlaneGeometry(19.8,27),paperMat);page.receiveShadow=false;page.castShadow=false;root.add(page);
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
 return {root,draw,pencil};
}

export function buildAppraiser(materialLibrary){
 const root=new THREE.Group();root.position.set(30,1,8);root.rotation.y=-.5;
 const mat=(c,metalness=0,cloth=false)=>new THREE.MeshPhysicalMaterial({color:c,roughness:cloth?.7:.55,metalness,sheen:cloth?.2:0,sheenRoughness:.78,envMapIntensity:metalness?.9:.48});const coat=mat(0x997a5c,0,true),shirt=mat(0xe9e4ce,0,true),pants=mat(0x344749,0,true),skin=mat(0xceaf8c),hair=mat(0x35403a),shoe=mat(0x223330),gold=mat(0xa6a188,.6);
 function m(g,ma,x,y,z){const o=new THREE.Mesh(g,ma);o.position.set(x,y,z);o.castShadow=true;root.add(o);return o;}
 function limb(a,b,r,ma){const p=new THREE.Vector3(...a),q=new THREE.Vector3(...b),d=q.clone().sub(p);const o=m(new THREE.CapsuleGeometry(r,Math.max(.05,d.length()-2*r),6,12),ma,...p.clone().add(q).multiplyScalar(.5).toArray());o.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());return o;}
 for(const side of [-1,1]){limb([side*.44,.7,0],[side*.42,3.15,0],.32,pants);m(new THREE.BoxGeometry(.65,.36,1.1),shoe,side*.44,.3,.24);}
 m(new THREE.CylinderGeometry(.8,.68,2.2,18),coat,0,4,0);m(new THREE.BoxGeometry(.37,1.7,.12),shirt,0,4.12,.7);
 const lapel1=m(new THREE.BoxGeometry(.25,1.35,.09),coat,-.24,4.35,.81);lapel1.rotation.z=.17;const lapel2=m(new THREE.BoxGeometry(.25,1.35,.09),coat,.24,4.35,.81);lapel2.rotation.z=-.17;
 m(new THREE.CylinderGeometry(.24,.27,.5,12),skin,0,5.2,0);const head=m(new THREE.SphereGeometry(.63,24,18),skin,0,5.98,.04);head.scale.set(.85,1.15,.86);
 const cap=m(new THREE.SphereGeometry(.65,20,12,0,Math.PI*2,0,Math.PI*.58),hair,0,6.12,-.06);cap.scale.set(.86,1,.86);
 for(const side of [-1,1]){m(new THREE.TorusGeometry(.16,.022,6,16),gold,side*.23,6.05,.52);m(new THREE.SphereGeometry(.035,8,6),hair,side*.23,6.05,.55);}m(new THREE.BoxGeometry(.13,.035,.035),gold,0,6.05,.55);
 limb([-.72,4.7,0],[-1.1,3.7,.55],.24,coat);limb([-1.1,3.7,.55],[-.65,3.8,1.2],.21,coat);limb([.72,4.7,0],[1.05,3.85,.55],.24,coat);limb([1.05,3.85,.55],[.58,4.05,1.2],.2,coat);
 m(new THREE.SphereGeometry(.22,12,8),skin,-.62,3.86,1.2);m(new THREE.SphereGeometry(.22,12,8),skin,.52,4.08,1.25);
 const tablet=m(new THREE.BoxGeometry(1.75,1.22,.1),pants,0,4.12,1.23);tablet.rotation.x=-.4;
 const screen=m(new THREE.PlaneGeometry(1.52,1.02),mat(0x85aaa2),0,4.13,1.3);screen.rotation.x=-.4;
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
