import * as THREE from '../three.module.min.js';

export class PostProcessingSystem{
 constructor(renderer,quality){
  this.renderer=renderer;this.quality=quality;this.target=new THREE.WebGLRenderTarget(1,1,{depthBuffer:true,stencilBuffer:false,type:THREE.UnsignedByteType});this.target.texture.colorSpace=THREE.SRGBColorSpace;this.target.texture.generateMipmaps=false;this.target.texture.minFilter=THREE.LinearFilter;this.target.texture.magFilter=THREE.LinearFilter;
  this.scene=new THREE.Scene();this.camera=new THREE.OrthographicCamera(-1,1,1,-1,0,1);this.uniforms={tScene:{value:this.target.texture},resolution:{value:new THREE.Vector2(1,1)},intensity:{value:.3},bloom:{value:.08},dof:{value:0},time:{value:0}};
  const material=new THREE.ShaderMaterial({uniforms:this.uniforms,depthTest:false,depthWrite:false,toneMapped:false,vertexShader:`varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}`,fragmentShader:`
   uniform sampler2D tScene;uniform vec2 resolution;uniform float intensity;uniform float bloom;uniform float dof;uniform float time;varying vec2 vUv;
   float lum(vec3 c){return dot(c,vec3(.2126,.7152,.0722));}
   void main(){
    vec2 px=1./resolution;vec3 base=texture2D(tScene,vUv).rgb;
    vec3 blur=(texture2D(tScene,clamp(vUv+vec2(px.x,0.)*1.25,vec2(0.),vec2(1.))).rgb+texture2D(tScene,clamp(vUv-vec2(px.x,0.)*1.25,vec2(0.),vec2(1.))).rgb+texture2D(tScene,clamp(vUv+vec2(0.,px.y)*1.25,vec2(0.),vec2(1.))).rgb+texture2D(tScene,clamp(vUv-vec2(0.,px.y)*1.25,vec2(0.),vec2(1.))).rgb)*.25;
    float highlight=smoothstep(.9,1.35,lum(blur));vec3 color=base+blur*highlight*bloom*intensity;
    if(dof>.001){vec2 radial=(vUv-.5)*px*5.;vec3 cinematic=texture2D(tScene,clamp(vUv+radial,vec2(0.),vec2(1.))).rgb+texture2D(tScene,clamp(vUv-radial,vec2(0.),vec2(1.))).rgb;float edge=smoothstep(.32,.72,length(vUv-.5));color=mix(color,cinematic*.5,dof*edge*.55);}
    float vignette=smoothstep(.92,.28,length((vUv-.5)*vec2(1.,.84)));color*=mix(.955,1.,vignette);gl_FragColor=vec4(color,1.);
    #include <colorspace_fragment>
   }`});
  this.quad=new THREE.Mesh(new THREE.PlaneGeometry(2,2),material);this.scene.add(this.quad);this.enabled=quality.settings.post;
 }
 resize(width,height,dpr){const w=Math.max(1,Math.round(width*dpr)),h=Math.max(1,Math.round(height*dpr));this.target.setSize(w,h);this.uniforms.resolution.value.set(w,h);}
 update(elapsed,state,night){this.uniforms.time.value=elapsed;this.uniforms.intensity.value=state.postprocessingIntensity;this.uniforms.bloom.value=.025+night*.05;this.uniforms.dof.value=state.dof;this.enabled=this.quality.settings.post;}
 render(scene,camera){if(!this.enabled){this.renderer.render(scene,camera);return;}this.renderer.setRenderTarget(this.target);this.renderer.clear();this.renderer.render(scene,camera);this.renderer.setRenderTarget(null);this.renderer.render(this.scene,this.camera);}
}
