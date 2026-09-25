.PHONY: install data test app api report demo diagrams all

install:
	pip install -r requirements.txt

data:        ## download public filings from SEC EDGAR, extract, model, index, data-quality report
	python -m scripts.build_financial_model

test:
	python -m pytest

app:
	streamlit run app/streamlit_app.py

api:
	uvicorn src.api.main:app --reload

report:
	python -m src.reporting.report

demo:
	python -m scripts.run_demo

diagrams:
	python -m scripts.generate_diagrams

all: data test report demo diagrams
