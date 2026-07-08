# Command Catalog Pattern

This folder is a public placeholder for command-driven second-brain workflows. It does not include private command bodies from a real vault.

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

Do not publish private `.codex/commands/` files from a real vault. Instead, publish command patterns, redacted examples, or synthetic fixtures.
