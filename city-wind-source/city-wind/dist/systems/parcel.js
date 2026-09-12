import * as THREE from '../three.module.min.js';

class ScreenSpacePolyline extends THREE.Mesh{
 constructor(points,{color=0xff7a18,width=2.8,opacity=1}={}){
  const count=points.length,positions=[],previous=[],next=[],sides=[],indices=[];
  for(let i=0;i<count;i++)for(const side of [-1,1]){
   const p=points[i],prev=points[(i-1+count)%count],after=points[(i+1)%count];positions.push(p.x,p.y,p.z);previous.push(prev.x,prev.y,prev.z);next.push(after.x,after.y,after.z);sides.push(side);
  }
  for(let i=0;i<count;i++){const j=(i+1)%count,a=i*2,b=a+1,c=j*2,d=c+1;indices.push(a,c,b,c,d,b);}
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.setAttribute('previous',new THREE.Float32BufferAttribute(previous,3));geometry.setAttribute('next',new THREE.Float32BufferAttribute(next,3));geometry.setAttribute('side',new THREE.Float32BufferAttribute(sides,1));geometry.setIndex(indices);
  const material=new THREE.ShaderMaterial({uniforms:{uResolution:{value:new THREE.Vector2(1,1)},uLineWidth:{value:width},uColor:{value:new THREE.Color(color)},uOpacity:{value:opacity}},vertexShader:`
   attribute vec3 previous;attribute vec3 next;attribute float side;uniform vec2 uResolution;uniform float uLineWidth;
   void main(){
    vec4 c=projectionMatrix*modelViewMatrix*vec4(position,1.);vec4 p=projectionMatrix*modelViewMatrix*vec4(previous,1.);vec4 n=projectionMatrix*modelViewMatrix*vec4(next,1.);
    vec2 cp=(c.xy/c.w*.5+.5)*uResolution;vec2 pp=(p.xy/p.w*.5+.5)*uResolution;vec2 np=(n.xy/n.w*.5+.5)*uResolution;
    vec2 da=normalize(cp-pp);vec2 db=normalize(np-cp);vec2 tangent=normalize(da+db);vec2 miter=vec2(-tangent.y,tangent.x);vec2 normalA=vec2(-da.y,da.x);float denom=max(.32,abs(dot(miter,normalA)));vec2 offset=miter*(uLineWidth*.5/denom)*side;
    c.xy+=offset/uResolution*2.*c.w;gl_Position=c;
   }`,fragmentShader:`uniform vec3 uColor;uniform float uOpacity;void main(){gl_FragColor=vec4(uColor,uOpacity);}`,
   transparent:true,depthWrite:false,depthTest:false,blending:THREE.NormalBlending,toneMapped:false
  });super(geometry,material);this.frustumCulled=false;this.renderOrder=998;
 }
 resize(width,height,dpr=1){this.material.uniforms.uResolution.value.set(Math.max(1,width*dpr),Math.max(1,height*dpr));}
 set width(value){this.material.uniforms.uLineWidth.value=value;}
 set opacity(value){this.material.uniforms.uOpacity.value=value;}
}

export class ParcelOverlay{
 constructor(parcel){
  this.root=new THREE.Group();this.root.name='PersistentTargetParcel';const y=.735,w=parcel.w/2,d=parcel.d/2,points=[new THREE.Vector3(parcel.x-w,y,parcel.z-d),new THREE.Vector3(parcel.x+w,y,parcel.z-d),new THREE.Vector3(parcel.x+w,y,parcel.z+d),new THREE.Vector3(parcel.x-w,y,parcel.z+d)];
  this.glow=new ScreenSpacePolyline(points,{color:0xff7a18,width:8,opacity:.08});this.line=new ScreenSpacePolyline(points,{color:0xff7a18,width:2.8,opacity:.3});this.glow.renderOrder=997;this.root.add(this.glow,this.line);
  this.fill=new THREE.Mesh(new THREE.PlaneGeometry(parcel.w,parcel.d),new THREE.MeshBasicMaterial({color:0xff7a18,transparent:true,opacity:.05,depthWrite:false,depthTest:true,polygonOffset:true,polygonOffsetFactor:-2,polygonOffsetUnits:-2,side:THREE.DoubleSide,toneMapped:false}));this.fill.rotation.x=-Math.PI/2;this.fill.position.set(parcel.x,y-.015,parcel.z);this.fill.renderOrder=996;this.root.add(this.fill);
 }
 resize(width,height,dpr,mobile=false){this.line.resize(width,height,dpr);this.glow.resize(width,height,dpr);this.line.width=(mobile?2.35:2.8)*dpr;this.glow.width=(mobile?6.6:8)*dpr;}
 update(state,elapsed){const visible=state.parcelVisibility;this.root.visible=visible>.001;this.line.opacity=state.parcelOutlineOpacity*visible;this.glow.opacity=(.045+.025*Math.sin(elapsed*.75))*state.parcelOutlineOpacity*visible;this.fill.material.opacity=state.parcelFillOpacity*visible;}
}

export class CadastralLayer{
 constructor(survey){this.survey=survey;this.root=survey.root;this.opacity=0;}
 update(state,drawProgress){
  this.opacity=state.cadastralOpacity;this.root.visible=this.opacity>.002;
  const lineCount=Math.round(drawProgress*121);this.survey.lines.forEach((line,i)=>{line.geometry.setDrawRange(0,Math.min(121,Math.max(0,lineCount-i*3+18)));line.material.opacity=(line.userData.baseOpacity??.72)*this.opacity;});
  this.survey.fills?.forEach(fill=>fill.material.opacity=(fill.userData.baseOpacity??.055)*this.opacity);
  this.survey.nodes.forEach(node=>{node.material.opacity=this.opacity;node.scale.setScalar(.65+.45*this.opacity);});
  this.survey.labels?.forEach(label=>{label.material.opacity=this.opacity;label.visible=this.opacity>.08;});
 }
}
