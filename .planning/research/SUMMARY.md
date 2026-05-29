# Research Summary — Global Bond Intelligence

**Synthesized:** 2026-05-29
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

---

## Recommended Stack

- **Ingestion:** `sec-edgar-downloader` 5.x (bulk archive) + `httpx` 0.27.x (EDGAR full-text search API) + `prefect` 3.4.x (orchestration with task-level caching and retry). SQLite as the filing registry — zero infrastructure overhead, sufficient for tens of thousands of rows.
- **Extraction + Chunking:** `arelle` 2.x for iXBRL (the only production-grade option for SEC filings post-2020); `pymupdf` 1.24.x + `pymupdf4llm` as primary PDF extractor; `pdfplumber` 0.11.x as table-extraction fallback. `llama-index-core` 0.10.x `HierarchicalNodeParser` for structure-aware chunking; `langchain-text-splitters` 0.3.x `RecursiveCharacterTextSplitter` for flat fallback.
- **Indexing + Query:** `sentence-transformers` 3.x with `BAAI/bge-large-en-v1.5` (1024d, top MTEB financial retrieval) for embeddings; `chromadb` 0.6.x `PersistentClient` with cosine HNSW for local vector store; hybrid retrieval (dense + BM25) with `cross-encoder/ms-marco-MiniLM-L6-v2` reranking; `langchain-core` 0.3.x LCEL chains + `langchain-ollama` 0.2.x `ChatOllama`; `ollama` 0.3.x with `llama3.1:8b-instruct-q4_K_M` (dev) or `qwen2.5:14b-instruct-q4_K_M` (production).

---

## Table Stakes Features

These must work correctly before v1 ships:

- **Core bond term extraction**: Coupon rate, maturity date, principal amount, currency, ISIN/CUSIP, issuer name, ranking, governing law — from XBRL when tagged, PDF extraction as fallback.
- **Offering metadata**: Filing date, effective date, offering price, underwriters, use of proceeds — from cover page of 424B* prospectuses.
- **Call/put schedule extraction**: Callable/putable provisions with exact dates and redemption prices. Demands table-aware chunking.
- **Credit rating at issuance**: Moody's/S&P/Fitch ratings extracted from filing text via pattern matching.
- **Section-level retrieval**: Route queries to the correct document section rather than returning whole documents.
- **Filing type awareness**: Distinguish 424B*, S-1/S-3, indentures, 8-K bond disclosures, ABS-EE.
- **Filing version tracking**: Always serve the most recent amendment; mark superseded accession numbers in the registry.
- **Citation with verbatim passage**: Every answer must return the exact source passage, accession number, section name, and EDGAR URL. Non-negotiable for compliance-aware users.
- **Null/not-found handling**: Return "not found" rather than a hallucinated answer when a provision does not exist.
- **Incremental ingestion**: New EDGAR filings ingested within hours of submission via EDGAR RSS/daily index polling.

---

## Architecture in Brief

The pipeline decomposes into five sequential, single-responsibility stages: **Ingestion** (EDGAR download + SQLite filing registry as idempotency gate) → **Extraction** (FormatRouter delegates to XBRLParser for tagged fields, PDFExtractor + TableExtractor for unstructured content) → **Chunking** (three typed chunkers — SectionChunker at 1024-2048 tokens, ClauseChunker at 256-512 tokens, TableChunker as atomic units — each chunk carries a full `ChunkMetadata` envelope) → **Indexing** (batch embedding → Chroma `PersistentClient` upsert keyed on deterministic `chunk_id = sha256(filing_id + chunk_index)`) → **Query** (hybrid dense + BM25 retrieval, cross-encoder reranking, Ollama synthesis, CitationAssembler).

The single most important architectural decision is the **two-track answer architecture**: structured numeric fields (coupon, maturity, principal, CUSIP) are served directly from XBRL extraction, never through LLM generation; narrative covenant questions go through RAG with strict context-only prompting. This prevents numeric hallucination. The `ChunkMetadata` schema must be finalized before any chunking or indexing code is written — retrofitting citation fields requires a full re-index.

---

## Critical Pitfalls to Avoid

1. **EDGAR IP ban from missing User-Agent** — Set `User-Agent: GlobalBondIntelligence contact@yourdomain.com` at the HTTP client level, enforce 10 req/s token-bucket, add circuit-breaker on consecutive 403s. Must be solved in Phase 1 before any bulk crawl.

2. **Numeric hallucination from LLM on bond figures** — Two-track architecture from the start: XBRL-extracted numerics served directly; RAG for narrative only. Temperature=0. Post-generation consistency check that verifies every number appears verbatim in a retrieved chunk.

3. **PDF table extraction producing garbage chunks** — Use pdfplumber's `extract_tables()` for grid detection; dual-extraction strategy (narrative and tables separated, tables serialized as Markdown); treat each table as an atomic chunk unit never split mid-row.

4. **Inline XBRL namespace collision causing silent empty fields** — Use Arelle (not lightweight alternatives); maintain a concept alias map for all target fields; log `(filing_id, concept_count, facts_extracted)` for every parse — zero facts is a warning, not a success.

5. **Chroma collection collapse at scale** — Use `PersistentClient`, set `hnsw:M=64` and `hnsw:construction_ef=200` at collection creation, use atomic batches with a SQLite checkpoint table. Abstract the vector store behind an interface from day one to support migration to Qdrant if corpus exceeds ~1M chunks.

---

## Open Questions / Risks

- **Chroma HNSW performance at 200k+ chunks**: Degradation threshold needs benchmarking on actual hardware. Determines whether to shard or migrate.
- **BGE-large domain retrieval quality on bond covenant text**: Build 50 hand-labeled (query, relevant_chunk) pairs in Phase 3 before bulk indexing. If recall@5 < 0.7, evaluate `FinLang/finance-embeddings-investopedia`.
- **Arelle iXBRL coverage across SEC filing vintages (2015-2025)**: Concept alias map needs calibration against a 200-500 filing sample before extraction layer can be trusted at scale.
- **EDGAR full-text search 10,000 result cap**: Validate that the date-range bisection workaround achieves complete coverage across all bond prospectus form types.
- **Cross-encoder reranking precision gain on bond-domain queries**: Measure recall@5 pre- and post-reranking — general benchmark gains may not transfer to bond-specific terminology.

---

## Roadmap Implications

**Recommended 5 phases (strictly sequenced by data dependency):**

1. **Ingestion Foundation** — EDGAR download, SQLite registry, rate limiting, retry manifest, form type coverage, amendment deduplication. Delivers real filings for all downstream phases. *(Skip per-phase research — EDGAR API well-documented)*
2. **Extraction and Chunking** — XBRL + PDF extraction, dual-table strategy, frozen ChunkMetadata schema, three typed chunkers. Fix quality at the source before embedding. *(Phase research recommended — Arelle iXBRL calibration, pdfplumber bond prospectus tuning)*
3. **Indexing, Retrieval, and RAG Engine** — Embedding model validation, Chroma HNSW setup, hybrid retrieval, two-track answer architecture. Validates end-to-end correctness before SDK wrapping. *(Phase research recommended — embedding domain eval set, Chroma scale benchmarking)*
4. **Python SDK and Citation API** — Stable Pydantic models (`QueryResponse`, `Citation`, `BondTerm`, `CovenantClause`), public `BondIntelligence` class, confidence scoring, abstention logic. Only wraps a proven working engine. *(Skip per-phase research — SDK follows from engine)*
5. **Incremental Pipeline and Corpus Scale** — Prefect scheduling, full corpus ingestion, EDGAR amendment tracking, monitoring. *(Skip per-phase research — Prefect patterns well-documented)*

**Deferred to v2:** Multi-regulator support (EDINET/ESMA/HKEX), cross-reference resolution in indentures, change detection between filing versions, multi-hop covenant reasoning, web UI and REST API, alerting infrastructure, non-English document translation.

**Schema decisions that must not slip (before Phase 2 code is written):**
- Complete `ChunkMetadata` schema (all citation fields, chunk type, extraction method flag)
- Pydantic models for `QueryResponse`, `Citation`, and core bond term objects
