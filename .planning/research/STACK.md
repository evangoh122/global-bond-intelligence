# Stack Research — Global Bond Intelligence

**Project:** End-to-end regulatory bond intelligence pipeline
**Researched:** 2026-05-29
**Sources:** Context7 (official library docs), Arelle GitHub, PyMuPDF docs, LangChain OSS docs, LlamaIndex docs, Prefect docs, Ollama docs, sbert.net, Chroma Cookbook

---

## Recommended Stack (2025)

---

### Layer 1: SEC EDGAR Ingestion

**Recommended:** `sec-edgar-downloader` 5.x + `httpx` 0.27.x for direct EDGAR full-text search API calls

**Rationale:**
`sec-edgar-downloader` (by jadchaar) is the de facto standard Python library for programmatic EDGAR filing retrieval. It handles rate limiting automatically, supports all SEC filing types (10-K, 10-Q, 8-K, S-1, indentures), downloads by ticker or CIK, and organizes output into a structured directory tree (`sec-edgar-filings/{ticker}/{form}/{accession-number}/`). Built-in rate limiting ensures SEC access policy compliance. For the EDGAR full-text search API (`efts.sec.gov/hits.json`), use `httpx` directly — it is async-native and handles the connection pool correctly for thousands of requests. The `sec-edgar-downloader` library is the right abstraction for bulk archive downloads; `httpx` handles targeted full-text search queries and filing index JSON fetching.

**Confidence:** High (verified via Context7 / official library docs)

**Alternatives considered:**
- `edgar` (bellingcat) — CLI-focused, less ergonomic for pipeline embedding; rejected
- `sec-api.io` SDK — commercial, rate-limited on free tier, adds a cloud dependency; rejected for a local-first pipeline
- Raw `requests` — synchronous only, no connection pooling; replaced by `httpx` for async correctness

---

### Layer 2: XBRL Parsing

**Recommended:** `arelle` 2.x (Python API / `arelle.api.Session`)

**Rationale:**
Arelle is the only production-grade, actively maintained Python XBRL platform as of 2025. It handles Inline XBRL (iXBRL), traditional XBRL, and SEC's specific transform extensions via the bundled `EDGAR/transforms` plugin. It can produce interactive iXBRL viewers and supports full EDGAR EFM validation. The Python API (`arelle.api.Session` + `RuntimeOptions`) provides programmatic control without spawning subprocesses. SEC filings since 2020 are predominantly iXBRL wrapped in HTML; Arelle handles both paths. For simpler scenarios where only tagged facts are needed (not validation), `python-xbrl` is a lighter option, but it does not handle Inline XBRL reliably.

**Confidence:** High (verified via Context7 / Arelle GitHub docs)

**Alternatives considered:**
- `python-xbrl` — does not handle iXBRL; rejected for SEC filings post-2020
- `xbrlware` — abandoned; rejected
- SEC EDGAR Viewer APIs — HTTP-only viewer, not a parsing library; rejected
- Manual lxml/BeautifulSoup parsing of iXBRL HTML — fragile, misses namespace transforms; rejected

---

### Layer 3: PDF Extraction for Financial Documents

**Recommended:** `pymupdf` 1.24.x (primary) + `pymupdf4llm` 0.0.x (LLM-optimized output) + `pdfplumber` 0.11.x (table fallback)

**Rationale:**
PyMuPDF (`pymupdf`) is the fastest and most accurate general-purpose PDF extraction library in Python. It extracts text with layout metadata (bounding boxes, font, size, block structure) via `page.get_text("dict")`, which is essential for section detection. It has native table detection (`page.find_tables()`) that outputs pandas DataFrames or Markdown without external dependencies. For LLM pipeline ingestion, `pymupdf4llm` wraps PyMuPDF to output structured Markdown with table-as-markdown conversion, page chunking, and controllable `table_strategy` — a direct fit for this pipeline's chunking layer input. Use `pdfplumber` as a fallback specifically for scanned or borderless-table PDFs where PyMuPDF's line-based table detector struggles; pdfplumber's word-alignment heuristics handle more irregular layouts.

**Do NOT use:** `camelot` as the primary extractor — it requires Ghostscript as a system dependency, is significantly slower on large document sets, and the `lattice` flavor only works on ruled-line tables. It is suitable only as a last-resort fallback for specific problematic PDFs. `pdfminer.six` is too low-level and slow for tens-of-thousands-of-filings scale.

**Confidence:** High (verified via Context7 / PyMuPDF and pdfplumber official docs)

**Alternatives considered:**
- `pdfminer.six` — lowest-level, slow, no table support; rejected as primary
- `camelot` — Ghostscript dependency, slow, lattice-only for ruled tables; demoted to last-resort fallback
- `pypdf` — text-only, no layout, no tables; rejected
- `LlamaParse` (cloud) — adds cloud dependency and cost; rejected for local-first design

---

### Layer 4: Structure-Aware Chunking

**Recommended:** `llama-index-core` 0.10.x — `HierarchicalNodeParser` + `SentenceSplitter` for hierarchical chunking; `langchain-text-splitters` 0.3.x — `RecursiveCharacterTextSplitter` for flat fallback

**Rationale:**
Bond indentures and SEC filings have clear hierarchical structure: Articles → Sections → Clauses → Paragraphs. LlamaIndex's `HierarchicalNodeParser` is purpose-built for this — it produces a hierarchy of nodes at configurable chunk sizes (e.g., `[2048, 512, 128]`) where child nodes carry parent context. This enables "small-to-big" retrieval: retrieve small precise chunks at query time, expand to parent context for the LLM. The parent-child metadata links are preserved automatically. For flat fallback on unstructured text (cover pages, boilerplate), `RecursiveCharacterTextSplitter` from LangChain is the documented default recommendation — it respects paragraph and sentence boundaries with configurable separators. Use `pymupdf4llm`'s Markdown output as input to the chunkers; the Markdown heading structure maps directly to LlamaIndex node hierarchy.

**Confidence:** High (verified via Context7 / LlamaIndex and LangChain official docs)

**Alternatives considered:**
- LangChain `HTMLHeaderTextSplitter` — useful for HTML filing bodies, but bond PDFs are better handled through pymupdf4llm Markdown output first
- Semantic chunking (embedding-based splits) — too slow for tens of thousands of filings at ingestion time; use as optional post-processing
- Fixed-size token chunking — destroys clause boundaries; rejected for regulatory text

---

### Layer 5: Embeddings

**Recommended:** `sentence-transformers` 3.x with model `BAAI/bge-large-en-v1.5` (primary) or `nomic-ai/nomic-embed-text-v1.5` via Ollama for fully local inference

**Rationale:**
`BAAI/bge-large-en-v1.5` consistently ranks top-5 on MTEB English retrieval benchmarks and runs locally via `sentence-transformers`. It produces 1024-dimensional embeddings with strong performance on domain-specific financial/legal text. It supports asymmetric retrieval (query prefix `Represent this sentence for searching relevant passages:` vs. passage encoding without prefix), which is the correct pattern for RAG. For a fully Ollama-integrated stack, `nomic-embed-text` (768d) is available as `ollama pull nomic-embed-text` and is verified in LlamaIndex/Chroma integration examples — it avoids a separate Python embedding process. At tens-of-thousands-of-filings scale, batch encode with `sentence-transformers` offline ingestion pipeline, then switch to Ollama embeddings at query time if you want a single inference server.

**Dimension guidance for Chroma:**
- `bge-large-en-v1.5`: 1024 dimensions
- `nomic-embed-text-v1.5`: 768 dimensions (can be resized to 128 for cost efficiency)
- `all-MiniLM-L6-v2`: 384 dimensions (fast but weaker on financial text — not recommended)

**Confidence:** Medium-High (MTEB rankings verified via sbert.net docs; model availability via Ollama/LlamaIndex docs)

**Alternatives considered:**
- OpenAI `text-embedding-3-large` — cloud dependency, cost at scale; rejected for local-first design
- `all-MiniLM-L6-v2` — fast but underperforms on domain-specific legal/financial retrieval; rejected as primary
- `e5-large-v2` — strong but BGE-large has higher MTEB retrieval score; rejected
- `Qwen3-Embedding` — very new (2025), promising but less ecosystem tooling; consider for future upgrade

---

### Layer 6: Chroma Vector Store

**Recommended:** `chromadb` 0.6.x with `PersistentClient` and HNSW cosine similarity; batch ingestion via `chromadb.utils.batch_utils.create_batches`

**Rationale:**
Chroma's `PersistentClient` stores the HNSW index and SQLite metadata on disk — correct for local tens-of-thousands-of-filings use. The key operational patterns from Chroma Cookbook (verified):
1. **Batch ingestion:** Use `create_batches()` utility to split large inserts; very large single batches cause HNSW graph update bottlenecks.
2. **HNSW tuning:** For 50k+ vectors, increase `hnsw:M` to 64 (from default ~16) and `hnsw:construction_ef` to 200 for better recall. Rebuild with `chops hnsw rebuild` after bulk ingestion.
3. **HNSW defragmentation:** Frequent updates cause fragmentation; run `chops hnsw rebuild` periodically for accuracy/speed recovery.
4. **Pagination:** Use `limit`/`offset` in `collection.get()` for batch iteration — do not attempt to load full collections into memory.
5. **Distance function:** Use `cosine` for normalized embeddings (BGE and nomic-embed produce normalized vectors).

**Collection design for this project:** One collection per document type (e.g., `bond_indentures`, `sec_filings_text`) with rich metadata (`{"cik": ..., "accession_number": ..., "filing_type": ..., "section": ..., "filing_date": ...}`) for pre-filtering before vector search.

**Confidence:** High (verified via Chroma Cookbook official docs via Context7)

**Alternatives considered:**
- `qdrant` (local) — stronger at large scale, but adds Docker dependency; overkill for local use before 500k vectors
- `faiss` — no metadata filtering, no persistence layer out of the box; rejected for document stores needing metadata
- `pgvector` — requires PostgreSQL; adds heavy infrastructure for a local-first pipeline; rejected
- Chroma `HttpClient` (server mode) — correct for multi-process access but adds complexity; use only if concurrent writers are needed

---

### Layer 7: RAG Orchestration

**Recommended:** `langchain-core` 0.3.x + `langchain-ollama` 0.2.x + `langchain-chroma` 0.1.x, using LCEL (LangChain Expression Language) chains

**Rationale:**
LangChain's LCEL provides a composable, type-safe chain DSL that handles the full RAG retrieval-prompt-generate loop. The `langchain-ollama` package (not deprecated `langchain-community.llms.Ollama`) provides the `ChatOllama` integration. The `langchain-chroma` package provides the `Chroma` vector store retriever with metadata filtering. LCEL's `RunnablePassthrough.assign` pattern cleanly implements the standard RAG pattern (retrieve → format → prompt → generate → parse). For citation tracking — critical for regulatory bond intelligence — the `return_source_documents=True` option on retrieval chains or LCEL's document passthrough yields exact chunk provenance (accession number, section, page) from Chroma metadata.

Use LlamaIndex's `HierarchicalNodeParser` at ingestion time, then LangChain at query time. The two libraries are complementary, not mutually exclusive.

**Confidence:** High (verified via Context7 / LangChain OSS Python docs and Ollama integration docs)

**Alternatives considered:**
- Pure LlamaIndex for the full RAG stack — viable, but LangChain has better Ollama + Chroma integration docs and more active LCEL development for custom chains
- Raw implementation (no framework) — maximum control, but loses retriever abstractions, chain composition, and output parsing; only justified if frameworks add unacceptable overhead
- `haystack` 2.x — solid alternative, but smaller community and fewer Ollama integration examples; rejected
- LangGraph — adds agentic routing complexity; overkill for citation-focused Q&A; consider for future agentic retrieval

---

### Layer 8: Local LLM via Ollama

**Recommended:** `ollama` Python SDK 0.3.x; model `llama3.1:8b-instruct-q4_K_M` for primary (fits in 8GB VRAM) or `qwen2.5:14b-instruct-q4_K_M` for highest quality (requires 16GB VRAM)

**Rationale:**
Ollama provides a clean OpenAI-compatible API locally, with first-class structured output support via Pydantic schema enforcement (`format=MyModel.model_json_schema()`, `options={'temperature': 0}`). This is critical for returning structured bond term objects (covenant definitions, interest rate schedules, maturity dates) rather than free text.

**Model selection for structured finance Q&A:**
- `llama3.1:8b-instruct` (Q4_K_M, ~4.7GB): Best balance of speed and quality for a development environment. Strong instruction following; handles JSON output reliably with `format=` schema.
- `qwen2.5:14b-instruct` (Q4_K_M, ~9GB): Materially better at complex clause interpretation and multi-hop bond term reasoning. Recommended for production if hardware allows.
- `mistral:7b-instruct` — fast but weaker than Llama 3.1 on structured output compliance; acceptable fallback.
- `phi3:14b` — strong reasoning but slower; consider if VRAM is constrained.

LangChain integration uses `from langchain_ollama import ChatOllama` (the modern `langchain-ollama` package, not `langchain-community`).

**Confidence:** Medium-High (model rankings from Ollama docs + Pydantic structured output from Context7; specific finance benchmark data not available without WebSearch)

**Alternatives considered:**
- Llama 3.2:3b — too small for multi-clause bond covenant reasoning; rejected
- OpenAI API — cloud dependency; rejected for local-first design
- vLLM — more efficient at serving but adds complexity vs. Ollama for single-machine use; rejected
- GPT4All — less maintained Python SDK; rejected

---

### Layer 9: Data Pipeline Orchestration

**Recommended:** `prefect` 3.x (latest stable: 3.4.10)

**Rationale:**
Prefect 3.x is the standard for Python-native data pipeline orchestration in 2025. It converts plain Python functions into observable, retriable, cacheable pipeline steps with `@task` and `@flow` decorators — zero boilerplate. Critical features for this pipeline:
1. **Task-level caching:** `cache_policy=INPUTS` prevents re-downloading and re-parsing already-processed filings. Essential at tens-of-thousands scale.
2. **Concurrent mapping:** `task.map(list_of_filings)` parallelizes ingestion across filing batches natively.
3. **Retry logic:** `@task(retries=3, retry_delay_seconds=5)` handles SEC EDGAR transient rate limits gracefully.
4. **Resumability:** Failed runs can be re-triggered from the point of failure, not from scratch.
5. **Local execution:** No server required for development; Prefect runs entirely locally. Optional Prefect Cloud for monitoring.

**Confidence:** High (verified via Context7 / Prefect official docs and GitHub)

**Alternatives considered:**
- `apache-airflow` — heavyweight, requires a separate database and scheduler; overkill for a single-machine pipeline; rejected
- `dagster` — excellent but heavier setup; better fit if the pipeline grows to a multi-team data platform; consider as upgrade path
- `dask` — parallel computing library, not an orchestration framework; no retry/caching primitives; rejected as primary orchestrator
- Plain `asyncio` — no retry, no caching, no observability; rejected
- `luigi` — outdated ergonomics; rejected

---

## What NOT to Use

| Library | Reason |
|---------|--------|
| `camelot` (as primary PDF extractor) | Requires Ghostscript system dependency; slow at scale; lattice flavor only handles ruled tables |
| `pdfminer.six` | Too low-level; no table support; slow for 10k+ documents |
| `python-xbrl` | Does not handle Inline XBRL (iXBRL); SEC filings post-2020 are predominantly iXBRL |
| `xbrlware` | Abandoned project |
| `requests` | Synchronous; use `httpx` instead for async-compatible ingestion |
| `faiss` (standalone) | No metadata filtering, no persistence without wrappers |
| `openai` SDK for embeddings | Cloud dependency at scale; use local `sentence-transformers` or Ollama |
| `all-MiniLM-L6-v2` | 384d model underperforms on financial/legal domain text; use BGE-large instead |
| `langchain-community` Ollama classes | Deprecated; use `langchain-ollama` package |
| Chroma `EphemeralClient` | In-memory only; data lost on process exit; use `PersistentClient` |
| Apache Airflow | Server + DB required; too heavy for single-machine local pipeline |

---

## Key Versions (as of 2025)

| Library | Recommended Version | Notes |
|---------|---------------------|-------|
| `sec-edgar-downloader` | 5.x | Rate-limiting built in; directory structure output |
| `httpx` | 0.27.x | Async HTTP for EDGAR full-text search API |
| `arelle` | 2.x | Inline XBRL + SEC EDGAR plugin |
| `pymupdf` | 1.24.x | Primary PDF extraction; native table detection |
| `pymupdf4llm` | 0.0.x (latest) | Markdown output for LLM ingestion; wraps PyMuPDF |
| `pdfplumber` | 0.11.x | Fallback for borderless-table PDFs |
| `llama-index-core` | 0.10.x | `HierarchicalNodeParser`, `SentenceSplitter` |
| `langchain-text-splitters` | 0.3.x | `RecursiveCharacterTextSplitter` fallback |
| `sentence-transformers` | 3.x | Embedding generation; MTEB-validated models |
| `chromadb` | 0.6.x | Persistent local vector store |
| `langchain-core` | 0.3.x | LCEL chain composition |
| `langchain-ollama` | 0.2.x | `ChatOllama` (replaces deprecated community class) |
| `langchain-chroma` | 0.1.x | Chroma retriever integration |
| `ollama` | 0.3.x | Python SDK for local LLM inference |
| `prefect` | 3.4.x | Pipeline orchestration; task-level caching |
| `pydantic` | 2.x | Structured output schemas for Ollama |

---

## Installation

```bash
# Core ingestion
pip install sec-edgar-downloader httpx arelle-release

# PDF extraction
pip install pymupdf pymupdf4llm pdfplumber

# Chunking
pip install llama-index-core langchain-text-splitters

# Embeddings
pip install sentence-transformers

# Vector store
pip install chromadb

# RAG orchestration
pip install langchain-core langchain-ollama langchain-chroma llama-index-vector-stores-chroma

# Local LLM (Python SDK only — install Ollama binary separately)
pip install ollama

# Pipeline orchestration
pip install prefect

# Data validation
pip install pydantic
```

```bash
# Ollama models (run after installing Ollama binary)
ollama pull llama3.1:8b-instruct-q4_K_M
ollama pull nomic-embed-text
# Optional higher-quality model
ollama pull qwen2.5:14b-instruct-q4_K_M
```

---

## Sources

- sec-edgar-downloader: https://context7.com/jadchaar/sec-edgar-downloader/llms.txt
- Arelle EDGAR plugin: https://github.com/arelle/arelle/blob/master/docs/source/plugins/popular/edgar.md
- PyMuPDF docs: https://context7.com/pymupdf/pymupdf (table extraction, layout metadata)
- PyMuPDF4LLM: https://github.com/pymupdf/pymupdf4llm
- pdfplumber docs: https://context7.com/jsvine/pdfplumber
- LlamaIndex HierarchicalNodeParser: https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules
- LangChain RecursiveCharacterTextSplitter: https://docs.langchain.com/oss/python/integrations/splitters
- sbert.net MTEB evaluation: https://www.sbert.net/docs/sentence_transformer/usage/mteb_evaluation.html
- Chroma Cookbook (batching, HNSW, performance): https://cookbook.chromadb.dev
- LangChain Ollama + Chroma RAG: https://docs.langchain.com/oss/python/integrations/chat/ollama
- Ollama structured outputs: https://context7.com/ollama/ollama-python/llms.txt
- Prefect 3 caching + retries: https://github.com/prefecthq/prefect/blob/main/docs/v3
