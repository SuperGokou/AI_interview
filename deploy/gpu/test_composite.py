import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('mouth_composite',Path(__file__).with_name('mouth_composite.py'))
module=importlib.util.module_from_spec(spec)
if Path(spec.origin).exists(): spec.loader.exec_module(module)

class CompositeTests(unittest.TestCase):
    def make(self):
        self.assertTrue(hasattr(module,'MouthComposite'),'Mouth compositor is missing')
        return module.MouthComposite(np.full((941,1672,3),180,dtype=np.uint8))

    def test_nose_eyes_cheeks_and_background_are_unchanged(self):
        compositor=self.make()
        result=compositor.apply(np.zeros((280,240,3),dtype=np.uint8))
        np.testing.assert_array_equal(result[:330],180)
        np.testing.assert_array_equal(result[383:],180)
        np.testing.assert_array_equal(result[:,:820],180)
        np.testing.assert_array_equal(result[:,937:],180)

    def test_generated_lips_align_with_original_lip_center(self):
        compositor=self.make()
        patch=np.full((280,240,3),180,dtype=np.uint8)
        # Generated center is x=883,y=358; original center is x=878,y=350.
        patch[358-139-5:358-139+6,883-750-20:883-750+21]=[70,70,200]
        result=compositor.apply(patch)
        weight=np.maximum(result[:,:,2].astype(float)-result[:,:,1]-30,0)
        y,x=np.indices(weight.shape)
        self.assertAlmostEqual(float((weight*x).sum()/weight.sum()),878,delta=1)
        self.assertAlmostEqual(float((weight*y).sum()/weight.sum()),350,delta=1)

if __name__=='__main__': unittest.main()
