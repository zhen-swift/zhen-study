# The paper

The write-up of the netsanity measurement study, against `Study/`.

**The venue is unsettled.** This draft is **IEEEtran conference format** by
default, which is what `PROTOCOL.md` section 10 asks for ("8–12 pages, IEEE or
ACM two-column, with the Pareto figure as Figure 1"). The note at the top of
`paper.tex` says how to move it to `acmart`: it is two lines of preamble, and
nothing in the body depends on the class. Every figure is drawn at 3.5 in, the
IEEEtran column width, so a move to acmart's 3.33 in column costs a
regeneration of `figures/` and not a redraw.

## Building

The figure and table scripts need numpy and matplotlib. They live in the
study's own virtual environment (`Study/.venv`, created as `SIMULATION.md`
describes), which is git-ignored and so is not present in a fresh worktree; the
`Makefile` looks for it beside this directory and then in a sibling checkout,
and `PY=/path/to/python make` overrides it.

```bash
# once, if there is no TeX on the machine
brew install --cask basictex
tlmgr init-usertree
tlmgr --usermode install ieeetran siunitx preprint courier times helvetic psnfss

make            # figures, tables, then two pdflatex passes
make figures    # Paper/figures/*.pdf from Study/data/runs.ndjson
make tables     # Paper/tables/*.tex from the same file
```

## What is generated, and from what

Nothing in `figures/` or `tables/` is drawn or typed by hand. Both are
regenerated from **`Study/data/runs.ndjson` plus `Study/analysis/strata.json`**
— the collected data and the stratum sidecar — by the two scripts in
`scripts/`. A number transcribed into a LaTeX source by hand is a number nobody
can recompute, which is the rule `PROTOCOL.md` section 8 sets for the whole
study.

| path | what it is |
|---|---|
| `paper.tex` | the paper |
| `scripts/paperdata.py` | the loader; re-uses `Study/analysis/collection.py` so the recall rule and the stratum map have one definition |
| `scripts/figstyle.py` | matplotlib settings: 3.5 in width, `pdf.fonttype 42`, the validated palette, marker-and-dash identity so the figures survive greyscale |
| `scripts/make_figures.py` | Figures 1–5, `.pdf` and `.png` |
| `scripts/make_tables.py` | Tables I–IV as complete `tabular` environments |

`Study/` is **read-only** to this directory. `paperdata.py` sets
`sys.dont_write_bytecode` before importing from it, because an import that
leaves a `__pycache__` behind is a write.

**`Study/figures/` holds the *simulation's* figures and none of them is reused
here.** They are evidence about the model, not measurements, and the paper says
so where it cites them.

## `pdf.fonttype 42`

IEEE's submission checker rejects Type 3 fonts outright. `figstyle.py` sets
`pdf.fonttype` and `ps.fonttype` to 42 so matplotlib embeds TrueType, and every
figure is drawn at its final size so nothing is scaled in LaTeX and the font
sizes in the figure are the font sizes on the page.
