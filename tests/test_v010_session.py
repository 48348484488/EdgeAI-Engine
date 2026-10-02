"""Behavioral tests for reusable native code-search sessions."""
import json, os, subprocess, tempfile, unittest, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BUILD=Path(os.environ.get('EDGEAI_BUILD_DIR',ROOT/'build'))
class SearchSessionTests(unittest.TestCase):
    def test_batch_returns_one_verified_result_per_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'a.cpp').write_text('void Alpha() {}\nvoid Beta() {}\n')
            p=subprocess.run([str(BUILD/'edgeai_code_search'),tmp,'--batch','--json'],input='Alpha\nBeta\n',text=True,capture_output=True,timeout=20)
            self.assertEqual(p.returncode,0,p.stderr)
            rows=p.stdout.splitlines();self.assertEqual(len(rows),2,p.stdout)
            values=[json.loads(r) for r in rows]
            self.assertEqual([v['hits'][0]['match_line'] for v in values],[1,2])
            self.assertEqual(values[1]['reused_files'],1)
            self.assertEqual(values[1]['reindexed_files'],0)
    def test_batch_edit_same_length_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'x.cpp');path.write_text('void Alpha() {}\n');st=path.stat()
            with subprocess.Popen([str(BUILD/'edgeai_code_search'),tmp,'--batch','--json'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as p:
                try:
                    p.stdin.write('Alpha\n');p.stdin.flush()
                    first=json.loads(p.stdout.readline());self.assertTrue(first['hits'])
                    path.write_text('void Bravo() {}\n');os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns))
                    p.stdin.write('Alpha\nBravo\n');p.stdin.flush()
                    self.assertEqual(json.loads(p.stdout.readline())['hits'],[])
                    self.assertTrue(json.loads(p.stdout.readline())['hits'])
                finally:
                    p.stdin.close();p.wait(timeout=20)
    def test_invalid_query_yields_explicit_batch_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'a.cpp').write_text('void Alpha() {}\n')
            p=subprocess.run([str(BUILD/'edgeai_code_search'),tmp,'--batch','--json'],input='x'*513+'\nAlpha\n',text=True,capture_output=True,timeout=20)
            self.assertEqual(p.returncode,1)
            rows=[json.loads(s) for s in p.stdout.splitlines()]
            self.assertEqual(len(rows),2);self.assertIn('error',rows[0]);self.assertTrue(rows[1]['hits'])
    def test_long_line_cannot_hide_overflow_after_carriage_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'a.cpp').write_text('void Alpha() {}\n')
            payload=b'a'*512+b'\rhidden suffix\nAlpha\n'
            p=subprocess.run([str(BUILD/'edgeai_code_search'),tmp,'--batch','--json'],input=payload,capture_output=True,timeout=20)
            rows=[json.loads(s) for s in p.stdout.splitlines()]
            self.assertEqual(p.returncode,1)
            self.assertIn('error',rows[0]);self.assertTrue(rows[1]['hits'])
    def test_removed_root_never_returns_cached_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp,'project');root.mkdir();path=root/'a.cpp';path.write_text('void Alpha() {}\n')
            with subprocess.Popen([str(BUILD/'edgeai_code_search'),str(root),'--batch','--json'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as p:
                try:
                    p.stdin.write('Alpha\n');p.stdin.flush();self.assertTrue(json.loads(p.stdout.readline())['hits'])
                    path.unlink();root.rmdir()
                    p.stdin.write('Alpha\n');p.stdin.flush();row=json.loads(p.stdout.readline())
                    self.assertIn('error',row);self.assertEqual(row['hits'],[])
                finally:
                    p.stdin.close();p.wait(timeout=20)
    def test_file_edited_while_waiting_for_first_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'a.cpp');path.write_text('void Alpha() {}\n')
            with subprocess.Popen([str(BUILD/'edgeai_code_search'),tmp,'--batch','--json'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as p:
                try:
                    # Tiny fixture; allow startup to reach its stdin wait, then edit.
                    time.sleep(0.15);self.assertIsNone(p.poll())
                    path.write_text('void Bravo() {}\n')
                    p.stdin.write('Bravo\n');p.stdin.flush()
                    self.assertTrue(json.loads(p.stdout.readline())['hits'])
                finally:
                    p.stdin.close();p.wait(timeout=20)
if __name__=='__main__':unittest.main()
