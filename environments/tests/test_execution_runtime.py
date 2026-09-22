from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import execution_runtime as ex

class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
    def tearDown(self):
        for d in self.root.glob('jobs/*'):
            if (d/'state.json').exists():
                s=ex.read_json(d/'state.json')
                if ex.alive(s.get('supervisor')):ex.terminate_tree(s['supervisor']['pid'],grace=.1)
        self.temp.cleanup()
    def command(self,code):return [sys.executable,'-c',code]
    def run_cmd(self,code,**kwargs):
        return ex.supervise(self.command(code),self.root,self.root/'out.log',self.root/'state.json',heartbeat=.03,**kwargs)
    def wait_job(self,name,limit=8):
        end=time.monotonic()+limit
        while time.monotonic()<end:
            result=ex.job_status(self.root/'jobs',name)
            if result['state'] in ex.TERMINAL:return result
            time.sleep(.05)
        self.fail('job did not finish within test bound')
    def test_atomic_json_and_suffix_read(self):
        p=self.root/'state.json';ex.atomic_json(p,{'hello':'world'})
        self.assertEqual(ex.read_json(p),{'hello':'world'})
        p.write_text('a'*100000+'\nFINAL\n')
        self.assertEqual(ex.tail(p,1,max_bytes=20),'FINAL')
    def test_success_and_stderr_capture(self):
        r=self.run_cmd('import sys; print("stdout");print("stderr",file=sys.stderr)')
        self.assertEqual(r['state'],'succeeded');self.assertTrue(r['completed'])
        self.assertIn('stderr',(self.root/'out.log').read_text())
    def test_repeat_attempt_has_fresh_log_and_preserves_history(self):
        self.run_cmd('print("old-attempt")')
        r=self.run_cmd('print("new-attempt")')
        self.assertEqual(r['state'],'succeeded')
        self.assertEqual((self.root/'out.log').read_text(),'new-attempt\n')
        archived=list((self.root/'.execution-history').glob('*/out.log'))
        self.assertEqual(len(archived),1)
        self.assertEqual(archived[0].read_text(),'old-attempt\n')
    def test_nonzero_is_not_success(self):
        r=self.run_cmd('raise SystemExit(7)')
        self.assertEqual(r['returncode'],7);self.assertEqual(r['state'],'failed');self.assertFalse(r['completed'])
    def test_missing_executable_is_recorded(self):
        r=ex.supervise(['/no/such/executable'],self.root,self.root/'log',self.root/'state.json')
        self.assertEqual(r['state'],'failed');self.assertIn('FileNotFoundError',r['error'])
    def test_timeout_is_explicit(self):
        r=self.run_cmd('import time;time.sleep(30)',timeout=.15)
        self.assertEqual(r['state'],'timed_out');self.assertFalse(ex.alive(r['child']))
    def test_cancel_request(self):
        p=self.root/'cancel';p.write_text('cancel')
        r=self.run_cmd('import time;time.sleep(30)',cancel_path=p)
        self.assertEqual(r['state'],'cancelled')
    def test_resource_budget_preempts_large_job(self):
        r=self.run_cmd('import time; data=bytearray(80*1024*1024);time.sleep(5)',memory_bytes=32*ex.MiB)
        self.assertEqual(r['state'],'resource_limit');self.assertGreater(r['peak_tree_rss_bytes'],32*ex.MiB)
    def test_thread_budgets_agree(self):
        env=ex.thread_environment(2)
        self.assertEqual(env['OMP_NUM_THREADS'],'2');self.assertEqual(env['NUMBA_NUM_THREADS'],'2')
        self.assertEqual(env['OPENBLAS_NUM_THREADS'],'1')
        with self.assertRaises(ValueError):ex.thread_environment(0)
    def test_live_lock_and_stale_recovery(self):
        p=self.root/'owner.lock'
        with ex.owned_lock(p):
            before=p.read_bytes()
            with self.assertRaises(RuntimeError):
                with ex.owned_lock(p):pass
            self.assertEqual(p.read_bytes(),before)
        with ex.owned_lock(p):pass
        self.assertTrue(p.exists())
    def test_owner_death_releases_lock(self):
        lock=self.root/'owner.lock'
        code=f'import sys,time;sys.path.insert(0,{str(Path(ex.__file__).parent)!r});from execution_runtime import owned_lock\nwith owned_lock({str(lock)!r}):\n print("LOCKED",flush=True);time.sleep(30)'
        p=subprocess.Popen(self.command(code),stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(p.stdout.readline().strip(),'LOCKED')
            with self.assertRaises(RuntimeError):
                with ex.owned_lock(lock):pass
        finally:
            p.kill();p.wait();p.stdout.close()
        with ex.owned_lock(lock):pass
    def test_identity_prevents_pid_reuse(self):
        token=ex.identity(os.getpid());self.assertTrue(ex.alive(token))
        token['start_ticks']+=1;self.assertFalse(ex.alive(token))
    def test_detached_job_survives_short_launcher(self):
        script=f'import sys;sys.path.insert(0,{str(Path(ex.__file__).parent)!r});import execution_runtime as e;e.start_job({str(self.root/"jobs")!r},"detach",{self.command("import time;time.sleep(.3);print('FINISHED')")!r},{str(self.root)!r})'
        subprocess.run(self.command(script),check=True,timeout=5)
        r=self.wait_job('detach');self.assertEqual(r['state'],'succeeded');self.assertIn('FINISHED',r['tail'])
    def test_duplicate_job_and_path_traversal_refused(self):
        ex.start_job(self.root/'jobs','same',self.command('print(1)'),self.root)
        with self.assertRaises(FileExistsError):ex.start_job(self.root/'jobs','same',self.command('print(2)'),self.root)
        with self.assertRaises(ValueError):ex.job_directory(self.root,'../escape')
        self.wait_job('same')
    def test_missing_cwd_fails_before_job_creation(self):
        with self.assertRaises(ValueError):ex.start_job(self.root/'jobs','missing',self.command('print(1)'),self.root/'missing')
        self.assertFalse((self.root/'jobs/missing').exists())
    def test_missing_supervisor_becomes_interrupted(self):
        folder=self.root/'jobs/interrupted';folder.mkdir(parents=True)
        ex.atomic_json(folder/'spec.json',{'created_unix':time.time()-30})
        ex.atomic_json(folder/'state.json',{'state':'running','started_unix':time.time()-30,'supervisor':{'pid':99999999},'completed':False})
        r=ex.job_status(self.root/'jobs','interrupted')
        self.assertEqual(r['state'],'interrupted');self.assertFalse(r['completed'])
    def test_nested_session_child_is_stopped(self):
        out=self.root/'child.json'
        code=f'import subprocess,sys,time,json;from pathlib import Path\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],start_new_session=True)\nPath({str(out)!r}).write_text(str(p.pid))\ntime.sleep(30)'
        r=self.run_cmd(code,timeout=2.0)
        self.assertEqual(r['state'],'timed_out')
        pid=int(out.read_text());info=ex.proc_info(pid)
        self.assertTrue(info is None or info['state']=='Z')
    def test_batch_continues_after_failure(self):
        import cybr_scenes as scenes
        calls=[];saved=[]
        def prepare(scene,threads):
            calls.append(scene['id'])
            if len(calls)==1:raise RuntimeError('intentional')
            return Path('ok')
        with patch.object(sys,'argv',['cybr_scenes.py','prepare','all']),patch.object(scenes,'prepare_scene',prepare),patch.object(scenes,'atomic_json',lambda p,v:saved.append(json.loads(json.dumps(v)))):
            rc=scenes.main()
        self.assertEqual(rc,1);self.assertEqual(len(calls),6)
        self.assertEqual(saved[-1][0]['state'],'failed')
        self.assertEqual(saved[-1][-1]['state'],'succeeded')
    def test_legacy_command_receipt_is_preserved(self):
        r=ex.run_recorded(self.command('print("ok")'),self.root,self.root/'native.log',threads=2)
        self.assertEqual(r['returncode'],0)
        self.assertTrue((self.root/'native.command.json').exists())
        self.assertEqual(ex.read_json(self.root/'native.execution.json')['state'],'succeeded')

    def test_checkpoint_is_atomic_and_verifiable(self):
        import tools.package_delivery as package
        source=self.root/'input.txt';source.write_text('original source')
        output=self.root/'checkpoint.zip'
        with patch.object(package,'ROOT',self.root):
            result=package.archive(output,[source])
        self.assertTrue(result['zip_crc_passed'])
        import zipfile
        with zipfile.ZipFile(output) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read(self.root.name+'/input.txt'),b'original source')
    def test_bad_checkpoint_does_not_replace_previous(self):
        import tools.package_delivery as package
        import zipfile
        source=self.root/'input.txt';source.write_text('source')
        output=self.root/'checkpoint.zip';output.write_bytes(b'previous checkpoint')
        with patch.object(package,'ROOT',self.root),patch.object(zipfile.ZipFile,'testzip',return_value='bad-entry'):
            with self.assertRaises(RuntimeError):package.archive(output,[source])
        self.assertEqual(output.read_bytes(),b'previous checkpoint')

if __name__=='__main__':unittest.main()
