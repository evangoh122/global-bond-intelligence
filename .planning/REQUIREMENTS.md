# Requirements: Global Bond Intelligence

**Defined:** 2026-05-29
**Core Value:** An analyst or downstream system can ask a question about a bond filing and receive a cited, structured answer with direct pointers back to source document sections.

## v1 Requirements

### Ingestion

- [ ] **INGEST-01**: Pipeline downloads bond filings in bulk from SEC EDGAR archives by form type using sec-edgar-downloader
- [ ] **INGEST-02**: SQLite filing registry tracks each filing's download and processing status to enable safe re-runs and incremental ingestion
- [ ] **INGEST-03**: Pipeline ingests 424B2, 424B3, 424B5 prospectus supplement form types
- [ ] **INGEST-04**: Pipeline ingests S-1, S-3, F-1, F-3 registration statement form types
- [ ] **INGEST-05**: Amendment deduplication — pipeline identifies the most recent filing version and marks superseded accession numbers so queries always reflect current documents
- [ ] **INGEST-06**: HTTP client enforces SEC EDGAR rate limiting (10 req/s token bucket) and includes required User-Agent header to prevent IP bans

### Extraction

- [ ] **EXTRT-01**: XBRL parser extracts structured bond fields from inline iXBRL filings: coupon rate, maturity date, principal amount, currency, ISIN, CUSIP, issuer name, debt ranking, governing law
- [ ] **EXTRT-02**: PDF text extractor recovers narrative text from bond filings with layout preservation (PyMuPDF primary)
- [ ] **EXTRT-03**: PDF table extractor recovers structured tables (pricing tables, call/put schedules, covenant schedules) as Markdown-formatted output (pdfplumber fallback for borderless tables)
- [ ] **EXTRT-04**: Format router detects filing format (iXBRL vs PDF) and dispatches to the correct extractor
- [ ] **EXTRT-05**: Credit rating extractor identifies Moody's, S&P, and Fitch ratings at issuance via pattern matching in filing text
- [ ] **EXTRT-06**: Extraction audit log records (filing_id, xbrl_facts_extracted, pdf_pages_extracted) per filing — zero XBRL facts triggers a warning

### Chunking

- [ ] **CHUNK-01**: ChunkMetadata schema defined and frozen before any chunking code is written — schema includes: filing_id (EDGAR accession number), filing_url, section_title, section_hierarchy, page_number, chunk_type (section/clause/table), extraction_method (xbrl/pdf), table_caption where applicable
- [ ] **CHUNK-02**: Section chunker splits documents at heading boundaries (1024–2048 tokens) so Risk Factors, Terms, and Covenant sections remain intact as retrievable units
- [ ] **CHUNK-03**: Clause chunker produces semantic clause/provision units from covenant text (256–512 tokens with overlap) for fine-grained retrieval
- [ ] **CHUNK-04**: Table chunker treats each extracted table as an atomic unit (never split mid-row); tables serialized as Markdown with caption metadata preserved

### Indexing

- [ ] **INDEX-01**: Embeddings generated locally using sentence-transformers (BAAI/bge-large-en-v1.5) — no external embedding API calls
- [ ] **INDEX-02**: Chunks stored in Chroma PersistentClient collection with cosine HNSW index tuned for scale (hnsw:M=64, construction_ef=200)
- [ ] **INDEX-03**: Chunks upserted using deterministic chunk_id (sha256 of filing_id + chunk_index) enabling safe re-indexing without full corpus rebuild
- [ ] **INDEX-04**: Vector store abstracted behind an interface (not hardcoded to Chroma) to allow future migration if corpus exceeds scale limits

### Retrieval & RAG

- [ ] **RAG-01**: Hybrid retrieval combining dense vector search and BM25 keyword search via Reciprocal Rank Fusion — critical for exact-match of defined bond terms and thresholds
- [ ] **RAG-02**: Local Ollama LLM (llama3.1:8b or qwen2.5:14b) generates narrative answers strictly from retrieved context only (temperature=0, context-only system prompt)
- [ ] **RAG-03**: Structured numeric fields (coupon, maturity, principal, CUSIP) served directly from XBRL extraction without passing through the LLM to prevent numeric hallucination

### SDK

- [ ] **SDK-01**: `BondIntelligence` Python class accepts natural language queries and returns `QueryResponse` objects
- [ ] **SDK-02**: `QueryResponse` includes: answer text, list of `Citation` objects (accession number, section title, verbatim passage, EDGAR URL, page number), and structured `BondTerm` fields where extractable
- [ ] **SDK-03**: `BondTerm` is a Pydantic model with typed fields: coupon_rate, maturity_date, principal_amount, currency, isin, cusip, issuer_name, debt_ranking, governing_law, ratings
- [ ] **SDK-04**: Every response includes a source_confidence flag indicating whether answer came from XBRL direct extraction or RAG generation
- [ ] **SDK-05**: SDK supports async queries via `async def query()` for non-blocking use in downstream pipelines

## v2 Requirements

### Ingestion

- **INGEST-V2-01**: Daily incremental polling via EDGAR RSS and daily index feeds to ingest new filings within hours of submission
- **INGEST-V2-02**: 8-K (material event) form type ingestion for bond pricing press releases and indenture filings
- **INGEST-V2-03**: 10-K / 20-F annual report ingestion for debt schedule and covenant compliance sections
- **INGEST-V2-04**: EDGAR full-text search API integration for targeted filing discovery by keyword

### Retrieval & RAG

- **RAG-V2-01**: Cross-encoder reranking of top retrieved chunks before LLM synthesis
- **RAG-V2-02**: Null/not-found abstention — explicit "not found in filing" response when a provision is absent, rather than any generated answer
- **RAG-V2-03**: Multi-hop covenant reasoning for cross-references within indentures (definitions referencing basket amounts)

### Multi-Regulator

- **MULTI-V2-01**: EDINET ingestion for Japanese bond filings
- **MULTI-V2-02**: ESMA/ESEF ingestion for European bond filings
- **MULTI-V2-03**: HKEX ingestion for Hong Kong bond filings
- **MULTI-V2-04**: Cross-regulator field harmonization (map equivalent concepts across jurisdictions)

### Analytics

- **ANLYT-V2-01**: Negative covenant screening across corpus (flag filings matching a covenant condition)
- **ANLYT-V2-02**: Change detection between filing versions (diff two amendments)
- **ANLYT-V2-03**: Covenant compliance timeline extraction from periodic reports

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web UI / chat interface | Python SDK only in v1 — no frontend scope |
| REST API | Python SDK interface is sufficient; REST adds infra overhead without v1 value |
| CLI tool | SDK serves both human analysts (via notebook/script) and programmatic consumers |
| External LLM APIs (OpenAI, Anthropic, etc.) | Data privacy + cost at scale; local Ollama only |
| Cloud vector DB (Pinecone, Weaviate, Qdrant) | Local Chroma sufficient for v1; migration path designed in via abstraction layer |
| Real-time / streaming ingestion | Batch pipeline only; incremental polling deferred to v2 |
| Pricing / yield analytics | Different engineering domain; not bond document intelligence |
| Credit scoring / risk models | Out of scope — this is a document retrieval layer, not an analytics engine |
| Entity hierarchy / issuer graph | High complexity, low v1 value |
| Alerting / notifications | No event infrastructure in v1 |
| Non-English document translation | EDINET/ESMA deferred to v2; English-only corpus in v1 |
| ABS / CLO / CMBS specialized extraction | Complex structured products deferred; corporate bonds first |

## Traceability

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

**Coverage:**
- v1 requirements: 28 total
- Mapped to phases: 28
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-29*
*Last updated: 2026-05-29 after initial definition*
