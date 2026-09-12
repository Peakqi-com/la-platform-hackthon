import * as THREE from '../three.module.min.js';

export const QUALITY_LEVELS=Object.freeze({HIGH:'HIGH',MEDIUM:'MEDIUM',LOW:'LOW'});
// dpr 是上限，ssaa 是下限（超取樣）。舊版用 min(devicePixelRatio, dpr)，
// 在 devicePixelRatio=1 的一般螢幕上永遠等於 1，等於完全沒有超取樣；
// 再被 resolutionScale 一乘就低於原生，畫面就糊掉。改成允許渲染解析度高於顯示解析度。
const SETTINGS={
 HIGH:{dpr:2,ssaa:1.5,targetFps:55,shadowMap:2560,activeLights:8,shadowLights:4,npcLimit:45,nearNpc:12,midUpdate:1,birdScale:1,post:true},
 MEDIUM:{dpr:1.6,ssaa:1.25,targetFps:44,shadowMap:1536,activeLights:6,shadowLights:2,npcLimit:34,nearNpc:8,midUpdate:2,birdScale:.72,post:true},
 LOW:{dpr:1.25,ssaa:1,targetFps:29,shadowMap:1024,activeLights:4,shadowLights:1,npcLimit:22,nearNpc:5,midUpdate:3,birdScale:.45,post:false}
};

export class QualityManager{
 constructor(){
  const coarse=matchMedia('(pointer:coarse)').matches,small=Math.min(innerWidth,innerHeight)<700,memory=navigator.deviceMemory||4,cores=navigator.hardwareConcurrency||4;
  this.level=coarse||small||memory<=3||cores<=2?QUALITY_LEVELS.LOW:(cores>=8||memory>=8)?QUALITY_LEVELS.HIGH:QUALITY_LEVELS.MEDIUM;
  // 網址加 ?q=LOW|MEDIUM|HIGH 可覆寫自動分級。現場筆電效能未知時用得到：
  // 畫面卡就 ?q=LOW，機器夠力就 ?q=HIGH。
  const forced=new URLSearchParams(location.search).get('q');
  if(forced&&SETTINGS[forced.toUpperCase()])this.level=forced.toUpperCase();
  this.settings=SETTINGS[this.level];this.resolutionScale=1;this.sampleTime=0;this.frames=0;this.cooldown=0;this.changed=true;this.fps=this.settings.targetFps;
 }
 get pixelRatio(){
  const native=devicePixelRatio||1;
  const target=Math.min(Math.max(native,this.settings.ssaa),this.settings.dpr)*this.resolutionScale;
  return Math.max(native,target);   // 效能不足時最多退回原生解析度，絕不低於原生（低於原生就是糊）
 }
 update(dt){
  if(document.hidden||dt<=0||dt>.2)return false;this.sampleTime+=dt;this.frames++;this.cooldown=Math.max(0,this.cooldown-dt);
  if(this.sampleTime<1.8)return false;this.fps=this.frames/this.sampleTime;this.sampleTime=0;this.frames=0;
  if(this.cooldown>0)return false;const before=this.resolutionScale;
  if(this.fps<this.settings.targetFps*.8)this.resolutionScale=Math.max(.5,this.resolutionScale-.08);
  else if(this.fps>this.settings.targetFps+10)this.resolutionScale=Math.min(1,this.resolutionScale+.04);
  if(before!==this.resolutionScale){this.cooldown=3.5;this.changed=true;return true;}return false;
 }
 applyRenderer(renderer){renderer.setPixelRatio(this.pixelRatio);renderer.shadowMap.enabled=true;renderer.shadowMap.type=this.level===QUALITY_LEVELS.LOW?THREE.PCFShadowMap:THREE.PCFSoftShadowMap;this.changed=false;}
 setLevel(level){if(!SETTINGS[level])return;this.level=level;this.settings=SETTINGS[level];this.resolutionScale=1;this.changed=true;}
}
