"""Retrieval: provenance of chunks, relevance, source filtering, and graceful no-evidence behaviour."""
from src.retrieval.chunker import Chunk, read_chunks
from src.retrieval.vector_store import VectorStore, get_store
from tests.conftest import requires_index


def _toy():
    mk = lambda i, text, ct="management_commentary", src="DOC-A": Chunk(f"c{i}", src, "Doc", "https://x", i, "Item 7", "H", "paragraph", ct, text)  # noqa: E731
    return VectorStore([
        mk(1, "Research and development expenses increased driven by investments in AI engineering."),
        mk(2, "Cash from operations increased due to cash received from customers."),
        mk(3, "Our business faces intense competition and cybersecurity risk.", "risk_factor"),
        mk(4, "Research and development in a different filing.", src="DOC-B"),
    ])


def test_toy_relevance_and_filters():
    s = _toy()
    hits = s.search("why did R&D expenses increase", k=1)
    assert hits[0].chunk.chunk_id == "c1"  # synonym expansion R&D -> research and development
    assert all(h.chunk.content_type == "risk_factor" for h in s.search("competition risk", content_types={"risk_factor"}))
    assert all(h.chunk.source_id == "DOC-B" for h in s.search("research and development", source_ids={"DOC-B"}))


def test_no_evidence_returns_empty():
    assert _toy().search("volcanic eruption forecast in Iceland", min_score=0.2) == []


@requires_index
def test_chunks_keep_provenance():
    chunks = read_chunks()
    assert len(chunks) > 300
    for c in chunks[:200]:
        assert c.document and c.page > 0 and c.section and c.source_url.startswith("https://www.sec.gov/")


@requires_index
def test_md_and_a_retrieval_is_period_correct():
    hits = get_store().search("research and development expenses increased driven by", k=1,
                              content_types={"management_commentary"}, source_ids={"MSFT-10K-FY2026"})
    assert hits and hits[0].chunk.document == "Microsoft FY2026 Form 10-K"
    assert "Research and development expenses increased" in hits[0].chunk.text
    assert hits[0].chunk.section.startswith("Item 7")


@requires_index
def test_risk_factor_retrieval():
    hits = get_store().search("AI cost structure uncertainty", k=3, content_types={"risk_factor"})
    assert hits and all(h.chunk.section.startswith(("Item 1A", "Item 7A")) for h in hits)
