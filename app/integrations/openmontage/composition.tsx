// Original AI Video Studio projection. No upstream source or template copied.
import React from 'react';
import {AbsoluteFill,Composition,Img,OffthreadVideo,Sequence,registerRoot,staticFile,useCurrentFrame} from 'remotion';
const asset=(clip:any,style:any={})=>clip.type==='video'
  ? <OffthreadVideo src={staticFile(clip.asset)} muted playbackRate={1} startFrom={Math.round(clip.source_in*30)} style={{width:'100%',height:'100%',objectFit:clip.fit==='contain'?'contain':'cover',...style}}/>
  : <Img src={staticFile(clip.asset)} style={{width:'100%',height:'100%',objectFit:clip.fit==='contain'?'contain':'cover',...style}}/>;
const Scene:React.FC<any>=({clip,theme})=>{
 const frame=useCurrentFrame(),w=clip.layout_window,within=w&&frame>=Math.round((w.start-clip.start)*30)&&frame<Math.round((w.end-clip.start)*30);
 const light=theme==='clean_light',bg=light?'#eceee8':theme==='soft_documentary'?'#19232d':'#101823',fg=light?'#202020':'white';
 const split=['split_media_text','dual_media'].includes(clip.layout),left=clip.orientation==='left';
 const opacity=w?Math.min(1,Math.max(0,(frame-(w.start-clip.start)*30)/5),Math.max(0,((w.end-clip.start)*30-frame)/5)):1;
 return <AbsoluteFill style={{background:bg}}>{asset(clip)}{within&&clip.layout!=='full_broll'&&<>
  {split?<AbsoluteFill style={{display:'flex',flexDirection:left?'row':'row-reverse'}}><div style={{width:'50%',height:'100%'}}>{asset(clip)}</div><div style={{width:'50%',background:bg}}>{clip.secondary&&asset(clip.secondary)}</div></AbsoluteFill>
    :<div style={{position:'absolute',left:120,right:120,top:clip.layout==='minimal_title'?180:clip.layout==='quote_emphasis'?350:180,height:clip.layout==='minimal_title'?200:clip.layout==='quote_emphasis'?300:720,background:bg,borderLeft:'12px solid #559eaa'}}/>}
  {theme==='grid_dark'&&!split&&<AbsoluteFill style={{pointerEvents:'none',backgroundImage:'linear-gradient(#ffffff08 1px,transparent 1px),linear-gradient(90deg,#ffffff08 1px,transparent 1px)',backgroundSize:'120px 120px'}}/>}
  <div style={{position:'absolute',left:split?(left?'50%':'0'):180,width:split?'50%':1560,top:clip.layout==='minimal_title'?220:clip.layout==='quote_emphasis'?390:280,padding:60,boxSizing:'border-box',fontFamily:'Arial,sans-serif',color:fg,textAlign:'center',fontSize:54,fontWeight:700,opacity}}>
   {clip.layout==='big_number'&&<div style={{fontSize:110,marginBottom:50}}>{clip.number}</div>}
   {(clip.texts||[]).map((text:string,i:number)=><div key={i} style={{marginBottom:30}}>{text}</div>)}
  </div></>}
 </AbsoluteFill>;
};
const Film:React.FC<any>=props=>{
 const frame=useCurrentFrame();const cue=props.subtitle_display==='full'?props.subtitles.find((c:any)=>frame>=Math.round(c.start*30)&&frame<Math.round(c.end*30)):null;
 return <AbsoluteFill style={{background:'#101823'}}>
  {props.clips.map((c:any)=><Sequence key={c.slot_id} from={c.start_frame} durationInFrames={c.end_frame-c.start_frame}><Scene clip={c} theme={props.theme}/></Sequence>)}
  {cue&&<div style={{position:'absolute',left:100,right:100,bottom:72,textAlign:'center',color:'white',font:'bold 50px Arial,sans-serif',textShadow:'-2px -2px 1px black,2px 2px 1px black'}}>{cue.text}</div>}
 </AbsoluteFill>;
};
registerRoot(()=> <Composition id="AIVideoStudio" component={Film} width={1920} height={1080} fps={30} durationInFrames={30} calculateMetadata={({props}:any)=>({durationInFrames:props.frames})}/>);
