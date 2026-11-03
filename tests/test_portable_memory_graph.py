import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / 'system/vault-runtime/memory_graph/memory_graph_cli.py'

class PortableGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.edges = Path(self.tmp.name) / 'edges.jsonl'
        self.edges.write_text(json.dumps({'id':'edge_demo', 'from':'會議記錄', 'to':'證據鏈', 'relation':'preferred_tool_for', 'weight':0.95, 'confidence':'verified', 'action':'檢查會議記錄證據鏈'}, ensure_ascii=False) + '\n')
        self.db = Path(self.tmp.name) / 'shadow.db'
    def run_cli(self, *args, allow=False, shadow=False, ok=True):
        command = [sys.executable, str(CLI), '--edges', str(self.edges)]
        if allow: command += ['--authorize-write']
        if shadow: command += ['--shadow-db', str(self.db)]
        p = subprocess.run(command + list(args), text=True, capture_output=True)
        if ok: self.assertEqual(p.returncode, 0, p.stderr)
        else: self.assertNotEqual(p.returncode, 0)
        return p
    def test_preflight_chinese_and_authorization(self):
        p = json.loads(self.run_cli('preflight','會議記錄證據鏈','--json').stdout)
        self.assertEqual(p['route_plan'][0]['edge_id'], 'edge_demo')
        self.assertIn('explicitly authorized', p['delivery_contract']['rule'])
        self.assertIn('explicit save authorization', p['record_after_task'])
        self.assertIn('success or failure', p['record_after_task'])
    def test_writes_denied_until_authorized_and_guard(self):
        args = ('record-attempt','--context','sample workflow','--path','sample route','--outcome','failure','--error','sample error','--json')
        before = self.edges.read_bytes()
        self.run_cli(*args, ok=False)
        self.assertEqual(before, self.edges.read_bytes())
        self.run_cli(*args, allow=True)
        result = json.loads(self.run_cli('attempt-guard','--context','sample workflow','--path','sample route','--error','sample error','--json').stdout)
        self.assertFalse(result['allowed'])
    def test_shadow_is_explicit_and_does_not_modify_graph(self):
        args = ('shadow-observe','會議記錄證據鏈','--profile','demo','--json')
        before = self.edges.read_bytes()
        self.run_cli(*args, shadow=True, ok=False)
        self.assertFalse(self.db.exists())
        p = json.loads(self.run_cli(*args, shadow=True, allow=True).stdout)
        self.assertFalse(p['injection_enabled'])
        self.assertFalse(p['canonical_edge_write'])
        self.assertTrue(self.db.exists())
        self.assertEqual(before, self.edges.read_bytes())
        self.assertNotIn('會議記錄證據鏈'.encode(), self.db.read_bytes())
    def test_evidence_chain(self):
        p = json.loads(self.run_cli('evidence-chain','edge_demo','--json').stdout)
        self.assertTrue(p)

if __name__ == '__main__': unittest.main()
