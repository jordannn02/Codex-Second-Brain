# Health Hardening

This reference package keeps health maintenance bounded and evidence-safe.

- Run health checks with an explicit scope and treat reports as read-only evidence.
- Separate routine capture from weekly consolidation; routine capture should have a small target budget.
- Require an allowlist before a rollout or external export. Publish methods and synthetic fixtures, never private vault content.
- Record automation trigger, terminal status, duration, runner version, and known-versus-unknown cost. Do not estimate missing billing data.
- Persist JSONL state atomically: write a complete temporary file, `fsync`, then replace the old file.
- Verify backups by checking archive hashes and restoring into a separate working directory. Never test restoration by overwriting the source vault.

These are operating constraints, not a substitute for user approval around deletion, archiving, merging, or sensitive data.
