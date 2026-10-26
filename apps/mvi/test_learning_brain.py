"""Right-hemisphere intake must remain separate from the analyzed footage path."""
import http.client
import json
import os
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
import durable_runtime
import learning_brain
import server
from editor_report import render_markdown
from review_pipeline import review


SAMPLE = ("Most editing tutorials recommend adding more cuts, but that advice is wrong "
          "when the audience expects authenticity because fast transitions can damage "
          "the emotional impact of a raw video. "
          "You should understand the promise from the title before changing the edit, "
          "because the viewer clicked with expectations that the opening must satisfy. "
          "Always check whether the ending actually delivers that promise and avoid "
          "additional visual effects when they distract from the story.")


class SourceTests(unittest.TestCase):
    def test_transcript_captions_are_deduplicated(self):
        vtt = ("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n"
               "Cut slower scenes\n\n00:00:01.000 --> 00:00:02.000\n"
               "Cut slower scenes only when appropriate\n")
        self.assertEqual(learning_brain.normalize_captions(vtt),
                         'Cut slower scenes only when appropriate')

    def test_candidates_are_unverified_not_decisions(self):
        candidates=learning_brain.extract_candidates(SAMPLE)
        self.assertGreater(len(candidates),0)
        self.assertTrue(all(c['review_status']=='candidate_unverified' for c in candidates))
        self.assertTrue(all(c['excerpt'] in SAMPLE for c in candidates))

    def test_missing_subtitles_requires_transcription_not_fabricated_knowledge(self):
        with tempfile.TemporaryDirectory() as root:
            job='c'*32
            folder=Path(root)/job
            folder.mkdir()
            (folder/'learning.mp4').write_bytes(b'fake video')
            claim={'job_id':job,'kind':'learn_upload','attempt':1,
                   'payload':{'filename':'learning.mp4','title':'training'}}
            attempt=folder/'attempt-1';attempt.mkdir()
            with patch.object(learning_brain,'_extract_video_subtitles',return_value=None):
                learning_brain.process_source(root,claim,attempt)
            result=json.loads((attempt/'learning.json').read_text())
            self.assertEqual(result['phase'],'needs_transcript')
            self.assertEqual(result['candidates'],[])
            self.assertEqual(result['transcript_characters'],0)

    def test_unapproved_material_never_enters_editorial_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(learning_brain.approved_principles(root,'editing'),[])


class LearningHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'jobs'
        self.root.mkdir()
        self.patch_env=patch.dict(os.environ,{'MVI_API_TOKEN':'secret-token',
             'MVI_REQUIRE_AUTH':'1','MVI_DATA_DIR':str(self.root),
             'MVI_DURABLE_QUEUE':'1','MVI_ENABLE_LOCAL_VISION':'0'})
        self.patch_root=patch.object(server,'ROOT',self.root)
        self.patch_env.start()
        self.patch_root.start()
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.patch_root.stop()
        self.patch_env.stop()
        self.temp.cleanup()

    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_address[1],timeout=8)
        conn.request(method,path,body=body,headers=headers or {})
        res=conn.getresponse()
        raw=res.read()
        code=res.status
        conn.close()
        try:return code,json.loads(raw)
        except ValueError:return code,raw.decode(errors='replace')

    def secured(self,method,path,body=None,headers=None):
        h={'Authorization':'Bearer secret-token',**(headers or {})}
        return self.request(method,path,body,h)

    def test_dashboard_has_two_hemispheres_and_auth_gate(self):
        code,html=self.request('GET','/')
        self.assertEqual(code,200)
        self.assertIn('id="analysis-drop"',html)
        self.assertIn('id="learning-drop"',html)
        self.assertIn('brainview',html)
        self.assertIn('viewBox="0 0 680 306"',html)
        self.assertIn('id="token"',html)
        self.assertEqual(self.request('GET','/api/learn/jobs/'+'a'*32)[0],401)
        self.assertEqual(self.request('POST','/api/learn/decide')[0],401)

    def test_transcript_upload_review_approval_and_report_knowledge(self):
        body=SAMPLE.encode()
        code,submission=self.secured('POST','/api/learn/upload',body,
             {'X-Filename':'research.txt','Content-Length':str(len(body))})
        self.assertEqual(code,202,submission)
        job=submission['job_id']
        self.assertEqual(self.secured('GET','/api/learn/jobs/'+job)[1]['status'],'queued')
        self.assertIsNotNone(durable_runtime.work_once(self.root))
        code,finished=self.secured('GET','/api/learn/jobs/'+job)
        self.assertEqual(code,200)
        self.assertEqual(finished['phase'],'candidate_review')
        self.assertGreater(finished['candidate_count'],0)
        self.assertEqual(learning_brain.approved_principles(self.root,'edit'),[])
        card=finished['candidates'][0]
        data=json.dumps({'job_id':job,'card_id':card['id'],'decision':'approve'}).encode()
        code,approval=self.secured('POST','/api/learn/decide',data,
                                   {'Content-Type':'application/json'})
        self.assertEqual(code,200,approval)
        self.assertEqual(approval['decision'],'approve')
        approved=learning_brain.approved_principles(self.root,'editing')
        self.assertEqual(approved[0]['excerpt'],card['excerpt'])
        self.assertFalse(approved[0]['verified_target_observation'])
        with tempfile.TemporaryDirectory() as report_dir:
            report=review(report_dir,{'title':'GTA editing'},
                          {'duration_seconds':26},enable_local_vision=False)
            self.assertTrue(report['learned_principles'])
            markdown=render_markdown(report)
            self.assertIn('Approved knowledge sources',markdown)
            self.assertIn(card['excerpt'],markdown)
        # Rejected cards must immediately disappear from retrieval.
        data=json.dumps({'job_id':job,'card_id':card['id'],'decision':'reject'}).encode()
        self.assertEqual(self.secured('POST','/api/learn/decide',data)[0],200)
        self.assertEqual(learning_brain.approved_principles(self.root,'editing'),[])

    def test_youtube_intake_rejects_non_youtube_domains(self):
        raw=json.dumps({'url':'http://127.0.0.1/internal'}).encode()
        code,answer=self.secured('POST','/api/learn/url',raw)
        self.assertEqual(code,400)
        self.assertIn('Only YouTube',answer['error'])

    def test_filename_is_fixed_not_uploaded_path(self):
        raw=SAMPLE.encode()
        code,answer=self.secured('POST','/api/learn/upload',raw,
                            {'X-Filename':'../../sneaky.txt'})
        self.assertEqual(code,202)
        self.assertTrue((self.root/answer['job_id']/'learning.txt').is_file())
        self.assertFalse((self.root/'sneaky.txt').exists())


if __name__=='__main__':
    unittest.main()
