"""Encode native mouth patches using a forward-only loop with matched endpoints."""
import argparse,json,pathlib,subprocess
import cv2,numpy as np,imageio_ffmpeg
p=argparse.ArgumentParser();p.add_argument('patches');p.add_argument('output');args=p.parse_args()
f=np.load(args.patches);assert f.ndim==4 and f.shape[1:]==(224,384,3)
# Choose a naturally matching seam, preserving at least four seconds of speech.
small=np.array([cv2.cvtColor(cv2.resize(a,(96,56)),cv2.COLOR_RGB2GRAY)[12:42,16:80] for a in f]).astype(float)
best=None
for start in range(27,51):
 for end in range(max(start+100,135),175):
  seam=np.abs(small[start]-small[end]).mean()
  velocity=np.abs((small[start+1]-small[start])-(small[end]-small[end-1])).mean()
  score=seam+.35*velocity
  if best is None or score<best[0]:best=(score,start,end,seam)
_,start,end,seam=best;loop=f[start:end+1]
# No reverse playback or frame interpolation; avoids a conspicuous backwards gesture.
cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','384x224','-r','25','-i','pipe:0','-an','-vf','scale=out_color_matrix=bt709:out_range=tv','-c:v','libx264','-preset','slow','-crf','12','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv','-movflags','+faststart',args.output]
p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
for frame in loop:p.stdin.write(frame.tobytes())
p.stdin.close();assert p.wait()==0
print(json.dumps({'start_frame':start,'end_frame':end,'duration':len(loop)/25,'seam_luma_mae':seam,'regular_frame_mae_p95':float(np.percentile(np.abs(np.diff(small[start:end+1],axis=0)).mean((1,2)),95)),'bytes':pathlib.Path(args.output).stat().st_size},indent=2))
