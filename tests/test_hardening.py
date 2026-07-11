from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from codex_second_brain.hardening import (
    analyze_health,
    audit_retention,
    check_index_freshness,
    create_backup,
    evaluate_capture_gate,
    input_fingerprint,
    inspect_status,
    render_index_stats_marker,
    run_retrieval_benchmark,
    scan_sensitive_content,
    validate_automation_ledger,
    vault_stats,
    verify_backup,
)


class HardeningTests(unittest.TestCase):
    def make_vault(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name) / "vault"
        vault.mkdir()
        for name in ["_CLAUDE.md", "index.md", "Home.md", "CRITICAL_FACTS.md"]:
            (vault / name).write_text(
                "---\ntype: system\nai-first: true\n---\n\n## For future Claude\n\nSynthetic fixture.\n",
                encoding="utf-8",
            )
        return tmp, vault

    def test_health_checks_every_unchecked_task_line(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)
        board = vault / "Board.md"
        board.write_text(
            "# Board\n\n- [ ] Future task @{2026-07-20}\n- [ ] Overdue task @{2026-07-08}\n",
            encoding="utf-8",
        )

        result = analyze_health(vault, today=date(2026, 7, 11))

        self.assertEqual(result["overdue_task_count"], 1)
        self.assertEqual(result["overdue_tasks"][0]["path"], "Board.md")
        self.assertEqual(result["overdue_tasks"][0]["line"], 4)
        self.assertEqual(result["overdue_tasks"][0]["due"], "2026-07-08")

    def test_health_reports_invalid_task_date_without_crashing(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)
        (vault / "Board.md").write_text(
            "- [ ] Invalid date @{2026-99-99}\n",
            encoding="utf-8",
        )

        result = analyze_health(vault, today=date(2026, 7, 11))

        self.assertEqual(result["state"], "degraded")
        self.assertEqual(result["invalid_task_date_count"], 1)

    def test_capture_gate_fails_closed_and_enforces_budget(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)

        denied = evaluate_capture_gate(vault, "AUTO_CAPTURE", ["Notes/result.md"], False)
        too_many = evaluate_capture_gate(
            vault,
            "AUTO_CAPTURE",
            ["Notes/one.md", "Notes/two.md"],
            True,
        )

        self.assertFalse(denied["allowed"])
        self.assertEqual(denied["exit_code"], 1)
        self.assertFalse(too_many["allowed"])
        self.assertIn("target budget", " ".join(too_many["errors"]))

    def test_capture_gate_rejects_invalid_target_as_usage_error(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)

        result = evaluate_capture_gate(vault, "AUTO_CAPTURE", ["../outside.md"], True)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["exit_code"], 2)

    def test_input_fingerprint_changes_when_corpus_changes(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)
        note = vault / "Knowledge.md"
        note.write_text("alpha", encoding="utf-8")
        first = input_fingerprint(vault)
        note.write_text("beta", encoding="utf-8")
        second = input_fingerprint(vault)

        self.assertNotEqual(first["corpus_sha256"], second["corpus_sha256"])

    def test_status_watch_detects_changed_input_and_expiry(self) -> None:
        current = {
            "corpus_sha256": "new",
            "cases_sha256": "cases",
            "policy_sha256": "policy",
        }
        manifest = {
            "valid_until": "2026-07-11T09:00:00+00:00",
            "input_fingerprint": {**current, "corpus_sha256": "old"},
        }

        result = inspect_status(
            manifest,
            current,
            now=datetime(2026, 7, 11, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(result["state"], "blocked")
        self.assertTrue(result["expired"])
        self.assertTrue(result["input_changed"])

    def test_status_watch_blocks_unknown_manifest_state(self) -> None:
        fingerprint = {
            "corpus_sha256": "corpus",
            "cases_sha256": "cases",
            "policy_sha256": "policy",
        }
        result = inspect_status(
            {
                "state": "green",
                "valid_until": "2026-07-12T00:00:00+00:00",
                "input_fingerprint": fingerprint,
            },
            fingerprint,
            now=datetime(2026, 7, 11, tzinfo=timezone.utc),
        )

        self.assertEqual(result["state"], "blocked")
        self.assertIn("unsupported manifest state: green", result["errors"])

    def test_rank_aware_retrieval_reports_topk_and_mrr(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)
        knowledge = vault / "Knowledge"
        knowledge.mkdir()
        (knowledge / "Graph Routing.md").write_text(
            "Memory graph routing uses verified edges after noisy source search.",
            encoding="utf-8",
        )
        (knowledge / "Meeting Followup.md").write_text(
            "Meeting decisions become owners, tasks, and due dates.",
            encoding="utf-8",
        )
        cases = [
            {"query": "memory graph noisy search", "expected": "Knowledge/Graph Routing.md"},
            {"query": "會議 owner due date", "expected": "Knowledge/Meeting Followup.md"},
        ]

        result = run_retrieval_benchmark(vault, cases)

        self.assertEqual(result["case_count"], 2)
        self.assertEqual(result["metrics"]["top3"], 1.0)
        self.assertGreaterEqual(result["metrics"]["mrr"], 0.75)
        self.assertIn("rank", result["cases"][0])

    def test_index_freshness_uses_machine_readable_marker(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)
        (vault / "Dev Logs").mkdir()
        (vault / "Dev Logs" / "One.md").write_text("log", encoding="utf-8")
        stats = vault_stats(vault)
        (vault / "index.md").write_text(
            "# Index\n\n" + render_index_stats_marker(stats) + "\n",
            encoding="utf-8",
        )

        self.assertTrue(check_index_freshness(vault / "index.md", stats)["current"])
        (vault / "Another.md").write_text("new", encoding="utf-8")
        self.assertFalse(
            check_index_freshness(vault / "index.md", vault_stats(vault))["current"]
        )

    def test_privacy_scanner_checks_file_contents(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)
        safe = vault / "safe.md"
        unsafe = vault / "unsafe.md"
        safe.write_text("Synthetic public note", encoding="utf-8")
        unsafe.write_text("-----BEGIN " + "PRIVATE KEY-----", encoding="utf-8")

        result = scan_sensitive_content([safe, unsafe])

        self.assertFalse(result["ok"])
        self.assertEqual(result["findings"][0]["path"], str(unsafe.resolve()))
        self.assertEqual(result["findings"][0]["rule"], "private-key")

    def test_automation_ledger_requires_real_scheduled_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "runs.jsonl"
            ledger.write_text(
                json.dumps(
                    {
                        "trigger": "manual",
                        "status": "completed",
                        "started_at": "2026-07-11T00:00:00+00:00",
                        "finished_at": "2026-07-11T00:01:00+00:00",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            missing = validate_automation_ledger(ledger, require_scheduled=True)
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "trigger": "scheduled",
                            "status": "completed",
                            "started_at": "2026-07-12T13:00:00+00:00",
                            "finished_at": "2026-07-12T13:02:00+00:00",
                        }
                    )
                    + "\n"
                )
            complete = validate_automation_ledger(ledger, require_scheduled=True)

        self.assertFalse(missing["ok"])
        self.assertTrue(complete["ok"])
        self.assertEqual(complete["scheduled_success_count"], 1)

    def test_automation_ledger_rejects_reversed_run_times(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "runs.jsonl"
            ledger.write_text(
                json.dumps(
                    {
                        "trigger": "scheduled",
                        "status": "completed",
                        "started_at": "2026-07-12T13:02:00+00:00",
                        "finished_at": "2026-07-12T13:00:00+00:00",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = validate_automation_ledger(ledger, require_scheduled=True)

        self.assertFalse(result["ok"])
        self.assertEqual(result["scheduled_success_count"], 0)
        self.assertTrue(any("precedes" in error for error in result["errors"]))

    def test_backup_includes_approved_external_state_and_verifies_restore(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)
        (vault / "Knowledge.md").write_text("durable", encoding="utf-8")
        external = Path(tmp.name) / "automation.json"
        external.write_text('{"enabled": true}', encoding="utf-8")
        destination = Path(tmp.name) / "backups"

        manifest_path = create_backup(
            vault,
            destination,
            "test",
            external={"automation": external},
        )
        result = verify_backup(manifest_path, Path(tmp.name) / "restore")

        self.assertTrue(result["ok"])
        self.assertEqual(result["mismatches"], [])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        external_roots = {
            "/".join(row["archive_path"].split("/")[:2])
            for row in manifest["files"]
            if row["archive_path"].startswith("external/")
        }
        self.assertIn("external/automation", external_roots)

    def test_backup_rejects_destination_or_restore_inside_source_vault(self) -> None:
        tmp, vault = self.make_vault()
        self.addCleanup(tmp.cleanup)
        with self.assertRaisesRegex(ValueError, "outside the source vault"):
            create_backup(vault, vault / "backups", "unsafe")

        manifest_path = create_backup(vault, Path(tmp.name) / "backups", "safe")
        with self.assertRaisesRegex(ValueError, "outside the source vault"):
            verify_backup(manifest_path, vault / "restore")

    def test_retention_audit_keeps_scheduled_evidence_separate(self) -> None:
        policy = {
            "minimum_backup_count": 1,
            "maximum_backup_age_days": 7,
            "maximum_status_age_hours": 24,
            "require_scheduled_success": True,
        }
        backup_times = [datetime(2026, 7, 11, 8, tzinfo=timezone.utc)]
        status_manifest = {"generated_at": "2026-07-11T08:30:00+00:00"}
        ledger = [
            {
                "trigger": "manual",
                "status": "completed",
                "finished_at": "2026-07-11T08:45:00+00:00",
            }
        ]

        result = audit_retention(
            policy,
            backup_times,
            ledger,
            status_manifest,
            now=datetime(2026, 7, 11, 9, tzinfo=timezone.utc),
        )

        self.assertEqual(result["state"], "degraded")
        self.assertIn("scheduled_run_evidence_missing", result["issues"])

    def test_retention_audit_flags_stale_scheduled_success(self) -> None:
        result = audit_retention(
            {
                "minimum_backup_count": 1,
                "maximum_backup_age_days": 7,
                "maximum_status_age_hours": 24,
                "maximum_scheduled_run_age_hours": 24,
                "require_scheduled_success": True,
            },
            [datetime(2026, 7, 11, 8, tzinfo=timezone.utc)],
            [
                {
                    "trigger": "scheduled",
                    "status": "completed",
                    "finished_at": "2026-07-09T08:00:00+00:00",
                }
            ],
            {"generated_at": "2026-07-11T08:30:00+00:00"},
            now=datetime(2026, 7, 11, 9, tzinfo=timezone.utc),
        )

        self.assertIn("scheduled_run_too_old", result["issues"])


if __name__ == "__main__":
    unittest.main()
