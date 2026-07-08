import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, "-m", "codex_second_brain.cli"]
DEMO_VAULT = ROOT / "demo-vault"


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*CLI, *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def parse_json(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_validate_demo_vault(self) -> None:
        result = self.run_cli("validate", str(DEMO_VAULT))
        payload = self.parse_json(result)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["errors"], [])

    def test_consolidate_demo_vault_dry_run(self) -> None:
        result = self.run_cli("consolidate", str(DEMO_VAULT), "--dry-run")
        payload = self.parse_json(result)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["startup_missing"], [])
        self.assertIn("deleting notes", payload["permission_required_for"])
        self.assertGreaterEqual(payload["markdown_file_count"], 8)

    def test_route_suggest_uses_memory_graph_fixture(self) -> None:
        result = self.run_cli("route-suggest", str(DEMO_VAULT), "debugging noisy search source trace")
        payload = self.parse_json(result)
        self.assertTrue(payload["suggestions"])
        self.assertEqual(payload["suggestions"][0]["id"], "edge_debugging_graph_first_after_noisy_search")

    def test_capture_is_dry_run_by_default(self) -> None:
        result = self.run_cli(
            "capture",
            "--vault",
            str(DEMO_VAULT),
            "--type",
            "route-worked",
            "--summary",
            "Synthetic route succeeded",
            "--evidence",
            "demo-vault/fixtures/momo-route-result.json",
        )
        payload = self.parse_json(result)
        self.assertFalse(payload["written"])
        self.assertTrue(payload["event"]["dry_run_first"])


if __name__ == "__main__":
    unittest.main()
