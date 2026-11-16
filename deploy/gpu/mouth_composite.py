"""Calibrated mouth-only blend for the original Kunyao portrait."""
import cv2
import numpy as np

class MouthComposite:
    box=(750,139,990,419)
    def __init__(self,frame):
        self.frame=frame
        x1,y1,x2,y2=self.box
        self.original=frame[y1:y2,x1:x2].astype(np.float32)
        yy,xx=np.mgrid[y1:y2,x1:x2].astype(np.float32)
        radius=((xx-878)/57)**2+((yy-350)/32)**2
        alpha=np.clip((1-radius)/.5,0,1)
        top=np.clip((yy-330)/5,0,1)
        alpha*=top*top*(3-2*top)
        self.mask=(alpha*alpha*(3-2*alpha))[...,None]
        self.mapx=xx+5-x1
        self.mapy=(yy-350)/.78+358-y1

    def apply(self,patch):
        patch=cv2.remap(patch,self.mapx,self.mapy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
        result=self.frame.copy()
        x1,y1,x2,y2=self.box
        result[y1:y2,x1:x2]=np.clip(self.original*(1-self.mask)+patch*self.mask,0,255).astype(np.uint8)
        return result
