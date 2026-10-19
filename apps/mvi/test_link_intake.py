import unittest
from link_intake import video_id
class LinkTest(unittest.TestCase):
 def test_watch(self):self.assertEqual(video_id('https://www.youtube.com/watch?v=dqDqeht_FOE'),'dqDqeht_FOE')
 def test_short(self):self.assertEqual(video_id('https://youtu.be/dqDqeht_FOE'),'dqDqeht_FOE')
 def test_untrusted_domain(self):
  with self.assertRaises(ValueError):video_id('https://youtube.com.evil.test/watch?v=dqDqeht_FOE')
if __name__=='__main__':unittest.main()
