---
description: obsidian-export — portable task instructions with explicit write authorization
category: meta
triggers_en: ["export vault", "snapshot vault", "dump vault", "vault export"]
---

# /obsidian-export

Clarify the export format, source scope, destination and whether the result is local or external. First produce an exact plan. Prefer the installed `export_okf.py --help` workflow when available; obey its gate manifests and validation. No export is authorization to publish or upload it. Include only authorized source material; scan every generated artifact before external release using the installed privacy gate. If a helper is unavailable, explain the limit and provide a read-only plan rather than inventing a successful export. Never include credentials, private runtime databases or agent session state.

## Authorization and execution boundary

Read `_CLAUDE.md` if present and the smallest relevant index/source. State which startup context was read. These are portable agent instructions, not CLI subcommands or a separately installed skill. Use available read-only tools or local Python; never invent a connector, credential, completed operation, or missing helper.

A research, search, review, correction, useful result, or completed task does not authorize saving. A command whose explicit purpose is creating/updating a note authorizes that requested target only. Ordinary saves use at most one durable target. Do not add Daily, board, index, log, backlink, stub, PINNED, graph feedback, or retrospective writes as follow-ups. A reusable-rule request authorizes one target containing Trigger / Rule / Scope / Evidence / Exception; it does not authorize changes to global rules or skills.

For an authorized write, enumerate exact relative targets and run:
```bash
python3 .codex/scripts/capture_gate.py --path . --mode EXPLICIT_COMMAND --target "<relative-note.md>" --dry-run --json
```
`EXPLICIT_COMMAND` permits at most one target. Explicitly requested bounded multi-file maintenance uses `EXPLICIT_MAINTENANCE` (at most five targets per manifest); `WEEKLY_CONSOLIDATION` is only for an existing authorized scheduled scope. `AUTO_CAPTURE` is disabled. A gate result is not authorization. Write only `manifest.proposed_changes`, execute its exact required post-write validation command, then read back the same targets. Preserve existing changes and evidence; do not rewrite/reformat unrelated history. Missing gate or required validation is a blocker for a write, not a reason to bypass it.

Read `.codex/references/ai-first-rules.md` and `.codex/references/write-rules.md` before note writes. New notes require `type`, `date`, `tags`, `ai-first: true`, `## For future Claude`, relevant wikilinks, dated sources and confidence where needed. Report unknown values rather than inventing them. Deliver the usable result before an attached save; if saving is the primary task, perform it directly. Retrospective analysis and saving its output require their respective authorization. Never save secrets. Sensitive, destructive, external-upload and production actions require corresponding authorization. No automatic external messages, uploads, scheduling, deletion, archive or merge.
