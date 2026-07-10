# Codex Second Brain OS

Adaptive route memory for AI agents.

Codex Second Brain OS is a public-safe reference package for agent memory workflows. It turns Markdown, Obsidian-style vaults, command files, local evidence, and workflow history into a small operating layer for AI agents.

It is not a note-taking template. It helps an agent decide what to read, which capability to use, what proof is required, and which failed route should be weakened next time.

The design language comes from human memory: association, retrieval, reinforcement, inhibition, consolidation, forgetting, and reconsolidation.

## What Makes It Different

Most "AI + notes" systems store information. Codex Second Brain OS changes agent behavior.

| Capability | What it means |
|---|---|
| Failure-path weakening | Routes that repeatedly fail become less attractive or explicitly suppressed. |
| Self-correction | A failed path can be replaced by a corrected route with evidence. |
| Success-route reinforcement | Verified successful workflows become easier to reuse. |
| Evidence layers | Memory, documents, source code, query results, runtime checks, and manual approval stay separate. |
| Adaptive tool selection | The agent routes tasks to the narrowest useful capability instead of using one generic workflow. |
| Long-term memory evolution | Old conclusions can be updated when new evidence appears. |
| Contradiction handling | Conflicting notes become review targets instead of silent confusion. |
| Dry-run-first automation | Maintenance reports before it writes, deletes, archives, or merges. |

## Current Status

This repository is an alpha reference implementation. It includes:

- a system specification;
- a synthetic demo vault;
- machine-readable schemas;
- a minimal CLI;
- dry-run consolidation reports;
- tests over the demo vault;
- a `momo-tools` integration fixture;
- public safety and licensing files.
- atomic JSONL persistence for capture and route-memory writes.

The goal is not to ship a huge memory platform in one step. The goal is to make the method inspectable, forkable, and testable.

## Visual Overview

![Human-memory-inspired agent memory loop](assets/visual-overview-route-memory.png)

![Redacted demo vault example](assets/visual-overview-demo-vault.png)

## Quick Start

Run the reference CLI from the repository root:

```bash
python3 -m codex_second_brain.cli validate demo-vault
python3 -m codex_second_brain.cli consolidate demo-vault --dry-run
python3 -m codex_second_brain.cli route-suggest demo-vault "debugging noisy search source trace"
```

Create a new minimal vault skeleton:

```bash
python3 -m codex_second_brain.cli init ./my-vault
```

Generate a capture event without writing it:

```bash
python3 -m codex_second_brain.cli capture \
  --vault demo-vault \
  --type route-worked \
  --summary "Debugging route succeeded after graph-first tracing" \
  --evidence "demo-vault/fixtures/memory-graph.jsonl"
```

Add `--write` only when you intentionally want to append to `captures.jsonl`.

## Adaptive Memory Operations

The reference CLI includes executable memory-graph operations:

```bash
python3 -m codex_second_brain.cli record-outcome demo-vault \
  --edge-id edge_tool_overload_use_capability_router \
  --outcome success \
  --evidence tests/evidence/route-pass.md

python3 -m codex_second_brain.cli self-correct demo-vault \
  --failed-edge-id edge_momo_route_result_to_memory_graph \
  --corrected-edge-id edge_momo_route_result_to_capture_event_first \
  --from "momo route result without verification" \
  --to "capture event -> verified outcome -> memory edge update" \
  --action "Capture momo route results before strengthening route memory."

python3 -m codex_second_brain.cli decay demo-vault --days-unused 30 --amount 0.1
python3 -m codex_second_brain.cli explain-edge demo-vault edge_debugging_graph_first_after_noisy_search
python3 -m codex_second_brain.cli ingest-momo-route demo-vault demo-vault/fixtures/momo-route-result.json
```

These commands stay dry-run-first unless `--write` is set. Successful outcomes reinforce useful paths, failed outcomes weaken or suppress bad paths, decay prevents stale memory from dominating, and `explain-edge` makes a route recommendation inspectable.

## Runtime Loop

```text
load startup context
  -> run capability preflight
  -> deliver user-visible result
  -> verify evidence
  -> capture durable signal
  -> reinforce or weaken route memory
  -> consolidate with dry-run reports
```

The startup context is intentionally small:

- `_CLAUDE.md` for local agent rules;
- `index.md` for the vault map;
- `Home.md` for the dashboard;
- `CRITICAL_FACTS.md` for tiny always-load facts.

The agent should not read the entire vault before every task.

## Repository Layout

```text
.
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── ROADMAP.md
├── pyproject.toml
├── codex_second_brain/
│   └── cli.py
├── schemas/
│   ├── memory-edge.schema.json
│   ├── capture-event.schema.json
│   └── vault-index.schema.json
├── docs/
│   ├── architecture.md
│   ├── dry-run-automation.md
│   ├── momo-tools-integration.md
│   └── schemas.md
├── system/
│   ├── AGENTS.example.md
│   ├── capture-routing.md
│   ├── memory-graph.md
│   ├── weekly-consolidation.md
│   └── .codex/commands/README.md
├── demo-vault/
│   ├── _CLAUDE.md
│   ├── index.md
│   ├── Home.md
│   ├── CRITICAL_FACTS.md
│   ├── Knowledge/Examples/
│   └── fixtures/
└── tests/
    └── test_cli.py
```

## Schemas

The `schemas/` folder defines machine-readable formats for:

- `memory-edge.schema.json`: route memory edges with weight, confidence, decay state, evidence, and action;
- `capture-event.schema.json`: post-delivery durable memory candidates;
- `vault-index.schema.json`: a compact machine-readable vault navigation map.

See [docs/schemas.md](docs/schemas.md).

## Minimal CLI

The reference CLI is deliberately small and keeps schema validation explicit.

| Command | Purpose |
|---|---|
| `second-brain init <vault>` | Create `_CLAUDE.md`, `index.md`, `Home.md`, `CRITICAL_FACTS.md`, `memory-graph.jsonl`, and `captures.jsonl`. |
| `second-brain validate <vault>` | Validate startup files plus JSONL fixtures. |
| `second-brain capture ...` | Create a capture event; dry-run unless `--write` is set. |
| `second-brain consolidate <vault> --dry-run` | Report startup gaps, orphan candidates, and low-confidence edges. |
| `second-brain route-suggest <vault> <query>` | Suggest routes from memory graph edges. |
| `second-brain record-outcome <vault> ...` | Reinforce successful routes or weaken failed routes. |
| `second-brain self-correct <vault> ...` | Suppress a failed route and reinforce the corrected one. |
| `second-brain decay <vault>` | Lower old unused edge weights so stale memory stops dominating. |
| `second-brain explain-edge <vault> <edge-id>` | Explain why a route memory edge would be selected. |
| `second-brain ingest-momo-route <vault> <json>` | Convert a momo-tools route result into a capture event and memory edge update. |

After installation, the console script is available as `second-brain`. During development, use:

```bash
python3 -m codex_second_brain.cli --help
```

## Demo Vault as Golden Fixture

The demo vault is synthetic and public-safe. It includes:

- repeated debugging route learning;
- tool overload auto-routing;
- meeting-to-execution memory;
- capture events;
- memory graph edges;
- a synthetic `momo-tools` route result.

The tests treat this demo vault as a golden fixture:

```bash
python3 -m unittest discover -s tests
```

## momo-tools Integration

`momo-tools` can act as the front-end capability router and risk gate. Codex Second Brain OS acts as the long-term route-learning layer.

```text
user task
  -> momo-tools route / gate / verify
  -> agent executes bounded task
  -> deliver result
  -> Codex Second Brain captures durable signal
  -> memory graph strengthens or weakens route
  -> future routing gets better context
```

See [docs/momo-tools-integration.md](docs/momo-tools-integration.md).

## Safety Rule

Publish the operating system, not the private memory.

This public repository should contain methods, schemas, docs, and synthetic fixtures only. Do not publish raw transcripts, credentials, financial records, private notes, internal customer data, production identifiers, or private vault exports.

See [SECURITY.md](SECURITY.md).

## Health Hardening

Version 0.4 adds operational hardening learned from a real vault maintenance pass, without publishing any private vault data. JSONL capture and memory-graph updates now use `fsync` plus atomic replacement, so an interrupted write leaves either the old complete file or the new complete file. The companion design note covers scoped health checks, bounded capture, privacy gates, and snapshot/restore verification: [docs/health-hardening.md](docs/health-hardening.md).

## Roadmap and Contributions

- See [ROADMAP.md](ROADMAP.md) for the implementation plan.
- See [CONTRIBUTING.md](CONTRIBUTING.md) for public-safe contribution rules.

## License

MIT. See [LICENSE](LICENSE).
