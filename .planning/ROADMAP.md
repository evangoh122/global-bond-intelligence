# Roadmap: Global Bond Intelligence

**Milestone:** v1.0 — Local Bond Intelligence Pipeline
**Phases:** 4
**Requirements covered:** 28 / 28

---

## Phases

- [ ] **Phase 1: Ingestion Foundation** — EDGAR bulk download, SQLite registry, rate-limit enforcement, form type coverage, and amendment deduplication deliver real filings on disk as the data substrate for all downstream phases.
- [ ] **Phase 2: Extraction and Chunking** — iXBRL field extraction, PDF text and table recovery, format routing, credit rating extraction, and three typed chunkers (section, clause, table) with a frozen ChunkMetadata schema turn raw filings into clean, citable chunks.
- [ ] **Phase 3: Indexing, Retrieval, and RAG Engine** — Local embedding generation, Chroma HNSW vector store, hybrid dense+BM25 retrieval, two-track answer architecture (XBRL direct for numerics, RAG for narrative), and Ollama synthesis deliver end-to-end question answering with cited responses.
- [ ] **Phase 4: Python SDK and Citation API** — Stable Pydantic models (`QueryResponse`, `Citation`, `BondTerm`), public `BondIntelligence` class, confidence scoring, and async query support expose the engine as a usable Python library.

---

## Phase Details

### Phase 1: Ingestion Foundation

**Goal:** Real SEC EDGAR bond filings are on disk and tracked in a filing registry, with rate limiting and amendment deduplication in place, so all downstream phases have a reliable, idempotent data source.

**Depends on:** Nothing (first phase)

**Requirements:** INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06

**Plans:**
1. EDGAR bulk downloader — implement `sec-edgar-downloader` integration for 424B2, 424B3, 424B5, S-1, S-3, F-1, F-3 form types with configurable date range and output directory
2. Filing registry — SQLite schema and data-access layer tracking filing status (downloaded, extracted, chunked, indexed) enabling safe re-runs and incremental updates
3. Rate limiting, headers, and amendment deduplication — token-bucket HTTP client (10 req/s), required User-Agent header, and amendment-detection logic that marks superseded accession numbers in the registry

**Success Criteria:**
1. Running the ingestion pipeline for a given ticker or date range downloads filing files to disk and populates the SQLite registry with one row per filing, showing accession number, form type, and status.
2. Re-running the pipeline on the same date range does not re-download already-present filings and does not create duplicate registry entries.
3. When multiple amendments exist for the same filing, only the most recent accession number has status "current"; superseded versions are marked as such in the registry.
4. The pipeline completes a 100-filing bulk download without receiving an HTTP 429 or 403 error from EDGAR (rate limiting and User-Agent header enforced).
5. All six target form types (424B2, 424B3, 424B5, S-1, S-3, F-1, F-3) appear in the registry after a corpus-level ingestion run.

**Phase Research:** No — EDGAR bulk download API and `sec-edgar-downloader` are well-documented; rate-limit and User-Agent requirements are specified in EDGAR developer guidance.

---

### Phase 2: Extraction and Chunking

**Goal:** Every downloaded filing is parsed into structured XBRL fields and narrative text, tables are recovered as Markdown, and all content is split into typed chunks carrying complete citation metadata, so embeddings in Phase 3 have clean, citable inputs.

**Depends on:** Phase 1

**Requirements:** EXTRT-01, EXTRT-02, EXTRT-03, EXTRT-04, EXTRT-05, EXTRT-06, CHUNK-01, CHUNK-02, CHUNK-03, CHUNK-04

**Plans:**
1. ChunkMetadata schema and Pydantic models — freeze the `ChunkMetadata` dataclass (filing_id, filing_url, section_title, section_hierarchy, page_number, chunk_type, extraction_method, table_caption) and `BondTerm` Pydantic model before any extraction or chunking code is written
2. XBRL and PDF extractors — Arelle iXBRL parser for structured bond fields; PyMuPDF primary text extractor; pdfplumber table extractor with Markdown serialization; FormatRouter dispatching by format detection; credit rating pattern matcher; extraction audit log
3. Three typed chunkers — SectionChunker (1024–2048 tokens at heading boundaries), ClauseChunker (256–512 tokens with overlap for covenant text), TableChunker (atomic table units never split mid-row, caption preserved)

**Success Criteria:**
1. For a sample iXBRL filing, the XBRL parser returns coupon rate, maturity date, principal amount, currency, ISIN, CUSIP, issuer name, debt ranking, and governing law as typed fields — zero silent empty fields.
2. For a sample PDF-only prospectus, narrative text is recovered section by section with layout intact, and pricing tables are returned as valid Markdown with no truncated rows.
3. The FormatRouter dispatches iXBRL filings to the XBRL path and PDF-only filings to the PDF path without manual intervention; extraction audit log records `(filing_id, xbrl_facts_extracted, pdf_pages_extracted)` for every filing and emits a warning when XBRL fact count is zero.
4. Every chunk produced carries a fully-populated `ChunkMetadata` envelope including `filing_id`, `section_title`, `chunk_type`, and `page_number` — no chunk is produced with null citation fields.
5. Section chunks stay within the 1024–2048 token window, clause chunks within 256–512 tokens, and table chunks are never split mid-row across a sample of 50 filings.

**Phase Research:** Yes — Arelle iXBRL concept alias map needs calibration against a 200–500 filing sample across SEC filing vintages (2015–2025) to validate coverage of all target fields; pdfplumber table detection quality on borderless prospectus tables needs empirical tuning before bulk extraction.

**UI hint**: no

---

### Phase 3: Indexing, Retrieval, and RAG Engine

**Goal:** Chunks are embedded locally, stored in a Chroma HNSW vector store, and queryable via hybrid retrieval feeding a two-track answer architecture — structured numerics served directly from XBRL extraction, narrative answers synthesized by a local Ollama LLM with citations — so the end-to-end pipeline produces correct, cited answers without numeric hallucination.

**Depends on:** Phase 2

**Requirements:** INDEX-01, INDEX-02, INDEX-03, INDEX-04, RAG-01, RAG-02, RAG-03

**Plans:**
1. Embedding pipeline and Chroma setup — batch embedding with `BAAI/bge-large-en-v1.5` (sentence-transformers), Chroma `PersistentClient` collection with `hnsw:M=64` and `hnsw:construction_ef=200`, deterministic `chunk_id` (sha256 of filing_id + chunk_index) for safe upsert, vector store abstraction interface
2. Hybrid retrieval — dense vector search + BM25 keyword search merged via Reciprocal Rank Fusion; retrieval accuracy benchmarked against a 50-query hand-labeled eval set (target: recall@5 >= 0.70)
3. Two-track answer synthesis — XBRL direct path for structured numeric fields (coupon, maturity, principal, CUSIP); Ollama RAG path for narrative answers (temperature=0, context-only system prompt); post-generation consistency check that every number in a narrative answer appears verbatim in a retrieved chunk

**Success Criteria:**
1. Given a query for a specific CUSIP or coupon rate, the system returns the exact value sourced from XBRL extraction without invoking the LLM, and the response is identical to the value in the raw filing.
2. Given a narrative query (e.g., "What are the change-of-control covenant provisions for this bond?"), the system returns an answer with at least one citation containing accession number, section title, verbatim passage, EDGAR URL, and page number.
3. Hybrid retrieval achieves recall@5 >= 0.70 on the 50-query bond-domain eval set; adding BM25 fusion measurably improves recall over dense-only retrieval for exact bond term queries.
4. Re-indexing a previously-indexed filing (e.g., after re-extraction) does not duplicate chunks — the upsert using deterministic chunk_id results in the same chunk count before and after.
5. The vector store is accessed exclusively through the abstraction interface — no call site in retrieval or indexing code imports Chroma directly, making future migration substitutable.

**Phase Research:** Yes — embedding domain retrieval quality on bond covenant text must be validated with a hand-labeled eval set before bulk indexing; Chroma HNSW performance at 200k+ chunks needs benchmarking on target hardware to determine whether sharding or migration is required.

**UI hint**: no

---

### Phase 4: Python SDK and Citation API

**Goal:** A stable, typed Python SDK wraps the proven engine so analysts and downstream systems can call `BondIntelligence().query(...)` and receive a fully-structured `QueryResponse` with citations, typed bond term fields, confidence flags, and async support.

**Depends on:** Phase 3

**Requirements:** SDK-01, SDK-02, SDK-03, SDK-04, SDK-05

**Plans:**
1. Public API surface and Pydantic models — `BondIntelligence` class, `QueryResponse`, `Citation`, and `BondTerm` Pydantic models with all typed fields; `source_confidence` flag distinguishing XBRL direct extraction from RAG generation
2. Sync and async query interfaces — synchronous `query()` and asynchronous `async def query()` on `BondIntelligence`; integration tests covering a representative set of query types (structured field, narrative, mixed)
3. SDK hardening and packaging — end-to-end integration test suite against a real 50-filing corpus sample; `pip install`-able package with declared dependencies and usage examples

**Success Criteria:**
1. An analyst can install the SDK, instantiate `BondIntelligence()`, and call `.query("What is the coupon rate for CUSIP 123456789?")` to receive a `QueryResponse` where `bond_terms.coupon_rate` contains the correct numeric value sourced from XBRL extraction.
2. A narrative query (e.g., "Summarize the negative pledge covenant for this issuer") returns a `QueryResponse` where `citations` contains at least one `Citation` object with non-null `accession_number`, `section_title`, `verbatim_passage`, `edgar_url`, and `page_number`.
3. Every `QueryResponse` includes a `source_confidence` field that is `"xbrl_direct"` for structured numeric answers and `"rag_generated"` for narrative answers — an analyst can always tell the provenance of the answer.
4. `async def query()` executes without blocking the event loop and returns the same `QueryResponse` structure as the synchronous path — downstream async pipelines can use it without additional wrappers.
5. The full integration test suite (sync + async, structured + narrative query types) passes against a 50-filing local corpus with no hallucinated numeric values in any response.

**Phase Research:** No — SDK design follows directly from the working engine; Pydantic model design and async interface patterns are well-established Python conventions.

**UI hint**: no

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Ingestion Foundation | 0/3 | Not started | - |
| 2. Extraction and Chunking | 0/3 | Not started | - |
| 3. Indexing, Retrieval, and RAG Engine | 0/3 | Not started | - |
| 4. Python SDK and Citation API | 0/3 | Not started | - |

---

## Coverage

| Requirement | Phase | Status |
|-------------|-------|--------|
| INGEST-01 | Phase 1 | Pending |
| INGEST-02 | Phase 1 | Pending |
| INGEST-03 | Phase 1 | Pending |
| INGEST-04 | Phase 1 | Pending |
| INGEST-05 | Phase 1 | Pending |
| INGEST-06 | Phase 1 | Pending |
| EXTRT-01 | Phase 2 | Pending |
| EXTRT-02 | Phase 2 | Pending |
| EXTRT-03 | Phase 2 | Pending |
| EXTRT-04 | Phase 2 | Pending |
| EXTRT-05 | Phase 2 | Pending |
| EXTRT-06 | Phase 2 | Pending |
| CHUNK-01 | Phase 2 | Pending |
| CHUNK-02 | Phase 2 | Pending |
| CHUNK-03 | Phase 2 | Pending |
| CHUNK-04 | Phase 2 | Pending |
| INDEX-01 | Phase 3 | Pending |
| INDEX-02 | Phase 3 | Pending |
| INDEX-03 | Phase 3 | Pending |
| INDEX-04 | Phase 3 | Pending |
| RAG-01 | Phase 3 | Pending |
| RAG-02 | Phase 3 | Pending |
| RAG-03 | Phase 3 | Pending |
| SDK-01 | Phase 4 | Pending |
| SDK-02 | Phase 4 | Pending |
| SDK-03 | Phase 4 | Pending |
| SDK-04 | Phase 4 | Pending |
| SDK-05 | Phase 4 | Pending |

**Total:** 28 / 28 v1 requirements mapped. No orphans.

---

*Roadmap created: 2026-05-29*
*Last updated: 2026-05-29 after initial creation*
