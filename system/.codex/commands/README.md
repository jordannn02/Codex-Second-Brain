# Command Catalog Pattern

This folder demonstrates how command files can be grouped without publishing private command bodies.

## Recommended Groups

| Group | Example commands | Purpose |
|---|---|---|
| Vault | `obsidian-save`, `obsidian-find`, `obsidian-health` | Capture, search, and maintain notes. |
| Thinking | `obsidian-challenge`, `obsidian-synthesize`, `obsidian-decide` | Turn notes into judgment. |
| Research | `research`, `youtube`, `podcast`, `notebooklm` | Bring outside sources into the vault. |
| Meta | `obsidian-init`, `obsidian-export`, `obsidian-visualize` | Bootstrap and inspect the system. |

## Public-Safe Rule

Publish command structure and design intent. Redact:

- private vault paths;
- customer-specific terms;
- credentials;
- internal company procedures;
- raw prompts copied from proprietary systems;
- production database details.

