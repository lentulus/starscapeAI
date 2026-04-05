# Feature Name

## Overview
Brief description of what this feature does and why.

## Requirements
- Bullet list of what must be true when this is done.
- Be specific: inputs, outputs, edge cases.

## Data / Schema
Describe any new tables, columns, or changes to `sql/schema.sql`.

```sql
-- example
CREATE TABLE IF NOT EXISTS foo (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
```

## Shared Code
Modules to add or modify under `src/starscape5/`.

## Scripts
New programs to add under `scripts/`, with expected CLI usage.

```
uv run scripts/foo.py --option value
```

## Tests
What should be tested and any specific scenarios to cover.

## Notes
Anything else relevant: performance concerns, dependencies to add, open questions.
