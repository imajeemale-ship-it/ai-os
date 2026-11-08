import http.client, json, os, tempfile, time, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
import knowledge_base as kb, scoring, server, trends
from test_scoring import FakeJudge, TREND, full, make_clip, trend_fit, PRICES
from analyze import analyze

def items(n=8):
 return [{'id':'v%d'%i,'snippet':{'title':'Top %d GTA TRICKS?'%i,'channelTitle':'c','publishedAt':'2026-10-20T00:00:00Z'},
          'contentDetails':{'duration':'PT%dM%dS'%(i,i)},'statistics':{'viewCount':str(1000*i)}} for i in range(1,n+1)]

class TrendTests(unittest.TestCase):
 def test_duration_and_stats(self):
  self.assertEqual(trends.parse_duration('PT1H2M3S'),3723);self.assertEqual(trends.parse_duration('PT45S'),45)
  self.assertIsNone(trends.parse_duration('garbage'))
  st=trends.stats(trends._summarize(items()))
  self.assertEqual(st['count'],8);self.assertEqual(st['share_titles_with_number'],1.0)
  self.assertEqual(st['share_titles_with_question'],1.0);self.assertEqual(st['share_titles_with_allcaps_word'],1.0)
  self.assertEqual(trends.stats([]),{'count':0})
 def test_fetch_chart_and_search_modes_use_official_api_only(self):
  calls=[]
  def get(ep,params,key):
   calls.append((ep,params));return {'items':items()} if ep=='videos' else {'items':[{'id':{'videoId':'v1'}}]}
  p=trends.fetch_youtube('SECRET',get=get,now=1_000_000)
  self.assertEqual(calls[0][0],'videos');self.assertEqual(calls[0][1]['chart'],'mostPopular')
  self.assertEqual(calls[0][1]['videoCategoryId'],'20');self.assertNotIn('SECRET',json.dumps(p))
  calls.clear();trends.fetch_youtube('SECRET',query='gta online',get=get,now=1_000_000)
  self.assertEqual([c[0] for c in calls],['search','videos']);self.assertEqual(calls[0][1]['q'],'gta online')
  with self.assertRaises(trends.TrendError):trends.fetch_youtube('')
 def test_form_split_filters_and_caches_separately(self):
  self.assertEqual(trends.form_for_duration(45),'shorts');self.assertEqual(trends.form_for_duration(180),'shorts')
  self.assertEqual(trends.form_for_duration(181),'long');self.assertEqual(trends.form_for_duration(None),'long')
  calls=[]
  def get(ep,params,key):
   calls.append((ep,params))
   return {'items':items(8)} if ep=='videos' else {'items':[{'id':{'videoId':'v1'}}]}
  p=trends.fetch_youtube('K',query='gta',form='shorts',get=get,now=1_000_000)
  self.assertEqual(calls[0][1]['videoDuration'],'short')
  self.assertTrue(all(r['duration_seconds']<=180 for r in p['examples']));self.assertEqual(p['form'],'shorts')
  calls.clear();p=trends.fetch_youtube('K',query='gta',form='long',get=get,now=1_000_000)
  self.assertEqual([c[1].get('videoDuration') for c in calls if c[0]=='search'],['medium'])
  self.assertTrue(all(r['duration_seconds']>180 for r in p['examples']))
  live=items(8);live[0]['liveStreamingDetails']={'actualStartTime':'x'}
  p=trends.fetch_youtube('K',query='gta',form='long',get=lambda e,pa,k:{'items':live} if e=='videos' else {'items':[{'id':{'videoId':'v1'}}]},now=1_000_000)
  self.assertNotIn('v1',[r['video_id'] for r in p['examples']])
  with self.assertRaises(trends.TrendError):trends.fetch_youtube('K',form='shorts',get=get)
  with self.assertRaises(trends.TrendError):trends.fetch_youtube('K',query='gta',form='bogus',get=get)
  self.assertNotEqual(trends._cache_path('r','US','20','q','shorts'),trends._cache_path('r','US','20','q','long'))
 def test_error_text_never_contains_key(self):
  self.assertNotIn('SECRET',trends._clean_error('boom https://x?key=SECRET',  'SECRET'))
 def test_cache_ttl_and_no_key(self):
  with tempfile.TemporaryDirectory() as t:
   n={'c':0}
   def fetch(key,**k):
    n['c']+=1;return {'retrieved_at':k['now'],'stats':{'count':8},'scope':'x'}
   with patch.dict(os.environ,{'YOUTUBE_API_KEY':''}):self.assertIsNone(trends.get(t,now=100,fetch=fetch))
   with patch.dict(os.environ,{'YOUTUBE_API_KEY':'k'}):
    trends.get(t,now=100,fetch=fetch);trends.get(t,now=100+3600,fetch=fetch);self.assertEqual(n['c'],1)
    trends.get(t,now=100+trends.TTL_SECONDS+5,fetch=fetch);self.assertEqual(n['c'],2)
 def test_freshness(self):
  now=1_000_000
  self.assertTrue(trends.is_fresh({'retrieved_at':now-3600,'stats':{'count':8}},now))
  self.assertFalse(trends.is_fresh({'retrieved_at':now-3*86400,'stats':{'count':8}},now))
  self.assertFalse(trends.is_fresh({'retrieved_at':now,'stats':{'count':2}},now));self.assertFalse(trends.is_fresh(None,now))

class KnowledgeTests(unittest.TestCase):
 def test_nothing_applies_until_approved(self):
  with tempfile.TemporaryDirectory() as t:
   self.assertEqual(kb.approved(t),[]);self.assertTrue(all(p['decision']=='pending' for p in kb.listing(t)))
   kb.decide(t,'P-YT-01','approve');self.assertEqual([p['id'] for p in kb.approved(t)],['P-YT-01'])
   kb.decide(t,'P-YT-01','reject');self.assertEqual(kb.approved(t),[])
   with self.assertRaises(ValueError):kb.decide(t,'P-NOPE','approve')
   with self.assertRaises(ValueError):kb.decide(t,'P-YT-01','maybe')
 def test_every_principle_has_a_source_and_confidence(self):
  for p in kb.PRINCIPLES:self.assertTrue(p['source'] and p['confidence'] in('high','medium','low') and p['categories'])

class BlendTests(unittest.TestCase):
 def run_score(self,judge_out,trend,principles=None):
  with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,PRICES):
   clip=Path(t)/'c.mp4';make_clip(clip);jd=Path(t)/'j';jd.mkdir();(jd/'transcript.txt').write_text('hello')
   return scoring.score_video(clip,analyze(clip),{'timeline':[],'scene_count':1},jd,FakeJudge(judge_out),max_usd=1,frame_count=4,trends=trend,principles=principles)
 def test_80_20_math(self):
  out=full(0.9);out['trend_fit']=trend_fit(10)   # trend 50%
  r=self.run_score(out,TREND())
  self.assertEqual(r['knowledge_score'],90.0);self.assertEqual(r['trend_fit_percent'],50.0)
  self.assertEqual(r['overall_score'],83.2);self.assertEqual(r['recommendation'],'REVISE')   # 85% of (80/20 blend = 82) + 15% visual quality 90
 def test_no_trends_means_pending_not_a_made_up_score(self):
  r=self.run_score(full(0.9),None)
  self.assertEqual(r['knowledge_score'],90.0);self.assertIsNone(r['overall_score']);self.assertEqual(r['recommendation'],'PENDING_REVIEW')
  self.assertIn('YOUTUBE_API_KEY',r['trend_fit']['reason']);self.assertEqual(r['status'],'partial')
 def test_stale_trends_rejected(self):
  r=self.run_score(full(0.9),TREND(now=time.time()-4*86400))
  self.assertIsNone(r['overall_score']);self.assertIn('48 hours',r['trend_fit']['reason'])
 def test_trend_citations_must_name_real_metrics(self):
  out=full(0.9);out['trend_fit']=trend_fit(18,('made_up_metric','also_fake'))
  r=self.run_score(out,TREND());self.assertIsNone(r['overall_score']);self.assertIn('real trend metrics',r['trend_fit']['reason'])
 def test_only_approved_principles_can_be_cited(self):
  out=full(0.9)
  for c in out['categories'].values():c['principles']=['P-YT-01','P-JY-01']
  ok=[p for p in kb.PRINCIPLES if p['id']=='P-YT-01']
  r=self.run_score(out,TREND(),ok)
  self.assertEqual(r['scorecard']['categories']['opening_hook']['principles'],['P-YT-01'])
  self.assertEqual(r['principles_used'],['P-YT-01'])
  r2=self.run_score(full(0.9),TREND(),[]);self.assertIn('No approved principles',' '.join(r2['caveats']))

class KnowledgeEndpointTests(unittest.TestCase):
 def test_auth_and_decide(self):
  with tempfile.TemporaryDirectory() as t,patch.object(server,'ROOT',Path(t)),patch.dict(os.environ,{'MVI_API_TOKEN':'tok','MVI_REQUIRE_AUTH':'1'}):
   httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);Thread(target=httpd.serve_forever,daemon=True).start()
   port=httpd.server_address[1]
   def req(m,p,body=b'',auth=True):
    h={'Content-Length':str(len(body))}
    if auth:h['Authorization']='Bearer tok'
    c=http.client.HTTPConnection('127.0.0.1',port,timeout=10);c.request(m,p,body=body,headers=h);r=c.getresponse();d=r.read();c.close()
    return r.status,json.loads(d) if d[:1]==b'{' else d
   try:
    self.assertEqual(req('GET','/api/knowledge',auth=False)[0],401)
    self.assertEqual(req('POST','/api/knowledge/decide',b'{}',auth=False)[0],401)
    self.assertEqual(req('GET','/api/trends/youtube',auth=False)[0],401)
    code,r=req('GET','/api/knowledge');self.assertEqual(code,200);self.assertEqual(len(r['principles']),len(kb.PRINCIPLES))
    self.assertEqual(req('POST','/api/knowledge/decide',b'{"id":"P-YT-01","decision":"approve"}')[0],200)
    self.assertEqual([p['decision'] for p in req('GET','/api/knowledge')[1]['principles'] if p['id']=='P-YT-01'],['approve'])
    self.assertEqual(req('POST','/api/knowledge/decide',b'{"id":"x","decision":"approve"}')[0],400)
    with patch.dict(os.environ,{'YOUTUBE_API_KEY':''}):self.assertEqual(req('GET','/api/trends/youtube')[0],403)
   finally:httpd.shutdown();httpd.server_close()
if __name__=='__main__':unittest.main()

class GameTests(unittest.TestCase):
 def test_registry_and_page_agree(self):
  import games
  html=(Path(__file__).parent/'brain_studio.html').read_text()
  for k in games.GAMES:self.assertIn('<option value="%s">'%k,html)
  self.assertEqual(games.query_for('cod'),'call of duty');self.assertIsNone(games.query_for('other'))
  self.assertEqual(games.query_for(None),os.environ.get('MVI_TREND_QUERY','gta online'))
 def test_context_keeps_only_known_games(self):
  self.assertEqual(server.editorial_context({'game':'cod'}),{'game':'cod'})
  self.assertEqual(server.editorial_context({'game':'<script>','audience':'x'}),{'audience':'x'})
 def test_unknown_game_and_no_query_are_refused_by_trends_endpoint(self):
  import games
  with tempfile.TemporaryDirectory() as t,patch.object(server,'ROOT',Path(t)),patch.dict(os.environ,{'MVI_REQUIRE_AUTH':'1','MVI_API_TOKEN':'tok'}):
   httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);Thread(target=httpd.serve_forever,daemon=True).start()
   def get(path):
    c=http.client.HTTPConnection('127.0.0.1',httpd.server_address[1]);c.request('GET',path,headers={'Authorization':'Bearer tok'});r=c.getresponse();return r.status,json.loads(r.read())
   self.assertEqual(get('/api/trends/youtube?game=minecraft')[0],400)
   self.assertEqual(get('/api/trends/youtube?game=other')[0],403)
   self.assertEqual(get('/api/games')[1]['games'][0]['key'],'gta')
   httpd.shutdown()

class GameScoringPathTests(unittest.TestCase):
 def run_job(self,game,duration=45):
  seen={}
  def fake_get(root,query=None,form=None,**k):seen.update(query=query,form=form);return {'retrieved_at':1,'stats':{'count':8},'scope':'x'}
  def fake_score(*a,**k):seen['trends']=k.get('trends');return {'ok':True}
  info={'video':'v','technical':{'duration_seconds':duration},'timeline':None,'state':{'metadata':{'editorial_context':({'game':game} if game else {})}}}
  with tempfile.TemporaryDirectory() as t,patch.object(server,'ROOT',Path(t)),patch.object(server,'_job_or_none',lambda j:info),\
       patch.object(server,'get_judge',lambda:object()),patch.object(server.trendlib,'get',fake_get),patch.object(server.scoring,'score_video',fake_score),\
       patch.object(server.knowledge_base,'approved',lambda r:[]):
   (Path(t)/('a'*32)).mkdir();server.run_score_job('a'*32,1.0,['youtube_long']);seen['status']=json.loads((Path(t)/('a'*32)/'score_status.json').read_text())['status']
  return seen
 def test_cod_uses_cod_query_and_format(self):
  s=self.run_job('cod',45);self.assertEqual((s['query'],s['form'],s['status']),('call of duty','shorts','done'))
  self.assertEqual(self.run_job('cod',600)['form'],'long')
 def test_other_game_gets_no_trends_and_unset_keeps_default(self):
  s=self.run_job('other');self.assertNotIn('query',s);self.assertIsNone(s['trends'])
  self.assertEqual(self.run_job(None)['query'],os.environ.get('MVI_TREND_QUERY','gta online'))
