import cv2,numpy as np,torch,json,time
from pathlib import Path
from src.live_portrait_wrapper import LivePortraitWrapper
from src.config.inference_config import InferenceConfig
from src.utils.human_landmark_runner import LandmarkRunner
from src.utils.crop import crop_image
from src.utils.retargeting_utils import calc_eye_close_ratio
torch.set_num_threads(4);t=time.monotonic()
base=cv2.cvtColor(cv2.imread('/opt/kunyao-musetalk/MuseTalk/zoom-interviewer-listening.png'),cv2.COLOR_BGR2RGB)
runner=LandmarkRunner(ckpt_path='pretrained_weights/liveportrait/landmark.onnx',onnx_provider='cpu')
lmk=runner.run(base[115:415,725:1025])+np.array([725,115]);lmk=runner.run(base,lmk)
np.save('source_landmarks.npy',lmk)
crop=crop_image(base,lmk,dsize=512,scale=2.3,vy_ratio=-.125,flag_do_rot=True)
model=LivePortraitWrapper(InferenceConfig());source=model.prepare_source(crop['img_crop']);info=model.get_kp_info(source);kp=model.transform_keypoint(info);feature=model.extract_feature_3d(source)
ratio=calc_eye_close_ratio(lmk[None]);print('source ratios',ratio,flush=True)
def decode(k):return model.parse_output(model.warp_decode(feature,kp,k)['out'])[0]
neutral=decode(kp)
# Keep source face texture by transferring only the local change from neutral reconstruction.
M=(np.array([[2,0,-1540],[0,2,-370],[0,0,1.]])@crop['M_c2o'])[:2]
def patch(im):return cv2.warpAffine(im.astype(np.float32),M,(440,200),flags=cv2.INTER_CUBIC)
ref=cv2.resize(base[185:285,770:990],(440,200),interpolation=cv2.INTER_CUBIC).astype(float)
neutral_patch=patch(neutral)
y,x=np.indices((200,440));xx=x/2+770;yy=y/2+185
mask=np.zeros((200,440))
for pts in [lmk[:24],lmk[24:48]]:
 cx,cy=pts.mean(0);r=((xx-cx)/43)**4+((yy-(cy-10))/38)**4
 a=np.clip((1-r)/.55,0,1);mask=np.maximum(mask,a*a*(3-2*a))
mask=mask[...,None]
for name,n in [('blink',24),('expression',60)]:
 frames=[];controls=[]
 for i in range(n):
  if name=='blink':
   sequence=[0,0,0,.15,.55,.9,1.,.95,.7,.35,.08,0];amount=sequence[i] if i<len(sequence) else 0
   target=float(ratio.mean())*(1-amount)
   r=torch.tensor([[float(ratio[0,0]),float(ratio[0,1]),target]],device=model.device)
   r0=torch.tensor([[float(ratio[0,0]),float(ratio[0,1]),float(ratio.mean())]],device=model.device)
   delta=model.retarget_eye(kp,r)-model.retarget_eye(kp,r0)
   k=kp+delta
  else:
   amount=float(np.sin(np.pi*i/(n-1))**2)*1.4;k=kp.clone();k[0,1,1]+=amount*.001;k[0,2,1]-=amount*.001
  animated=patch(decode(k))
  edge=np.zeros((200,440),bool);edge[:12]=True;edge[-12:]=True;edge[:,:12]=True;edge[:,-12:]=True
  offset=np.clip((ref[edge]-animated[edge]).mean(0),-25,25)
  strength=min(1,amount*5) if name=='blink' else min(1,amount*2)
  alpha=mask*strength
  result=np.clip(ref*(1-alpha)+(animated+offset)*alpha,0,255).astype(np.uint8)
  if amount==0 or i==n-1:result=ref.astype(np.uint8)
  frames.append(result);controls.append(amount)
 np.save(name+'-patches.npy',np.array(frames));print(name,'saved',len(frames),flush=True)
Path('render-stats.json').write_text(json.dumps({'seconds':time.monotonic()-t,'gpu_peak_gb':torch.cuda.max_memory_allocated()/1e9,'ratios':ratio.tolist()}))
