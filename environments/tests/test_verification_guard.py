"""Tiny owned-process fixtures; no renderer or scene assets are required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import psutil
import verify_geode_resume as guard


class VerificationGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])

    def tearDown(self):
        # Only fixture identities recorded by this test may be cleaned up.
        for receipt in self.root.glob('*.json'):
            for token in json.loads(receipt.read_text()).get('owned', []):
                proc = guard._matching_process(token)
                if proc is not None:
                    proc.kill()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        pass
        self.sentinel.terminate()
        self.sentinel.wait(timeout=3)
        self.temp.cleanup()

    def invoke(self, code, name, **limits):
        policy = dict(preflight_bytes=0, floor_bytes=0, rss_limit_bytes=256*1024**2,
                      process_tree=True, sample_interval=.02, timeout_seconds=5)
        policy.update(limits)
        return guard.run([sys.executable, '-c', code], self.root, os.environ.copy(), name, **policy)

    def parent(self, child, *, early_exit=False):
        return ("import subprocess,sys,time; "
                f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
                + ('time.sleep(.4)' if early_exit else 'p.wait()'))

    def assert_stopped(self, name, reason, minimum_owned=2):
        record = json.loads((self.root/(name+'.json')).read_text())
        self.assertFalse(record['completed'])
        self.assertEqual(record['guard_stop'], reason)
        self.assertGreaterEqual(len(record['owned']), minimum_owned)
        self.assertEqual(record['cleanup_remaining'], [])
        self.assertTrue(all(guard._matching_process(t) is None for t in record['owned']))
        self.assertIsNone(self.sentinel.poll(), 'Unrelated process must survive owned cleanup')
        return record

    def test_success_observes_and_sums_child_without_touching_sentinel(self):
        result = self.invoke(self.parent('import time; time.sleep(.2)'), 'success')
        self.assertTrue(result['completed'])
        self.assertEqual(result['exit'], 0)
        self.assertGreaterEqual(len(result['owned']), 2)
        self.assertTrue(any(len(s['pids']) >= 2 for s in result['samples']))
        self.assertGreater(result['peak_rss_bytes'], 0)
        self.assertIsNone(self.sentinel.poll())

    def test_child_memory_limit_terminates_owned_tree_only(self):
        child = 'import time; payload=bytearray(64*1024*1024); time.sleep(30)'
        with self.assertRaisesRegex(RuntimeError, 'partial files retained'):
            self.invoke(self.parent(child), 'memory', rss_limit_bytes=48*1024**2)
        result = self.assert_stopped('memory', 'rss_limit')
        self.assertGreater(result['peak_rss_bytes'], 48*1024**2)

    def test_timeout_cleans_up_child(self):
        with self.assertRaises(RuntimeError):
            self.invoke(self.parent('import time; time.sleep(30)'), 'timeout', timeout_seconds=.4)
        self.assert_stopped('timeout', 'timeout')

    def test_late_grandchild_and_early_parent_exit_fail_closed(self):
        grandchild = 'import time; time.sleep(30)'
        child = ('import subprocess,sys,time; time.sleep(.12); '
                 f'p=subprocess.Popen([sys.executable,"-c",{grandchild!r}]); p.wait()')
        with self.assertRaises(RuntimeError):
            self.invoke(self.parent(child, early_exit=True), 'early')
        self.assert_stopped('early', 'parent_exited_with_live_children', minimum_owned=3)

    def test_supervisor_exception_cleans_owned_children(self):
        observe = guard._observe

        def interrupted(owned, root, include_children):
            result = observe(owned, root, include_children)
            if len(owned) >= 2:
                raise RuntimeError('injected supervisor failure')
            return result

        with patch.object(guard, '_observe', interrupted):
            with self.assertRaisesRegex(RuntimeError, 'injected supervisor failure'):
                self.invoke(self.parent('import time; time.sleep(30)'), 'exception')
        record = json.loads((self.root/'exception.json').read_text())
        self.assertFalse(record['completed'])
        self.assertEqual(record['supervisor_exception'], 'RuntimeError')
        self.assertEqual(record['cleanup_remaining'], [])
        self.assertTrue(all(guard._matching_process(t) is None for t in record['owned']))
        self.assertIsNone(self.sentinel.poll())

    def test_preflight_failure_launches_nothing_and_identity_mismatch_is_unowned(self):
        with patch.object(guard.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, 'no process launched'):
                self.invoke('pass', 'preflight', preflight_bytes=psutil.virtual_memory().total+1)
            popen.assert_not_called()
        self.assertFalse((self.root/'preflight.json').exists())
        proc = psutil.Process(self.sentinel.pid)
        self.assertIsNone(guard._matching_process({'pid': proc.pid, 'created': proc.create_time()+1}))
        self.assertIsNone(self.sentinel.poll())

    def test_existing_receipt_is_preserved_before_launch(self):
        receipt = self.root/'exists.json'
        receipt.write_text('{}')
        with patch.object(guard.subprocess, 'Popen') as popen:
            with self.assertRaises(FileExistsError):
                self.invoke('pass', 'exists')
            popen.assert_not_called()
        self.assertEqual(receipt.read_text(), '{}')


if __name__ == '__main__':
    unittest.main()
