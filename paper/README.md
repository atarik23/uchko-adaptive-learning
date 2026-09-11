# Uchko IEEE paper

This directory contains the written report for the Seminar in Artificial Intelligence project.

## Files

- `uchko_ieee.tex` - main manuscript
- `references.bib` - BibTeX references
- `uchko_ieee.pdf` - compiled preview

The manuscript uses the official `IEEEtran` conference class when it is available. The fallback class in the source exists only so the file can still be previewed in minimal LaTeX installations.

## Compile

On Overleaf, select the IEEE Conference template or ensure that `IEEEtran.cls` is available, then compile `uchko_ieee.tex`.

Locally:

```bash
latexmk -pdf uchko_ieee.tex
```

The paper documents the released XGBoost and BKT system. If a deep knowledge tracing experiment is completed, update the model description, results table, discussion, and conclusion only after its held-out metrics have been verified.
