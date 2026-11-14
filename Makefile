# `make paper` regenerates every result, figure and submission file of the IJCARS paper (see README, "Reproducing the paper").
# On Windows without make: .venv\Scripts\python paper\scripts\make_paper.py
PY ?= .venv/Scripts/python

.PHONY: paper paper-results verify

paper:
	$(PY) paper/scripts/make_paper.py

# results only (no figures or documents)
paper-results:
	$(PY) paper/scripts/make_paper.py --skip=capture,fig1,fig2,fig3,fig4,fig5,draft,manuscript,frontmatter,esm1,esm2,audit

verify:
	cd web && npm run verify
