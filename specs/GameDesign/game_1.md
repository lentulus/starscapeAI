# Concept: {Name}

## Overview
{1-2 sentence description of what this concept does and why it exists.}

## Scope
**Includes:** {what this spec covers}  
**Excludes:** {deliberate out-of-scope items}

## Modules Involved

| Module | Role |
|--------|------|
| `module_a` | {responsibility in this concept} |
| `module_b` | {responsibility in this concept} |

## Data Flow
{Describe how data moves between modules. A numbered sequence or ASCII diagram works well here.}

1. `module_a` does X, producing Y
2. `module_b` receives Y and does Z
3. ...

## Interface Contracts

### `module_a` → `module_b`
- **Input:** {type/shape of data}
- **Output:** {type/shape of data}
- **Errors:** {expected failure modes}

### `module_b` → `module_c`
- ...

## Key Decisions
- {Decision and rationale}
- {Alternative considered and why it was rejected}

## Open Questions
- [ ] {Question} — owner: {name}, due: {date}

## References
- {Link to related spec, ticket, or doc}
