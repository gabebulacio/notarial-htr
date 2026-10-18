# Envoltorio fino; la lógica vive en tasks.py para que funcione en Windows sin make.
PY ?= python

.PHONY: setup models status ingest preprocess segment refine recognize correct evaluate check-gt train overlay viewer test lint
setup: ; $(PY) tasks.py setup
models: ; $(PY) tasks.py models
status: ; $(PY) tasks.py status
ingest: ; $(PY) tasks.py ingest
preprocess: ; $(PY) tasks.py preprocess
segment: ; $(PY) tasks.py segment
refine: ; $(PY) tasks.py refine
recognize: ; $(PY) tasks.py recognize
correct: ; $(PY) tasks.py correct
evaluate: ; $(PY) tasks.py evaluate
check-gt: ; $(PY) tasks.py check-gt
train: ; $(PY) tasks.py train
overlay: ; $(PY) tasks.py overlay
viewer: ; $(PY) tasks.py viewer
test: ; $(PY) tasks.py test
lint: ; $(PY) tasks.py lint
