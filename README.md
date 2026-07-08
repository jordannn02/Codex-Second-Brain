# Codex Second Brain OS: Adaptive Route Memory for AI Agents

Failure-path weakening, self-correction, success-route reinforcement, evidence layers, verifiable conclusions, route memory, capability routing, adaptive tool selection, auto-triggered capture routing, and weekly consolidation for Codex-powered work.

This is not a note-taking template. Codex Second Brain OS is an agent operating layer that turns Markdown, Obsidian, command files, local evidence, and workflow history into an adaptive routing system. It starts from three claims: long-term memory evolution matters, old conclusions can be updated, and contradictions can be detected before they silently mislead future work.

The design language comes from human memory: association, retrieval, reinforcement, inhibition, consolidation, forgetting, and reconsolidation translated into practical AI-agent workflows.

## Core Features: Route Memory, Evidence Layers, Capability Routing, Auto-Triggers

Most "AI + notes" systems store information. Codex Second Brain OS changes agent behavior.

### 1. Failure-Path Weakening, Self-Correction, and Success-Route Reinforcement

When a workflow succeeds and is verified, that route can become stronger. When a route fails, the system records the error signature and weakens or suppresses that path. The corrected route becomes easier for future agents to retrieve.

### 2. Evidence Layers, Verifiable Conclusions, and Route Memory

The system separates memory from proof. Notes can guide investigation, but source code, SQL results, runtime checks, documents, screenshots, and manual verification remain distinct evidence layers. A conclusion becomes stronger only when its proof path is clear.

### 3. Capability Routing and Adaptive Tool Selection

The agent does not use one generic workflow for every request. It first classifies the task, then chooses the narrowest useful capability: document conversion, code search, SQL, browser automation, GitHub workflow, dashboard generation, vault search, or memory-graph lookup.

### 4. Auto-Triggered Capture Routing and Weekly Consolidation

Capture, logging, health checks, route review, and weekly consolidation can be triggered by explicit commands, scheduled automation, post-delivery hooks, or repeated failure patterns. The vault improves without requiring the user to manually organize every note.

### 5. Adaptive Learning Loop

Every meaningful attempt can update the memory graph:

```text
task -> route -> execution -> verification -> reinforcement or correction
```

The system learns successful paths, failed paths, stale paths, corrected paths, and contradictions.

### 6. Long-Term Knowledge Evolution and Old-Conclusion Updates

Old conclusions can be updated when new evidence appears. The previous belief is preserved as history, while the current conclusion points to the newest verified source.

### 7. Contradiction Handling

Contradictions are not hidden. The system can surface conflicts between old notes and new evidence, preserve what was believed before, and mark which conclusion is currently trusted.

### 8. Delivery-First Memory

The user-visible result comes first. Capture, save, graph updates, and cleanup happen only after the answer, file, query result, report, or artifact has been delivered.

## Visual Overview

![Human-memory-inspired agent memory loop](assets/homepage-system-flow.svg)

![Redacted demo vault example](assets/homepage-demo-vault.svg)

## Core Idea

An agent should not rediscover the same workflow every day.

When a task succeeds, the system records the route:

```text
task context -> chosen capability -> evidence used -> result -> verification -> reusable edge
```

When a task fails, the failure is also useful:

```text
task context -> failed path -> error signature -> suppression rule -> corrected route
```

When a conclusion becomes stale, the system keeps history and updates the current answer:

```text
old conclusion -> new evidence -> contradiction review -> revised conclusion
```

Over time, the vault becomes more than storage. It becomes an inspectable memory graph that tells future agents:

- what to read first;
- which tool to prefer;
- what proof is required;
- which path to avoid;
- what should be automated;
- which conclusion changed;
- what must stay private.

## Runtime Loop

1. **Load startup context**
   Read `_CLAUDE.md`, `index.md`, `Home.md`, and `CRITICAL_FACTS.md` so the agent understands local rules before acting.

2. **Run capability preflight**
   Classify the task and choose the narrowest useful route.

3. **Deliver first**
   Produce the answer, file, query result, report, or artifact before saving memory.

4. **Separate evidence layers**
   Keep memory, documentation, source code, SQL, runtime screens, and write authority as separate claims.

5. **Capture durable signals**
   Save decisions, exact commands, source paths, error strings, verified query shapes, tool choices, and reusable workflow lessons.

6. **Reinforce and weaken graph edges**
   Strengthen routes that worked. Decay unused routes. Suppress routes with repeated failure signatures. Record corrected paths.

7. **Trigger maintenance automatically**
   Scheduled command-driven consolidation refreshes indexes, surfaces stale rules, detects orphan notes, and proposes cleanup without deleting evidence.

## Repository Scope

This public repository contains only two publishable layers:

| Folder | Contains | Does not contain |
|---|---|---|
| `system/` | Agent rules, capture routing, memory graph model, weekly consolidation workflow, and command catalog patterns. | Private notes, credentials, production systems, or real customer data. |
| `demo-vault/` | A synthetic Markdown vault showing how tasks become delivered artifacts plus reusable memory. | Real people, company data, finance notes, internal meetings, or production IDs. |

## Practical Examples

### Repeated Debugging Route Learns From Failure

An agent first tries broad text search and wastes time. The verified fix is to start from the code graph, trace callers and callees, then inspect the exact source snippet. The failed route is weakened, the corrected route is reinforced, and the next similar debugging task starts from a better path.

### Tool Overload Auto-Router

A user has many skills, plugins, connectors, and local tools. Instead of asking the user which tool to use, the agent classifies the task and routes itself: document parser for files, GitHub workflow for repository work, browser automation for live UI, SQL for data questions, and memory graph lookup for repeated workflow patterns.

### Meeting-to-Execution Memory

A meeting produces decisions, owners, risks, and follow-up tasks. The agent delivers the meeting summary first, then captures only durable signals. Weekly consolidation promotes repeated themes into reusable rules and flags contradictions between earlier decisions and what the team now believes.

## Repository Layout

```text
.
├── README.md
├── assets/
│   ├── homepage-system-flow.svg
│   └── homepage-demo-vault.svg
├── system/
│   ├── README.md
│   ├── AGENTS.example.md
│   ├── capture-routing.md
│   ├── memory-graph.md
│   ├── weekly-consolidation.md
│   └── .codex/commands/README.md
└── demo-vault/
    ├── README.md
    ├── _CLAUDE.md
    ├── index.md
    ├── Home.md
    ├── CRITICAL_FACTS.md
    ├── Knowledge/Examples/
    ├── Dev Logs/
    └── Logs/
```

## How to Adopt

1. Copy `system/AGENTS.example.md` into your agent instructions and trim it for your environment.
2. Create a small vault with `_CLAUDE.md`, `index.md`, `Home.md`, and `CRITICAL_FACTS.md`.
3. Use capture routing only after the user-visible result is complete.
4. Start recording workflow successes and failures as memory-graph edges.
5. Add scheduled consolidation only after captures begin to accumulate.
6. Keep real private data in a private vault or private repository.

## Safety Rule

Publish the operating system, not the private memory.

The examples in this repository are synthetic, redacted, and intentionally generic. Never publish raw transcripts, credentials, financial records, private notes, internal customer data, or production identifiers.
