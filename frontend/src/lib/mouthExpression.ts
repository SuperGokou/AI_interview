/** Continuous acoustic lip geometry, not phoneme recognition. */
export function mouthExpression(value: number) {
  const amount=Number.isFinite(value)?Math.max(0,Math.min(.9,value)):0;
  const strength=Math.pow(amount/.9,.65);
  const blend=Math.min(1,amount/.28);
  const opacity=blend*blend*(3-2*blend);
  return {visible:opacity>.0001,opacity,width:1,
    height:.46+.12*strength,jawDrop:1.5*strength};
}
/** Frame-rate independent motion; brief energy dips must not snap the lips shut. */
export function smoothMouth(previous:number,target:number,dt:number){
 const safe=Number.isFinite(target)?Math.max(0,Math.min(.9,target)):0;
 const elapsed=Math.min(.05,Math.max(0,dt));
 return previous+(safe-previous)*(1-Math.exp(-elapsed/(safe>previous?.055:.095)));
}
