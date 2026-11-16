import importlib.util
from pathlib import Path
import unittest
import numpy as np
spec=importlib.util.spec_from_file_location('identity_mouth',Path(__file__).with_name('identity_mouth.py'))
module=importlib.util.module_from_spec(spec)
if Path(spec.origin).exists():spec.loader.exec_module(module)
class OriginalLipsTests(unittest.TestCase):
 def renderer(self):
  self.assertTrue(hasattr(module,'OriginalLips'),'Original-lip renderer is missing')
  rng=np.random.default_rng(5)
  self.original=rng.integers(0,256,(941,1672,3),dtype=np.uint8)
  return module.OriginalLips(self.original,self.original)
 def test_closed_pose_is_exact_original(self):
  r=self.renderer()
  np.testing.assert_array_equal(r.frame(0),self.original)
 def test_nose_and_face_are_never_replaced(self):
  r=self.renderer();output=r.frame(1)
  np.testing.assert_array_equal(output[:331],self.original[:331])
  np.testing.assert_array_equal(output[385:],self.original[385:])
  np.testing.assert_array_equal(output[:,:820],self.original[:,:820])
  np.testing.assert_array_equal(output[:,937:],self.original[:,937:])
 def test_model_aperture_distinguishes_closed_from_speech(self):
  # Current portrait: three dark rows remain at rest, seven during speech.
  patch=np.full((280,240,3),(130,140,170),dtype=np.uint8)
  patch[210:213,105:157]=40
  self.assertEqual(module.OriginalLips.model_opening(patch),0)
  patch[210:217,105:157]=40
  self.assertGreaterEqual(module.OriginalLips.model_opening(patch),.95)
 def test_opening_is_bounded(self):
  r=self.renderer()
  np.testing.assert_array_equal(r.frame(100),r.frame(1))
  np.testing.assert_array_equal(r.frame(-1),self.original)
if __name__=='__main__':unittest.main()
