"""MuseTalk 1.5 fixed-portrait inference. Run from the checked-out MuseTalk directory.

Modes:
  lower_face     (default) the model's mouth, jaw and chin feathered into the portrait,
                 faded out during silence. Clear articulation.
  original_lips  the portrait's own lip pixels warped by the model's mouth aperture.
                 Sharpest, but the mouth barely moves.
Pixels above the nose, hair, clothes and background are always the original portrait.
"""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path
import cv2
import numpy as np
import soundfile
import torch
from transformers import WhisperModel
from musetalk.utils.utils import load_all_model, datagen
from musetalk.utils.audio_processor import AudioProcessor
from continuous_mouth import speech_envelope
from identity_mouth import OriginalLips
from lower_face import LowerFace

MODES = ('lower_face', 'original_lips')
FPS = 25

class PortraitRenderer:
    def __init__(self, portrait, mode='lower_face'):
        if mode not in MODES:
            raise ValueError(f'mode must be one of {MODES}')
        self.mode = mode
        torch.set_num_threads(4)
        torch.manual_seed(42)
        self.device = torch.device('cuda:0')
        self.vae, self.unet, self.pe = load_all_model(device=self.device)
        self.vae.vae.half()
        self.unet.model.half()
        self.pe = self.pe.half().to(self.device)
        self.whisper = WhisperModel.from_pretrained('models/whisper').half().to(self.device).eval()
        self.processor = AudioProcessor('models/whisper')
        self.frame = cv2.imread(str(portrait))
        if self.frame is None or self.frame.shape[:2] != (941, 1672):
            raise ValueError('Expected the original 1672x941 interviewer portrait')
        self.box = (750, 139, 990, 419)
        x1,y1,x2,y2 = self.box
        crop = cv2.resize(self.frame[y1:y2,x1:x2], (256,256))
        with torch.inference_mode():
            self.latent = self.vae.get_latents_for_unet(crop)
        talking = cv2.imread('interviewer-mouth-open.png')
        if talking is None or talking.shape[1] != 1672 or talking.shape[0] not in (940, 941, 942):
            raise ValueError('Original interviewer talking reference is required')
        self.compositor = OriginalLips(self.frame, talking)
        self.lower_face = LowerFace(self.frame, self.box)
        self.steps = torch.tensor([0],device=self.device)

    @torch.inference_mode()
    def render(self,audio,output):
        start=time.monotonic()
        features,length=self.processor.get_audio_feature(str(audio),weight_dtype=torch.float16)
        chunks=self.processor.get_whisper_chunk(features,self.device,torch.float16,self.whisper,length,fps=FPS)
        gate=self._speech_gate(audio,len(chunks))
        output=Path(output)
        output.parent.mkdir(parents=True,exist_ok=True)
        # 941 is odd; pad one row rather than stretch the original image.
        cmd=['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','bgr24','-s','1672x941','-r','25','-i','pipe:0','-i',str(audio),'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p','-c:a','aac','-shortest','-movflags','+faststart',str(output)]
        encoder=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        count=0
        opening=0.0
        raw_frames=[] if os.environ.get("MOUTH_DUMP") else None
        x1,y1,x2,y2=self.box
        try:
            for audio_batch,latent_batch in datagen(chunks,[self.latent],batch_size=16):
                emb=self.pe(audio_batch.to(self.device))
                pred=self.unet.model(latent_batch.to(self.device,dtype=torch.float16),self.steps,encoder_hidden_states=emb).sample
                for result in self.vae.decode_latents(pred):
                    if raw_frames is not None: raw_frames.append(result.copy())
                    if self.mode=='lower_face':
                        patch=cv2.resize(result,(x2-x1,y2-y1),interpolation=cv2.INTER_CUBIC)
                        frame=self.lower_face.apply(patch,gate[count] if count<len(gate) else 0.)
                    else:
                        patch=cv2.resize(result,(x2-x1,y2-y1))
                        target=self.compositor.model_opening(patch)
                        opening+=(target-opening)*(.5 if target>opening else .35)
                        frame=self.compositor.frame(opening)
                    encoder.stdin.write(frame.tobytes())
                    count+=1
        finally:
            encoder.stdin.close()
        if encoder.wait()!=0:
            raise RuntimeError('Video encoding failed')
        if raw_frames is not None: np.savez_compressed(os.environ["MOUTH_DUMP"],frames=np.stack(raw_frames))
        elapsed=time.monotonic()-start
        stats={'mode':self.mode,'frames':count,'duration_s':count/25,'render_s':round(elapsed,3),'fps':round(count/elapsed,2),'output':str(output)}
        print(json.dumps(stats),flush=True)
        return stats

    @staticmethod
    def _speech_gate(audio,count):
        """Per-frame 0..1 level: 1 while someone is speaking, easing to 0 in pauses."""
        samples,rate=soundfile.read(str(audio),dtype='float32',always_2d=True)
        return speech_envelope(samples.mean(axis=1),rate,FPS,count)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--portrait',required=True)
    parser.add_argument('--audio',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--repeat',type=int,default=1)
    parser.add_argument('--mode',choices=MODES,default='lower_face')
    args=parser.parse_args()
    renderer=PortraitRenderer(args.portrait,args.mode)
    for _ in range(args.repeat):
        renderer.render(args.audio,args.output)
