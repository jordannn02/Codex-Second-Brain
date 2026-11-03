import sys
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1] / 'system/vault-runtime/scripts'
sys.path.insert(0, str(RUNTIME))
import capture_gate as gate
import vault_health as health
import vault_backup_restore as backup

VALID = '---\ntype: note\ndate: 2026-01-01\ntags: [example]\nai-first: true\n---\n\n## For future Claude\n\nA note.\n'

class PortableRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.vault = self.root / 'vault'
        self.vault.mkdir()
    def tearDown(self):
        self.tmp.cleanup()
    def plan(self, mode, targets):
        return gate.plan_capture(self.vault, mode, targets, True, True)
    def test_limits_and_target_guards(self):
        self.assertFalse(self.plan('AUTO_CAPTURE', ['a.md'])['allowed'])
        self.assertFalse(self.plan('EXPLICIT_COMMAND', ['a.md', 'b.md'])['allowed'])
        self.assertTrue(self.plan('EXPLICIT_MAINTENANCE', [f'{i}.md' for i in range(5)])['allowed'])
        self.assertFalse(self.plan('EXPLICIT_MAINTENANCE', [f'{i}.md' for i in range(6)])['allowed'])
        for targets in ([], ['../outside.md'], ['/tmp/outside.md'], ['a.md','a.md'], ['a.txt']):
            self.assertFalse(self.plan('EXPLICIT_COMMAND', targets)['allowed'])
        (self.vault/'escape').symlink_to(self.root, target_is_directory=True)
        self.assertFalse(self.plan('EXPLICIT_COMMAND', ['escape/outside.md'])['allowed'])
    def test_schema_delta_and_vault_binding(self):
        note = self.vault / 'note.md'
        note.write_text(VALID)
        result = self.plan('EXPLICIT_COMMAND', ['note.md'])
        token = result['manifest']['post_write_schema_validation']['verification_token']
        self.assertTrue(gate.verify_capture(self.vault, token)['passed'])
        note.write_text('plain text')
        self.assertFalse(gate.verify_capture(self.vault, token)['passed'])
        other = self.root/'other'; other.mkdir()
        with self.assertRaises(ValueError): gate.verify_capture(other, token)
        result = self.plan('EXPLICIT_COMMAND', ['new.md'])
        token = result['manifest']['post_write_schema_validation']['verification_token']
        (self.vault/'new.md').write_text('plain text')
        self.assertFalse(gate.verify_capture(self.vault, token)['passed'])
    def test_health_and_isolated_backup_restore(self):
        (self.vault/'note.md').write_text(VALID)
        result = health.run_health_check(self.vault, health.SCOPE_PROFILES['core'])
        self.assertIsInstance(result, dict)
        snap = backup.snapshot(self.vault, self.root/'backups', 'test')
        verification = backup.verify_restore(Path(snap['manifest']), self.root/'isolated')
        self.assertEqual(verification['level'], 'verified-working')
        self.assertEqual((self.vault/'note.md').read_text(), VALID)

    def test_backup_rejects_links_and_nested_destination(self):
        outside = self.root/'private.txt'; outside.write_text('private')
        link = self.vault/'linked.md'; link.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlink_not_supported'):
            backup.snapshot(self.vault, self.root/'backups', 'test')
        link.unlink()
        directory = self.vault/'linked-dir'; directory.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink_not_supported'):
            backup.snapshot(self.vault, self.root/'backups', 'test')
        directory.unlink()
        alias = self.root/'vault-alias'; alias.symlink_to(self.vault, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'vault_symlink'):
            backup.snapshot(alias, self.root/'backups', 'test')
        with self.assertRaisesRegex(ValueError, 'backup_destination_inside_source'):
            backup.snapshot(self.vault, self.vault/'backups', 'test')
        self.assertFalse((self.vault/'backups').exists())

    def test_snapshot_status_does_not_claim_restore_verified(self):
        (self.vault/'note.md').write_text(VALID)
        snap = backup.snapshot(self.vault, self.root/'backups', 'test')
        self.assertEqual(snap['level'], 'snapshot-created')
        self.assertFalse(snap['restore_verified'])

    def test_restore_rejects_escaping_archive_without_touching_outside(self):
        archive = self.root/'hostile.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            member = tarfile.TarInfo('../outside.txt'); member.size = 1
            tar.addfile(member, io.BytesIO(b'x'))
        manifest = self.root/'hostile.json'
        manifest.write_text(json.dumps({'archive': str(archive), 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'schema': 'vault-backup/v2', 'files': {}}))
        archive.chmod(0o400); manifest.chmod(0o400)
        outside = self.root/'outside.txt'; outside.write_text('original')
        with self.assertRaises(tarfile.TarError): backup.verify_restore(manifest, self.root/'restore')
        self.assertEqual(outside.read_text(), 'original')

if __name__ == '__main__': unittest.main()
