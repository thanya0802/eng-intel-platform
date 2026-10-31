PY ?= python3
.PHONY: setup data ingest index demo test eval gate api dashboard lint clean all

setup:            ## create venv + install
	$(PY) -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt
data:             ## generate synthetic records + PDFs
	$(PY) data/generate.py
ingest:           ## structured load + document ingestion (quality checks, lineage, DLQ)
	$(PY) -m engintel.cli reset && $(PY) -m engintel.cli ingest
index:            ## build vector + BM25 index
	$(PY) -m engintel.cli index
all: data ingest index
demo:
	$(PY) -m engintel.cli ask "Which requirements have failing tests linked to open change requests?"
test:
	$(PY) -m pytest -q
eval:
	$(PY) evals/run_evals.py
gate:
	$(PY) evals/run_evals.py --gate
lint:
	ruff check .
api:
	uvicorn api.main:app --reload --port 8000
dashboard:
	streamlit run dashboard/app.py
clean:
	rm -rf data/raw data/structured data/index data/warehouse.db evals/results
