# The paper. Figures and tables are generated from the collected data; see README.md.
#
# The figure and table scripts need numpy and matplotlib, which live in the
# study's own virtual environment.  That environment is git-ignored, so in a
# fresh worktree it is not beside this file -- look for it next door too, and
# fall back to whatever `python3` is on PATH so the failure names the missing
# package rather than a missing path.
PY ?= $(firstword $(wildcard ../Study/.venv/bin/python \
                             ../../InfinityCastle/Study/.venv/bin/python) \
                  python3)

LATEX  ?= pdflatex
TEXBIN := /Library/TeX/texbin
export PATH := $(TEXBIN):$(PATH)

.PHONY: all figures tables clean

all: paper.pdf

figures:
	$(PY) scripts/make_figures.py

tables:
	$(PY) scripts/make_tables.py

# Two passes: the second resolves the cross-references the first one wrote.
paper.pdf: paper.tex figures tables
	$(LATEX) -interaction=nonstopmode paper.tex >/dev/null
	$(LATEX) -interaction=nonstopmode paper.tex | grep -E '^!|Output written' || true

clean:
	rm -f paper.aux paper.log paper.out paper.pdf
