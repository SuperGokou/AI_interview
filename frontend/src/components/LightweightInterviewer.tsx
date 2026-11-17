import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import { mouthExpression, smoothMouth } from '../lib/mouthExpression';

/** Retains the original interviewer. Only her own mouth region is blended
 * from the existing preview clip, using the actual output-audio envelope. */
export default function LightweightInterviewer({ mouthOpeningRef }: { mouthOpeningRef?: MutableRefObject<number> }) {
  const host = useRef<HTMLDivElement>(null);
  const mouth = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({width:1672,height:941});
  useEffect(() => {
    const element=host.current;if(!element || typeof ResizeObserver === 'undefined')return;
    const observer=new ResizeObserver(([entry])=>{
      const width=Math.max(entry.contentRect.width,entry.contentRect.height*1672/941);
      setSize({width,height:width*941/1672});
    });observer.observe(element);return()=>observer.disconnect();
  },[]);
  useEffect(() => {
    const canvas=mouth.current, ctx=canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    let frame=0, disposed=false, opening=0, previousTime=0;
    const image=new Image();image.src='/interviewer-mouth-open.png';
    const patch=document.createElement('canvas');patch.width=168;patch.height=112;
    const paint=patch.getContext('2d');if(!paint)return;
    const tick = (now: number) => {
      if(disposed)return;
      opening=smoothMouth(opening,mouthOpeningRef?.current ?? 0,previousTime ? (now-previousTime)/1000 : 1/60);
      previousTime=now;
      const pose=mouthExpression(opening);
      ctx.clearRect(0,0,168,112);
      if(pose.visible && image.complete && image.naturalWidth){
        paint.clearRect(0,0,168,112);
        // Warp the original performer's mouth pixels around the lip line.
        // Continuous feathered transition avoids threshold flashes in quiet syllables.
        for(let y=0;y<112;y++){
          const sourceY=352+(300+y-346-pose.jawDrop)/pose.height;
          paint.drawImage(image,876-84/pose.width,sourceY,168/pose.width,1/pose.height,0,y,168,1);
        }
        ctx.globalAlpha=pose.opacity;
        ctx.drawImage(patch,0,0);
        ctx.globalAlpha=1;
        ctx.globalCompositeOperation='destination-in';
        ctx.save();ctx.translate(84,55);ctx.scale(1,.38);
        const feather=ctx.createRadialGradient(0,0,42,0,0,68);
        feather.addColorStop(0,'rgba(0,0,0,1)');feather.addColorStop(1,'rgba(0,0,0,0)');
        ctx.fillStyle=feather;ctx.fillRect(-84,-148,168,296);ctx.restore();
        ctx.globalCompositeOperation='source-over';
      }
      frame=requestAnimationFrame(tick);
    };
    frame=requestAnimationFrame(tick);
    return()=>{disposed=true;cancelAnimationFrame(frame);};
  }, [mouthOpeningRef]);
  return <div ref={host} className="absolute inset-0 overflow-hidden" aria-label="坤曜轻量口型数字人">
    <div style={{...size,position:'absolute',top:0,left:'50%',transform:'translateX(-50%)'}}>
      <img src="/zoom-interviewer-listening.png" alt="坤曜 AI 面试官" className="absolute inset-0 h-full w-full" draggable={false}/>
      <canvas ref={mouth} width={168} height={112} aria-hidden="true" style={{position:'absolute',left:`${792/1672*100}%`,top:`${300/941*100}%`,width:`${168/1672*100}%`,height:`${112/941*100}%`}}/>
    </div>
  </div>;
}
