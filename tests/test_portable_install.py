"""Portable install and real lexical-search acceptance using isolated temp vaults."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "bin/install-vault-runtime.py"
RUNTIME = ROOT / "system/vault-runtime"


class PortableInstallTests(unittest.TestCase):
    def run_json(self, *args: str, cwd: Path | None = None, code: int = 0):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, *map(str, args)], cwd=cwd or ROOT,
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def install(self, vault: Path):
        return self.run_json(INSTALLER, vault, "--apply")

    def test_dry_run_then_install_idempotently_without_notes_or_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp) / "new-vault"
            preview = self.run_json(INSTALLER, vault)
            self.assertFalse(vault.exists())
            self.assertEqual(preview["written"], [])
            written = self.install(vault)
            self.assertTrue(written["ok"])
            self.assertEqual(len(list((vault / ".codex/commands").glob("*.md"))), 41)
            self.assertTrue((vault / "AGENTS.md").is_file())
            self.assertIn("EXPLICIT_MAINTENANCE", (vault / "AGENTS.md").read_text())
            self.assertTrue((vault / "Knowledge/Codex/memory_graph/memory_graph_cli.py").is_file())
            self.assertEqual((vault / "Knowledge/Codex/memory_graph_edges.jsonl").read_bytes(), b"")
            self.assertFalse((vault / "index.md").exists())
            self.assertFalse((vault / "_CLAUDE.md").exists())
            again = self.install(vault)
            self.assertEqual(again["written"], [])
            self.assertFalse(any(path.suffix in {".sqlite", ".db", ".key", ".pyc"} for path in vault.rglob("*")))

    def test_existing_difference_blocks_entire_apply(self):
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            target = vault / ".codex/commands/obsidian-save.md"
            target.parent.mkdir(parents=True)
            target.write_text("user-owned change")
            report = self.run_json(INSTALLER, vault, "--apply", code=1)
            self.assertIn(".codex/commands/obsidian-save.md", report["conflicts"])
            self.assertEqual(target.read_text(), "user-owned change")
            self.assertFalse((vault / "AGENTS.md").exists())

    def test_existing_routing_and_graph_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            (vault / "AGENTS.md").write_text("existing instructions")
            graph = vault / "Knowledge/Codex/memory_graph_edges.jsonl"
            graph.parent.mkdir(parents=True)
            graph.write_text("existing graph")
            self.install(vault)
            self.assertEqual((vault / "AGENTS.md").read_text(), "existing instructions")
            self.assertEqual(graph.read_text(), "existing graph")
            self.assertTrue((vault / ".codex/AGENTS.runtime.md").is_file())

    def test_symlink_destination_is_refused_without_external_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            vault, outside = base / "vault", base / "outside"
            vault.mkdir(); outside.mkdir()
            (vault / ".codex").symlink_to(outside, target_is_directory=True)
            result = self.run_json(INSTALLER, vault, "--apply", code=2)
            self.assertIn("symlink", result["error"])
            self.assertEqual(list(outside.iterdir()), [])

    def test_real_chinese_lexical_search_and_semantic_unavailable_are_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            vault, home = Path(temp) / "vault", Path(temp) / "runtime"
            self.install(vault)
            notes = vault / "Projects"
            notes.mkdir()
            (notes / "Continuity.md").write_text("# 專案交接\n接續專案先閱讀進度與驗證證據。\n")
            script = vault / ".codex/scripts/qwen3_search.py"
            before = sorted(str(path.relative_to(vault)) for path in vault.rglob("*"))
            lexical = self.run_json(script, "--path", vault, "--home", home, "search", "專案交接", "--json")
            self.assertEqual(lexical["lexical"]["hits"][0]["path"], "Projects/Continuity.md")
            self.assertEqual(lexical["semantic"]["status"], "skipped")
            fallback = self.run_json(script, "--path", vault, "--home", home, "--backend", "qwen3", "search", "如何接續專案", "--semantic-mode", "always", "--json")
            self.assertTrue(fallback["lexical"]["hits"])
            self.assertEqual(fallback["semantic"]["status"], "unavailable")
            self.assertFalse(fallback["routing_decision"]["semantic_called"])
            self.assertFalse(home.exists())
            self.assertEqual(before, sorted(str(path.relative_to(vault)) for path in vault.rglob("*")))
            refused = self.run_json(script, "--path", vault, "--home", home, "--backend", "qwen3", "index", "--json", code=2)
            self.assertIn("--apply", refused["error"])
            self.assertFalse(home.exists())

    def test_templates_have_no_private_identity_or_obsolete_save_directive(self):
        commands = sorted((RUNTIME / "commands").glob("*.md"))
        self.assertEqual(len(commands), 41)
        for path in commands:
            content = path.read_text()
            self.assertIn("EXPLICIT_MAINTENANCE", content, path.name)
            self.assertIn("AUTO_CAPTURE` is disabled", content, path.name)
            for forbidden in ("/Users/", "saves automatically", "auto-save the following"):
                self.assertNotIn(forbidden, content, path.name)


if __name__ == "__main__":
    unittest.main()
