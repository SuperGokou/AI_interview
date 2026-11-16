import unittest
import numpy as np
from aligned_mouth import AlignedMouth
class AlignedMouthTests(unittest.TestCase):
 def test_silence_preserves_identity_exactly(self):
  a=np.full((941,1672,3),100,np.uint8);b=np.full((942,1672,3),200,np.uint8)
  np.testing.assert_array_equal(AlignedMouth(a).apply(b,0),a)
 def test_neural_output_cannot_change_eyes_nose_or_body(self):
  a=np.full((941,1672,3),100,np.uint8);b=np.full((942,1672,3),200,np.uint8)
  out=AlignedMouth(a).apply(b,1)
  self.assertEqual(out[350,878,0],200)
  for region in [(slice(None,329),slice(None)),(slice(405,None),slice(None)),(slice(None),slice(None,800)),(slice(None),slice(956,None))]:
   np.testing.assert_array_equal(out[region],a[region])
if __name__=='__main__':unittest.main()
