import * as THREE from '../three.module.min.js';

const clamp=THREE.MathUtils.clamp,smooth=(a,b,v)=>{const t=clamp((v-a)/(b-a),0,1);return t*t*(3-2*t);};
let seed=9347;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};

function addSkinnedTorso(worker,color){
 const geometry=new THREE.CylinderGeometry(.23,.27,.72,8,5);const pos=geometry.attributes.position,skinIndices=[],skinWeights=[];
 for(let i=0;i<pos.count;i++){const t=clamp((pos.getY(i)+.36)/.72,0,1);skinIndices.push(0,1,0,0);skinWeights.push(1-t,t,0,0);}
 geometry.setAttribute('skinIndex',new THREE.Uint16BufferAttribute(skinIndices,4));geometry.setAttribute('skinWeight',new THREE.Float32BufferAttribute(skinWeights,4));
 const hip=new THREE.Bone(),chest=new THREE.Bone();hip.position.y=-.36;chest.position.y=.72;hip.add(chest);
 const material=new THREE.MeshPhysicalMaterial({color,roughness:.72,metalness:0,sheen:.18,sheenRoughness:.78,envMapIntensity:.45});const mesh=new THREE.SkinnedMesh(geometry,material);mesh.position.y=1.16;mesh.add(hip);mesh.bind(new THREE.Skeleton([hip,chest]));mesh.castShadow=true;worker.g.add(mesh);if(worker.torso)worker.torso.visible=false;worker.skinRig={mesh,chest};
}

function addBike(worker,materials){
 const bike=new THREE.Group();for(const x of [-.35,.35]){const wheel=new THREE.Mesh(new THREE.TorusGeometry(.27,.035,6,16),materials.black);wheel.rotation.y=Math.PI/2;wheel.position.set(x,.31,0);bike.add(wheel);}const frame=new THREE.Mesh(new THREE.TorusGeometry(.24,.025,5,3),materials.red);frame.rotation.set(Math.PI/2,0,Math.PI/2);frame.position.y=.43;bike.add(frame);bike.position.set(0,-.05,-.18);worker.g.add(bike);worker.bike=bike;
}
function addDog(worker,materials){
 const dog=new THREE.Group(),body=new THREE.Mesh(new THREE.CapsuleGeometry(.13,.34,3,6),materials.trunk);body.rotation.z=Math.PI/2;body.position.y=.25;dog.add(body);const head=new THREE.Mesh(new THREE.SphereGeometry(.16,7,5),materials.sand);head.position.set(.28,.35,0);dog.add(head);for(const x of [-.2,.2])for(const z of [-.09,.09]){const leg=new THREE.Mesh(new THREE.CylinderGeometry(.025,.025,.22,5),materials.trunk);leg.position.set(x,.11,z);dog.add(leg);}dog.position.set(.65,0,.45);worker.g.add(dog);const leashGeo=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(.28,1.05,.08),new THREE.Vector3(.65,.42,.45)]);dog.add(new THREE.Line(leashGeo,new THREE.LineBasicMaterial({color:0x4a392e,transparent:true,opacity:.7})));worker.dog=dog;
}

function addImpostor(worker){
 const width=16,height=32,data=new Uint8Array(width*height*4),cloth=worker.torso?.material?.color||new THREE.Color(0x6f8178),rgb=[Math.round(cloth.r*255),Math.round(cloth.g*255),Math.round(cloth.b*255)];
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){const nx=(x-width/2)/(width/2),ny=y/height,head=(nx*nx+Math.pow((ny-.18)*2.2,2))<.11,body=ny>.28&&ny<.7&&Math.abs(nx)<(.42-(ny-.28)*.22),legs=ny>=.7&&ny<.98&&(Math.abs(nx-.16)<.11||Math.abs(nx+.16)<.11),i=(y*width+x)*4;if(head){data[i]=205;data[i+1]=166;data[i+2]=132;data[i+3]=255;}else if(body||legs){data[i]=rgb[0];data[i+1]=rgb[1];data[i+2]=rgb[2];data[i+3]=255;}}
 const texture=new THREE.DataTexture(data,width,height,THREE.RGBAFormat);texture.colorSpace=THREE.SRGBColorSpace;texture.magFilter=THREE.LinearFilter;texture.needsUpdate=true;const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthWrite:false}));sprite.position.y=.95;sprite.scale.set(.75,1.9,1);worker.g.children.forEach(child=>child.visible=false);worker.g.add(sprite);worker.impostor=sprite;
}

export class CrowdSystem{
 constructor(city,materials,quality){
  this.city=city;this.workers=city.workers;this.quality=quality;this.frame=0;this.behaviors=['walking','dogWalking','checkingPhone','walking','dogWalking','coupleWalking','coupleWalking','walking','dogWalking','cycling','dogWalking','crossingRoad'];
  this.crossings=[new THREE.LineCurve3(new THREE.Vector3(5.05,.29,16.25),new THREE.Vector3(10.95,.29,16.25)),new THREE.LineCurve3(new THREE.Vector3(32.25,.29,-10.95),new THREE.Vector3(32.25,.29,-5.05))];
  this.workers.forEach((worker,i)=>{
   worker.behavior=this.behaviors[i%this.behaviors.length];worker.mps=.8+random();worker.baseSpeed=worker.mps/Math.max(1,worker.route.getLength());worker.speed=(i%4===0?-1:1)*worker.baseSpeed;worker.updateModulo=i<12?1:i<35?quality.settings.midUpdate:4;worker.lod=i<12?'near':i<35?'medium':'far';worker.fixed=random();worker.worldPosition=new THREE.Vector3();worker.shadowState=false;
   if(worker.lod==='near')addSkinnedTorso(worker,worker.torso?.material?.color||0x8d765e);
   if(worker.behavior==='cycling')addBike(worker,materials.materials);if(worker.behavior==='dogWalking')addDog(worker,materials.materials);
   if(worker.behavior==='crossingRoad'){worker.crossingIndex=(i>>1)%this.crossings.length;worker.crossing=this.crossings[worker.crossingIndex];worker.crossingDirection=i%2;}if(worker.lod==='far')addImpostor(worker);
   const previous=this.workers[i-1];if(previous&&worker.behavior===previous.behavior&&['talking','coupleWalking'].includes(worker.behavior)){worker.route=previous.route;worker.offset=previous.offset+(worker.behavior==='coupleWalking'?.008:0);worker.fixed=previous.fixed;}
   const initialCurve=worker.crossing||worker.route,initial=initialCurve.getPointAt(clamp(worker.offset,0,1));worker.g.position.copy(initial);
   worker.meshes=[];worker.g.traverse(object=>{if(object.isMesh&&!object.isSprite)worker.meshes.push(object);});
  });
 }
 update(elapsed,dt,camera,state,reduced=false){
  this.frame++;const limit=Math.max(6,Math.round(this.quality.settings.npcLimit*state.npcDensity)),ranked=this.workers.map((w,i)=>({i,d:w.g.getWorldPosition(w.worldPosition).distanceToSquared(camera.position)})).sort((a,b)=>a.d-b.d),visible=new Set(ranked.slice(0,limit).map(v=>v.i)),rankByIndex=new Map(ranked.map((v,rank)=>[v.i,rank]));
  this.workers.forEach((w,i)=>{
   w.g.visible=visible.has(i);if(!w.g.visible)return;const near=rankByIndex.get(i)<this.quality.settings.nearNpc;if(near!==w.shadowState){w.shadowState=near;w.meshes.forEach(mesh=>mesh.castShadow=near);}
   if(!reduced&&this.frame%Math.max(1,w.updateModulo)!==0)return;let u=((w.offset+elapsed*w.speed)%1+1)%1,p,tan,moving=!['standing','talking','waiting','sitting'].includes(w.behavior);
   if(w.behavior==='crossingRoad'){
    // One shared pedestrian signal per crosswalk: wait at the curb, cross only
    // during the eight-second walk phase, then remain safely at the far curb.
    const cycle=14,clock=elapsed+w.crossingIndex*2.1,cycleNumber=Math.floor(clock/cycle),signal=clock-cycleNumber*cycle,walkStart=1.5,travel=clamp(w.crossing.getLength()/w.mps,3.3,7.4),walk=clamp((signal-walkStart)/travel,0,1),forward=(cycleNumber+w.crossingDirection)%2===0,t=forward?walk:1-walk;
    p=w.crossing.getPointAt(t);tan=w.crossing.getTangentAt(t).normalize().multiplyScalar(forward?1:-1);moving=signal>=walkStart&&signal<walkStart+travel;
   }else{p=w.route.getPointAt(u);tan=w.route.getTangentAt(u).normalize();}
   if(!moving&&w.behavior!=='crossingRoad'){p=w.route.getPointAt(w.fixed);tan=w.route.getTangentAt(w.fixed).normalize();}const side=new THREE.Vector3(-tan.z,0,tan.x);
   const lane=w.lane+(w.behavior==='coupleWalking'?(i%2?-.24:.24):0)+(w.behavior==='talking'?(i%2?-.34:.34):0);w.g.position.copy(p).addScaledVector(side,lane);
   // Citizens are authored facing local +Z. Align that axis with the path tangent;
   // the previous +X assumption made every figure appear to slide sideways.
   w.g.rotation.y=Math.atan2(tan.x,tan.z);
   const pace=w.behavior==='cycling'?7.4:4.25*w.mps,amplitude=moving?(w.behavior==='cycling'?.12:THREE.MathUtils.lerp(.31,.46,clamp((w.mps-.8),0,1))):0,step=Math.sin(elapsed*pace+w.phase)*amplitude;
   // 站定的人不能是雕像。standing / talking / waiting / sitting 佔了行為清單的五分之二，
   // 原本沒位移就 amplitude=0，四肢與身體完全凍住，看起來像畫面當掉。
   // 沒走路時改給重心轉移、呼吸起伏與緩慢環顧，位置仍然固定，但看得出還活著。
   const idleT=elapsed*.9+w.phase,
         idleSway=moving?0:Math.sin(idleT*.57)*.075+Math.sin(idleT*.21)*.042,
         idleBreath=moving?0:Math.sin(idleT*1.22)*.013+Math.abs(Math.sin(idleT*.57))*.008;
   w.legs?.forEach((leg,j)=>leg.rotation.x=moving?(j?-step:step):(j?-idleSway*.55:idleSway*.55));
   w.arms?.forEach((arm,j)=>{if(moving){arm.rotation.x=j?step*.65:-step*.65;}else{arm.rotation.x=(j?1:-1)*idleSway*.45;arm.rotation.z=(j?-1:1)*(.07+Math.abs(idleSway)*.85);}});
   w.g.position.y=p.y+(moving?Math.abs(Math.sin(elapsed*pace+w.phase))*.023:idleBreath);
   if(!moving)w.g.rotation.y+=Math.sin(idleT*.26+w.fixed*6.3)*.22;
   if(w.behavior==='checkingPhone'&&w.arms){w.arms[0].rotation.x=-1.05;w.arms[1].rotation.x=-.82;}
   if(w.behavior==='talking'){
    w.g.rotation.y+=(i%2?1:-1)*1.18;
    const gesture=Math.sin(elapsed*1.55+w.phase),beat=Math.sin(elapsed*2.4+w.phase*1.7);
    if(w.arms){w.arms[0].rotation.z=.42+gesture*.32;w.arms[0].rotation.x=-.16+beat*.24;w.arms[1].rotation.x=-.12+gesture*.16;}
    w.g.position.y+=Math.abs(Math.sin(elapsed*1.15+w.phase))*.011;   // 說話時的輕微點頭
   }
   if(w.behavior==='waiting'&&w.arms){const check=Math.max(0,Math.sin(elapsed*.34+w.phase*2.1)-.74)*3.6;w.arms[0].rotation.z=.22;w.arms[0].rotation.x=-check*1.2;}
   if(w.behavior==='sitting'){w.g.position.y-=.48;w.legs?.forEach(leg=>leg.rotation.x=-1.25);}
   if(w.behavior==='cycling'){w.g.position.y+=.34;w.legs?.forEach((leg,j)=>leg.rotation.x=Math.sin(elapsed*pace+w.phase+j*Math.PI)*.7);}
   if(w.dog)w.dog.position.y=.02+Math.abs(Math.sin(elapsed*pace*1.25+w.phase))*.025;
   if(w.skinRig)w.skinRig.chest.rotation.z=Math.sin(elapsed*pace+w.phase)*.035;
  });
 }
}

function birdShape(material,near=false){
 const root=new THREE.Group(),body=new THREE.Mesh(new THREE.CapsuleGeometry(near?.13:.07,near?.42:.23,3,6),material);body.rotation.z=Math.PI/2;root.add(body);const wings=[];
 for(const side of [-1,1]){const wing=new THREE.Mesh(new THREE.BufferGeometry(),material);wing.geometry.setAttribute('position',new THREE.Float32BufferAttribute([0,0,0,side*(near?.72:.38),.02,-.08,side*(near?.16:.09),.03,.24],3));wing.geometry.setIndex([0,1,2]);wing.geometry.computeVertexNormals();root.add(wing);wings.push(wing);}return {root,wings};
}

export class BirdSystem{
 constructor(scene,quality){
  this.quality=quality;this.root=new THREE.Group();this.root.name='BirdSystem';scene.add(this.root);this.near=[];this.mid=[];
  const nearMat=new THREE.MeshStandardMaterial({color:0x32484b,roughness:.82,side:THREE.DoubleSide}),midMat=new THREE.MeshBasicMaterial({color:0x23383b,side:THREE.DoubleSide,transparent:true,opacity:.7});
  for(let i=0;i<7;i++)this.makeBird(i,true,nearMat,this.near);for(let i=0;i<20;i++)this.makeBird(i+20,false,midMat,this.mid);
  const count=44,data=new Float32Array(count*3);this.far=new THREE.Points(new THREE.BufferGeometry(),new THREE.PointsMaterial({color:0x1b2e34,size:.72,transparent:true,opacity:.5,depthWrite:false}));this.far.geometry.setAttribute('position',new THREE.BufferAttribute(data,3));this.farData=data;this.root.add(this.far);
 }
 makeBird(index,near,material,list){
  const bird=birdShape(material,near),z=-52+random()*104,y=(near?18:35)+random()*(near?18:35),points=[new THREE.Vector3(-105,y,z),new THREE.Vector3(-38,y+random()*8,z+8),new THREE.Vector3(30,y-4+random()*9,z-6),new THREE.Vector3(110,y+random()*5,z+12)],curve=new THREE.CatmullRomCurve3(points,false,'centripetal'),baseScale=(near?.72:.45)+random()*(near?.35:.22);bird.root.scale.setScalar(baseScale);this.root.add(bird.root);list.push({...bird,curve,baseScale,speed:(near?.008:.004)+random()*(near?.006:.004),offset:random(),phase:random()*Math.PI*2,altNoise:random()*4,index});
 }
 update(elapsed,time,state,windDirection,reduced=false){
  const daylight=time.day<.3?1:time.day<.65?.34:time.day<.88?.88:1-smooth(.88,.98,time.day),density=daylight*(1-time.night)*state.birdVisibility*this.quality.settings.birdScale,all=[...this.near,...this.mid];
  const flockCentre=new THREE.Vector3();let active=0;all.forEach((b,i)=>{const allowed=i<Math.round(all.length*density);b.root.visible=allowed;if(!allowed)return;active++;const u=(b.offset+elapsed*b.speed)%1,p=b.curve.getPointAt(u),tan=b.curve.getTangentAt(u).normalize(),edge=smooth(0,.08,u)*(1-smooth(.9,1,u));p.y+=Math.sin(elapsed*.37+b.phase)*b.altNoise;p.x+=windDirection.x*Math.sin(elapsed*.21+b.phase)*1.4;p.z+=windDirection.y*Math.sin(elapsed*.21+b.phase)*1.4;b.root.position.copy(p);b.root.rotation.y=-Math.atan2(tan.z,tan.x);b.root.scale.setScalar(b.baseScale*(.18+.82*edge));flockCentre.add(p);if(!reduced&&b.wings.length)b.wings.forEach((wing,j)=>wing.rotation.x=(j?1:-1)*Math.sin(elapsed*7.2+b.phase)*.65);});
  if(active){flockCentre.multiplyScalar(1/active);const visibleBirds=all.filter(b=>b.root.visible);for(const bird of visibleBirds){const steer=flockCentre.clone().sub(bird.root.position).multiplyScalar(.0015);for(const other of visibleBirds){if(other===bird)continue;const away=bird.root.position.clone().sub(other.root.position),distance=away.lengthSq();if(distance>0&&distance<5.5)steer.add(away.normalize().multiplyScalar((5.5-distance)*.008));}bird.root.position.add(steer);}}
  for(let i=0;i<this.farData.length/3;i++){const u=(elapsed*.0018+i*.071)%1;this.farData[i*3]=-130+u*260;this.farData[i*3+1]=72+(i%9)*2.4+Math.sin(elapsed*.15+i)*3;this.farData[i*3+2]=-86+(i*37%160);}
  this.far.geometry.attributes.position.needsUpdate=true;this.far.material.opacity=.42*density;this.far.visible=density>.03;
 }
}

export class AircraftSystem{
 constructor(scene,materials){
  this.root=new THREE.Group();this.root.name='AircraftEvent';scene.add(this.root);const metal=new THREE.MeshPhysicalMaterial({color:0x727c82,roughness:.34,metalness:.84,clearcoat:.22});
  const fuselage=new THREE.Mesh(new THREE.CapsuleGeometry(.34,3.5,5,12),metal);fuselage.rotation.z=Math.PI/2;this.root.add(fuselage);const wing=new THREE.Mesh(new THREE.BoxGeometry(1.6,.08,7.2),metal);wing.position.x=.1;this.root.add(wing);const tail=new THREE.Mesh(new THREE.BoxGeometry(.75,.07,2.6),metal);tail.position.x=-1.7;this.root.add(tail);
  this.red=this.light(0xff2c20,-.05,0,3.65);this.green=this.light(0x31ff74,-.05,0,-3.65);this.white=this.light(0xffffff,-2.05,.65,0);this.root.add(this.red,this.green,this.white);this.root.scale.setScalar(1.7);this.root.visible=false;this.nextAt=40+random()*80;this.started=0;this.duration=26;this.active=false;this.path=null;
 }
 light(color,x,y,z){return new THREE.Mesh(new THREE.SphereGeometry(.12,8,6),new THREE.MeshBasicMaterial({color,transparent:true,opacity:0,toneMapped:false})).translateX(x).translateY(y).translateZ(z);}
 start(elapsed){const side=random()>.5?1:-1,z=-80+random()*160,y=92+random()*34;this.path=new THREE.CatmullRomCurve3([new THREE.Vector3(-170*side,y,z),new THREE.Vector3(-70*side,y+5,z+12),new THREE.Vector3(55*side,y-3,z-8),new THREE.Vector3(175*side,y+2,z+18)],false,'centripetal');this.started=elapsed;this.active=true;this.root.visible=true;}
 update(elapsed,time,state,reduced=false){
  if(!this.active&&elapsed>=this.nextAt&&!reduced)this.start(elapsed);if(!this.active)return;const u=(elapsed-this.started)/this.duration;if(u>=1){this.active=false;this.root.visible=false;this.nextAt=elapsed+40+random()*80;return;}const p=this.path.getPointAt(clamp(u,0,1)),tan=this.path.getTangentAt(clamp(u,0,1)).normalize();this.root.position.copy(p);this.root.rotation.y=-Math.atan2(tan.z,tan.x);const night=time.night,blink=(elapsed%1.45<.07)||(elapsed%1.45>.19&&elapsed%1.45<.25);this.red.material.opacity=night*.9;this.green.material.opacity=night*.9;this.white.material.opacity=night*(blink?1:.04);this.root.visible=state.worldOpacity>.2;
 }
}

export class EnvironmentSystem{
 constructor(scene,city,materials){
  this.materials=materials;this.windDirection=new THREE.Vector2(.82,.34).normalize();this.uniforms={time:{value:0},strength:{value:.06},direction:{value:this.windDirection}};this.root=new THREE.Group();this.root.name='WindEnvironment';city.root.add(this.root);
  const flagMat=new THREE.ShaderMaterial({uniforms:this.uniforms,vertexShader:`uniform float time;uniform float strength;uniform vec2 direction;varying float vWave;void main(){vec3 p=position;float mask=uv.x;float wave=sin(time*1.15+uv.x*7.+uv.y*2.)*strength*mask;p.z+=wave;vWave=wave;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}`,fragmentShader:`varying float vWave;void main(){gl_FragColor=vec4(mix(vec3(.86,.31,.12),vec3(1.,.55,.18),vWave*3.+.5),1.);}`,side:THREE.DoubleSide});
  for(const [x,z] of [[35,19],[43,19]]){const pole=new THREE.Mesh(new THREE.CylinderGeometry(.035,.045,4.6,7),materials.materials.trim);pole.position.set(x,2.55,z);this.root.add(pole);const flag=new THREE.Mesh(new THREE.PlaneGeometry(1.7,.85,12,3),flagMat);flag.position.set(x+.83,4.3,z);flag.rotation.y=Math.PI/2;this.root.add(flag);}
 }
 update(elapsed,state,reduced=false){const strength=reduced?0:.035+.018*Math.sin(elapsed*.16);this.uniforms.time.value=elapsed;this.uniforms.strength.value=strength;this.materials.wind.time.value=elapsed;this.materials.wind.strength.value=strength*.9;}
}
