"""HTTP contract tests use a fixture server, NOT a real neural model."""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
try:
    from local_reference import LocalReferenceClient, ReferenceError, validate_endpoint
except ImportError:
    LocalReferenceClient=None

class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(LocalReferenceClient,'local reference adapter not implemented')
        self.mode='ok'; self.requests=[]; outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                outer.requests.append(('GET',self.path,None))
                self.reply({'data':[{'id':'fixture-not-a-neural-model'}]})
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.requests.append(('POST',self.path,body))
                if outer.mode=='redirect':
                    self.send_response(302);self.send_header('Location','http://example.com/');self.end_headers();return
                if outer.mode=='error':self.reply({'error':'fixture failure'},503);return
                if outer.mode=='invalid':
                    self.send_response(200);self.end_headers();self.wfile.write(b'not json');return
                if outer.mode=='missing':self.reply({'choices':[]});return
                if outer.mode=='tool':self.reply({'choices':[{'message':{'content':None,'tool_calls':[{'x':1}]}}]});return
                if outer.mode=='large':self.reply({'text':'a'*(2*1024*1024+1)});return
                self.reply({'model':'fixture-not-a-neural-model','choices':[{'message':{'content':'resposta 😊'},'finish_reason':'stop'}], 'usage':{'prompt_tokens':2,'completion_tokens':3,'total_tokens':5}})
            def reply(self,obj,status=200):
                b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers()
                try:self.wfile.write(b)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.01},daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/v1'
    def tearDown(self):
        if hasattr(self,'server'):self.server.shutdown();self.server.server_close();self.thread.join(2)
    def test_http_contract_preserves_text_and_records_model(self):
        c=LocalReferenceClient(self.url);r=c.ask('pergunta: ação',max_tokens=9)
        self.assertEqual(r['text'],'resposta 😊');self.assertEqual(r['model'],'fixture-not-a-neural-model')
        self.assertIsNone(r['energy_joules']);self.assertIsNone(r['server_cpu_seconds'])
        self.assertEqual(self.requests[1][1],'/v1/chat/completions')
        body=self.requests[1][2];self.assertEqual(body['messages'],[{'role':'user','content':'pergunta: ação'}]);self.assertFalse(body['stream']);self.assertEqual(body['temperature'],0);self.assertEqual(body['max_tokens'],9)
    def test_remote_endpoints_and_credentials_refused(self):
        for endpoint in ['http://example.com','http://192.168.1.2:8080','https://127.0.0.1:8000','http://127.0.0.1:80@evil.com','http://user:pass@127.0.0.1','http://127.0.0.1:8080/v1?x=a','http://127.0.0.1:8080/evil','http://127.0.0.1:0']:
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError):validate_endpoint(endpoint)
    def test_localhost_resolves_to_literal_loopback(self):
        self.assertEqual(validate_endpoint('http://localhost:8080/v1'),('127.0.0.1',8080))
        self.assertEqual(validate_endpoint('http://[::1]:8080'),('::1',8080))
    def test_no_proxy_inherited(self):
        from unittest.mock import patch
        with patch.dict(os.environ,{'HTTP_PROXY':'http://invalid.proxy:1','http_proxy':'http://invalid.proxy:1'}):
            self.assertEqual(LocalReferenceClient(self.url).ask('hello')['text'],'resposta 😊')
    def test_redirect_never_followed(self):
        self.mode='redirect'
        with self.assertRaises(ReferenceError):LocalReferenceClient(self.url).ask('x')
        self.assertEqual(len(self.requests),2)
    def test_http_failure_explicit(self):
        self.mode='error'
        with self.assertRaises(ReferenceError):LocalReferenceClient(self.url).ask('x')
    def test_invalid_response_explicit(self):
        for mode in ['invalid','missing','tool','large']:
            self.mode=mode
            with self.subTest(mode=mode),self.assertRaises(ReferenceError):LocalReferenceClient(self.url).ask('x')
    def test_bounds_before_request(self):
        for n in [0,-1,513,True]:
            with self.assertRaises(ValueError):LocalReferenceClient(self.url).ask('x',max_tokens=n)
        with self.assertRaises(ValueError):LocalReferenceClient(self.url).ask('x'*65537)
        with self.assertRaises(ValueError):LocalReferenceClient(self.url,timeout=float('nan'))
        self.assertEqual(self.requests,[])
    def test_explicit_model_sent(self):
        LocalReferenceClient(self.url).ask('x',model='chosen')
        self.assertEqual(self.requests[0][2]['model'],'chosen')

if __name__=='__main__':unittest.main()
