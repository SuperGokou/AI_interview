"""Experimental continuous lip compositor, calibrated for the original portrait.
Internal evaluation only; not selected by the live service.
"""
import cv2
import numpy as np

def speech_envelope(audio, sample_rate, fps, count):
    energy=np.zeros(count)
    for i in range(count):
        block=audio[int(i*sample_rate/fps):int((i+1)*sample_rate/fps)]
        if len(block): energy[i]=np.sqrt(np.mean(block.astype(np.float64)**2))
    # Short release prevents rapid flashes between syllables, closes in pauses.
    active=energy>.008
    gate=np.zeros(count);level=0.
    for i in range(count):
        target=float(active[i] or (i+1<count and active[i+1]))
        level=min(1.,level+.6) if target else max(0.,level-.25)
        gate[i]=level
    return gate

class ContinuousMouth:
    box=(750,190,990,419)
    def __init__(self, original):
        self.original=original
        yy,xx=np.mgrid[330:390,815:942].astype(np.float32)
        radius=((xx-878)/65)**4+((yy-353)/34)**4
        m=np.clip((1-radius)/.45,0,1)*np.clip((yy-330)/7,0,1)
        self.mask=(m*m*(3-2*m))[...,None]
        self.mx=xx-750+4.4;self.my=(yy-351)/.9+355.1-190
    def apply(self, generated, speech=1.):
        speech=float(np.clip(speech,0,1))
        if speech==0:return self.original.copy()
        patch=cv2.resize(generated,(240,229),interpolation=cv2.INTER_CUBIC)
        patch=cv2.remap(patch,self.mx,self.my,cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT_101).astype(np.float32)
        original=self.original[330:390,815:942].astype(np.float32)
        # Match only surrounding skin; preserve generated lip and tooth geometry.
        ring=(self.mask[...,0]>.03)&(self.mask[...,0]<.35)
        offset=np.median(original[ring]-patch[ring],axis=0)
        patch=np.clip(patch+np.clip(offset,-12,12),0,255)
        alpha=self.mask*speech
        result=self.original.copy()
        result[330:390,815:942]=np.clip(original*(1-alpha)+patch*alpha,0,255).astype(np.uint8)
        return result
