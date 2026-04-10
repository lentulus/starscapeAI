# Documentation Pipeline Design
*Internal technical spec · Draft 1 · April 2026*

## Overview

A command-line markdown-to-PDF pipeline for building offline technical documentation. Source is a collection of markdown files sequenced and formatted via YAML config. Output is a single, print-ready PDF suitable for paper and tablet reading.

**Stack:** Pandoc + Typst + Bash

---

## Architecture

```
markdown files + sequence config + style config
         ↓
    build script
         ↓
    pandoc (markdown → typst)
         ↓
    typst compile
         ↓
    output.pdf
```

---

## Key Components

### Configuration Files

**sequence.yaml** — defines order, title, author, TOC metadata
- List of chapter files in order
- Global document metadata
- TOC generation flag

**template.typ** — Typst template for styling
- Typography: fonts, sizes, line height
- Colors and emphasis
- Page layout: margins, headers, footers
- Heading numbering
- Code block styling

### Build Script

Minimal orchestration in bash:
1. Read sequence.yaml to get chapter list
2. Concatenate markdown files with YAML frontmatter
3. Pipe to Pandoc (markdown → typst)
4. Compile with `typst compile`
5. Output to PDF

Run: `bash build.sh`

---

## Design Decisions

**Why Pandoc?**
- Mature markdown parser
- Understands metadata blocks
- Cross-reference support
- Templating system

**Why Typst?**
- Fast compilation (ms, not seconds)
- Clean defaults for technical docs
- Modern syntax vs LaTeX
- Better on-screen typography

**Why Config Files?**
- Version control friendly (text, not binary)
- Reproducible builds
- Easy to iterate style without touching markdown
- Sequential independence (reorder by editing YAML)

---

## Open Questions

- [ ] **Diagrams** — How to embed? Mermaid, Graphviz, SVG/PNG assets?
- [ ] **Code highlighting** — Language-specific syntax coloring?
- [ ] **Cross-references** — Auto-numbered sections/figures?
- [ ] **Incremental builds** — Only recompile changed files?
- [ ] **Watch mode** — Auto-rebuild on file change?

---

## Next Steps

1. Sketch Typst template with StarscapeAI branding
2. Test Mermaid/diagram support in Pandoc → Typst pipeline
3. Build prototype with 2–3 real markdown files from starscape5 repo
4. Add to project build system (alongside main simulation)

---

*To continue: pick up diagram tooling research and prototype template.*
