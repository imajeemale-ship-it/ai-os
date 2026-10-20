import sqlite3,tempfile,unittest
from pathlib import Path
from durable_queue import DurableQueue
from deployment.backup_queue import backup

class QueueBackupTests(unittest.TestCase):
 def test_snapshot_is_consistent_and_does_not_overwrite(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);db=root/'private'/'queue.db';q=DurableQueue(db)
   q.enqueue('job-1','upload',{'filename':'upload.mp4'})
   dest=root/'backups'/'snapshot.db'
   backup(db,dest)
   self.assertEqual(dest.stat().st_mode & 0o777,0o600)
   q.enqueue('job-2','upload',{'filename':'upload.mp4'})
   with sqlite3.connect(dest) as conn:
    self.assertEqual(conn.execute('select count(*) from jobs').fetchone()[0],1)
    self.assertEqual(conn.execute('pragma integrity_check').fetchone()[0],'ok')
   with self.assertRaises(FileExistsError):backup(db,dest)
   self.assertEqual(q.get('job-2')['status'],'queued')
 def test_missing_source_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(FileNotFoundError):backup(Path(tmp)/'missing.db',Path(tmp)/'out.db')

if __name__=='__main__':unittest.main()
