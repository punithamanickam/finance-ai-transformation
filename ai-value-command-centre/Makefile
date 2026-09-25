.PHONY: install data db test run api web diagrams deep-dive demo screenshots all

install:
	pip install -r requirements.txt

data:        ## regenerate the synthetic dataset (deterministic) and the public reference CSVs
	python -m src.synthetic.generator && python -m src.public.hpe

db:          ## build the database (SQLite by default, DATABASE_URL for PostgreSQL)
	python -m src.db.database

test:
	python -m pytest

run api:     ## API + web app on http://127.0.0.1:8000
	uvicorn src.api.main:app --reload

web:         ## self-contained static snapshot: web/dist/ai-value-command-centre.html
	python -m scripts.export_static

diagrams:
	python -m scripts.generate_diagrams

deep-dive:   ## docs/deep_dive_analysis.md, regenerated from the engines
	python -m scripts.build_deep_dive

demo:        ## docs/demo_transcript.md
	python -m scripts.run_demo

screenshots: ## needs node + playwright
	node scripts/screenshots.js docs/screenshots

all: data db test web diagrams deep-dive demo
