// Original AI Video Studio motion-graphic interpreter for OpenMontage/Remotion.
// It draws the renderer-neutral scene from app/motion/templates.py; the
// easing/keyframe maths mirror templates.py so both engines match.
import React,{useEffect,useState} from 'react';
import {AbsoluteFill,Composition,continueRender,delayRender,registerRoot,staticFile,useCurrentFrame} from 'remotion';
const W=1920,H=1080;
const ease=(name:string,t:number)=>{t=Math.min(1,Math.max(0,t));
 if(name==='snappy')return 1-Math.pow(1-t,3);if(name==='linear')return t;
 if(name==='bounce'){const n=7.5625,d=2.75;if(t<1/d)return n*t*t;if(t<2/d){t-=1.5/d;return n*t*t+.75;}if(t<2.5/d){t-=2.25/d;return n*t*t+.9375;}t-=2.625/d;return n*t*t+.984375;}
 return t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;};
const valueAt=(track:number[][],t:number,name:string)=>{if(t<=track[0][0])return track[0][1];
 for(let i=0;i<track.length-1;i++){const [t0,v0]=track[i],[t1,v1]=track[i+1];if(t<=t1)return v0+(v1-v0)*ease(name,(t-t0)/Math.max(1e-6,t1-t0));}
 return track[track.length-1][1];};
const propsAt=(el:any,t:number,name:string)=>{const p={...el.props};for(const k of Object.keys(el.tracks||{}))p[k]=valueAt(el.tracks[k],t,name);return p;};
const mapView=(p:any,zoom:number)=>{const span=p.span_from+(p.span_to-p.span_from)*zoom,height=span*H/W;
 const lat=Math.max(-85+height/2,Math.min(85-height/2,p.lat));return [p.lon-span/2,lat+height/2,span,height];};
const anchor=(a:string)=>a==='lm'?'start':a==='rm'?'end':'middle';
const Element:React.FC<any>=({el,index,t,scene,families,frame})=>{
 const p=propsAt(el,t,scene.ease),op=p.opacity??1;
 if(el.type==='rect'){if(index===0||p.w<=.5||op<=.003)return null;return <rect x={p.x} y={p.y+(p.dy||0)} width={p.w} height={p.h} rx={Math.min(p.radius||0,p.w/2,p.h/2)} fill={p.fill} opacity={op}/>;}
 if(el.type==='circle'){if(p.r<=.5||op<=.003)return null;return <circle cx={p.cx} cy={p.cy} r={p.r} fill={p.fill||'none'} stroke={p.stroke||'none'} strokeWidth={p.width||0} opacity={op}/>;}
 if(el.type==='line')return <line x1={p.x1} y1={p.y1} x2={p.x2} y2={p.y2} stroke={p.stroke} strokeWidth={p.width} opacity={op}/>;
 if(el.type==='pin'){if(op<=.003)return null;const x=p.x,y=p.y+(p.dy||0),s=p.size;return <g opacity={op}>
  <polygon points={`${x-s*.62},${y-s*1.6} ${x+s*.62},${y-s*1.6} ${x},${y}`} fill={p.fill}/><circle cx={x} cy={y-s*1.6} r={s} fill={p.fill}/><circle cx={x} cy={y-s*1.6} r={s*.4} fill={p.hole}/></g>;}
 if(el.type==='map'){const [left,top,span,height]=mapView(p,p.zoom||0),sx=W/span,sy=H/height;
  return <g><rect x={0} y={0} width={W} height={H} fill={p.ocean}/>{[-360,0,360].map(shift=><g key={shift}>{(scene.land||[]).map((poly:number[][],i:number)=>
   <polygon key={i} points={poly.map(([x,y])=>`${((x+shift-left)*sx).toFixed(1)},${((top-y)*sy).toFixed(1)}`).join(' ')} fill={p.land} stroke={p.coast} strokeWidth={1}/>)}</g>)}</g>;}
 if(el.type==='text'||el.type==='counter'){if(op<=.003)return null;
  const text=el.type==='counter'?(el.texts?el.texts[Math.min(frame,el.texts.length-1)]:p.target):p.text;
  const size=p.size*(p.scale||1);
  return <text x={p.x} y={p.y+(p.dy||0)} fontSize={size} fontFamily={families[p.font||'']||'Arial,sans-serif'} fontWeight={p.bold===false?400:700}
   fill={p.fill} opacity={op} textAnchor={anchor(p.anchor||'mm')} dominantBaseline="central">{text}</text>;}
 return null;};
const Motion:React.FC<any>=scene=>{
 const frame=useCurrentFrame(),t=frame/scene.fps;
 const [handle]=useState(()=>delayRender('motion-fonts'));
 const families:Record<string,string>={};
 for(const [file,family] of Object.entries(scene.font_families||{}))families[file]=`'${family}',Arial,sans-serif`;
 useEffect(()=>{Promise.all(Object.entries(scene.font_families||{}).map(([file,family])=>
   new FontFace(family as string,`url(${staticFile(file)})`,{weight:'100 900'}).load().then(f=>{(document as any).fonts.add(f);}).catch(()=>{})))
  .then(()=>continueRender(handle));},[]);
 return <AbsoluteFill style={{background:scene.background}}><svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
  {scene.elements.map((el:any,i:number)=><Element key={i} el={el} index={i} t={t} scene={scene} families={families} frame={frame}/>)}</svg></AbsoluteFill>;};
registerRoot(()=><Composition id="AVSMotion" component={Motion} width={1920} height={1080} fps={30} durationInFrames={30}
 calculateMetadata={({props}:any)=>({durationInFrames:Math.max(1,Math.round(props.duration*props.fps))})}/>);
