"""Rebuild the approved loop from source with bounded luma detail enhancement.
No generative restoration, interpolation, face replacement, or teeth whitening.
Run with Python containing cv2, numpy and imageio_ffmpeg.
"""
import argparse, pathlib, sys, subprocess
import cv2
import numpy as np
import imageio_ffmpeg
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy/gpu'))
from aligned_mouth import AlignedMouth

def detail(frame):
    f=frame.astype(np.float32)
    luma=.114*f[:,:,0]+.587*f[:,:,1]+.299*f[:,:,2]
    residual=luma-cv2.GaussianBlur(luma,(5,5),.8)
    # Suppress tiny codec fluctuations; cap contrast adjustment at 6/255.
    delta=np.clip(np.sign(residual)*np.maximum(np.abs(residual)-1.5,0)*.55,-6,6)
    y,x=np.indices(luma.shape)
    spatial=np.clip(1-((x-96)/69)**4-((y-52)/32)**4,0,1)
    spatial=spatial*spatial*(3-2*spatial)
    return np.clip(f+(delta*spatial)[:,:,None],0,255).astype(np.uint8)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('output');args=ap.parse_args()
    base=cv2.imread(str(ROOT/'frontend/public/zoom-interviewer-listening.png'))
    blend=AlignedMouth(base);cap=cv2.VideoCapture(args.source);frames=[]
    # Same approved 1.08..6.96s motion, followed by its reverse.
    for i in range(174):
        ok,f=cap.read();assert ok
        if i>=27:frames.append(detail(blend.apply(f)[311:423,782:974]))
    cap.release();loop=frames+frames[-2:0:-1]
    cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-f','rawvideo','-pix_fmt','bgr24','-s','192x112','-r','25','-i','pipe:0','-an','-vf','scale=out_color_matrix=bt709:out_range=tv','-c:v','libx264','-preset','slow','-crf','12','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv','-movflags','+faststart',args.output]
    p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    for f in loop:p.stdin.write(f.tobytes())
    p.stdin.close();assert p.wait()==0
    print({'frames':len(loop),'seconds':len(loop)/25,'bytes':pathlib.Path(args.output).stat().st_size})
if __name__=='__main__':main()
