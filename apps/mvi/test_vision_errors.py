import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO
from vision import evaluate
from PIL import Image
class VisionTests(unittest.TestCase):
 def test_http_error_reports_body(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);Image.new('RGB',(100,80)).save(p/'a.jpg');(p/'report.json').write_text(json.dumps({'frames':[{'file':'a.jpg','timestamp_seconds':1}]}))
   with patch('vision.urllib.request.urlopen',side_effect=HTTPError('x',400,'bad',{},BytesIO(b'{"error":"model cannot allocate memory"}'))):
    with self.assertRaisesRegex(RuntimeError,'cannot allocate memory'):evaluate(p)
if __name__=='__main__':unittest.main()
