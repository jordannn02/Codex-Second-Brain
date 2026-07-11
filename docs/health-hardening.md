# Health Hardening

This reference package keeps health maintenance bounded and evidence-safe. In
version 0.5 these controls are executable through `second-brain` and reusable
from `codex_second_brain.hardening`.

- Run health checks with an explicit scope and treat reports as read-only evidence.
- Separate routine capture from weekly consolidation; routine capture should have a small target budget.
- Require an allowlist before a rollout or external export. Publish methods and synthetic fixtures, never private vault content.
- Record automation trigger, terminal status, duration, runner version, and known-versus-unknown cost. Do not estimate missing billing data.
- Persist JSONL state atomically: write a complete temporary file, `fsync`, then replace the old file.
- Verify backups by checking archive hashes and restoring into a separate working directory. Never test restoration by overwriting the source vault.

These are operating constraints, not a substitute for user approval around deletion, archiving, merging, or sensitive data.

## Executable checks

```bash
second-brain health demo-vault --today 2026-07-11
second-brain capture-gate demo-vault \
  --mode AUTO_CAPTURE \
  --target "Knowledge/Synthetic capture.md" \
  --delivery-complete
second-brain retrieval-benchmark demo-vault \
  --cases demo-vault/fixtures/retrieval-cases.json
second-brain privacy-scan codex_second_brain demo-vault
```

Create a content-aware status manifest, then verify both its TTL and its input
fingerprints:

```bash
second-brain status-build demo-vault \
  --cases demo-vault/fixtures/retrieval-cases.json \
  --output /tmp/second-brain-status.json \
  --write
second-brain status-watch /tmp/second-brain-status.json demo-vault \
  --cases demo-vault/fixtures/retrieval-cases.json
```

The watchdog returns non-zero when the manifest is expired or when corpus,
benchmark-case, or policy content changed after the manifest was created.

## Evidence boundaries

- `manual` and `scheduled` automation ledger entries are distinct. A manual run
  cannot satisfy `--require-scheduled`.
- Backup verification restores into an empty, isolated work directory and
  compares every recorded hash. It never restores over the source vault.
- Secret findings are redacted in output. A clean synthetic fixture does not
  prove that some other export is safe; scan the exact release targets.
- The capability contract reports what the public package executes. It does not
  imply parity with a private vault or an installed skill surface.
