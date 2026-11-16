from pathlib import Path
import cv2,numpy as np,subprocess,imageio_ffmpeg,json,argparse
parser=argparse.ArgumentParser(description='Pack matching full-face listening/talking footage on one playback clock.')
parser.add_argument('source_dir',type=Path,help='Directory containing fullface-motion.mp4 and fullface-lipsync.mp4')
parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'frontend/public/interviewer-continuous-v1.mp4')
args=parser.parse_args();root=args.source_dir;out=args.output
out.parent.mkdir(parents=True,exist_ok=True)
caps=[cv2.VideoCapture(str(root/n)) for n in ['fullface-motion.mp4','fullface-lipsync.mp4']]
heads=[[],[]]
for c in caps:c.set(cv2.CAP_PROP_POS_FRAMES,25)
w,h=1672,942
cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-f','rawvideo','-pix_fmt','bgr24','-s',f'{w*2}x{h}','-r','25','-i','-','-an','-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=open(root/'runtime-encode.log','w'))
for i in range(150):
    frames=[]
    for j,c in enumerate(caps):
        ok,f=c.read();assert ok,(i,j)
        assert f.shape[:2]==(h,w),f.shape
        if i<8:heads[j].append(f.copy())
        if i>=142:
            weight=(i-141)/9
            f=cv2.addWeighted(f,1-weight,heads[j][i-142],weight,0)
        frames.append(f)
    if i>=8:p.stdin.write(np.concatenate(frames,axis=1).tobytes())
p.stdin.close();assert p.wait()==0
for c in caps:c.release()
print(json.dumps({'file':str(out),'frames':142,'fps':25,'seconds':142/25,'width':3344,'height':942,'audio':False,'bytes':out.stat().st_size}))
