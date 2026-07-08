---
date: 2026-07-08
type: knowledge
tags:
  - demo
  - workflow
  - image-to-markdown
ai-first: true
source: "Synthetic public demo fixture."
confidence: example
---

# Image to Markdown Workflow

## For future Claude

Use this note as a public-safe example of capture routing. It shows how a screenshot conversion task should preserve source, output, and verification boundary without exposing private source content.

## Scenario

User provides a screenshot containing a table and asks:

```text
Convert this into a Markdown file.
```

## Delivery

The agent creates:

```text
outputs/example-screenshot-table.md
```

The file contains a clean Markdown table with source filename and extraction boundary.

## Capture Boundary

Save:

- task type: image/document extraction;
- source artifact name;
- output artifact path;
- whether OCR or manual correction was used;
- verification method.

Do not save:

- private screenshot content;
- real customer names;
- production document numbers;
- unrelated conversation.

## Reusable Lesson

For screenshot-to-Markdown tasks, first try structured extraction. If OCR returns no useful text, use visual inspection and explicitly state the extraction boundary.

