// Original AI Video Studio projection. No upstream source or template copied.
// Camera math mirrors app/rendering/smart_edit.py (same eased/neutral curves,
// zoom and focus values) so both engines show the same edit decisions.
import React from 'react';
import {AbsoluteFill,Composition,Img,OffthreadVideo,Sequence,registerRoot,staticFile,useCurrentFrame} from 'remotion';
const W=1920,H=1080;
const clamp=(v:number)=>Math.min(1,Math.max(0,v));
const smooth=(t:number)=>t*t*(3-2*t);
// Fractional crop window (zoom, focus) → CSS transform. Sub-pixel by nature.
function camera(seg:any,local:number,length:number){
 const effect=seg?.motion_effect||'none',s=seg?.motion_strength||0;
 if(effect==='none')return {z:1,fx:.5,fy:.5};
 if(seg.camera_curve==='eased'){
  const p=clamp(local/Math.max(1,length-1)),e=.5*p+.25*(1-Math.cos(Math.PI*p)),base=1+(seg.base_zoom||0);
  if(effect==='push_in')return {z:base+s*e,fx:.5,fy:.5};
  if(effect==='push_out')return {z:base+s*(1-e),fx:.5,fy:.5};
  if(effect==='pan_left'||effect==='pan_right')return {z:base+s,fx:.5+(effect==='pan_right'?.35:-.35)*(2*e-1),fy:.5};
  if(effect==='pan_up'||effect==='pan_down')return {z:base+s,fx:.5,fy:.5+(effect==='pan_down'?.35:-.35)*(2*e-1)};
  return {z:base+s*(.5+.5*e),fx:.42+.16*e,fy:.5};
 }
 // neutral_cycle: in-out envelope with neutral framing at both ends.
 const start=Math.max(0,seg.head_hold||0),end=Math.max(start+1,seg.frames-1-Math.max(0,seg.tail_hold||0));
 const p=clamp((local-start)/Math.max(1,end-start)),peak=effect==='push_out'?.35:effect==='push_in'?.65:.5;
 const env=p<peak?smooth(clamp(p/peak)):1-smooth(clamp((p-peak)/(1-peak)));
 const z=1+s*env,amount=effect==='subtle_reframe'?.1:.35,sign=effect==='pan_left'||effect==='pan_up'?-1:1;
 if(['pan_left','pan_right','subtle_reframe'].includes(effect))return {z,fx:.5+sign*amount*env,fy:.5};
 if(effect==='pan_up'||effect==='pan_down')return {z,fx:.5,fy:.5+sign*.35*env};
 return {z,fx:.5,fy:.5};
}
const Media:React.FC<any>=({clip,cam})=>{
 const style:React.CSSProperties={width:'100%',height:'100%',objectFit:clip.fit==='contain'?'contain':'cover'};
 // Portrait/square source: blurred, darkened full-frame copy behind the sharp centre.
 const back:React.CSSProperties={width:'100%',height:'100%',objectFit:'cover',filter:'blur(40px) brightness(0.8)',transform:'scale(1.1)'};
 const left=(W-W/cam.z)*cam.fx,top=(H-H/cam.z)*cam.fy;
 return <AbsoluteFill style={{overflow:'hidden'}}><AbsoluteFill style={{transformOrigin:'0 0',transform:`translate(${-left*cam.z}px,${-top*cam.z}px) scale(${cam.z})`}}>
  {clip.fit==='contain'&&<AbsoluteFill>{clip.type==='video'?<OffthreadVideo src={staticFile(clip.asset)} muted playbackRate={1} startFrom={Math.round((clip.source_in||0)*30)} style={back}/>:<Img src={staticFile(clip.asset)} style={back}/>}</AbsoluteFill>}
  <AbsoluteFill>{clip.type==='video'?<OffthreadVideo src={staticFile(clip.asset)} muted playbackRate={1} startFrom={Math.round((clip.source_in||0)*30)} style={style}/>:<Img src={staticFile(clip.asset)} style={style}/>}</AbsoluteFill>
 </AbsoluteFill></AbsoluteFill>;
};
const Scene:React.FC<any>=({clip,theme})=>{
 const frame=useCurrentFrame(),w=clip.layout_window,within=w&&frame>=Math.round((w.start-clip.start)*30)&&frame<Math.round((w.end-clip.start)*30);
 const segments=clip.segments&&clip.segments.length?clip.segments:[{start_frame:0,end_frame:clip.end_frame-clip.start_frame,frames:clip.end_frame-clip.start_frame,motion_effect:'none'}];
 const index=Math.max(0,segments.findIndex((s:any)=>frame<s.end_frame)),seg=segments[index<0?segments.length-1:index]||segments[segments.length-1];
 const last=seg===segments[segments.length-1],length=seg.frames+(last?(clip.handle||0):0);
 const cam=camera(seg,frame-seg.start_frame,length);
 const light=theme==='clean_light',bg=light?'#eceee8':theme==='soft_documentary'?'#19232d':'#101823',fg=light?'#202020':'white';
 const split=['split_media_text','dual_media'].includes(clip.layout),left=clip.orientation==='left';
 const opacity=w?Math.min(1,Math.max(0,(frame-(w.start-clip.start)*30)/5),Math.max(0,((w.end-clip.start)*30-frame)/5)):1;
 return <AbsoluteFill style={{background:bg}}><Media clip={clip} cam={cam}/>{within&&clip.layout!=='full_broll'&&<>
  {split?<AbsoluteFill style={{display:'flex',flexDirection:left?'row':'row-reverse'}}><div style={{width:'50%',height:'100%',position:'relative',overflow:'hidden'}}><Media clip={clip} cam={cam}/></div><div style={{width:'50%',background:bg,position:'relative',overflow:'hidden'}}>{clip.secondary&&<Media clip={clip.secondary} cam={{z:1,fx:.5,fy:.5}}/>}</div></AbsoluteFill>
    :<div style={{position:'absolute',left:120,right:120,top:clip.layout==='minimal_title'?180:clip.layout==='quote_emphasis'?350:180,height:clip.layout==='minimal_title'?200:clip.layout==='quote_emphasis'?300:720,background:bg,borderLeft:'12px solid #559eaa',opacity:clip.layout==='minimal_title'||clip.layout==='quote_emphasis'?.85:1}}/>}
  {theme==='grid_dark'&&!split&&<AbsoluteFill style={{pointerEvents:'none',backgroundImage:'linear-gradient(#ffffff08 1px,transparent 1px),linear-gradient(90deg,#ffffff08 1px,transparent 1px)',backgroundSize:'120px 120px'}}/>}
  <div style={{position:'absolute',left:split?(left?'50%':'0'):180,width:split?'50%':1560,top:clip.layout==='minimal_title'?220:clip.layout==='quote_emphasis'?390:280,padding:60,boxSizing:'border-box',fontFamily:'Arial,sans-serif',color:fg,textAlign:'center',fontWeight:700,fontSize:54,opacity}}>
   {clip.layout==='big_number'&&<div style={{fontSize:110,marginBottom:50}}>{clip.number}</div>}
   {(clip.texts||[]).map((text:string,i:number)=><div key={i} style={{marginBottom:30}}>{text}</div>)}
  </div></>}
 </AbsoluteFill>;
};
// Transitions mirror the native engine: a crossfade blends the previous
// clip's extra handle frames under the first N frames of the next slot (no
// time added); dark fades dip each side by half the duration.
const Slot:React.FC<any>=({clip,previous,theme})=>{
 const frame=useCurrentFrame(),len=clip.end_frame-clip.start_frame;
 const into=previous?.transition_out,inN=Math.round((previous?.transition_duration||0)*30);
 const outN=Math.round((clip.transition_duration||0)*30);
 let opacity=1;
 if(into==='crossfade'&&inN>=2)opacity=clamp(frame/(inN-1));
 else if(['fade','fade_dark','dip_black'].includes(into)&&inN>=2)opacity=clamp(frame/Math.max(1,Math.round(inN/2)));
 if(['fade','fade_dark','dip_black'].includes(clip.transition_out)&&outN>=2)opacity=Math.min(opacity,clamp((len-frame)/Math.max(1,Math.round(outN/2))));
 return <AbsoluteFill style={{opacity}}><Scene clip={clip} theme={theme}/></AbsoluteFill>;
};
const Film:React.FC<any>=props=>{
 const frame=useCurrentFrame();const cue=props.subtitle_display==='full'?props.subtitles.find((c:any)=>frame>=Math.round(c.start*30)&&frame<Math.round(c.end*30)):null;
 const emphasis=props.subtitle_display!=='none'?(props.emphasis||[]).find((e:any)=>frame>=Math.round(e.start*30)&&frame<Math.round(e.end*30)):null;
 const emphasisOpacity=emphasis?Math.min(1,(frame-emphasis.start*30)/6,(emphasis.end*30-frame)/6):0;
 return <AbsoluteFill style={{background:'black'}}>
  {props.clips.map((c:any,i:number)=><Sequence key={c.slot_id} from={c.start_frame} durationInFrames={c.end_frame-c.start_frame+(c.transition_out==='crossfade'?(c.handle||0):0)}><Slot clip={c} previous={props.clips[i-1]} theme={props.theme}/></Sequence>)}
  {emphasis&&<div style={{position:'absolute',left:emphasis.style==='upper_left'?120:200,right:emphasis.style==='upper_left'?'auto':200,top:110,textAlign:emphasis.style==='upper_left'?'left':'center',color:'white',font:'bold 60px Arial,sans-serif',textShadow:'0 0 12px rgba(0,0,0,.85),2px 2px 2px black',opacity:emphasisOpacity}}>{emphasis.text}</div>}
  {cue&&<div style={{position:'absolute',left:100,right:100,bottom:72,textAlign:'center',color:'white',font:'bold 50px Arial,sans-serif',textShadow:'-2px -2px 1px black,2px 2px 1px black'}}>{cue.text}</div>}
 </AbsoluteFill>;
};
registerRoot(()=> <Composition id="AIVideoStudio" component={Film} width={1920} height={1080} fps={30} durationInFrames={30} calculateMetadata={({props}:any)=>({durationInFrames:props.frames})}/>);
