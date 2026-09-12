import * as THREE from '../three.module.min.js';

const clamp=THREE.MathUtils.clamp;
const smooth=(a,b,v)=>{const t=clamp((v-a)/(b-a),0,1);return t*t*(3-2*t);};

export const SCENE_STATES=Object.freeze({
 CITY_REVEAL:'CITY_REVEAL',CITY_DISTRICT:'CITY_DISTRICT',STREET_LEVEL:'STREET_LEVEL',
 TARGET_BLOCK:'TARGET_BLOCK',TARGET_PARCEL:'TARGET_PARCEL',CADASTRAL_VIEW:'CADASTRAL_VIEW'
});

const STATE_FRAMES=[
 {p:0,name:SCENE_STATES.CITY_REVEAL,cameraFov:37,fogDensity:.0019,exposure:1.2,sunIntensity:1,moonIntensity:0,parcelVisibility:1,parcelOutlineOpacity:.3,parcelFillOpacity:.05,buildingLOD:.58,npcDensity:.52,birdVisibility:1,postprocessingIntensity:.22,cadastralOpacity:0,worldOpacity:1,dof:.05},
 {p:.58,name:SCENE_STATES.CITY_DISTRICT,cameraFov:36,fogDensity:.0023,exposure:1.18,sunIntensity:1,moonIntensity:0,parcelVisibility:1,parcelOutlineOpacity:.38,parcelFillOpacity:.055,buildingLOD:.78,npcDensity:.7,birdVisibility:.74,postprocessingIntensity:.27,cadastralOpacity:0,worldOpacity:1,dof:.02},
 {p:.96,name:SCENE_STATES.STREET_LEVEL,cameraFov:44,fogDensity:.0031,exposure:1.12,sunIntensity:.98,moonIntensity:.02,parcelVisibility:1,parcelOutlineOpacity:.48,parcelFillOpacity:.065,buildingLOD:1,npcDensity:1,birdVisibility:.48,postprocessingIntensity:.32,cadastralOpacity:.04,worldOpacity:1,dof:.08},
 {p:1.19,name:SCENE_STATES.TARGET_BLOCK,cameraFov:39,fogDensity:.0027,exposure:1.1,sunIntensity:.92,moonIntensity:.08,parcelVisibility:1,parcelOutlineOpacity:.68,parcelFillOpacity:.085,buildingLOD:.92,npcDensity:.78,birdVisibility:.35,postprocessingIntensity:.38,cadastralOpacity:.28,worldOpacity:.94,dof:.16},
 {p:1.48,name:SCENE_STATES.TARGET_PARCEL,cameraFov:35,fogDensity:.0021,exposure:1.08,sunIntensity:.84,moonIntensity:.16,parcelVisibility:1,parcelOutlineOpacity:.78,parcelFillOpacity:.1,buildingLOD:.72,npcDensity:.55,birdVisibility:.18,postprocessingIntensity:.42,cadastralOpacity:.66,worldOpacity:.72,dof:.2},
 {p:1.82,name:SCENE_STATES.CADASTRAL_VIEW,cameraFov:31,fogDensity:.0014,exposure:1.03,sunIntensity:.72,moonIntensity:.28,parcelVisibility:1,parcelOutlineOpacity:1,parcelFillOpacity:.12,buildingLOD:.3,npcDensity:.18,birdVisibility:0,postprocessingIntensity:.28,cadastralOpacity:1,worldOpacity:.34,dof:.03},
 {p:3.72,name:SCENE_STATES.CADASTRAL_VIEW,cameraFov:39,fogDensity:.0024,exposure:.92,sunIntensity:.28,moonIntensity:.9,parcelVisibility:1,parcelOutlineOpacity:1,parcelFillOpacity:.12,buildingLOD:.26,npcDensity:.12,birdVisibility:0,postprocessingIntensity:.4,cadastralOpacity:1,worldOpacity:.3,dof:.12},
 {p:4.2,name:SCENE_STATES.CITY_REVEAL,cameraFov:37,fogDensity:.0032,exposure:.86,sunIntensity:.12,moonIntensity:1,parcelVisibility:1,parcelOutlineOpacity:.32,parcelFillOpacity:.05,buildingLOD:.68,npcDensity:.5,birdVisibility:.03,postprocessingIntensity:.34,cadastralOpacity:0,worldOpacity:1,dof:.05}
];

export class SceneStateMachine{
 constructor(){this.current={...STATE_FRAMES[0]};}
 sample(progress){
  let i=0;while(i<STATE_FRAMES.length-2&&progress>STATE_FRAMES[i+1].p)i++;
  const a=STATE_FRAMES[i],b=STATE_FRAMES[i+1],t=smooth(a.p,b.p,progress),out={name:t<.5?a.name:b.name,progress};
  for(const key of Object.keys(a))if(typeof a[key]==='number'&&key!=='p')out[key]=THREE.MathUtils.lerp(a[key],b[key],t);
  this.current=out;return out;
 }
}

export class ScrollController{
 constructor(sections,{reduced=()=>false}={}){
  this.sections=sections;this.reduced=reduced;this.offsets=[];this.progress=0;this.target=0;this.velocity=0;this.viewport={width:innerWidth,height:innerHeight};
  this.measure=this.measure.bind(this);this.read=this.read.bind(this);addEventListener('scroll',this.read,{passive:true});addEventListener('resize',this.measure,{passive:true});this.measure();
 }
 measure(){this.viewport.width=innerWidth;this.viewport.height=innerHeight;this.offsets=this.sections.map(s=>({top:s.offsetTop,height:s.offsetHeight}));this.read();}
 read(){const y=scrollY;let i=0;while(i<this.offsets.length-1&&y>=this.offsets[i+1].top)i++;const o=this.offsets[i];this.target=i+clamp((y-o.top)/Math.max(1,o.height),0,1);}
 update(dt){
  if(this.reduced()){this.progress=this.target;this.velocity=0;return this.progress;}
  const step=Math.min(dt,.05),error=this.target-this.progress;this.velocity+=error*step*46;this.velocity*=Math.exp(-step*11.5);this.velocity=clamp(this.velocity,-2.4,2.4);this.progress+=this.velocity*step;
  if(Math.abs(error)<.00008&&Math.abs(this.velocity)<.00008){this.progress=this.target;this.velocity=0;}
  return this.progress;
 }
 get pageProgress(){return clamp(scrollY/Math.max(1,document.documentElement.scrollHeight-innerHeight),0,1);}
 destroy(){removeEventListener('scroll',this.read);removeEventListener('resize',this.measure);}
}

const DESKTOP_POSES=[
 {p:0,pos:[94,83,114],look:[1,1,1],fov:37},{p:.52,pos:[94,70,112],look:[5,2,0],fov:36},
 {p:.82,pos:[52,31,66],look:[13,2,2],fov:38},{p:1.02,pos:[28,5.8,23],look:[18.5,2.2,2.5],fov:44},
 {p:1.2,pos:[38,21,37],look:[18.5,.8,2.5],fov:39},{p:1.5,pos:[27,19,24],look:[18.5,.65,2.5],fov:35},
 {p:1.82,pos:[18.9,78,2.9],look:[18.5,.6,2.5],fov:31},{p:2.23,pos:[38,28,42],look:[18.5,9,2.5],fov:37},
 {p:2.78,pos:[38,28,42],look:[18.5,9,2.5],fov:37},{p:3.24,pos:[48,22,42],look:[24,5,4],fov:39},
 {p:3.77,pos:[48,22,42],look:[24,5,4],fov:39},{p:4.2,pos:[89,76,115],look:[4,1,2],fov:37}
];
const MOBILE_POSES=[
 {p:0,pos:[128,128,169],look:[0,1,0],fov:43},{p:.52,pos:[132,122,170],look:[4,1,0],fov:43},
 {p:.82,pos:[72,55,89],look:[13,2,2],fov:44},{p:1.02,pos:[31,9,37],look:[18.5,2.1,2.5],fov:48},
 {p:1.2,pos:[44,36,57],look:[18.5,.8,2.5],fov:44},{p:1.5,pos:[35,31,44],look:[18.5,.65,2.5],fov:42},
 {p:1.82,pos:[19.2,99,3.2],look:[18.5,.6,2.5],fov:39},{p:2.23,pos:[32,29,56],look:[18.5,9,2.5],fov:43},
 {p:2.78,pos:[32,29,56],look:[18.5,9,2.5],fov:43},{p:3.24,pos:[40,23,49],look:[25,5,4],fov:44},
 {p:3.77,pos:[40,23,49],look:[25,5,4],fov:44},{p:4.2,pos:[124,117,165],look:[0,1,0],fov:43}
];

function splineValue(poses,index,key,t){
 const a=poses[Math.max(0,index-1)][key],b=poses[index][key],c=poses[Math.min(poses.length-1,index+1)][key],d=poses[Math.min(poses.length-1,index+2)][key];
 const points=[a,b,c,d].map(v=>new THREE.Vector3(...v));return new THREE.CatmullRomCurve3(points,false,'centripetal').getPoint(.333+t/3);
}

export class CameraDirector{
 constructor(camera){this.camera=camera;this.mobile=innerWidth<=600;this.position=camera.position.clone();this.target=new THREE.Vector3();this.desiredPos=new THREE.Vector3();this.desiredTarget=new THREE.Vector3();this.fov=camera.fov;this.initialized=false;}
 setMobile(value){this.mobile=value;}
 update(progress,state,dt,scrollVelocity=0,reduced=false){
  const poses=this.mobile?MOBILE_POSES:DESKTOP_POSES;let i=0;while(i<poses.length-2&&progress>poses[i+1].p)i++;
  const a=poses[i],b=poses[i+1],t=smooth(a.p,b.p,progress);this.desiredPos.copy(splineValue(poses,i,'pos',t));this.desiredTarget.copy(splineValue(poses,i,'look',t));
  const inertia=clamp(scrollVelocity*.045,-.12,.12);this.desiredTarget.y+=inertia;
  const targetFov=(state?.cameraFov??THREE.MathUtils.lerp(a.fov,b.fov,t))+(this.mobile?6:0),response=reduced?1:1-Math.exp(-Math.min(dt,.06)*7.5);
  if(!this.initialized||reduced){this.position.copy(this.desiredPos);this.target.copy(this.desiredTarget);this.fov=targetFov;this.initialized=true;}else{this.position.lerp(this.desiredPos,response);this.target.lerp(this.desiredTarget,response*.92);this.fov=THREE.MathUtils.lerp(this.fov,targetFov,response);}
  this.camera.position.copy(this.position);this.camera.fov=this.fov;this.camera.lookAt(this.target);this.camera.updateProjectionMatrix();this.camera.updateMatrixWorld();
 }
}

export {smooth};
