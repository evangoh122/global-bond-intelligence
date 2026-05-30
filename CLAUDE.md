# Global Bond Intelligence — Project Guide

## Project Overview

End-to-end Python pipeline for collecting, parsing, and querying bond filings from SEC EDGAR. Includes iXBRL/PDF extraction, structure-aware chunking, and a RAG layer for intelligent retrieval and citation over regulatory fixed income data.

**Core value:** An analyst or downstream system can ask a question about a bond filing and receive a cited, structured answer with direct pointers back to source document sections.

## GSD Workflow

This project uses Get Shit Done (GSD) for planning and execution.

**Current state:** See `.planning/STATE.md`
**Roadmap:** See `.planning/ROADMAP.md`
**Requirements:** See `.planning/REQUIREMENTS.md`

### Starting a phase
```
/gsd-discuss-phase 1    # gather context, clarify approach
/gsd-plan-phase 1       # skip discussion, plan directly
/gsd-execute-phase 1    # execute all plans in a phase
```

### Checking progress
```
/gsd-progress           # show current phase status
/gsd-next               # see what to work on next
```

## Architecture

The pipeline has 5 layers, strictly sequenced:

1. **Ingestion** — `sec-edgar-downloader` + SQLite filing registry
2. **Extraction** — Arelle (iXBRL) + PyMuPDF + pdfplumber + FormatRouter
3. **Chunking** — SectionChunker / ClauseChunker / TableChunker (all carrying `ChunkMetadata`)
4. **Indexing** — BGE-large-en-v1.5 embeddings → Chroma PersistentClient (HNSW)
5. **Query** — Hybrid dense+BM25 retrieval → two-track synthesis → `BondIntelligence` SDK

## Critical Constraints

- **Two-track answer architecture is non-negotiable.** Structured numeric fields (coupon, maturity, CUSIP, principal) MUST be served from XBRL extraction — never through the LLM. Numeric hallucination is a product-killer.
- **ChunkMetadata schema must be frozen before Phase 2 extraction code is written.** Retrofitting citation fields requires a full re-index of the entire corpus.
- **Vector store must be abstracted behind an interface.** No call site may import Chroma directly. Migration path to Qdrant must remain open.
- **Local only — no external APIs.** No OpenAI, no Anthropic, no Pinecone. Ollama + Chroma + local sentence-transformers only.
- **SEC EDGAR User-Agent header is required on every request.** Missing it causes silent IP bans. Format: `GlobalBondIntelligence contact@yourdomain.com`

## Stack

| Layer | Library |
|-------|---------|
| EDGAR ingestion | sec-edgar-downloader 5.x + httpx 0.27.x |
| Pipeline orchestration | prefect 3.4.x |
| Filing registry | SQLite (built-in) |
| iXBRL parsing | arelle 2.x |
| PDF text extraction | pymupdf 1.24.x + pymupdf4llm |
| PDF table extraction | pdfplumber 0.11.x |
| Chunking | llama-index-core 0.10.x HierarchicalNodeParser |
| Embeddings | sentence-transformers 3.x (BAAI/bge-large-en-v1.5) |
| Vector store | chromadb 0.6.x PersistentClient |
| RAG orchestration | langchain-core 0.3.x + langchain-ollama 0.2.x |
| Local LLM | ollama 0.3.x (llama3.1:8b or qwen2.5:14b) |
| Data models | pydantic v2 |

## Key Pydantic Models (finalized in Phase 2 Plan 1)

- `ChunkMetadata` — citation envelope carried by every chunk
- `BondTerm` — typed bond fields (coupon_rate, maturity_date, principal_amount, currency, isin, cusip, issuer_name, debt_ranking, governing_law, ratings)
- `Citation` — (accession_number, section_title, verbatim_passage, edgar_url, page_number)
- `QueryResponse` — (answer, citations, bond_terms, source_confidence)

**These schemas must not change after Phase 2 without a full re-index.**

## Phases at a Glance

| Phase | Name | Status |
|-------|------|--------|
| 1 | Ingestion Foundation | Not started |
| 2 | Extraction and Chunking | Not started |
| 3 | Indexing, Retrieval, and RAG Engine | Not started |
| 4 | Python SDK and Citation API | Not started |
