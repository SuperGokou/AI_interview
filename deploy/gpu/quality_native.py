"""Offline experiment: preserve native decoded mouth details before full-frame downsampling."""
import time,json,sys,runpy,cv2,numpy as np,torch,subprocess
from pathlib import Path
from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline
torch.set_num_threads(4)
old=LipsyncPipeline.restore_video

def restore(self,faces,video_frames,boxes,matrices):
    np.savez("quality-native-decoded.npz", faces=faces.detach().cpu().numpy(), matrices=np.array([a.detach().cpu().numpy() if torch.is_tensor(a) else a for a in matrices]), boxes=np.array(boxes))
    patches=[]
    base=cv2.cvtColor(cv2.imread('/opt/kunyao-musetalk/MuseTalk/zoom-interviewer-listening.png'),cv2.COLOR_BGR2RGB)
    background=cv2.resize(base[311:423,782:974],(384,224),interpolation=cv2.INTER_CUBIC).astype(np.float32)
    yy,xx=np.mgrid[0:224,0:384].astype(np.float32);xx=xx/2+782;yy=yy/2+311
    rad=((xx-878)/70)**4+((yy-357)/43)**4
    mask=np.clip((1-rad)/.45,0,1)*np.clip((yy-329)/8,0,1);mask=(mask*mask*(3-2*mask))[...,None]
    for face,box,A in zip(faces,boxes,matrices):
        rgb=((face.float().permute(1,2,0).cpu().numpy()/2+.5)*255).clip(0,255)
        w,h=box[2]-box[0],box[3]-box[1]
        S=np.array([[w/512,0,(w/512-1)/2],[0,h/512,(h/512-1)/2],[0,0,1.]])
        A=np.asarray(A.detach().cpu().numpy() if torch.is_tensor(A) else A,dtype=np.float32).reshape(2,3)
        inv=np.vstack([cv2.invertAffineTransform(A),[0,0,1.]])
        crop=np.array([[2,0,-1564],[0,2,-622],[0,0,1.]])
        M=(crop@inv@S)[:2]
        patch=cv2.warpAffine(rgb,M,(384,224),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
        patches.append((background*(1-mask)+patch*mask).clip(0,255).astype(np.uint8))
    np.save('quality-native-patches.npy',np.stack(patches))
    print('Native mouth patches saved',len(patches),flush=True)
    return old(self,faces,video_frames,boxes,matrices)
LipsyncPipeline.restore_video=restore
sys.argv=['inference','--unet_config_path','configs/unet/stage2_512.yaml','--inference_ckpt_path','checkpoints/latentsync_unet.pt','--inference_steps','40','--guidance_scale','1.5','--video_path','input-still.mp4','--audio_path','test-pauses.wav','--video_out_path','quality-native.mp4','--temp_dir','temp-quality-native']
t=time.monotonic();runpy.run_module('scripts.inference',run_name='__main__')
Path('quality-native-stats.json').write_text(json.dumps({'render_seconds':time.monotonic()-t,'gpu_peak_gb':torch.cuda.max_memory_allocated()/1e9}))
