"""Queue payloads must not read files outside the job directory."""
import tempfile,unittest
from pathlib import Path
from durable_runtime import process

class DurableUploadSecurityTests(unittest.TestCase):
 def test_rejects_relative_path_escape(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);job='c'*32;(root/job).mkdir()
   claim={'job_id':job,'attempt':1,'kind':'upload',
          'payload':{'filename':'../../private.env','title':'escape'}}
   with self.assertRaisesRegex(ValueError,'Unsupported queued upload filename'):
    process(root,claim)
 def test_rejects_symlinked_upload(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);job='d'*32;(root/job).mkdir()
   secret=root/'secret';secret.write_text('private')
   (root/job/'upload.mp4').symlink_to(secret)
   claim={'job_id':job,'attempt':1,'kind':'upload',
          'payload':{'filename':'upload.mp4','title':'escape'}}
   with self.assertRaisesRegex(FileNotFoundError,'missing'):
    process(root,claim)

if __name__=='__main__':unittest.main()
