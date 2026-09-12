import * as THREE from '../three.module.min.js';

export const QUALITY_LEVELS=Object.freeze({HIGH:'HIGH',MEDIUM:'MEDIUM',LOW:'LOW'});
const SETTINGS={
 HIGH:{dpr:1.7,targetFps:58,shadowMap:2048,activeLights:8,shadowLights:4,npcLimit:45,nearNpc:12,midUpdate:1,birdScale:1,post:true},
 MEDIUM:{dpr:1.25,targetFps:46,shadowMap:1024,activeLights:6,shadowLights:2,npcLimit:34,nearNpc:8,midUpdate:2,birdScale:.72,post:true},
 LOW:{dpr:1,targetFps:29,shadowMap:768,activeLights:4,shadowLights:1,npcLimit:22,nearNpc:5,midUpdate:3,birdScale:.45,post:false}
};

export class QualityManager{
 constructor(){
  const coarse=matchMedia('(pointer:coarse)').matches,small=Math.min(innerWidth,innerHeight)<700,memory=navigator.deviceMemory||4,cores=navigator.hardwareConcurrency||4;
  this.level=coarse||small||memory<=3?QUALITY_LEVELS.LOW:memory>=8&&cores>=8?QUALITY_LEVELS.HIGH:QUALITY_LEVELS.MEDIUM;
  this.settings=SETTINGS[this.level];this.resolutionScale=1;this.sampleTime=0;this.frames=0;this.cooldown=0;this.changed=true;this.fps=this.settings.targetFps;
 }
 get pixelRatio(){return Math.min(devicePixelRatio||1,this.settings.dpr)*this.resolutionScale;}
 update(dt){
  if(document.hidden||dt<=0||dt>.2)return false;this.sampleTime+=dt;this.frames++;this.cooldown=Math.max(0,this.cooldown-dt);
  if(this.sampleTime<1.8)return false;this.fps=this.frames/this.sampleTime;this.sampleTime=0;this.frames=0;
  if(this.cooldown>0)return false;const before=this.resolutionScale;
  if(this.fps<this.settings.targetFps*.8)this.resolutionScale=Math.max(.68,this.resolutionScale-.1);
  else if(this.fps>this.settings.targetFps+10)this.resolutionScale=Math.min(1,this.resolutionScale+.04);
  if(before!==this.resolutionScale){this.cooldown=3.5;this.changed=true;return true;}return false;
 }
 applyRenderer(renderer){renderer.setPixelRatio(this.pixelRatio);renderer.shadowMap.enabled=true;renderer.shadowMap.type=this.level===QUALITY_LEVELS.LOW?THREE.PCFShadowMap:THREE.PCFSoftShadowMap;this.changed=false;}
 setLevel(level){if(!SETTINGS[level])return;this.level=level;this.settings=SETTINGS[level];this.resolutionScale=1;this.changed=true;}
}
