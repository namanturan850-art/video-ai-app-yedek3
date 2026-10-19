// NAMAN HTML/CSS overlay layer. Original NAMAN code; no upstream template copied.
// Input is already sanitized by app/motion/html_layer.py (no script, URL or
// event handler). Each frame pauses every CSS animation at that frame's exact
// time, so the same frame index always produces the same picture.
import React,{useLayoutEffect,useRef} from 'react';
import {AbsoluteFill,Composition,continueRender,delayRender,registerRoot,useCurrentFrame,useVideoConfig} from 'remotion';

type Props={html:string;css:string;frames:number;fonts?:string};

const Layer:React.FC<Props>=({html,css,fonts})=>{
  const frame=useCurrentFrame();
  const {fps}=useVideoConfig();
  const root=useRef<HTMLDivElement>(null);
  useLayoutEffect(()=>{
    const handle=delayRender('naman-html-layer-frame');
    const node=root.current;
    if(node){
      const time=frame/fps*1000;
      for(const animation of node.getAnimations({subtree:true})){animation.pause();animation.currentTime=time;}
    }
    // Fonts are embedded @font-face data (see app/motion/fonts.py); wait until they are usable, then one
    // painted frame after seeking, and only then may the renderer capture it.
    const set=(document as any).fonts;
    const loading=set?Promise.all(Array.from(set as Iterable<any>).map((face:any)=>face.load().catch(()=>undefined))).then(()=>set.ready):Promise.resolve();
    Promise.resolve(loading).catch(()=>undefined).then(()=>requestAnimationFrame(()=>continueRender(handle)));
  },[frame,fps,html,css,fonts]);
  return (
    <AbsoluteFill style={{background:'transparent'}}>
      {/* Animations never run on wall-clock time: a frame captured before the
          seek below still shows time 0, not a few milliseconds of playback. */}
      <style>{(fonts||'')+css+'\n*,*::before,*::after{animation-play-state:paused!important}'}</style>
      <div ref={root} style={{position:'relative',width:1920,height:1080,overflow:'hidden'}}
           dangerouslySetInnerHTML={{__html:html}}/>
    </AbsoluteFill>
  );
};

const Root:React.FC=()=>(
  <Composition id="NAMANHtmlLayer" component={Layer} fps={30} width={1920} height={1080} durationInFrames={1}
    defaultProps={{html:'',css:'',frames:1,fonts:''}}
    calculateMetadata={({props})=>({durationInFrames:Math.max(1,Math.round(props.frames))})}/>
);

registerRoot(Root);
