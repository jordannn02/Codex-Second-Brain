# Contributing

Thanks for improving Codex Second Brain OS.

## Contribution Guidelines

- Keep examples synthetic and public-safe.
- Do not include private notes, raw transcripts, screenshots, credentials, customer data, production IDs, or private vault exports.
- Prefer dry-run reports before write behavior.
- Keep memory separate from proof.
- Add or update tests when changing CLI behavior.
- Update schemas when changing durable JSON or JSONL shapes.

## Local Checks

Run these before opening a pull request:

```bash
python3 -m codex_second_brain.cli validate demo-vault
python3 -m codex_second_brain.cli consolidate demo-vault --dry-run
python3 -m codex_second_brain.cli route-suggest demo-vault "debugging noisy search source trace"
python3 -m unittest discover -s tests
```

## Public Fixture Rule

Fixtures should show structure and behavior, not real history. If a fixture was inspired by private work, rewrite it into a synthetic scenario before committing.
