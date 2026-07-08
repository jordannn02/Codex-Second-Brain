import json
import shutil
import subprocess
import sys
import tempfile
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
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def copy_demo_vault(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name) / "vault"
        shutil.copytree(DEMO_VAULT, vault)
        return tmp, vault

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
        self.assertGreaterEqual(len(payload["proposed_changes"]), 1)
        self.assertIn(
            "review_orphan_candidate",
            {change["type"] for change in payload["proposed_changes"]},
        )

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
            "Graph-first routing worked",
            "--evidence",
            "Knowledge/Examples/demo.md",
        )
        payload = self.parse_json(result)
        self.assertFalse(payload["written"])
        self.assertTrue(payload["event"]["dry_run_first"])

    def test_capture_write_appends_event(self) -> None:
        tmp, vault = self.copy_demo_vault()
        self.addCleanup(tmp.cleanup)

        result = self.run_cli(
            "capture",
            "--vault",
            str(vault),
            "--type",
            "route-worked",
            "--summary",
            "Graph-first routing worked",
            "--evidence",
            "Knowledge/Examples/demo.md",
            "--write",
        )
        payload = self.parse_json(result)
        self.assertTrue(payload["written"])
        appended = (vault / "captures.jsonl").read_text(encoding="utf-8")
        self.assertIn("Graph-first routing worked", appended)

    def test_record_outcome_write_strengthens_existing_edge(self) -> None:
        tmp, vault = self.copy_demo_vault()
        self.addCleanup(tmp.cleanup)

        result = self.run_cli(
            "record-outcome",
            str(vault),
            "--edge-id",
            "edge_tool_overload_use_capability_router",
            "--outcome",
            "success",
            "--evidence",
            "tests/evidence/route-pass.md",
            "--write",
        )
        payload = self.parse_json(result)
        self.assertTrue(payload["written"])
        self.assertGreater(payload["edge"]["weight"], 0.79)
        self.assertEqual(payload["edge"]["success_count"], 3)
        self.assertIn("tests/evidence/route-pass.md", payload["edge"]["evidence"])

        stored = [
            json.loads(line)
            for line in (vault / "memory-graph.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(any(edge["id"] == "edge_tool_overload_use_capability_router" for edge in stored))

    def test_record_outcome_failure_weakens_edge(self) -> None:
        tmp, vault = self.copy_demo_vault()
        self.addCleanup(tmp.cleanup)

        result = self.run_cli(
            "record-outcome",
            str(vault),
            "--edge-id",
            "edge_momo_route_result_to_memory_graph",
            "--outcome",
            "failure",
            "--failure-signature",
            "candidate edge did not improve route suggestion",
            "--evidence",
            "tests/evidence/route-failed.md",
            "--write",
        )
        payload = self.parse_json(result)
        self.assertTrue(payload["written"])
        self.assertLess(payload["edge"]["weight"], 0.72)
        self.assertEqual(payload["edge"]["fail_count"], 1)
        self.assertEqual(
            payload["edge"]["failure_signature"],
            "candidate edge did not improve route suggestion",
        )

    def test_self_correct_weakens_failed_and_reinforces_corrected(self) -> None:
        tmp, vault = self.copy_demo_vault()
        self.addCleanup(tmp.cleanup)

        result = self.run_cli(
            "self-correct",
            str(vault),
            "--failed-edge-id",
            "edge_momo_route_result_to_memory_graph",
            "--corrected-edge-id",
            "edge_momo_route_result_to_capture_event_first",
            "--from",
            "momo route result without verification",
            "--to",
            "capture event -> verified outcome -> memory edge update",
            "--action",
            "Capture momo route results before strengthening route memory.",
            "--failure-signature",
            "route memory was strengthened before verification",
            "--evidence",
            "tests/evidence/self-correct.md",
            "--write",
        )
        payload = self.parse_json(result)
        self.assertTrue(payload["written"])
        self.assertEqual(payload["failed_edge"]["relation"], "suppress")
        self.assertEqual(payload["corrected_edge"]["relation"], "preferred_tool_for")
        self.assertGreaterEqual(payload["corrected_edge"]["success_count"], 1)

    def test_decay_proposes_stale_edge_changes(self) -> None:
        result = self.run_cli(
            "decay",
            str(DEMO_VAULT),
            "--days-unused",
            "0",
            "--amount",
            "0.2",
            "--now",
            "2026-07-09T00:00:00+00:00",
        )
        payload = self.parse_json(result)
        self.assertFalse(payload["written"])
        self.assertTrue(payload["proposed_changes"])
        self.assertTrue(all(change["after_weight"] < change["before_weight"] for change in payload["proposed_changes"]))

    def test_explain_edge_returns_evidence_and_policy(self) -> None:
        result = self.run_cli(
            "explain-edge",
            str(DEMO_VAULT),
            "edge_debugging_graph_first_after_noisy_search",
        )
        payload = self.parse_json(result)
        self.assertEqual(payload["edge"]["id"], "edge_debugging_graph_first_after_noisy_search")
        self.assertIn("why", payload)
        self.assertTrue(payload["evidence"])
        self.assertIn("verify", payload["interruption_policy"].lower())

    def test_ingest_momo_route_write_appends_capture_and_edge(self) -> None:
        tmp, vault = self.copy_demo_vault()
        self.addCleanup(tmp.cleanup)

        result = self.run_cli(
            "ingest-momo-route",
            str(vault),
            str(vault / "fixtures" / "momo-route-result.json"),
            "--write",
        )
        payload = self.parse_json(result)
        self.assertTrue(payload["written"])
        self.assertEqual(payload["capture_event"]["type"], "route-worked")
        self.assertEqual(payload["edge"]["id"], "edge_momo_route_result_to_memory_graph")
        self.assertTrue((vault / "captures.jsonl").read_text(encoding="utf-8").strip())

    def test_validate_reports_schema_errors_for_invalid_edge(self) -> None:
        tmp, vault = self.copy_demo_vault()
        self.addCleanup(tmp.cleanup)
        (vault / "memory-graph.jsonl").write_text(
            json.dumps(
                {
                    "id": "bad-edge",
                    "from": "x",
                    "to": "y",
                    "relation": "preferred_tool_for",
                    "weight": 1.4,
                    "confidence": "verified-by-use",
                    "evidence": [],
                    "action": "Bad edge should fail full schema validation.",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = self.run_cli("validate", str(vault))
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("schema" in error for error in payload["errors"]))
