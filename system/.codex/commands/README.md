# Command Catalog Pattern

This legacy catalog describes the reference CLI. The full public-safe set of 41 command templates now ships in `system/vault-runtime/commands/`; install it with `bin/install-vault-runtime.py` as described in `docs/installation.md`. Templates are adapted workflows, not private vault notes or credentials.

## Recommended Commands

| Command | Purpose | Reference CLI |
|---|---|---|
| `/second-brain-init` | Create a minimal vault skeleton. | `second-brain init <vault>` |
| `/second-brain-validate` | Check startup files and JSONL fixtures. | `second-brain validate <vault>` |
| `/second-brain-capture` | Create a dry-run capture event after delivery. | `second-brain capture ...` |
| `/second-brain-route` | Suggest a route from memory graph edges. | `second-brain route-suggest <vault> <query>` |
| `/second-brain-consolidate` | Produce a dry-run maintenance report. | `second-brain consolidate <vault> --dry-run` |

## Command Safety Rules

Commands should:

- load startup context before acting;
- deliver the user-visible result before memory work;
- produce dry-run output before writing;
- keep evidence layers separate;
- ask before deletion, archival, merging, publishing, or production changes.

## Public Boundary

Publish reviewed, public-safe command templates and synthetic fixtures only. Do not publish private notes, account details or machine-specific command bodies.
