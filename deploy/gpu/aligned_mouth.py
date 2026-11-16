"""Internal offline compositor for aligned neural video; never replace whole face."""
import numpy as np
class AlignedMouth:
    def __init__(self,original):
        self.original=original
        yy,xx=np.mgrid[329:405,800:956].astype(np.float32)
        radius=((xx-878)/70)**4+((yy-357)/43)**4
        m=np.clip((1-radius)/.45,0,1)*np.clip((yy-329)/8,0,1)
        self.mask=(m*m*(3-2*m))[...,None]
    def apply(self,generated,speech=1):
        if generated.shape[1]!=self.original.shape[1] or generated.shape[0]<405:
            raise ValueError('Neural output must be aligned with the original image')
        alpha=self.mask*float(np.clip(speech,0,1))
        result=self.original.copy()
        a=self.original[329:405,800:956].astype(np.float32)
        b=generated[329:405,800:956].astype(np.float32)
        result[329:405,800:956]=np.clip(a*(1-alpha)+b*alpha,0,255).astype(np.uint8)
        return result
