# Portable Second Brain Agent Routing

Read this vault's `_CLAUDE.md` if present, then its compact `index.md` only when historical context matters. State which startup context was read. Read the smallest related source; memory is advisory and does not replace current source/runtime verification.

For a matching slash command or clear natural-language equivalent, open its `.codex/commands/<name>.md` and follow the concrete steps. These are agent instructions, not executable CLI commands. Optional external connectors and skills are not installed or implied. Use available tools and report missing capability honestly.

## Explicit authorization

Ordinary conversations, corrections, successes and failures never authorize persistence. Ordinary explicit saves use at most one durable target. Reusable rules require Trigger / Rule / Scope / Evidence / Exception. Do not propagate to Daily, index, board, log, PINNED, graph or stubs. Explicit bounded maintenance uses EXPLICIT_MAINTENANCE (at most five targets per manifest); weekly mode requires an existing authorized scheduled scope. AUTO_CAPTURE is disabled. Before writes run the capture gate, inspect the manifest, run its required post-write validation and read back exact targets. A gate result does not grant authorization. No automatic retrospective or global rule changes. Never save secrets.

## Read-only graph and search

From the vault root:
```bash
python3 Knowledge/Codex/memory_graph/memory_graph_cli.py --edges Knowledge/Codex/memory_graph_edges.jsonl preflight "<task>" --json
python3 .codex/scripts/qwen3_search.py --path . --scope core search "<query>" --json
```
Graph guidance must not trigger feedback writes. Search is lexical by default; optional Qwen requires explicit backend selection and existing local configuration. Never start/download a model from a task requiring only search.

## Command map

- `/create-command` → `.codex/commands/create-command.md`
- `/idea-discovery` → `.codex/commands/idea-discovery.md`
- `/notebooklm` → `.codex/commands/notebooklm.md`
- `/obsidian-adr` → `.codex/commands/obsidian-adr.md`
- `/obsidian-architect` → `.codex/commands/obsidian-architect.md`
- `/obsidian-board` → `.codex/commands/obsidian-board.md`
- `/obsidian-capture` → `.codex/commands/obsidian-capture.md`
- `/obsidian-catchup` → `.codex/commands/obsidian-catchup.md`
- `/obsidian-challenge` → `.codex/commands/obsidian-challenge.md`
- `/obsidian-connect` → `.codex/commands/obsidian-connect.md`
- `/obsidian-daily` → `.codex/commands/obsidian-daily.md`
- `/obsidian-decide` → `.codex/commands/obsidian-decide.md`
- `/obsidian-emerge` → `.codex/commands/obsidian-emerge.md`
- `/obsidian-export` → `.codex/commands/obsidian-export.md`
- `/obsidian-find` → `.codex/commands/obsidian-find.md`
- `/obsidian-graduate` → `.codex/commands/obsidian-graduate.md`
- `/obsidian-health` → `.codex/commands/obsidian-health.md`
- `/obsidian-ingest` → `.codex/commands/obsidian-ingest.md`
- `/obsidian-init` → `.codex/commands/obsidian-init.md`
- `/obsidian-learn` → `.codex/commands/obsidian-learn.md`
- `/obsidian-log` → `.codex/commands/obsidian-log.md`
- `/obsidian-panel` → `.codex/commands/obsidian-panel.md`
- `/obsidian-person` → `.codex/commands/obsidian-person.md`
- `/obsidian-project` → `.codex/commands/obsidian-project.md`
- `/obsidian-projects` → `.codex/commands/obsidian-projects.md`
- `/obsidian-recap` → `.codex/commands/obsidian-recap.md`
- `/obsidian-reconcile` → `.codex/commands/obsidian-reconcile.md`
- `/obsidian-recurring` → `.codex/commands/obsidian-recurring.md`
- `/obsidian-review` → `.codex/commands/obsidian-review.md`
- `/obsidian-save` → `.codex/commands/obsidian-save.md`
- `/obsidian-synthesize` → `.codex/commands/obsidian-synthesize.md`
- `/obsidian-task` → `.codex/commands/obsidian-task.md`
- `/obsidian-visualize` → `.codex/commands/obsidian-visualize.md`
- `/obsidian-world` → `.codex/commands/obsidian-world.md`
- `/podcast` → `.codex/commands/podcast.md`
- `/research-deep` → `.codex/commands/research-deep.md`
- `/research` → `.codex/commands/research.md`
- `/vault-deep-synthesis` → `.codex/commands/vault-deep-synthesis.md`
- `/x-pulse` → `.codex/commands/x-pulse.md`
- `/x-read` → `.codex/commands/x-read.md`
- `/youtube` → `.codex/commands/youtube.md`
