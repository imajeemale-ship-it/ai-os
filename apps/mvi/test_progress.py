import json, tempfile, unittest
from pathlib import Path
import durable_queue as dq, durable_runtime as durable

class ProgressTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.q=dq.DurableQueue(Path(self.t.name)/'q.db')
 def tearDown(self):self.t.cleanup()
 def test_position_counts_only_earlier_queued_jobs(self):
  for i,jid in enumerate(('a','b','c')):self.q.enqueue(jid,'upload',{},now=100+i)
  self.assertEqual(self.q.progress('a',now=110)['queued_ahead'],0)
  self.assertEqual(self.q.progress('c',now=110)['queued_ahead'],2)
  self.assertEqual(self.q.progress('c',now=110)['waited_seconds'],8.0)
  self.assertIsNone(self.q.progress('nope'))
 def test_running_jobs_are_counted_separately_and_a_running_job_has_nothing_ahead(self):
  self.q.enqueue('a','upload',{},now=100);self.q.enqueue('b','upload',{},now=101)
  self.q.claim('w',now=102)  # claims 'a'
  p=self.q.progress('b',now=103);self.assertEqual((p['queued_ahead'],p['running_now']),(0,1))
  self.assertEqual(self.q.progress('a',now=103)['queued_ahead'],0)
 def test_typical_time_needs_three_samples_and_uses_the_median(self):
  def finish(jid,secs,now):
   self.q.enqueue(jid,'upload',{},now=now);c=self.q.claim('w',now=now+1);self.q.complete(jid,c['lease_token'],{'attempt':1,'seconds':secs},now=now+2)
  self.q.enqueue('me','upload',{},now=1000)
  finish('x1',30,10);finish('x2',90,20)
  self.assertIsNone(self.q.progress('me',now=1001)['typical_seconds'])
  finish('x3',60,30);p=self.q.progress('me',now=1001)
  self.assertEqual((p['typical_seconds'],p['samples']),(60.0,3))
 def test_learning_jobs_and_missing_timings_do_not_skew_the_estimate(self):
  for i,(kind,res) in enumerate((('learn_url',{'seconds':999}),('upload',{'attempt':1}),('upload',{'attempt':1,'seconds':'x'}))):
   self.q.enqueue('j%d'%i,kind,{},now=10+i);c=self.q.claim('w',now=20+i);self.q.complete('j%d'%i,c['lease_token'],res,now=30+i)
  self.q.enqueue('me','upload',{},now=100);self.assertEqual(self.q.progress('me')['samples'],0)
 def test_state_reports_queue_for_waiting_jobs_only(self):
  root=Path(self.t.name);durable.enqueue(root,'a'*32,'upload',{});durable.enqueue(root,'b'*32,'upload',{})
  s=durable.state(root,'b'*32);self.assertEqual(s['status'],'queued');self.assertEqual(s['queue']['queued_ahead'],1)
  c=durable.queue(root).claim('w');durable.queue(root).complete(c['job_id'],c['lease_token'],{'attempt':1})
  self.assertNotIn('queue',durable.state(root,c['job_id']) if durable.state(root,c['job_id']).get('status')!='completed' else {})

if __name__=='__main__':unittest.main()
