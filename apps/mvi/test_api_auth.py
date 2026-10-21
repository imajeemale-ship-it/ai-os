import http.client,os,unittest
from threading import Thread
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import server

class ApiAuthTests(unittest.TestCase):
 def test_bearer_token_guards_all_routes(self):
  with patch.dict(os.environ,{'MVI_API_TOKEN':'test-secret-token'}):
   httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
   thread=Thread(target=httpd.serve_forever,daemon=True);thread.start()
   try:
    def request(method,path,auth=None):
     conn=http.client.HTTPConnection('127.0.0.1',httpd.server_address[1],timeout=5)
     headers={} if auth is None else {'Authorization':auth}
     conn.request(method,path,headers=headers)
     res=conn.getresponse();code=res.status;res.read();conn.close();return code
    for path in ('/','/api/jobs/'+'a'*32,'/api/reports/'+'a'*32+'/editor'):
     self.assertEqual(request('GET',path),401)
     self.assertEqual(request('GET',path,'Bearer wrong'),401)
    self.assertEqual(request('GET','/health'),200)
    self.assertEqual(request('GET','/health','Bearer wrong'),200)
    self.assertEqual(request('POST','/api/url'),401)
   finally:
    httpd.shutdown();httpd.server_close();thread.join()

if __name__=='__main__':unittest.main()
