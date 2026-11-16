import unittest
import numpy as np
from continuous_mouth import ContinuousMouth, speech_envelope
class ContinuousMouthTests(unittest.TestCase):
 def test_silence_is_original(self):
  a=np.full((941,1672,3),125,np.uint8);r=ContinuousMouth(a)
  np.testing.assert_array_equal(r.apply(np.zeros((256,256,3),np.uint8),0),a)
 def test_face_outside_mouth_unchanged(self):
  a=np.full((941,1672,3),125,np.uint8);b=ContinuousMouth(a).apply(np.full((256,256,3),200,np.uint8),1)
  np.testing.assert_array_equal(b[:330],a[:330]);np.testing.assert_array_equal(b[390:],a[390:])
  np.testing.assert_array_equal(b[:,:815],a[:,:815]);np.testing.assert_array_equal(b[:,942:],a[:,942:])
 def test_gate_closes_during_long_pause_and_opens_for_speech(self):
  a=np.r_[np.zeros(24000),np.ones(24000)*.12,np.zeros(24000)]
  gate=speech_envelope(a,24000,25,75)
  self.assertTrue(np.all(gate[:23]==0));self.assertGreater(gate[30],.99);self.assertEqual(gate[-1],0)
if __name__=='__main__':unittest.main()
