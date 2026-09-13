import * as THREE from './three.module.min.js';
import {MaterialLibrary} from './systems/materials.js';

// @@traffic-begin
// 車流控制器：不依賴 DOM。frontend/scripts/trafficsim.mjs 會把這一段原封不動抽出來做長時間模擬，
// 改這裡或改車的路線之後都要重跑：重疊必須是 0，也不能有車停超過 30 秒。
// 目標是絕不相撞。每台車只控制自己的油門：
//  1) 沿自己的車道往前掃 14 m（用實際畫出來的車身：中心沿路線、車身沿切線），前方有任何車的車身
//     （不分路線、方向）就在 0.8 m 外停住，6 m 內依距離減速；
//  2) 和其他車道交叉或匯入的衝突區：已在區內的車先過；都還沒進去時離入口近的先過，一樣近編號小的先過；
//     前車很慢而出口放不下整台車就不進去，停車時車身也不壓在衝突區裡（不堵路口）；
//  3) 後車逼近到 6 m 內，前車在自己前方允許的範圍內加速，最多 1.7 倍；
//  4) 減速立即生效、加速有上限（1.2 m/s²）；每幀位移遠小於安全距離，不會一步跨進別的車。
// 車道偏移：兩條對向車道相隔 2 m。原本 .72（相隔 1.44）時，廂型車轉彎車頭沿切線伸出約 0.4 m，
// 會伸進對向車道，兩台對向右轉的車互相把對方當成前車而一起停住。
const TRAFFIC_LANE=1;
function createTraffic(routes,specs){
 const STEP=.25,LOOK=14,LOOKZ=9,SAFE=.8,SLOW=6,MARGIN=.15,BOOST=.7,ACCEL=1.2,CLR=1.34,LANE=TRAFFIC_LANE;
 const wrap=(x,L)=>x-Math.floor(x/L)*L,within=(x,a,len,L)=>wrap(x-a,L)<=len;
 const lanes=new Map();
 function laneOf(ri,dir){
  const key=ri+'|'+dir;let ln=lanes.get(key);if(ln)return ln;
  const route=routes[ri],L=route.getLength(),N=Math.max(16,Math.round(L/STEP)),step=L/N;
  const px=new Float32Array(N),pz=new Float32Array(N),fx=new Float32Array(N),fz=new Float32Array(N);
  for(let k=0;k<N;k++){
   const u=wrap((dir>0?k*step:L-k*step)/L,1),p=route.getPointAt(u),t=route.getTangentAt(u).normalize();
   px[k]=p.x-t.z*LANE*dir;pz[k]=p.z+t.x*LANE*dir;fx[k]=t.x*dir;fz[k]=t.z*dir;
  }
  ln={key,L,N,step,px,pz,fx,fz,zones:[],cars:[]};lanes.set(key,ln);return ln;
 }
 function at(ln,s,o){
  const f=wrap(s,ln.L)/ln.step,k=Math.floor(f)%ln.N,k2=(k+1)%ln.N,t=f-Math.floor(f);
  o.x=ln.px[k]+(ln.px[k2]-ln.px[k])*t;o.z=ln.pz[k]+(ln.pz[k2]-ln.pz[k])*t;
  const fx=ln.fx[k]+(ln.fx[k2]-ln.fx[k])*t,fz=ln.fz[k]+(ln.fz[k2]-ln.fz[k])*t,n=Math.hypot(fx,fz)||1;o.fx=fx/n;o.fz=fz/n;return o;
 }
 function ptSeg(px,pz,ax,az,bx,bz){const dx=bx-ax,dz=bz-az,l2=dx*dx+dz*dz;let t=l2>0?((px-ax)*dx+(pz-az)*dz)/l2:0;t=t<0?0:t>1?1:t;return Math.hypot(ax+dx*t-px,az+dz*t-pz);}
 // 兩台車身（沿車頭方向的線段）最短距離，交叉時為 0
 function bodyDist(c,o){
  const ax=c.x-c.fx*c.hl,az=c.z-c.fz*c.hl,bx=c.x+c.fx*c.hl,bz=c.z+c.fz*c.hl,cx=o.x-o.fx*o.hl,cz=o.z-o.fz*o.hl,dx=o.x+o.fx*o.hl,dz=o.z+o.fz*o.hl;
  const d1=(dx-cx)*(az-cz)-(dz-cz)*(ax-cx),d2=(dx-cx)*(bz-cz)-(dz-cz)*(bx-cx),d3=(bx-ax)*(cz-az)-(bz-az)*(cx-ax),d4=(bx-ax)*(dz-az)-(bz-az)*(dx-ax);
  if(d1*d2<0&&d3*d4<0)return 0;
  return Math.min(ptSeg(ax,az,cx,cz,dx,dz),ptSeg(bx,bz,cx,cz,dx,dz),ptSeg(cx,cz,ax,az,bx,bz),ptSeg(dx,dz,ax,az,bx,bz));
 }
 const cars=specs.map((sp,i)=>{const ln=laneOf(sp.ri,sp.dir),c={i,ln,len:sp.len,hl:sp.len/2,hw:sp.w/2,vmax:sp.vmax,v:0,s:wrap(sp.s,ln.L),x:0,z:0,fx:1,fz:0,gap:LOOK,stop:LOOK,prevStop:LOOK,blocker:null,press:0};ln.cars.push(c);return c;});
 // 衝突區：兩條車道中心線靠近到 CLR 以內、且行進方向不同（交叉或匯入）的路段
 const laneArr=[...lanes.values()];
 function runs(idx,N){
  const out=[];let st=idx[0],pr=idx[0];
  for(let n=1;n<idx.length;n++){if(idx[n]-pr>2){out.push([st,pr]);st=idx[n];}pr=idx[n];}
  out.push([st,pr]);
  if(out.length>1&&out[0][0]<=2&&out[out.length-1][1]>=N-3){const last=out.pop();out[0]=[last[0],out[0][1]+N];}
  return out;
 }
 for(let a=0;a<laneArr.length;a++)for(let b=a+1;b<laneArr.length;b++){
  const A=laneArr[a],B=laneArr[b],grid=new Map(),cell=1.5,pairs=[];
  for(let j=0;j<B.N;j++){const key=Math.floor(B.px[j]/cell)+','+Math.floor(B.pz[j]/cell);let g=grid.get(key);if(!g)grid.set(key,g=[]);g.push(j);}
  for(let i=0;i<A.N;i++){
   const gx=Math.floor(A.px[i]/cell),gz=Math.floor(A.pz[i]/cell);
   for(let ox=-1;ox<=1;ox++)for(let oz=-1;oz<=1;oz++){const g=grid.get((gx+ox)+','+(gz+oz));if(!g)continue;
    for(const j of g){const ex=B.px[j]-A.px[i],ez=B.pz[j]-A.pz[i];if(ex*ex+ez*ez<CLR*CLR&&A.fx[i]*B.fx[j]+A.fz[i]*B.fz[j]<.7)pairs.push([i,j]);}}
  }
  if(!pairs.length)continue;
  for(const ir of runs([...new Set(pairs.map(p=>p[0]))].sort((x,y)=>x-y),A.N)){
   const js=[...new Set(pairs.filter(p=>wrap(p[0]-ir[0],A.N)<=ir[1]-ir[0]).map(p=>p[1]))].sort((x,y)=>x-y);
   for(const jr of runs(js,B.N)){
    const z={a0:ir[0]*A.step,alen:(ir[1]-ir[0]+1)*A.step,other:B,b0:jr[0]*B.step,blen:(jr[1]-jr[0]+1)*B.step};
    A.zones.push(z);B.zones.push({a0:z.b0,alen:z.blen,other:A,b0:z.a0,blen:z.alen});
   }
  }
 }
 // 開場位置：依序放，跟已放好的車太近就往前挪，保證一開始沒有重疊
 for(let n=0;n<cars.length;n++){const c=cars[n];
  for(let k=0;k<800;k++){at(c.ln,c.s,c);let ok=true;for(let m=0;m<n;m++)if(bodyDist(c,cars[m])<c.hw+cars[m].hw+1){ok=false;break;}if(ok)break;c.s=wrap(c.s+.5,c.ln.L);}
 }
 const Q={x:0,z:0,fx:0,fz:0};
 function update(dt){
  if(!(dt>0))return;
  for(const c of cars)at(c.ln,c.s,c);
  // 1) 前方掃描：未來的車頭（中心沿路線前進 d、車頭沿切線伸出半個車長）碰到任何車身，就是前方距離
  for(const c of cars){
   c.gap=LOOK;c.blocker=null;
   const near=[];for(const o of cars)if(o!==c&&Math.abs(o.x-c.x)+Math.abs(o.z-c.z)<LOOK+c.len+o.len+2)near.push(o);
   if(!near.length)continue;
   scan:for(let d=0;d<=LOOK;d+=.5){
    at(c.ln,c.s+d,Q);const qx=Q.x+Q.fx*c.hl,qz=Q.z+Q.fz*c.hl;
    for(const o of near)if(ptSeg(qx,qz,o.x-o.fx*o.hl,o.z-o.fz*o.hl,o.x+o.fx*o.hl,o.z+o.fz*o.hl)<c.hw+o.hw+MARGIN){c.gap=d;c.blocker=o;break scan;}
   }
  }
  // 2) 衝突區讓車，停車時不壓在衝突區裡
  for(const c of cars){
   const ln=c.ln,L=ln.L,front=c.s+c.hl,rear=c.s-c.hl,slowAhead=c.blocker&&c.blocker.v<.5*c.blocker.vmax;
   let stop=c.gap,gave=false;const ahead=[];
   for(const z of ln.zones){
    if(within(rear,z.a0,z.alen,L)||within(z.a0,rear,c.len,L))continue;      // 車身已在區內：不讓，趕快通過
    const dA=wrap(z.a0-front,L);if(dA>LOOK)continue;ahead.push(z,dA);
    if(dA>LOOKZ)continue;
    let give=false;
    for(const o of z.other.cars){
     const oL=z.other.L,oRear=o.s-o.hl;
     if(within(oRear,z.b0,z.blen,oL)||within(z.b0,oRear,o.len,oL)){give=true;break;}   // 對方已在區內
     const dB=wrap(z.b0-(o.s+o.hl),oL);
     if(dB<=LOOKZ&&o.prevStop>dB+.01&&(dB<dA-.05||(Math.abs(dB-dA)<=.05&&o.i<c.i))){give=true;break;}   // 對方會先到
    }
    if(!give&&slowAhead&&c.gap<dA+z.alen+c.len+SAFE)give=true;                // 前車很慢、出口放不下整台車：不進去
    if(give&&dA<stop){stop=dA;gave=true;}
   }
   if(gave||slowAhead)for(let it=0;it<6;it++){let moved=false;
    for(let n=0;n<ahead.length;n+=2){const z=ahead[n],dA=ahead[n+1];if(dA<stop-SAFE&&dA+z.alen>stop-SAFE-c.len){stop=dA;moved=true;}}
    if(!moved)break;}
   c.stop=stop;
  }
  // 3) 後車逼近：被當成前車的那台加速
  for(const c of cars)c.press=0;
  for(const o of cars)if(o.blocker){const p=Math.min(1,Math.max(0,(SLOW-o.gap)/(SLOW-SAFE)));if(p>o.blocker.press)o.blocker.press=p;}
  // 4) 油門：減速立即、加速有上限
  for(const c of cars){
   const limit=c.vmax*(1+BOOST)*Math.min(1,Math.max(0,(c.stop-SAFE)/(SLOW-SAFE))),want=Math.min(c.vmax*(1+BOOST*c.press),limit);
   c.v=want<c.v?want:Math.min(want,c.v+ACCEL*dt);c.prevStop=c.stop;
  }
  for(const c of cars)c.s=wrap(c.s+c.v*dt,c.ln.L);
 }
 return {cars,update,at,bodyDist,lanes};
}
// @@traffic-end

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
 const waterMaterial=new THREE.ShaderMaterial({uniforms:{uTime:{value:0},uDay:{value:0},uSunX:{value:.25},uFire:{value:new THREE.Vector3(0,0,0)},uFireAt:{value:new THREE.Vector2(-99,-99)},uFireK:{value:0}},vertexShader:`varying vec2 vUv;varying float vWave;uniform float uTime;void main(){vUv=uv;vec3 p=position;float a=sin((uv.y*23.0)+(uTime*.62))*0.075;float b=sin((uv.y*41.0)-(uTime*.9)+(uv.x*6.0))*0.038;vWave=a+b;p.z=(a+b)*.5+.06;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);}`,fragmentShader:`varying vec2 vUv;varying float vWave;uniform float uTime;uniform float uDay;uniform float uSunX;uniform vec3 uFire;uniform vec2 uFireAt;uniform float uFireK;
   void main(){
    float night=smoothstep(.68,1.,uDay);
    vec3 deep=mix(vec3(.055,.28,.34),vec3(.018,.075,.12),night);
    vec3 shallow=mix(vec3(.16,.48,.52),vec3(.04,.18,.25),night);
    float phase=vUv.y*48.-uTime*1.25+sin(vUv.x*14.)*1.35;
    float phw=fwidth(phase);
    float bandFade=1.-smoothstep(1.1,2.8,phw);
    float flow=.5+.5*sin(phase);
    float aa=max(phw*.5,.012);
    float bands=smoothstep(.66-aa,.94+aa,flow)*(.17+vWave*1.05)*bandFade;
    float path=exp(-pow((vUv.x-uSunX)*8.,2.))*smoothstep(.03,.34,vUv.y)*(1.-smoothstep(.72,.98,vUv.y));
    float gphase=vUv.y*96.-uTime*2.2+vUv.x*23.;
    float gphw=fwidth(gphase);
    float gFade=1.-smoothstep(1.1,2.8,gphw);
    float glitter=.5+.5*sin(gphase);
    float gaa=max(gphw*.5,.018);
    float sparkle=smoothstep(.94-gaa,1.,glitter)*path*gFade;
    vec3 sun=mix(vec3(1.,.63,.30),vec3(.62,.77,1.),night);
    vec3 c=mix(deep,shallow,.42+vWave*1.1)+bands*vec3(.07,.15,.15)+sun*(path*.23+sparkle*.72);
    if(uFireK>.001){
     vec2 fd=vUv-uFireAt;
     float ripple=.5+.5*sin(vUv.y*36.-uTime*2.4);
     float spread=exp(-dot(fd*vec2(2.6,1.15),fd*vec2(2.6,1.15))*7.0);
     c+=uFire*uFireK*spread*(.55+.45*ripple);
    }
    gl_FragColor=vec4(c,.98);
   }`,transparent:false,side:THREE.DoubleSide});
 const water=mesh(terrain,new THREE.PlaneGeometry(19,88,28,120),waterMaterial,-31,.18,0);water.rotation.x=-Math.PI/2;water.castShadow=false;
 for(const x of [-41.3,-20.7]){box(terrain,x,.4,0,1.4,.7,88,'curb');box(terrain,x+(x<-30?-1.3:1.3),.15,0,1.1,.12,88,'gold');}
 // River promenades and benches.
 for(const x of [-45,-17.5])for(let z=-39;z<=39;z+=6){box(terrain,x,.8,z,1.5,.2,.6,'roof');box(terrain,x-.5,.4,z,.12,.6,.4,'black');box(terrain,x+.5,.4,z,.12,.6,.4,'black');box(terrain,x,.99,z-.3,1.5,.6,.12,'roof');}
 const xs=[-13,8,29,50],zs=[-29,-8,13,34];
 for(const x of xs){box(terrain,x,.14,0,4.7,.1,86,'road');for(let z=-41;z<43;z+=3.4)box(terrain,x,.21,z,.1,.01,1.8,'roadMark');for(const dx of [-2.48,2.48])box(terrain,x+dx,.25,0,.28,.3,86,'curb');}
 for(const z of zs){box(terrain,19,.17,z,68,.1,4.8,'road');for(let x=-12;x<53;x+=3.4)box(terrain,x,.235,z,1.8,.01,.1,'roadMark');for(const dz of [-2.48,2.48])box(terrain,19,.25,z+dz,68,.3,.25,'curb');}
 for(const x of xs)for(const z of zs){for(let i=0;i<6;i++){box(terrain,x-2+i*.8,.25,z+3.25,.43,.025,1.15,'roadMark');box(terrain,x+3.25,.25,z-2+i*.8,1.15,.025,.43,'roadMark');}}
 // Two bridges: a cable bridge and a fine-railed promenade.
 // 夜間發光的燈具收進 nightGlow，統一由 animate() 依 night 調亮度，
 // 亮度值每幀是同一個算式算出來的，不會閃。
 const nightGlow=[];
 const glowLamp=(x,y,zz,size,color,gain)=>{
  const m=new THREE.MeshBasicMaterial({color,transparent:true,opacity:0,toneMapped:false,depthWrite:false});
  mesh(terrain,new THREE.SphereGeometry(size,8,6),m,x,y,zz);
  nightGlow.push({mat:m,base:0,gain});
  return m;
 };
 // 斜張橋夜間 LED 燈條：沿斜張索、橋塔稜線與橋面兩側，紅、洋紅、藍、青循環變色，
 // 並有一段亮帶沿燈條往下流動。加法混色且亮度乘上 night，白天等於完全不顯示。
 // 亮帶是一個週期的低頻正弦，縮到很遠也不會變成高頻閃爍。
 const ledMat=new THREE.ShaderMaterial({
  uniforms:{uTime:{value:0},uNight:{value:0}},
  transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false,
  vertexShader:`attribute float aPhase;varying float vT;varying float vPh;
   void main(){vT=uv.y;vPh=aPhase;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
  fragmentShader:`uniform float uTime;uniform float uNight;varying float vT;varying float vPh;
   // palette cycles red -> magenta -> blue -> cyan -> red
   vec3 pal(float x){x=fract(x);
    vec3 r=vec3(1.,.12,.22),m=vec3(.95,.18,.9),b=vec3(.18,.38,1.),c=vec3(.15,.9,1.);
    if(x<.25)return mix(r,m,x*4.);if(x<.5)return mix(m,b,(x-.25)*4.);if(x<.75)return mix(b,c,(x-.5)*4.);return mix(c,r,(x-.75)*4.);}
   void main(){
    vec3 col=pal(vT*.7+vPh-uTime*.16);
    float chase=.5+.5*smoothstep(.15,.9,.5+.5*sin(vT*6.2831-uTime*2.2+vPh*6.2831));
    gl_FragColor=vec4(col*chase*1.7*uNight,1.);
   }`
 });
 const ledStrip=(a,b,r,phase)=>{
  const A=new THREE.Vector3(...a),B=new THREE.Vector3(...b),d=B.clone().sub(A),len=d.length();
  const g=new THREE.CylinderGeometry(r,r,len,6,1,true);
  g.setAttribute('aPhase',new THREE.BufferAttribute(new Float32Array(g.attributes.position.count).fill(phase),1));
  const m=new THREE.Mesh(g,ledMat);
  m.position.copy(A).add(B).multiplyScalar(.5);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());
  m.castShadow=false;m.receiveShadow=false;m.renderOrder=5;terrain.add(m);return m;
 };
 for(const [z,cable]of [[-19,true],[24,false]]){
  box(terrain,-31,1,z,35,.75,5,'concrete');box(terrain,-31,1.42,z,35,.1,4.4,'road');
  for(const dz of [-2.4,2.4]){box(terrain,-31,2,z+dz,35,.12,.12,'light');for(let x=-48;x<-13;x+=1.8)box(terrain,x,1.7,z+dz,.12,.8,.12,'trim');}
  for(let x=-45;x<-15;x+=3)box(terrain,x,1.5,z,1.6,.04,.12,'roadMark');
  for(const x of [-39,-23]){box(terrain,x,-.2,z,.9,3.5,3,'concrete');if(cable){for(const dz of [-2.7,2.7]){box(terrain,x,6.2,z+dz,.65,12,.6,'light');for(const dx of [-8,-5,-2,2,5,8])beam(terrain,[x,11.4,z+dz],[x+dx,1.6,z+dz],.045,'gold');}box(terrain,x,10.5,z,1,.65,6,'light');}}
  // 步道橋保留暖色欄杆燈；斜張橋改成 LED 燈條
  if(!cable)for(let x=-46.5;x<-14;x+=2.4)for(const dz of [-2.4,2.4])glowLamp(x,2.16,z+dz,.09,0xffcf95,.92);
  if(cable){
   // 橋面兩側
   for(const dz of [-2.4,2.4])ledStrip([-48.5,2.1,z+dz],[-13.5,2.1,z+dz],.075,dz>0?0:.5);
   for(const x of [-39,-23]){
    glowLamp(x,11.9,z,.16,0xff8a6a,.95);   // 塔頂航空燈
    // 斜張索：每一條從塔頂往橋面，相位依位置錯開，顏色像在沿著索流動
    for(const dz of [-2.7,2.7])for(const dx of [-8,-5,-2,2,5,8])ledStrip([x,11.4,z+dz],[x+dx,1.6,z+dz],.07,(x+dx)*.018+dz*.04);
    // 橋塔稜線與頂部橫梁
    for(const dz of [-2.7,2.7])for(const ex of [-.34,.34])ledStrip([x+ex,.6,z+dz+(dz>0?.31:-.31)],[x+ex,12.1,z+dz+(dz>0?.31:-.31)],.06,x*.01+ex);
    ledStrip([x,10.86,z-3],[x,10.86,z+3],.06,x*.013);
   }
  }
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
 const cars=[],carLights=[];let lastTime=0;
 function roundedLoop(x1,z1,x2,z2,y=.49,r=1.3){const path=new THREE.CurvePath(),v=(x,z)=>new THREE.Vector3(x,y,z);path.add(new THREE.LineCurve3(v(x1+r,z1),v(x2-r,z1)));path.add(new THREE.QuadraticBezierCurve3(v(x2-r,z1),v(x2,z1),v(x2,z1+r)));path.add(new THREE.LineCurve3(v(x2,z1+r),v(x2,z2-r)));path.add(new THREE.QuadraticBezierCurve3(v(x2,z2-r),v(x2,z2),v(x2-r,z2)));path.add(new THREE.LineCurve3(v(x2-r,z2),v(x1+r,z2)));path.add(new THREE.QuadraticBezierCurve3(v(x1+r,z2),v(x1,z2),v(x1,z2-r)));path.add(new THREE.LineCurve3(v(x1,z2-r),v(x1,z1+r)));path.add(new THREE.QuadraticBezierCurve3(v(x1,z1+r),v(x1,z1),v(x1+r,z1)));path.autoClose=true;return path;}
 const routes=[roundedLoop(-13,-29,50,34,.49,3),roundedLoop(8,-29,29,13,.49,3),roundedLoop(29,-8,50,34,.49,3),roundedLoop(-13,-8,8,13,.49,3),roundedLoop(8,13,50,34,.49,3)];
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
  // 每台車的燈亮度不同（0.78～1.18 倍），像真的車隊而不是複製貼上。
  // 倍率在建立時就固定，不隨時間變動，所以不會閃。
  const bulb=.78+random()*.4;
  const headMat=new THREE.MeshBasicMaterial({color:0xffe8c2,transparent:true,opacity:.1,toneMapped:false}),tailMat=new THREE.MeshBasicMaterial({color:0xef5b48,transparent:true,opacity:.12,toneMapped:false});
  // 燈泡球半徑從 .055 放大到 .085，並外加一顆半透明光暈球。
  // 原本的燈在遠處不到一個像素，是造成車燈閃爍的主因之一。
  const haloMat=new THREE.MeshBasicMaterial({color:0xffdca8,transparent:true,opacity:0,toneMapped:false,depthWrite:false,blending:THREE.AdditiveBlending});
  for(const z of [-.27,.27]){
   mesh(g,new THREE.SphereGeometry(.085,8,6),headMat,len*.5+.015,.47,z);
   mesh(g,new THREE.SphereGeometry(.22,8,6),haloMat,len*.5+.02,.47,z);
   mesh(g,new THREE.SphereGeometry(.07,8,6),tailMat,-len*.5-.015,.44,z);
  }
  carLights.push({mat:headMat,base:.1,gain:1.05*bulb},{mat:tailMat,base:.12,gain:.86*bulb},{mat:haloMat,base:0,gain:.3*bulb});
  g.userData.lights={head:headMat,halo:haloMat,tail:tailMat,bulb};
  if(type!==4){const lightGeo=new THREE.BufferGeometry();lightGeo.setAttribute('position',new THREE.Float32BufferAttribute([len*.45,-.19,-.28,len*.45,-.19,.28,len*.45+4.2,-.19,1.05,len*.45+4.2,-.19,-1.05],3));lightGeo.setIndex([0,1,2,0,2,3]);/* 路面光斑放在世界高度 .30：原本 .215 剛好等於南北向標線頂、又比東西向路面低 5 mm，遠鏡頭下夜裡會跟路面 z-fighting 亂閃 */const footprintMat=new THREE.MeshBasicMaterial({color:0xffd49a,transparent:true,opacity:0,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false,side:THREE.DoubleSide,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-4});g.add(new THREE.Mesh(lightGeo,footprintMat));carLights.push({mat:footprintMat,base:0,gain:.16*bulb});g.userData.lights.foot=footprintMat;}
  return g;
 }
 for(let i=0;i<27;i++){
  const type=i%9===0?3:i%7===0?4:i%5===0?2:i%4===0?1:0,g=vehicle(type,vehicleColors[i%vehicleColors.length]);terrain.add(g);
  // 靠右行駛：車道偏移由行駛方向決定（順著路線切線走的在右側、反向的在左側），對向車道相隔 2 m
  const route=routes[i%routes.length],dir=i%3===0?-1:1;
  cars.push({g,i,type,route,dir,lane:TRAFFIC_LANE*dir,u:random(),baseSpeed:.008+random()*.008,len:Math.max(1,route.getLength()),
             key:(i%routes.length)+'|'+dir});
 }
 // 同一條路線、同一車道、同方向的車編成一組，起點均分，開場就不會疊在一起
 const laneGroups=new Map();
 for(const car of cars){if(!laneGroups.has(car.key))laneGroups.set(car.key,[]);laneGroups.get(car.key).push(car);}
 for(const group of laneGroups.values())group.forEach((c,k)=>{c.u=(k/group.length+k*.011)%1;});
 // 車流控制器（檔案最上方 @@traffic 區段）：絕不相撞、靠近減速、後車逼近時前車加速
 const VEH_W=[.98,.98,.98,1.04,.5],VEH_L=[1.7,2.55,2.15,3.25,.85];
 const traffic=createTraffic(routes,cars.map(c=>({ri:routes.indexOf(c.route),dir:c.dir,len:VEH_L[c.type],w:VEH_W[c.type],vmax:c.baseSpeed*c.len,s:(c.dir>0?c.u:1-c.u)*c.len})));
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
  // 車流：每台車的速度交給控制器（檔案最上方 @@traffic 區段），這裡只負責把車擺到位置上
 const dt=Math.min(.05,Math.max(0,time-lastTime));lastTime=time;
 traffic.update(dt);
 for(let n=0;n<cars.length;n++){
  const car=cars[n],t=traffic.cars[n],L=t.ln.L;
  car.u=car.dir>0?t.s/L:((L-t.s)/L)%1;
  const p=car.route.getPointAt(car.u),tan=car.route.getTangentAt(car.u).normalize(),side=new THREE.Vector3(-tan.z,0,tan.x);
  // 車頭朝行進方向：反向行駛（dir=-1）的車要轉 180°，否則車頭燈在後面、看起來是倒著開
  car.g.position.copy(p).addScaledVector(side,car.lane);car.g.rotation.y=-Math.atan2(tan.z*car.dir,tan.x*car.dir);
 }
  // 車燈亮度固定：只隨 night，不隨與前車的距離變。舊版「照到前車變亮」那段每幀都被下面這行蓋掉，已移除；
  // 不要再加回來——亮度跟著車距跳動，夜裡看起來就是在閃。
  for(const light of carLights)light.mat.opacity=light.base+night*light.gain;
  for(const light of nightGlow)light.mat.opacity=light.base+night*light.gain;
  ledMat.uniforms.uTime.value=time;ledMat.uniforms.uNight.value=night;
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
 // 原本 5 條流線都在城外偏高處。加到 9 條，後 4 條壓低到屋頂高度並橫越市區，
 // 風才看得出是「穿過城市」而不是從旁邊飄過。
 for(let i=0;i<9;i++){
  const inner=i>=5,k=i-5;
  const points=[];
  for(let j=0;j<=12;j++){
   const t=j/12;
   points.push(inner
    ? new THREE.Vector3(-62+t*126, 3.2+Math.sin(t*Math.PI*2.4+k*.7)*1.9+k*.9, 6+Math.sin(t*Math.PI*1.7-k*.6)*21-k*9)
    : new THREE.Vector3(-58+t*117, 6+Math.sin(t*Math.PI*2+i*.45)*3+i*1.2, -15+Math.sin(t*Math.PI*2-i*.25)*17+i*2));
  }
  const curve=new THREE.CatmullRomCurve3(points),geo=new THREE.TubeGeometry(curve,160,inner?.014:.018+(i===2?.022:0),3,false);
  const line=new THREE.Mesh(geo,new THREE.MeshBasicMaterial({color:i===2?0xf3c191:inner?0xcfe4dd:0xa9d4d0,transparent:true,opacity:i===2?.42:inner?.11:.16,depthWrite:false}));root.add(line);curves.push(curve);
  const dot=new THREE.Mesh(new THREE.SphereGeometry(i===2?.1:inner?.05:.065,8,6),new THREE.MeshBasicMaterial({color:0xffdcb0}));root.add(dot);dots.push(dot);
 }

 // 順風飄過的樹葉：沿流線前進，一邊翻滾。純位移與旋轉，沒有高頻閃爍。
 // buildWind 在 buildCity 的作用域外，用不到那邊的 random，這裡自備一個種子亂數
 let seed=90210;const rnd=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
 const leafGeo=new THREE.PlaneGeometry(.26,.17);
 const leafColors=[0x7f9a63,0x9aa96f,0xc2a055,0xb8794a,0x6f8f70];
 const leaves=[];
 for(let i=0;i<34;i++){
  const m=new THREE.MeshBasicMaterial({color:leafColors[i%leafColors.length],transparent:true,opacity:.85,side:THREE.DoubleSide,depthWrite:false});
  const leaf=new THREE.Mesh(leafGeo,m);root.add(leaf);
  leaves.push({o:leaf,curve:curves[i%curves.length],offset:rnd(),speed:.02+rnd()*.028,
               spin:new THREE.Vector3(.7+rnd()*1.6,1.1+rnd()*1.9,.5+rnd()*1.3),
               drift:1.2+rnd()*2.4,phase:rnd()*6.28,scale:.7+rnd()*.8});
  leaf.scale.setScalar(leaves[i].scale);
 }

 const tmp=new THREE.Vector3();
 function update(elapsed,reduced=false){
  for(let i=0;i<dots.length;i++)dots[i].position.copy(curves[i].getPointAt(reduced?.45:(elapsed*.042+i*.18)%1));
  for(const l of leaves){
   const u=reduced?(l.offset%1):((l.offset+elapsed*l.speed)%1+1)%1;
   l.curve.getPointAt(u,tmp);
   // 橫向與上下的擺盪，讓葉子不是沿著線走，而是被風帶著飄
   tmp.x+=Math.sin(elapsed*.9+l.phase)*l.drift;
   tmp.y+=Math.sin(elapsed*1.35+l.phase*1.7)*l.drift*.35-u*1.4;
   tmp.z+=Math.cos(elapsed*.75+l.phase*1.3)*l.drift;
   l.o.position.copy(tmp);
   if(!reduced){l.o.rotation.x=elapsed*l.spin.x+l.phase;l.o.rotation.y=elapsed*l.spin.y;l.o.rotation.z=elapsed*l.spin.z;}
  }
 }
 return {root,curves,dots,leaves,update};
}
