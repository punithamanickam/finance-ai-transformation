from src.agents.orchestrator import ask
from src.rag.corpus import load_chunks
from src.rag.retriever import Retriever, get_retriever


def test_every_chunk_is_attributable():
    chunks = load_chunks()
    assert len(chunks) > 50
    for c in chunks:
        assert c["url"].startswith("https://") and c["date"] and c["doc_id"] and c["source_type"]


def test_retrieval_returns_cited_passages():
    res = get_retriever().search("HPE Private Cloud AI NVIDIA", k=3)
    assert res and all(r["url"] and r["citation"] == i + 1 for i, r in enumerate(res))


def test_metadata_filter():
    res = get_retriever().search("revenue", k=5, source_type="10-K")
    assert res and all("10-K" in r["source_type"] for r in res)


def test_research_answers_cite_sources():
    r = ask("What is HPE's AI backlog?", use_llm=False)
    assert r["intent"] == "hpe_research"
    assert r["evidence"] and all(e["url"] for e in r["evidence"])
    assert "[" in r["answer"] and "PUBLIC" in r["data_label"]


def test_hpe_financial_figure_comes_from_the_filing():
    r = ask("What was HPE revenue in FY2025?", use_llm=False)
    assert "$34.3B" in r["answer"]
    assert any("sec.gov" in (e["url"] or "") for e in r["evidence"])


def test_no_answer_without_retrieved_evidence():
    r = Retriever(chunks=[]).search("anything")
    assert r == []
