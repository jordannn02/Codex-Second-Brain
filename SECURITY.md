# Security Policy

Codex Second Brain OS is a public-safe reference package for agent memory workflows. It should publish methods, schemas, fixtures, and redacted examples, not private memory.

## Supported Scope

This repository contains:

- public operating rules;
- synthetic demo vault content;
- schemas for route memory and capture events;
- a minimal dry-run-first CLI;
- tests for public fixtures.

It must not contain:

- credentials, tokens, keys, cookies, or secrets;
- raw private notes, transcripts, screenshots, or financial records;
- customer data, employee data, internal meeting notes, production identifiers, or private system names;
- generated exports of a real vault unless manually redacted and reviewed.

## Dry-Run-First Rule

Automation should report before it writes. The reference CLI follows this boundary:

- `second-brain capture` prints an event by default and writes only with `--write`.
- `second-brain consolidate --dry-run` reports candidates and does not delete, archive, merge, or rewrite notes.
- destructive cleanup is intentionally outside the public reference CLI.

## Reporting a Vulnerability

If you find a security issue, open a private channel with the maintainer before posting details publicly. Include:

- affected file or command;
- reproduction steps;
- why the behavior could expose private data or perform an unsafe action;
- suggested mitigation if known.

Do not include real secrets, private notes, tokens, or customer data in the report.

## Maintainer Checklist Before Publishing

Before pushing changes to this public repository:

1. Run a sensitive-term scan for private company names, production IDs, credentials, and personal data.
2. Run `python3 -m codex_second_brain.cli validate demo-vault`.
3. Run `python3 -m unittest discover -s tests`.
4. Confirm the changed files are under this public package, not the private vault root.
