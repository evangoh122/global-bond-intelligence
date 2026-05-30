# global-bond-intelligence

End-to-end pipeline for collecting, parsing, and querying bond filings from SEC EDGAR. Includes iXBRL/PDF extraction, structure-aware chunking, and a Python SDK backed by a RAG layer for intelligent retrieval and citation over regulatory fixed income data.

> This project is AI-assisted — developed in collaboration with [Claude Code](https://claude.ai/code).

---

## What it does

Given a natural language question about a bond filing, the pipeline returns a cited, structured answer:

```python
from bond_intelligence import BondIntelligence

bi = BondIntelligence()
response = bi.query("What is the coupon rate and negative pledge covenant for CUSIP 123456789?")

print(response.bond_terms.coupon_rate)       # 5.875% (from XBRL)
print(response.citations[0].verbatim_passage) # "The Issuer shall not..."
print(response.citations[0].edgar_url)        # https://www.sec.gov/...
print(response.source_confidence)             # "xbrl_direct" | "rag_generated"
```

---

## Data sources

| Regulator | Status |
|-----------|--------|
| SEC EDGAR | v1 — in scope |
| EDINET (Japan) | v2 |
| ESMA/ESEF (EU) | v2 |
| HKEX (Hong Kong) | v2 |

**Form types (v1):** 424B2, 424B3, 424B5, S-1, S-3, F-1, F-3

---

## Stack

| Layer | Library |
|-------|---------|
| EDGAR ingestion | sec-edgar-downloader 5.x + httpx 0.27.x |
| Pipeline orchestration | prefect 3.4.x |
| Filing registry | SQLite |
| iXBRL parsing | arelle 2.x |
| PDF text extraction | pymupdf 1.24.x + pymupdf4llm |
| PDF table extraction | pdfplumber 0.11.x |
| Chunking | llama-index-core 0.10.x |
| Embeddings | sentence-transformers 3.x (BAAI/bge-large-en-v1.5) |
| Vector store | chromadb 0.6.x (local) |
| RAG orchestration | langchain-core 0.3.x + langchain-ollama 0.2.x |
| Local LLM | ollama 0.3.x (llama3.1:8b / qwen2.5:14b) |
| Data models | pydantic v2 |

**Local-only** — no external LLM APIs, no cloud vector DB.

---

## Architecture

```
SEC EDGAR
    │
    ▼
Ingestion (sec-edgar-downloader + SQLite registry)
    │
    ▼
Extraction (Arelle iXBRL  ──┐
            PyMuPDF PDF   ──┤  FormatRouter
            pdfplumber    ──┘)
    │
    ▼
Chunking (SectionChunker / ClauseChunker / TableChunker)
    │  each chunk carries ChunkMetadata (filing_id, section, page, type)
    ▼
Indexing (BGE-large embeddings → Chroma HNSW)
    │
    ▼
Query (Hybrid dense+BM25 retrieval)
    │
    ├── Structured numerics → XBRL direct (no LLM)
    └── Narrative text     → Ollama RAG (context-only prompt)
    │
    ▼
BondIntelligence SDK (QueryResponse + Citations + BondTerm)
```

---

## Roadmap

| Phase | Name | Status |
|-------|------|--------|
| 1 | Ingestion Foundation | Not started |
| 2 | Extraction and Chunking | Not started |
| 3 | Indexing, Retrieval, and RAG Engine | Not started |
| 4 | Python SDK and Citation API | Not started |

See `.planning/ROADMAP.md` for full phase details and success criteria.

---

## Key design decisions

- **Two-track answer architecture** — structured numeric fields (coupon, maturity, CUSIP) are served directly from XBRL extraction and never pass through the LLM, preventing numeric hallucination.
- **Structure-aware chunking** — three typed chunkers handle sections (1024–2048 tokens), clauses (256–512 tokens), and tables (atomic units) separately so covenant text and pricing schedules stay intact.
- **Citation-first from day one** — every chunk carries a `ChunkMetadata` envelope (filing_id, section_title, page_number, EDGAR URL) so every answer can be traced back to its source.
- **Vector store abstraction** — Chroma is the v1 store but is accessed through an interface, keeping migration to Qdrant open if corpus exceeds scale limits.
