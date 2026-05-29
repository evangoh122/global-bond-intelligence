# Pitfalls Research — Global Bond Intelligence

**Domain:** Financial document RAG pipeline — SEC EDGAR ingestion, XBRL + PDF extraction, Chroma, Ollama
**Researched:** 2026-05-29
**Overall confidence:** MEDIUM-HIGH (based on verified knowledge of each component; web sources unavailable in this session)

---

## Critical Pitfalls (Project-Killers)

### 1. SEC EDGAR IP Ban from Missing or Invalid User-Agent
**Severity:** Critical
**Layer:** Ingestion
**Description:**
SEC EDGAR's fair-access policy (documented at `https://www.sec.gov/developer`) requires every automated HTTP request to carry a `User-Agent` header in the format `CompanyName contact@email.com`. Requests without it, or using generic strings like `python-requests/2.x`, are automatically rate-limited and eventually IP-banned — sometimes silently returning 403s or truncated responses with no error message. This is not a soft limit: EDGAR actively blocks IPs that violate the policy, and the ban can persist for hours or days.

**Warning signs:**
- Sudden 403 responses after successful early requests
- Requests returning empty or partial filing indexes
- No rate-limit header in responses (the ban bypasses the normal 429 flow)

**Prevention:**
1. Set `User-Agent: GlobalBondIntelligence contact@yourdomain.com` on every request — hardcode at the HTTP client level, not per-call.
2. Enforce a hard cap of **10 requests/second** (EDGAR's documented limit). Use a token-bucket rate limiter, not `time.sleep()` between calls — sleep is fragile under async or retry logic.
3. Add a circuit-breaker: if >3 consecutive 403s, pause all requests for 60s and alert.
4. Test with a single filing end-to-end before bulk ingestion.

**Phase to address:** Phase 1 (Ingestion) — must be solved before any bulk crawl begins.

---

### 2. Chroma Collection Collapse at Scale (Tens of Thousands of Docs)
**Severity:** Critical
**Layer:** Indexing
**Description:**
Chroma's default local (DuckDB/SQLite) persistence mode was not designed for hundreds of thousands of vectors. At ~50,000–200,000 chunks (which this project will hit quickly: tens of thousands of filings × multiple chunks per filing), several failure modes emerge: (a) write performance degrades catastrophically — inserts that took milliseconds take seconds; (b) the SQLite WAL file grows unbounded and corrupts under interruption; (c) `collection.query()` full-scan cost grows O(n) for large collections without HNSW tuning; (d) Chroma's persistence layer prior to v0.4.x had silent data-loss bugs on restart.

**Warning signs:**
- Insert rate drops from >1000/s to <10/s as collection grows
- `.persist()` calls taking >30 seconds
- Collection returning fewer results after process restart than were inserted
- Memory usage climbing linearly with collection size

**Prevention:**
1. Use Chroma's **PersistentClient** (not the deprecated `Client(Settings(...))`) with explicit `path=` — the new API in Chroma >= 0.4.0 has better WAL handling.
2. Benchmark at 10k, 50k, 200k chunks before committing to Chroma for production. Keep a migration shim (abstract the vector store behind an interface) from day one.
3. Shard by filing year or issuer type into separate Chroma collections — do not put all 200k+ chunks in one collection.
4. Set `hnsw:space` and `hnsw:construction_ef` explicitly at collection creation; defaults are tuned for small collections.
5. Never interrupt a `.add()` batch mid-way; use atomic batches with a checkpoint table (filing_id, chunk_id, indexed=True) in SQLite so you can resume without re-indexing.

**Phase to address:** Phase 1 (architecture) — the sharding strategy and abstraction layer must be designed before any indexing code is written.

---

### 3. Inline XBRL Namespace Collision Causing Silent Data Loss
**Severity:** Critical
**Layer:** Extraction
**Description:**
Bond filings increasingly use Inline XBRL (iXBRL), where XBRL tags are embedded directly in HTML. The same economic concept (e.g., "coupon rate") can appear under different namespace prefixes across filers (`us-gaap:`, `invest:`, `dei:`, custom extension namespaces) and across filing years (taxonomy versions change). A naive parser that only handles one prefix, or that fails silently on unknown namespaces, will extract 0 values for large subsets of filings with no error raised. This is harder to detect than a crash — the pipeline completes successfully but with empty structured fields.

**Warning signs:**
- Structured field extraction works on a sample set but `coupon`, `maturity`, `principal` are empty for 20-40% of production filings
- Different results for the same issuer's Q1 vs Q2 filing (taxonomy version changed)
- `arelle` or `python-xbrl` returning empty fact lists for valid XBRL documents

**Prevention:**
1. Use **Arelle** (the reference XBRL processor) rather than lightweight alternatives — it handles namespace resolution, taxonomy caching, and iXBRL correctly.
2. Maintain a **concept alias map**: a dictionary mapping all known namespace variants for each target field (coupon rate, maturity date, principal amount, issuer name). Update this map during testing.
3. Log every XBRL parse: record `(filing_id, concept_count, facts_extracted)` — any filing with 0 facts is a warning, not a success.
4. Test against iXBRL filings explicitly (these have `.htm`/`.html` primary documents, not `.xml`) — the parsing path is different.
5. Cache XBRL taxonomy files locally; EDGAR's taxonomy servers are rate-limited too.

**Phase to address:** Phase 2 (XBRL extraction) — build the alias map and validation from the start.

---

### 4. RAG Citation Hallucination on Numerical Bond Data
**Severity:** Critical
**Layer:** Retrieval / LLM
**Description:**
Local LLMs (Llama 3, Mistral, Phi-3, etc. via Ollama) hallucinate financial figures even when the correct chunk is in context. This is specifically acute for bond data: a model asked "what is the coupon rate?" may blend the number from a retrieved chunk with a memorized number from training data, producing a plausible but wrong figure (e.g., "5.25%" instead of the correct "5.875%"). For regulatory data, this is a project-ending trust failure. The problem is worse when: (a) the chunk is dense with numbers, (b) the query is about a specific numerical field, and (c) the model temperature is non-zero.

**Warning signs:**
- Answers that are plausible but off by small amounts (3-10 basis points, wrong dates)
- The cited chunk contains the correct value, but the answer differs
- Answers that change across repeated identical queries (temperature > 0)

**Prevention:**
1. For all structured numeric fields (coupon, maturity, principal, CUSIP, ISIN), **bypass the LLM entirely**: serve the XBRL-extracted value directly, not via RAG generation.
2. Use a **two-track answer architecture**: Track A = structured fields from XBRL/deterministic extraction (exact, cited by source tag); Track B = narrative answers via RAG (LLM-generated, cited by chunk). Never use Track B for numerical facts that Track A can answer.
3. Set LLM temperature to 0 for all financial Q&A.
4. Add a post-generation **consistency check**: extract all numbers from the LLM response; verify each appears verbatim in one of the retrieved chunks. Flag or reject responses where a number cannot be grounded.
5. Include explicit instructions in the system prompt: "Only use numbers that appear verbatim in the provided context. Do not estimate or interpolate."

**Phase to address:** Phase 3 (RAG layer) and SDK design — the two-track architecture must be a first-class design decision.

---

### 5. PDF Table Extraction Producing Garbage Chunks
**Severity:** Critical
**Layer:** Extraction / Chunking
**Description:**
Financial bond documents contain dense, multi-column pricing tables, covenant schedules, and amortization tables. PDF extraction tools (pdfminer, PyMuPDF, pdfplumber) read PDFs as character streams, not as grid structures. The result for a pricing table is typically a jumbled single-string where row values from different columns are concatenated in reading order — "3.500% 2026 100.00 2027 4.000% 99.75" instead of a structured table. When these garbage strings are chunked and embedded, the embedding model cannot understand them, and retrieval for table-based queries fails completely.

**Warning signs:**
- Embedding a "covenant schedule" chunk and querying it by covenant name returns wrong chunks
- The extracted text for a known table looks like a run of numbers with no labels
- Table-related queries consistently return lower cosine similarity scores than narrative queries

**Prevention:**
1. Use **pdfplumber** over pdfminer for table extraction — it has a dedicated `extract_tables()` API that uses bounding-box analysis to detect grid structure. Still imperfect, but far better than raw text flow.
2. Implement a **dual-extraction strategy**: extract narrative text and tables separately; serialize tables as Markdown or CSV strings ("| Coupon | Maturity | Price |\\n|--------|----------|-------|\\n| 3.5% | 2026 | 100.00 |"), then chunk and embed the serialized form.
3. For scanned PDFs (common in older filings pre-2005): detect scanned pages via text-to-page-area ratio; apply OCR (Tesseract or cloud) as fallback. Do not embed blank or near-blank pages.
4. Store the raw table structure (as JSON) alongside the text chunk in Chroma metadata — this allows structured post-retrieval parsing.
5. Multi-column narrative layouts (two-column prospectus format) require column detection before text flow extraction; PyMuPDF's `sort=True` and `clip` parameters can help but require per-filing calibration.

**Phase to address:** Phase 2 (PDF extraction) — define the table extraction strategy before chunking logic is built.

---

## High-Priority Pitfalls

### 6. Chunking That Breaks Tables and Covenant Schedules Mid-Row
**Severity:** High
**Layer:** Chunking
**Description:**
Fixed-size character or token chunking (e.g., "split every 512 tokens") will slice through tables and structured schedules at arbitrary points. A chunk ending mid-table loses the column headers; the next chunk has data rows with no headers. These orphan chunks embed poorly — the embedding model sees a list of numbers with no semantic context — and retrieval for "what are the covenant thresholds?" returns these orphan chunks, producing incomplete or wrong answers.

**Warning signs:**
- Chunks in the vector store that begin with data rows (numbers, percentages) and have no header context
- The same covenant table spread across 3+ chunks with headers only in the first
- Low retrieval precision for structured data questions

**Prevention:**
1. Table-aware chunking is mandatory: detect table boundaries (via pdfplumber bounding boxes, or HTML table tags in iXBRL) and treat each table as an **atomic chunk unit** — never split within a table.
2. If a table exceeds the embedding model's context window, split it row-by-row, but **repeat the column headers** at the start of every sub-chunk.
3. For narrative sections: use **header-aware recursive splitting** (LangChain's `RecursiveCharacterTextSplitter` with separators tuned to the document's header patterns, or a custom splitter that detects "Section X.Y" patterns). Always include the section header in each child chunk.
4. Add a `chunk_type` metadata field: `narrative | table | xbrl_fact | section_header`. Filter by chunk type at retrieval time for structured questions.

**Phase to address:** Phase 2 (chunking strategy) — define chunk types and splitting rules before any embeddings are generated.

---

### 7. EDGAR Filing Index Inconsistencies Causing Missed Filings
**Severity:** High
**Layer:** Ingestion
**Description:**
EDGAR's company search API (`/cgi-bin/browse-edgar`) and the newer JSON API (`/cgi-bin/browse-edgar?action=getcompany&CIK=...&type=...&output=atom`) return different result sets. Filings submitted before ~2000 are not always indexed in the JSON API. Some bond issuers file under multiple CIK numbers (e.g., after mergers or restructurings). Filing types overlap: a bond prospectus can be filed as S-1, S-3, S-11, 424B2, 424B3, 424B5, or ABS-EE depending on issuer type and offering structure. Targeting only one form type misses large portions of the corpus.

**Warning signs:**
- Known filings (verifiable via EDGAR web UI) not appearing in the pipeline's filing list
- Coverage gaps by year (pre-2000 or pre-1996 filings missing)
- Missing filings for known issuers after corporate events

**Prevention:**
1. Build a **form type coverage map** for bond filings: at minimum target `{S-1, S-3, S-11, 424B2, 424B3, 424B5, F-1, F-3, 20-F, 40-F, ABS-EE}` for prospectuses, plus `{10-K, 10-Q, 20-F}` for periodic reports.
2. Use the **EDGAR full-text search API** (`efts.sec.gov/LATEST/search-index`) as a supplementary index — it can find filings that mention bond terms even when form type classification is ambiguous.
3. Maintain a **CIK alias table**: when ingesting a company, query for related CIKs via the company search API and union all results.
4. Build an **audit log**: for each company targeted, log how many filings were found per form type. Manual spot-check against EDGAR web UI for 10 issuers before bulk ingestion.

**Phase to address:** Phase 1 (ingestion) — discovery logic must cover all form types before bulk download.

---

### 8. Embedding Model Not Trained on Financial / Legal Text
**Severity:** High
**Layer:** Indexing / Retrieval
**Description:**
General-purpose sentence embedding models (all-MiniLM-L6-v2, all-mpnet-base-v2) have weak performance on financial and legal terminology. Terms like "negative pledge covenant", "cross-default provision", "DSCR", "make-whole call" have embeddings that cluster poorly with their semantic neighbors in bond documents. This means retrieval by concept works for common language questions but fails for domain-specific queries. The failure is silent: retrieval returns *something*, but it is the wrong something — and this is only detectable with a labeled evaluation set.

**Warning signs:**
- Cosine similarity for clearly relevant chunks is below 0.5
- General questions ("what is the issuer name?") work but domain questions ("is there a change of control put?") return unrelated chunks
- No labeled retrieval eval set means this failure is invisible until a human checks answers

**Prevention:**
1. Use **financial domain-adapted embeddings**: `FinLang/finance-embeddings-investopedia`, `yiyanghkust/finbert-tone`, or `BAAI/bge-large-en-v1.5` (which performs well on financial text in MTEB benchmarks). Avoid generic MiniLM for this domain.
2. Build a **retrieval evaluation set early**: 50 hand-labeled (query, relevant_chunk) pairs covering bond-specific concepts. Measure recall@5 before committing to an embedding model.
3. Test retrieval quality with the actual model before bulk ingestion — changing the embedding model later requires re-embedding all chunks (expensive).
4. Consider **hybrid retrieval**: combine dense (embedding) retrieval with sparse (BM25/keyword) retrieval. Bond documents have exact-match terminology (CUSIP, ISIN, specific covenant names) where BM25 outperforms embedding search.

**Phase to address:** Phase 2-3 boundary — validate embedding model before bulk indexing.

---

### 9. EDGAR Rate Limit Causing Partial Ingestion with No Retry
**Severity:** High
**Layer:** Ingestion
**Description:**
EDGAR returns HTTP 429 (Too Many Requests) when the 10 req/s limit is exceeded. Naive ingestion code that does not handle 429 with exponential backoff will either crash (if exceptions are not caught) or silently skip filings (if errors are swallowed). At tens of thousands of filings, even a 1% silent-skip rate means hundreds of missing documents with no indication of what was missed.

**Warning signs:**
- Ingestion job completes faster than expected
- Filing count in the database is lower than the count returned by EDGAR's search API
- Log files show 429 errors mixed with successful responses

**Prevention:**
1. Implement **exponential backoff with jitter** on all EDGAR HTTP calls: on 429, wait 2^attempt seconds (capped at 60s) plus random jitter (0-1s). Retry up to 5 times before marking a filing as failed.
2. Persist a **download manifest**: a SQLite table `(accession_number, status, downloaded_at, retry_count)`. Only successful downloads advance the pipeline. Interrupted runs resume from the manifest.
3. Process all failed filings as a separate batch at the end of ingestion. Alert if >0.5% of targeted filings fail.
4. Never use threading/async to parallelize EDGAR requests beyond the 10 req/s limit — EDGAR blocks at the IP level, not the connection level.

**Phase to address:** Phase 1 (ingestion) — retry and manifest logic must be in the first working version.

---

### 10. Local LLM Context Window Overflow on Large Bond Documents
**Severity:** High
**Layer:** Retrieval / LLM
**Description:**
Bond prospectuses are long (50-400 pages). Even after chunking, a RAG query may retrieve 5-10 chunks that together exceed the local LLM's effective context window. Ollama models have nominal context windows (Llama 3 8B: 8192 tokens; Mistral 7B: 32k tokens), but **effective** context — where the model reliably attends to all content — is significantly shorter. Content placed in the middle of a long context ("lost in the middle" problem, documented in academic literature) is effectively invisible to the model. For bond Q&A, this means critical covenant terms buried in chunk #4 of 7 retrieved chunks may be ignored.

**Warning signs:**
- Correct chunks retrieved (verified by logging) but answer is wrong or incomplete
- Adding more retrieved chunks makes answers worse, not better
- Answers that reflect only the first and last retrieved chunk

**Prevention:**
1. Limit retrieved chunks to **3-5 per query** with a strict token budget (max 2000 tokens of context for 7B models, 4000 for 13B+). Quality over quantity.
2. **Re-rank** retrieved chunks before passing to the LLM: use a cross-encoder (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) to score relevance of each chunk against the query, then keep only top-K.
3. Place the most relevant chunk **first** in the context (not last) — attention patterns favor earlier content for most decoder models.
4. For multi-fact queries (e.g., "list all covenants and their thresholds"), use **iterative retrieval**: issue multiple sub-queries, aggregate structured results, then synthesize. Do not try to answer the full query in one LLM call.

**Phase to address:** Phase 3 (RAG layer) — design the retrieval strategy before building the SDK interface.

---

## Medium Priority Pitfalls

### 11. XBRL Taxonomy Caching Missing — Re-downloading on Every Parse
**Severity:** Medium
**Layer:** Extraction
**Description:**
XBRL parsing requires downloading taxonomy schemas from external servers (xbrl.fasb.org, xbrl.sec.gov). Arelle and other processors do this automatically, but without a local taxonomy cache, every filing parse triggers 5-20 external HTTP requests. At tens of thousands of filings, this creates thousands of unnecessary external calls, dramatically slows parsing, and will get the server's IP rate-limited or blocked by taxonomy servers.

**Prevention:**
1. Configure Arelle's **local taxonomy cache** (`--cache` flag or `cacheDir` setting) before any bulk parsing.
2. Pre-download the US-GAAP and SEC taxonomies used across the target filing date range.
3. Run XBRL parsing behind the ingestion rate limiter, not as a separate unthrottled process.

**Phase to address:** Phase 2 (XBRL extraction setup).

---

### 12. PDF OCR for Scanned Documents Not Detected
**Severity:** Medium
**Layer:** Extraction
**Description:**
A significant fraction of older EDGAR filings (pre-2005, and some ABS filings at any date) are scanned PDFs — they contain only images, no text layer. pdfminer, PyMuPDF, and pdfplumber will return an empty or near-empty text string for these pages, with no error. These empty chunks get embedded (as near-zero vectors) and indexed, creating noise in the vector store, while the actual content of the filing is lost.

**Prevention:**
1. After text extraction, check text density: if extracted text length < 100 characters per page (averaged over the document), flag as likely scanned.
2. Route flagged documents to an OCR pipeline (Tesseract via pytesseract, or a PDF-specific OCR wrapper). Store `extraction_method: ocr` in chunk metadata.
3. Log scanned filing rate — if >10% of filings require OCR, budget for OCR processing time in pipeline design.

**Phase to address:** Phase 2 (PDF extraction).

---

### 13. Chroma Metadata Filter Queries Not Indexed — Full Collection Scans
**Severity:** Medium
**Layer:** Indexing / Retrieval
**Description:**
Chroma supports metadata filtering (e.g., `where={"issuer": "Apple Inc.", "filing_year": 2023}`), but metadata fields are not indexed by default in the local DuckDB backend. Filtering on metadata triggers a full collection scan before the vector search, which is catastrophically slow at 200k+ chunks. Many developers discover this only when the SDK is already built around metadata filters.

**Prevention:**
1. Design queries to use **vector similarity as the primary filter**, not metadata. Metadata filters should be used only to narrow down already-retrieved candidates.
2. If metadata pre-filtering is required, maintain a separate **SQLite index** (filing_id, issuer, form_type, filing_date) and use it to retrieve a set of chunk IDs, then query Chroma with `ids=` restriction.
3. Benchmark metadata filter queries at target scale (200k chunks) before designing the SDK query interface.

**Phase to address:** Phase 3 (SDK design) — understand this limitation before designing the query API.

---

### 14. Chunk Metadata Insufficient for Citation Generation
**Severity:** Medium
**Layer:** Chunking / Retrieval
**Description:**
Citation quality depends entirely on metadata stored with each chunk at index time. If chunks only store `filing_id` and `chunk_text`, the SDK cannot generate citations like "Section 4.2, Covenant Schedule, 10-K filed 2023-03-15 by Acme Corp (CIK: 0000012345), page 47." Retrofitting citation metadata requires re-chunking and re-indexing the entire corpus.

**Prevention:**
1. Define the **full citation metadata schema before writing any chunking code**: at minimum, each chunk should store: `{filing_id, accession_number, cik, company_name, form_type, filed_date, period_of_report, section_title, section_hierarchy, page_number, chunk_index, chunk_type, xbrl_concept (if applicable)}`.
2. Store the full chunk metadata in both Chroma (for retrieval-time filtering) and a relational SQLite table (for structured queries and audit).
3. Test citation generation end-to-end with 10 filings before bulk ingestion — citation format bugs are easiest to fix at this stage.

**Phase to address:** Phase 2 (chunking) — metadata schema is a pre-condition for chunking implementation.

---

### 15. LLM Prompt Not Constrained to Provided Context
**Severity:** Medium
**Layer:** LLM
**Description:**
Local LLMs without explicit prompt constraints will blend retrieved context with training-time memorized knowledge about bond markets. A query about a specific issuer's covenants may return a response that mixes the correct retrieved covenant terms with generic bond covenant language the model was trained on. This is especially problematic for small/obscure issuers where training data is thin — the model "fills in" plausible but wrong details.

**Prevention:**
1. Use a strict system prompt: "Answer ONLY using the provided document excerpts. If the answer is not in the excerpts, say 'Not found in provided documents.' Do not use general financial knowledge."
2. Instruct the model to quote verbatim from context for all numerical values and defined terms.
3. Add a **refusal detection** post-processing step: if the response contains "I don't know" or "not available" but the retrieved chunks contain the answer (detectable via keyword match), flag for review rather than surfacing the refusal.

**Phase to address:** Phase 3 (RAG / SDK).

---

### 16. SEC EDGAR Full-Text Search API Pagination Incomplete
**Severity:** Medium
**Layer:** Ingestion
**Description:**
EDGAR's full-text search API (`efts.sec.gov/LATEST/search-index`) returns results in pages of up to 10 hits, with a maximum of 10,000 total results per query. For broad queries (e.g., all bond prospectuses in a date range), this cap silently truncates results — the API returns "10,000 of 47,000" with no indication beyond the total_hits field that results are truncated.

**Prevention:**
1. Always read `hits.total.value` from the first page response and compare against the number of pages × page_size. If truncated, narrow the query by date range (query month-by-month) and aggregate results.
2. Implement date-range bisection: if a query returns exactly 10,000 results, split the date range in half and re-query each half.
3. Use the **EDGAR company search API** as a parallel ingestion path: iterate CIKs, then iterate filings per CIK. This avoids full-text search truncation entirely for known issuers.

**Phase to address:** Phase 1 (ingestion discovery logic).

---

## Minor Pitfalls

### 17. Ollama Model Not Quantized Appropriately for Hardware
**Severity:** Low
**Layer:** LLM
**Description:**
Running a 13B+ model at full precision on a developer laptop (16-24GB RAM) causes OOM crashes mid-response. Q4_K_M quantization gives a good quality/performance tradeoff for bond Q&A; Q2 is too lossy for precise financial text reproduction.

**Prevention:** Default to Q4_K_M or Q5_K_M quantization. Test memory headroom at maximum context length before any bulk inference. Document minimum hardware requirements in the README.

**Phase to address:** Phase 3 (Ollama setup).

---

### 18. Vector Store Dimension Mismatch After Model Change
**Severity:** Low
**Layer:** Indexing
**Description:**
If the embedding model is changed after a Chroma collection is populated (e.g., from 384-dim MiniLM to 1024-dim BGE), Chroma raises a dimension mismatch error on subsequent inserts. The collection must be dropped and rebuilt. Without an abstraction layer, this is a full re-index of the entire corpus.

**Prevention:**
1. Store the embedding model name and dimension in collection metadata at creation time.
2. Implement a version check at startup: if the configured model does not match stored metadata, raise an explicit error rather than silently corrupting the collection.
3. Abstract the embedding step so re-embedding all chunks is a single runnable job (not manual).

**Phase to address:** Phase 2 (indexing infrastructure).

---

### 19. Duplicate Filings from EDGAR Amendment Versions
**Severity:** Low
**Layer:** Ingestion
**Description:**
EDGAR often has both an original filing and one or more amendments (e.g., `10-K/A`, `424B3` superseding an earlier `424B3`). Ingesting both creates duplicate and potentially contradictory chunks in the vector store. Queries may retrieve the outdated version.

**Prevention:**
1. For each filing, check for amendment relationships via the EDGAR submission API (`data.sec.gov/submissions/CIK{cik}.json` includes filing history with `isAmendment` and `amendedFormType` fields).
2. Ingest only the most recent version of each filing. Mark superseded accession numbers as `status=superseded` in the download manifest.
3. Store `amendment_sequence` in chunk metadata so retrieval can prefer the latest amendment.

**Phase to address:** Phase 1 (ingestion deduplication logic).

---

## Phase-Specific Warning Summary

| Phase | Topic | Most Likely Pitfall | Severity | Mitigation Priority |
|-------|-------|---------------------|----------|---------------------|
| Phase 1 | EDGAR HTTP client | Missing User-Agent → IP ban | Critical | First thing to implement |
| Phase 1 | Ingestion discovery | Form type coverage gaps | High | Define form type list before crawl |
| Phase 1 | Rate limiting | 429 without retry → silent gaps | High | Implement retry manifest before bulk run |
| Phase 1 | Pagination | Full-text search 10k cap | Medium | Date-range bisection logic |
| Phase 1 | Deduplication | Amendment versions creating duplicates | Low | EDGAR submissions API check |
| Phase 2 | XBRL parsing | Namespace collision → silent empty fields | Critical | Concept alias map + parse audit log |
| Phase 2 | PDF tables | Garbage table text → failed retrieval | Critical | pdfplumber table extraction + dual strategy |
| Phase 2 | Scanned PDFs | Empty pages ingested silently | Medium | Text density check + OCR routing |
| Phase 2 | Chunking | Tables split mid-row | High | Atomic table chunks, header repetition |
| Phase 2 | Chunk metadata | Citation data missing | Medium | Define schema before code |
| Phase 2 | XBRL taxonomy | External taxonomy fetches at scale | Medium | Local taxonomy cache |
| Phase 2 | Embedding model | Wrong model for financial text | High | Eval set + domain model selection |
| Phase 2 | Embedding model | Dimension mismatch after model change | Low | Model version metadata in collection |
| Phase 3 | Chroma scale | Collection collapse at 200k+ chunks | Critical | Shard + benchmark early |
| Phase 3 | Chroma metadata | Unindexed metadata filter → full scan | Medium | SQLite pre-filter pattern |
| Phase 3 | RAG architecture | Numeric hallucination | Critical | Two-track (XBRL + RAG) architecture |
| Phase 3 | LLM context | Lost-in-middle at large context | High | Re-rank + limit chunks |
| Phase 3 | LLM prompt | Training data bleed into responses | Medium | Strict context-only system prompt |
| Phase 3 | Ollama | OOM on large models | Low | Q4_K_M, hardware requirements doc |

---

## Sources and Confidence Notes

**HIGH confidence (from official documentation, well-documented in primary sources):**
- SEC EDGAR User-Agent requirement: documented at `https://www.sec.gov/developer` and EDGAR fair-access policy
- SEC EDGAR rate limit (10 req/s): documented in the EDGAR developer documentation
- EDGAR submissions API format (`data.sec.gov/submissions/CIK{cik}.json`): well-documented REST API
- Chroma >= 0.4.0 PersistentClient API: Chroma official changelog
- "Lost in the middle" LLM attention failure: documented in academic literature (Liu et al., 2023)
- XBRL taxonomy hosting at `xbrl.fasb.org` and `xbrl.sec.gov`: XBRL International documentation
- Arelle as reference XBRL processor: XBRL International's official tooling

**MEDIUM confidence (from strong community consensus and training data, unverified against live sources in this session):**
- Chroma DuckDB/SQLite performance degradation curve at 50k-200k vectors
- pdfplumber `extract_tables()` superiority over pdfminer for grid detection
- FinBERT and BGE models' relative performance on financial text retrieval
- EDGAR full-text search 10,000 result cap
- Inline XBRL namespace collision patterns across filer populations

**LOW confidence (flag for validation during Phase 1-2 research phases):**
- Exact Chroma HNSW parameter defaults and their impact at scale — validate against Chroma current docs
- OCR detection threshold (100 chars/page) — calibrate against actual EDGAR filing sample
- Cross-encoder re-ranking performance gain on bond document queries — benchmark with eval set
- Ollama Q4_K_M quality tradeoff for financial text specifically — test during Phase 3
