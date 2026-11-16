"""Animate the interviewer's original lip texture, without generated face pixels."""
import cv2
import numpy as np

class OriginalLips:
    def __init__(self, original, talking):
        self.original=original
        self.talking=talking
        self.x1,self.y1,self.x2,self.y2=820,331,937,385
        self.yy,self.xx=np.mgrid[self.y1:self.y2,self.x1:self.x2].astype(np.float32)
        dx=(self.xx-877)/44
        self.seam=347.5-4.8*np.minimum(dx*dx,1)
        self.side=np.maximum(1-dx*dx,0)**.8

    def frame(self, amount):
        amount=float(np.clip(amount,0,1))
        if amount<=0: return self.original.copy()
        gap=16*amount*self.side
        upper=self.seam-.25*gap
        lower=self.seam+.75*gap
        up=np.clip((self.yy-self.y1)/np.maximum(upper-self.y1,1),0,1)
        down=np.clip((self.y2-1-self.yy)/np.maximum(self.y2-1-lower,1),0,1)
        sy=np.where(self.yy<self.seam,self.yy+.25*gap*up,self.yy-.75*gap*down)
        warped=cv2.remap(self.original,self.xx,sy.astype(np.float32),cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT_101)
        # Only the thin mouth interior uses pixels from her own existing clip.
        vertical=np.clip((self.yy-upper)/np.maximum(gap,.01),0,1)
        reveal=np.clip((amount-.12)/.45,0,1)
        inner_y=(353+vertical*3)*(1-reveal)+(348+vertical*8)*reveal
        inner=cv2.remap(self.talking,self.xx,inner_y.astype(np.float32),cv2.INTER_LINEAR)
        inner=(inner.astype(np.float32)*.86)
        inside=np.minimum(self.yy-upper,lower-self.yy)
        alpha=np.clip(inside/.7,0,1)[...,None]
        result=self.original.copy()
        result[self.y1:self.y2,self.x1:self.x2]=np.clip(warped*(1-alpha)+inner*alpha,0,255).astype(np.uint8)
        return result

    @staticmethod
    def model_opening(patch):
        # Extract aperture only. Never transfer the model's lips, skin or teeth.
        roi=patch[203:240,105:157].astype(np.float32)
        b,g,r=cv2.split(roi)
        dark=(r<115)&(g<100)&(b<105)
        teeth=(g>155)&(np.abs(r-g)<30)&(np.abs(g-b)<35)
        row_fraction=(dark|teeth).mean(axis=1)
        return float(np.clip(((row_fraction>.22).sum()-3)/4,0,1))
