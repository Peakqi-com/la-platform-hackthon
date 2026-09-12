import * as THREE from './three.module.min.js';
import {MaterialLibrary} from './systems/materials.js';

// All scene geometry is original. Distances are illustrative local units.
export function buildCity(materialLibrary) {
 const library=materialLibrary||new MaterialLibrary(),materials=library.materials;
 const root=new THREE.Group(),buildings=new THREE.Group(),buildingShells=new THREE.Group(),buildingDetails=new THREE.Group(),terrain=new THREE.Group(),greenery=new THREE.Group(),peopleGroup=new THREE.Group();
 buildings.add(buildingShells,buildingDetails);root.add(terrain,buildings,greenery,peopleGroup);let seed=1248;
 const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
 const batches=new Map(), boxGeo=new THREE.BoxGeometry(1,1,1), matrix=new THREE.Matrix4(),pos=new THREE.Vector3(),scale=new THREE.Vector3(),quat=new THREE.Quaternion();
 function box(parent,x,y,z,w,h,d,mat,rot=0){const material=materials[mat]||mat,key=parent.uuid+(material.uuid||mat);let batch=batches.get(key);if(!batch){batch={parent,mat:material,items:[]};batches.set(key,batch);}batch.items.push([x,y,z,w,h,d,rot]);}
 function mesh(parent,geo,mat,x,y,z){const m=new THREE.Mesh(geo,materials[mat]||mat);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;}
 function beam(parent,a,b,r,mat){const p=new THREE.Vector3(...a),q=new THREE.Vector3(...b),v=q.clone().sub(p);const m=mesh(parent,new THREE.CylinderGeometry(r,r,v.length(),8),mat,...p.clone().add(q).multiplyScalar(.5).toArray());m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),v.normalize());return m;}
 box(terrain,0,-1.4,0,110,2.6,88,'black');box(terrain,0,-.05,0,110,.3,88,'stone');
 for(const z of [-44,44])box(terrain,0,-.7,z,110,.11,.09,'gold');for(const x of [-55,55])box(terrain,x,-.7,0,.09,.11,88,'gold');
 const waterMaterial=new THREE.ShaderMaterial({uniforms:{uTime:{value:0},uDay:{value:0},uSunX:{value:.25}},vertexShader:`varying vec2 vUv;varying float vWave;uniform float uTime;void main(){vUv=uv;vec3 p=position;float a=sin((uv.y*23.0)+(uTime*.62))*0.075;float b=sin((uv.y*41.0)-(uTime*.9)+(uv.x*6.0))*0.038;p.z=a+b;vWave=a+b;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);}`,fragmentShader:`varying vec2 vUv;varying float vWave;uniform float uTime;uniform float uDay;uniform float uSunX;void main(){float night=smoothstep(.68,1.,uDay);vec3 deep=mix(vec3(.055,.28,.34),vec3(.018,.075,.12),night);vec3 shallow=mix(vec3(.16,.48,.52),vec3(.04,.18,.25),night);float phase=vUv.y*48.-uTime*1.25+sin(vUv.x*14.)*1.35;float flow=.5+.5*sin(phase);float aa=max(fwidth(flow)*1.5,.012);float bands=smoothstep(.66-aa,.94+aa,flow)*(.17+vWave*1.05);float path=exp(-pow((vUv.x-uSunX)*8.,2.))*smoothstep(.03,.34,vUv.y)*(1.-smoothstep(.72,.98,vUv.y));float glitter=.5+.5*sin(vUv.y*96.-uTime*2.2+vUv.x*23.);float gaa=max(fwidth(glitter)*2.,.018);float sparkle=smoothstep(.94-gaa,1.,glitter)*path;vec3 sun=mix(vec3(1.,.63,.30),vec3(.62,.77,1.),night);vec3 c=mix(deep,shallow,.42+vWave*1.1)+bands*vec3(.07,.15,.15)+sun*(path*.23+sparkle*.72);gl_FragColor=vec4(c,.98);}`,transparent:false,side:THREE.DoubleSide});
 const water=mesh(terrain,new THREE.PlaneGeometry(19,88,28,120),waterMaterial,-31,.18,0);water.rotation.x=-Math.PI/2;water.castShadow=false;
 for(const x of [-41.3,-20.7]){box(terrain,x,.4,0,1.4,.7,88,'curb');box(terrain,x+(x<-30?-1.3:1.3),.15,0,1.1,.12,88,'gold');}
 // River promenades and benches.
 for(const x of [-45,-17.5])for(let z=-39;z<=39;z+=6){box(terrain,x,.8,z,1.5,.2,.6,'roof');box(terrain,x-.5,.4,z,.12,.6,.4,'black');box(terrain,x+.5,.4,z,.12,.6,.4,'black');box(terrain,x,.99,z-.3,1.5,.6,.12,'roof');}
 const xs=[-13,8,29,50],zs=[-29,-8,13,34];
 for(const x of xs){box(terrain,x,.14,0,4.7,.1,86,'road');for(let z=-41;z<43;z+=3.4)box(terrain,x,.21,z,.1,.01,1.8,'roadMark');for(const dx of [-2.48,2.48])box(terrain,x+dx,.25,0,.28,.3,86,'curb');}
 for(const z of zs){box(terrain,19,.17,z,68,.1,4.8,'road');for(let x=-12;x<53;x+=3.4)box(terrain,x,.235,z,1.8,.01,.1,'roadMark');for(const dz of [-2.48,2.48])box(terrain,19,.25,z+dz,68,.3,.25,'curb');}
 for(const x of xs)for(const z of zs){for(let i=0;i<6;i++){box(terrain,x-2+i*.8,.25,z+3.25,.43,.025,1.15,'roadMark');box(terrain,x+3.25,.25,z-2+i*.8,1.15,.025,.43,'roadMark');}}
 // Two bridges: a cable bridge and a fine-railed promenade.
 for(const [z,cable]of [[-19,true],[24,false]]){
  box(terrain,-31,1,z,35,.75,5,'concrete');box(terrain,-31,1.42,z,35,.1,4.4,'road');
  for(const dz of [-2.4,2.4]){box(terrain,-31,2,z+dz,35,.12,.12,'light');for(let x=-48;x<-13;x+=1.8)box(terrain,x,1.7,z+dz,.12,.8,.12,'trim');}
  for(let x=-45;x<-15;x+=3)box(terrain,x,1.5,z,1.6,.04,.12,'roadMark');
  for(const x of [-39,-23]){box(terrain,x,-.2,z,.9,3.5,3,'concrete');if(cable){for(const dz of [-2.7,2.7]){box(terrain,x,6.2,z+dz,.65,12,.6,'light');for(const dx of [-8,-5,-2,2,5,8])beam(terrain,[x,11.4,z+dz],[x+dx,1.6,z+dz],.045,'gold');}box(terrain,x,10.5,z,1,.65,6,'light');}}
 }
 function tree(x,z,size=1){box(greenery,x,1.05*size,z,.23*size,1.8*size,.23*size,'trunk');const crown=mesh(greenery,new THREE.SphereGeometry(1,10,7),random()>.5?'leaf':'leaf2',x,2.8*size,z);crown.scale.set(1.05*size,1.25*size,.95*size);}
 for(const x of [-47,-18])for(let z=-40;z<=40;z+=4.1){if(Math.abs(z+19)>4&&Math.abs(z-24)>4)tree(x,z,.85+random()*.2);}
 for(const x of [-9.5,11.5,32.5,53.5])for(let z=-38;z<40;z+=6){if(zs.every(s=>Math.abs(s-z)>4))tree(x,z,.58+random()*.2);}
 // Park in the southwest block: lawn, a circular path, seating and planting.
 box(terrain,-2.5,.25,23.5,15,.4,15,'leaf');
 const park=mesh(terrain,new THREE.RingGeometry(4.9,5.65,64), 'curb',-2.5,.48,23.5);park.rotation.x=-Math.PI/2;
 const pool=mesh(terrain,new THREE.CylinderGeometry(2.1,2.1,.18,40),'river',-2.5,.52,23.5);
 for(let i=0;i<12;i++){const a=i*Math.PI/6;tree(-2.5+6.6*Math.cos(a),23.5+6.6*Math.sin(a),.75);}
 for(let i=0;i<4;i++){const a=i*Math.PI/2;box(terrain,-2.5+4*Math.cos(a),.8,23.5+4*Math.sin(a),1.8,.2,.5,'roof',-a);}
 const parcels=[];
 // Individually varied buildings, with windows, cornices, balconies and rooftop equipment.
 function building(x,z,w,d,h,style=0){
 const bases=['ivory','concrete','glass','brick','terracotta','blue','mustard','teal','plum','sand'];
  const base=bases[style%bases.length],isTower=style===2||style===7,isBrick=style===3||style===4,isColor=style>=5,litRatio=.2+random()*.35;
  box(buildingShells,x,h/2+.5,z,w,h,d,base);
  box(buildingShells,x,.65,z,w+.4,.8,d+.4,isBrick?'sand':'roof');box(buildingDetails,x,h+.62,z,w+.45,.26,d+.45,isColor?'gold':'light');
  box(buildingDetails,x,h+.9,z,w-.4,.4,d-.4,isBrick?'terracotta':'roof');
  const floor=1.35,rows=Math.floor((h-1.1)/floor),cols=Math.max(2,Math.floor(w/.95)),sides=Math.max(2,Math.floor(d/1.15));
  for(let j=1;j<=rows;j++){
   const yy=.6+j*floor;
   for(const side of [-1,1]){
    for(let i=0;i<cols;i++){const xx=x-w/2+(i+.5)*w/cols;box(buildingDetails,xx,yy,z+side*(d/2+.03),w/cols*.58,.83,.05,library.window(random,litRatio));}
    for(let i=0;i<sides;i++){const zz=z-d/2+(i+.5)*d/sides;box(buildingDetails,x+side*(w/2+.03),yy,zz,.05,.83,d/sides*.58,library.window(random,litRatio));}
   }
   if(style===1&&j%2===0){for(const side of [-1,1]){box(buildingDetails,x,yy-.5,z+side*(d/2+.3),w+.25,.13,.75,'light');box(buildingDetails,x,yy-.2,z+side*(d/2+.61),w+.3,.38,.08,'trim');}}
   if(isTower&&j%3===0)box(buildingDetails,x,yy-.5,z,w+.14,.12,d+.14,'trim');
   if(isBrick&&j%2===1)for(const side of [-1,1])box(buildingDetails,x,yy+.5,z+side*(d/2+.1),w+.18,.09,.18,'sand');
   if(isColor&&j%3===1)box(buildingDetails,x,yy-.48,z+d/2+.24,w*.82,.1,.48,'gold');
  }
  if(isTower){for(let i=0;i<=cols;i++)for(const side of [-1,1])box(buildingDetails,x-w/2+i*w/cols,h/2+.5,z+side*(d/2+.1),.08,h,.12,'light');if(h>17){box(buildingShells,x,h*.78,z,w*.78,h*.45,d*.78,base);box(buildingDetails,x,h+1.35,z,w*.8,.17,d*.8,'gold');}}
  else {box(buildingDetails,x-w*.17,h+1.5,z+.3,w*.4,1.2,d*.35,'concrete');box(buildingDetails,x+w*.27,h+1.25,z-d*.25,.65,.6,.95,'trim');if(h<10){for(let i=0;i<3;i++)box(buildingDetails,x-w*.3+i*.7,h+1.05,z+d*.2,.52,.11,.85,'darkGlass',.08);}}
  if(style===6){const crown=mesh(buildingDetails,new THREE.CylinderGeometry(w*.32,w*.44,1.1,8),'mustard',x,h+1.55,z);crown.rotation.y=Math.PI/8;box(buildingDetails,x,h+3.1,z,.08,2.7,.08,'gold');}
  if(style===8){for(const dx of [-w*.32,w*.32])box(buildingDetails,x+dx,h+1.45,z,.18,1.45,d*.72,'plum');}
  if(style===5){box(buildingDetails,x+w*.13,h+1.65,z-d*.08,w*.58,1.55,d*.62,'blue');box(buildingDetails,x-w*.18,h+2.55,z+d*.2,w*.26,.35,d*.22,'gold');}
  if(style===9){const roof=mesh(buildingDetails,new THREE.ConeGeometry(Math.min(w,d)*.62,1.8,4),'slate',x,h+1.75,z);roof.rotation.y=Math.PI/4;for(const dx of [-w*.4,w*.4])box(buildingDetails,x+dx,h*.55,z+d*.51,.11,h*.78,.11,'sand');}
  if(style===3){const tank=mesh(buildingDetails,new THREE.CylinderGeometry(.52,.52,.85,12),'concrete',x+w*.2,h+1.65,z-d*.18);for(const dx of [-.34,.34])box(buildingDetails,x+w*.2+dx,h+1.05,z-d*.18,.05,.55,.05,'black');}
  if(h>17){box(buildingDetails,x,h+1.8,z,1.6,1.7,1.6,'roof');box(buildingDetails,x,h+4,z,.09,3.2,.09,'gold');}
  // Shopfront glazing and canopy on the ground floor.
  if(!isTower){box(buildingDetails,x,1.15,z+d/2+.04,w*.75,1.3,.06,'darkGlass');box(buildingDetails,x,1.9,z+d/2+.45,w*.92,.16,.9,isBrick||style===1?'gold':'trim');}
 }
 for(let bx=0;bx<3;bx++)for(let bz=0;bz<3;bz++){
  const cx=-2.5+21*bx,cz=-18.5+21*bz;
  parcels.push({x:cx,z:cz,w:15.8,d:15.8,id:`0${120+bx*3+bz}`,selected:bx===1&&bz===1});
  if(bx===0&&bz===2)continue;
  box(terrain,cx,.25,cz,16,.4,16,'curb');
  if(bx===2&&(bz===0||bz===2))continue;
  for(let row=0;row<2;row++)for(let col=0;col<3;col++){
   // Keep a continuous pedestrian clearance strip around every block.
   const x=cx-4.75+col*4.75+(random()-.5)*.22,z=cz-3.75+row*7.5;
   const w=3.5+random()*.9,d=5.2+random()*1.25,style=bx===1&&bz===0?(col===1?7:2):Math.floor(random()*10);
   let h=4.5+random()*8.5;if(bx===1&&bz===0)h=12+random()*8;if(bz===2)h*=.8;
   building(x,z,w,d,h,style);
  }
 }
 // Far-edge street and west-bank low houses create a legible skyline.
 for(let i=0;i<12;i++)building(-9+i*5.2,-37,3.3+random()*.6,4,4+random()*7,i%10);
 for(let i=0;i<9;i++)building(-51,-36+i*8,3.7,4.7,3+random()*3,(i+3)%10);
 // Distinct civic and skyline silhouettes make the districts recognizable at a glance.
 const roundTower=mesh(buildingShells,new THREE.CylinderGeometry(3.2,4.1,18,24),'teal',39.5,9.5,-18.5);for(let y=3;y<18;y+=2.2){const ring=mesh(buildingDetails,new THREE.TorusGeometry(3.4-y*.018,.1,6,24),'gold',39.5,y+.5,-18.5);ring.rotation.x=Math.PI/2;}const crown=mesh(buildingDetails,new THREE.ConeGeometry(3.5,2.4,24),'terracotta',39.5,19.7,-18.5);crown.rotation.y=Math.PI/8;
 for(let i=0;i<4;i++){const hallX=34+i*3.6;box(buildingShells,hallX,3.3,23.5,3.3,5.5,8,i%2?'brick':'sand');const saw=mesh(buildingDetails,new THREE.ConeGeometry(2.25,2.1,4),'slate',hallX,7,23.5);saw.rotation.y=Math.PI/4;}
 box(buildingShells,-51,4.1,15,5.4,7.2,8,'mustard');for(let y=3;y<8;y+=1.5)box(buildingDetails,-51,y,19.06,5.7,.11,.1,'gold');const clock=mesh(buildingDetails,new THREE.CylinderGeometry(1.25,1.45,5,12),'brick',-51,10.2,15);const clockFace=mesh(buildingDetails,new THREE.CircleGeometry(.72,24),new THREE.MeshBasicMaterial({color:0xf0e3c5}),-51,10.55,16.28);clockFace.rotation.y=0;box(buildingDetails,-51,13.4,15,.12,2.1,.12,'gold');
 const cars=[],carLights=[];
 function roundedLoop(x1,z1,x2,z2,y=.49,r=1.3){const path=new THREE.CurvePath(),v=(x,z)=>new THREE.Vector3(x,y,z);path.add(new THREE.LineCurve3(v(x1+r,z1),v(x2-r,z1)));path.add(new THREE.QuadraticBezierCurve3(v(x2-r,z1),v(x2,z1),v(x2,z1+r)));path.add(new THREE.LineCurve3(v(x2,z1+r),v(x2,z2-r)));path.add(new THREE.QuadraticBezierCurve3(v(x2,z2-r),v(x2,z2),v(x2-r,z2)));path.add(new THREE.LineCurve3(v(x2-r,z2),v(x1+r,z2)));path.add(new THREE.QuadraticBezierCurve3(v(x1+r,z2),v(x1,z2),v(x1,z2-r)));path.add(new THREE.LineCurve3(v(x1,z2-r),v(x1,z1+r)));path.add(new THREE.QuadraticBezierCurve3(v(x1,z1+r),v(x1,z1),v(x1+r,z1)));path.autoClose=true;return path;}
 const routes=[roundedLoop(-13,-29,50,34),roundedLoop(8,-29,29,13),roundedLoop(29,-8,50,34),roundedLoop(-13,-8,8,13),roundedLoop(8,13,50,34)];
 const vehicleColors=['red','carBlue','mustard','carGreen','ivory','terracotta','teal','plum','sand'];
 function vehicle(type,color){
  const g=new THREE.Group(),body=materials[color];
  if(type===0){mesh(g,new THREE.BoxGeometry(1.7,.46,.82),body,0,.3,0);mesh(g,new THREE.BoxGeometry(.95,.36,.7),'darkGlass',-.08,.68,0);}
  if(type===1){mesh(g,new THREE.BoxGeometry(2.55,.7,.92),body,0,.46,0);mesh(g,new THREE.BoxGeometry(1.7,.48,.8),'darkGlass',.16,.95,0);box(g,-.76,.73,0,.08,.42,.94,'light');}
  if(type===2){mesh(g,new THREE.BoxGeometry(2.15,.65,.9),body,0,.43,0);mesh(g,new THREE.BoxGeometry(.7,.46,.79),'darkGlass',.48,.92,0);box(g,-.72,.9,0,.55,.22,.72,'light');}
  if(type===3){mesh(g,new THREE.BoxGeometry(3.25,.82,1.02),body,0,.55,0);mesh(g,new THREE.BoxGeometry(2.65,.63,.9),'darkGlass',.06,1.2,0);for(let k=-1;k<=1;k++)box(g,k*.78,1.21,.48,.05,.45,.05,'light');}
  if(type===4){mesh(g,new THREE.BoxGeometry(.85,.23,.3),body,0,.46,0);mesh(g,new THREE.BoxGeometry(.13,.75,.13),'black',-.15,.86,0);mesh(g,new THREE.SphereGeometry(.16,8,6),'gold',-.15,1.25,0);}
  const len=[1.7,2.55,2.15,3.25,.85][type],wheelXs=type===4?[-.27,.27]:[-len*.32,len*.32];
  for(const xx of wheelXs)for(const zz of [-.43,.43]){if(type===4&&zz<0)continue;const wheel=mesh(g,new THREE.CylinderGeometry(type===4?.15:.2,type===4?.15:.2,.12,10),'black',xx,type===4?.27:.18,zz*(type===4?.55:1));wheel.rotation.x=Math.PI/2;}
  const headMat=new THREE.MeshBasicMaterial({color:0xffe3ae,transparent:true,opacity:.1,toneMapped:false}),tailMat=new THREE.MeshBasicMaterial({color:0xef5b48,transparent:true,opacity:.12,toneMapped:false});
  for(const z of [-.27,.27]){mesh(g,new THREE.SphereGeometry(.055,7,5),headMat,len*.5+.015,.47,z);mesh(g,new THREE.SphereGeometry(.05,7,5),tailMat,-len*.5-.015,.44,z);}carLights.push({mat:headMat,base:.1,gain:.85},{mat:tailMat,base:.12,gain:.74});
  if(type!==4){const lightGeo=new THREE.BufferGeometry();lightGeo.setAttribute('position',new THREE.Float32BufferAttribute([len*.45,-.275,-.28,len*.45,-.275,.28,len*.45+4.2,-.275,1.05,len*.45+4.2,-.275,-1.05],3));lightGeo.setIndex([0,1,2,0,2,3]);const footprintMat=new THREE.MeshBasicMaterial({color:0xffd49a,transparent:true,opacity:0,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false,side:THREE.DoubleSide});g.add(new THREE.Mesh(lightGeo,footprintMat));carLights.push({mat:footprintMat,base:0,gain:.095});}
  return g;
 }
 for(let i=0;i<27;i++){
  const type=i%9===0?3:i%7===0?4:i%5===0?2:i%4===0?1:0,g=vehicle(type,vehicleColors[i%vehicleColors.length]);terrain.add(g);
  cars.push({g,route:routes[i%routes.length],offset:random(),speed:(.008+random()*.008)*(i%3===0?-1:1),lane:(i%2?-.72:.72)});
 }
 // 百工百業：不同職業、服裝、工具與步態，沿街廓人行道移動。
 const workers=[],professions=['營造工程','護理照護','餐飲主廚','物流配送','測量人員','商務上班','環境清潔','花藝工作','消防救護','影像攝影','咖啡職人','藝術創作','園藝養護','機械維修','學生研究','市場攤商','道路工程','郵務服務'];
 const walkRoutes=[roundedLoop(-10,-26,5,-11,.29,.8),roundedLoop(11,-26,26,-11,.29,.8),roundedLoop(32,-26,47,-11,.29,.8),roundedLoop(-10,-5,5,10,.29,.8),roundedLoop(11,-5,26,10,.29,.8),roundedLoop(32,-5,47,10,.29,.8),roundedLoop(11,16,26,31,.29,.8),roundedLoop(32,16,47,31,.29,.8),roundedLoop(-47,-37,-45,37,.29,.45)];
 const skinTones=[0xd6ad89,0xb77f5e,0xe1bd9a,0x956247],hairTones=[0x302b27,0x564335,0x1d2424,0x75604b],uniforms=['gold','light','brick','carBlue','terracotta','slate','teal','plum','red','mustard','sand','carGreen'];
 function citizen(kind,index){
  const g=new THREE.Group(),skin=new THREE.MeshStandardMaterial({color:skinTones[index%skinTones.length],roughness:.8}),hair=new THREE.MeshStandardMaterial({color:hairTones[(index*3)%hairTones.length],roughness:.86}),cloth=materials[uniforms[(kind+index)%uniforms.length]],dark=materials.black;
  const torso=mesh(g,new THREE.BoxGeometry(.48,.72,.3),cloth,0,1.16,0);torso.rotation.z=(index%3-1)*.025;
  const head=mesh(g,new THREE.SphereGeometry(.22,10,8),skin,0,1.83,0);head.scale.y=1.08;
  const hairCap=mesh(g,new THREE.SphereGeometry(.225,10,6,0,Math.PI*2,0,Math.PI*.54),hair,0,1.94,-.015);hairCap.scale.y=.65;
  const legs=[],arms=[];for(const side of [-1,1]){const leg=new THREE.Group();leg.position.set(side*.14,.8,0);const lm=mesh(leg,new THREE.CapsuleGeometry(.075,.43,4,7),dark,0,-.27,0);const foot=mesh(leg,new THREE.BoxGeometry(.17,.1,.29),dark,0,-.57,.07);g.add(leg);legs.push(leg);const arm=new THREE.Group();arm.position.set(side*.31,1.45,0);const am=mesh(arm,new THREE.CapsuleGeometry(.055,.39,4,7),kind===1||kind===2?materials.light:cloth,0,-.23,0);arm.rotation.z=side*.08;g.add(arm);arms.push(arm);}
  // Profession-specific silhouettes remain legible even from the aerial camera.
  if([0,4,8,16].includes(kind)){const helmet=mesh(g,new THREE.CylinderGeometry(.25,.25,.12,12),kind===8?materials.red:materials.mustard,0,2.06,0);box(g,0,2.04,.15,.55,.05,.18,kind===8?'red':'mustard');}
  if(kind===1){box(g,0,1.18,.18,.34,.5,.05,'light');box(g,0,1.28,.22,.22,.055,.04,'red');box(g,0,1.28,.22,.045,.22,.04,'red');}
  if(kind===2){for(let i=0;i<3;i++)mesh(g,new THREE.SphereGeometry(.17-i*.025,9,6),'light',0,2.05+i*.13,0);box(g,0,1.3,.19,.34,.55,.04,'white');}
  if([3,14,17].includes(kind))box(g,-.02,1.28,-.25,.54,.65,.2,kind===17?'mustard':'slate');
  if(kind===4){const pole=mesh(g,new THREE.CylinderGeometry(.025,.025,1.25,6),'gold',.44,1.13,.08);pole.rotation.z=-.08;mesh(g,new THREE.OctahedronGeometry(.12),'red',.44,1.79,.08);}
  if(kind===5)box(g,.39,1.05,.05,.38,.48,.12,'sand');
  if(kind===6){const broom=mesh(g,new THREE.CylinderGeometry(.025,.025,1.35,6),'trunk',.43,1.02,.05);broom.rotation.z=-.22;box(g,.56,.35,.05,.32,.34,.12,'mustard');}
  if(kind===7){for(let i=0;i<5;i++)mesh(g,new THREE.SphereGeometry(.09,8,6),i%2?'red':'mustard',.31+(i%2)*.12,1.13+(i%3)*.12,.22);}
  if(kind===8)box(g,.38,1.08,.08,.22,.48,.12,'red');
  if(kind===9){box(g,0,1.45,.24,.3,.22,.18,'black');const lens=mesh(g,new THREE.CylinderGeometry(.09,.09,.12,10),'glass',0,1.45,.38);lens.rotation.x=Math.PI/2;}
  if(kind===10){box(g,0,1.28,.19,.34,.55,.04,'black');mesh(g,new THREE.CylinderGeometry(.08,.07,.18,8),'white',.38,1.15,.16);}
  if(kind===11){const palette=mesh(g,new THREE.CylinderGeometry(.2,.2,.035,12),'sand',.38,1.12,.15);palette.rotation.x=Math.PI/2;}
  if(kind===12){const brim=mesh(g,new THREE.CylinderGeometry(.34,.34,.04,14),'sand',0,2.02,0);mesh(g,new THREE.ConeGeometry(.22,.24,14),'sand',0,2.16,0);}
  if(kind===13){box(g,.37,1.05,.06,.18,.62,.1,'slate');mesh(g,new THREE.TorusGeometry(.11,.035,6,10,Math.PI*1.5),'gold',.42,.72,.06);}
  if(kind===14)box(g,.34,1.2,.08,.26,.34,.1,'blue');
  if(kind===15){box(g,0,1.25,.19,.34,.53,.04,'sand');box(g,.42,.83,.03,.36,.22,.3,'mustard');}
  if(kind===16){for(const side of [-1,1])box(g,side*.14,1.28,.17,.08,.55,.03,'light');}
  if(kind===17)box(g,.34,1.2,.12,.34,.42,.08,'mustard');
  g.scale.setScalar(.92+random()*.18);return {g,torso,legs,arms,profession:professions[kind]};
 }
 for(let i=0;i<45;i++){const person=citizen(i%professions.length,i);peopleGroup.add(person.g);workers.push({...person,route:walkRoutes[i%walkRoutes.length],offset:random(),speed:(.0045+random()*.003)*(i%4===0?-1:1),phase:random()*Math.PI*2,lane:(i%2?-.16:.16)});}
 // Legible architectural street lamps. Emissive fixtures stay visible at city scale;
 // only the nearest lamps receive pooled realtime lights at night.
 const streetLamps=[];
 function streetLamp(x,z,rotation=0){const dx=Math.cos(rotation),dz=Math.sin(rotation),headX=x+dx*.48,headZ=z+dz*.48;box(terrain,x,1.55,z,.14,2.7,.14,'black');box(terrain,x+dx*.24,2.86,z+dz*.24,.62,.1,.14,'black',-rotation);box(terrain,headX,2.7,headZ,.42,.22,.34,'lamp',-rotation);box(terrain,headX,2.57,headZ,.24,.055,.22,'white',-rotation);streetLamps.push({x:headX,z:headZ,y:2.58});}
 for(const x of xs)for(let z=-38;z<=37;z+=12.5)streetLamp(x+3.12,z,Math.PI);
 for(const z of zs)for(let x=-8;x<=48;x+=14)streetLamp(x,z+3.12,-Math.PI/2);
 for(const b of batches.values()){
  const im=new THREE.InstancedMesh(boxGeo,b.mat,b.items.length);im.name=b.mat.name||'instanced-pbr';
  // Large coplanar terrain and tiny decals must receive, never cast, sun shadows.
  // Casting them produced the screen-wide parallel bands visible at shallow angles.
  const terrainReceiver=b.parent===terrain&&[materials.black,materials.stone,materials.road,materials.roadMark,materials.curb,materials.leaf].includes(b.mat),fineFacadeDetail=b.parent===buildingDetails;im.castShadow=!terrainReceiver&&!fineFacadeDetail;im.receiveShadow=true;
  b.items.forEach(([x,y,z,w,h,d,r],i)=>{pos.set(x,y,z);scale.set(w,h,d);quat.setFromAxisAngle(new THREE.Vector3(0,1,0),r);matrix.compose(pos,quat,scale);im.setMatrixAt(i,matrix);});im.instanceMatrix.needsUpdate=true;b.parent.add(im);
 }
 function animate(time,night=0){
  waterMaterial.uniforms.uTime.value=time;waterMaterial.uniforms.uDay.value=night;
  for(const car of cars){const u=((car.offset+time*car.speed)%1+1)%1,p=car.route.getPointAt(u),tan=car.route.getTangentAt(u).normalize(),side=new THREE.Vector3(-tan.z,0,tan.x);car.g.position.copy(p).addScaledVector(side,car.lane);car.g.rotation.y=-Math.atan2(tan.z,tan.x);}
  for(const light of carLights)light.mat.opacity=light.base+night*light.gain;
 }
 return {root,buildings,buildingShells,buildingDetails,terrain,greenery,peopleGroup,parcels,cars,workers,professions,materials,materialLibrary:library,streetLamps,waterMaterial,animate};
}

export function buildSurvey(parcels){
 const root=new THREE.Group(),lines=[],nodes=[],fills=[],labels=[];
 for(const p of parcels){
  const x=p.x,z=p.z,w=p.w/2,d=p.d/2,verts=[new THREE.Vector3(x-w,.62,z-d),new THREE.Vector3(x+w,.62,z-d),new THREE.Vector3(x+w,.62,z+d),new THREE.Vector3(x-w,.62,z+d),new THREE.Vector3(x-w,.62,z-d)];
  // Subdivide for continuous drawing as the user scrolls.
  const pts=[];for(let i=0;i<4;i++)for(let j=0;j<30;j++)pts.push(verts[i].clone().lerp(verts[i+1],j/30));pts.push(verts[0]);
  const geo=new THREE.BufferGeometry().setFromPoints(pts);geo.setDrawRange(0,0);const lineMat=new THREE.LineBasicMaterial({color:p.selected?0xff7a18:0x9dcdb9,transparent:true,opacity:0,depthWrite:false});const l=new THREE.Line(geo,lineMat);l.renderOrder=800;l.userData.baseOpacity=p.selected?.32:.7;root.add(l);lines.push(l);
  const fill=new THREE.Mesh(new THREE.PlaneGeometry(p.w,p.d),new THREE.MeshBasicMaterial({color:p.selected?0xff7a18:0x7bbaa9,transparent:true,opacity:0,depthWrite:false,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1}));fill.rotation.x=-Math.PI/2;fill.position.set(x,.655,z);fill.userData.baseOpacity=p.selected?.04:.055;root.add(fill);fills.push(fill);
  for(let i=0;i<4;i++){const mat=new THREE.MeshBasicMaterial({color:p.selected?0xff9d4e:0xabd0ba,transparent:true,opacity:0,depthWrite:false});const n=new THREE.Mesh(new THREE.SphereGeometry(p.selected?.16:.09,10,6),mat);n.position.copy(verts[i]);n.position.y=.69;n.renderOrder=801;root.add(n);nodes.push(n);}
 }
 return {root,lines,nodes,fills,labels};
}

export function buildWind(){
 const root=new THREE.Group(),curves=[],dots=[];
 for(let i=0;i<5;i++){
  const points=[];for(let j=0;j<=12;j++){const t=j/12;points.push(new THREE.Vector3(-58+t*117,6+Math.sin(t*Math.PI*2+i*.45)*3+i*1.2,-15+Math.sin(t*Math.PI*2-i*.25)*17+i*2));}
  const curve=new THREE.CatmullRomCurve3(points),geo=new THREE.TubeGeometry(curve,160,.018+(i===2?.022:0),3,false);
  const line=new THREE.Mesh(geo,new THREE.MeshBasicMaterial({color:i===2?0xf3c191:0xa9d4d0,transparent:true,opacity:i===2?.42:.16,depthWrite:false}));root.add(line);curves.push(curve);
  const dot=new THREE.Mesh(new THREE.SphereGeometry(i===2?.1:.065,8,6),new THREE.MeshBasicMaterial({color:0xffdcb0}));root.add(dot);dots.push(dot);
 }
 return {root,curves,dots};
}
