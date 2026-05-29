# Architecture Research — Global Bond Intelligence

**Researched:** 2026-05-29
**Overall confidence:** HIGH (all major claims verified against LlamaIndex and Llama-cookbook official documentation)

---

## Recommended Architecture

The pipeline decomposes cleanly into five sequential stages with a thin SDK layer on top. Each stage has a single responsibility and a well-defined output type that feeds the next stage. There is no streaming requirement (batch pipeline, per PROJECT.md), which simplifies the design considerably.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          GLOBAL BOND INTELLIGENCE                           │
├───────────────┬──────────────────┬────────────────┬──────────────┬──────────┤
│   INGESTION   │   EXTRACTION     │   CHUNKING     │  INDEXING    │  QUERY   │
│               │                  │                │              │  LAYER   │
│  EDGAR API    │  XBRL Parser     │  Section       │  Embed       │  RAG     │
│  Filing DL    │  PDF Extractor   │  Chunker       │  Chroma      │  Engine  │
│  Registry     │  Table Extractor │  Clause        │  Persist     │  SDK     │
│  (SQLite)     │  Format Router   │  Chunker       │              │          │
│               │                  │  Table         │              │          │
│               │                  │  Chunker       │              │          │
└───────────────┴──────────────────┴────────────────┴──────────────┴──────────┘
         │               │                │               │              │
    raw files       structured         typed           vector        citations +
    + metadata      text + tables      chunks          index         answers
```

### Component Map

**1. Ingestion Layer**
Downloads filings from SEC EDGAR and maintains a registry of what has been ingested. This is the only component that talks to external systems (EDGAR APIs). It writes raw files to disk and records metadata (accession number, CIK, filing type, date, URL) in a local SQLite registry. The registry is the idempotency gate: re-runs skip already-downloaded filings.

**2. Extraction Layer**
Reads raw files and produces structured text + table data. Contains three sub-components:
- `XBRLParser`: parses iXBRL/XBRL-tagged fields into structured dicts (coupon, maturity, CUSIP, covenants, etc.)
- `PDFExtractor`: extracts text with layout hints (page number, bounding box) using pdfplumber or pymupdf
- `TableExtractor`: isolates tabular regions from PDFs (pricing tables, covenant schedules) using pdfplumber's table API or unstructured.io's `UnstructuredElementNodeParser` pattern
- `FormatRouter`: decides which extractor to invoke per filing type; XBRL-first with PDF fallback

The extraction layer outputs a canonical `ExtractedDocument` object: `{filing_id, format, text_blocks: [{text, page, bbox, section_hint}], tables: [{caption, rows, page}], structured_fields: dict}`.

**3. Chunking Layer**
Transforms `ExtractedDocument` into typed `Chunk` objects. Three chunker strategies, each with its own class:
- `SectionChunker`: splits by document section headers (regex + heuristic detection of "ARTICLE", "SECTION", numbered headings). Produces large chunks (1024–2048 tokens) for high-level context.
- `ClauseChunker`: splits sections into semantic clause-level pieces (256–512 tokens). Uses sentence boundary detection with overlap. Designed for narrative covenant text.
- `TableChunker`: converts each extracted table into a self-contained chunk that serializes the table as markdown or structured text with its caption. Preserves table integrity — never splits a table row mid-chunk.

Each chunk carries a `ChunkMetadata` envelope (see Citation Architecture below). The chunking layer is stateless — it reads `ExtractedDocument` and writes `List[Chunk]`.

**4. Indexing Layer**
Embeds chunks and loads them into Chroma. Operates in batch mode: processes chunks in batches of 500–1000 to avoid OOM on the local embedding model. Uses `chromadb.PersistentClient` to write to disk. The collection is pre-checked for existing IDs before insertion to support incremental re-indexing (Chroma `upsert` semantics via `collection.upsert()`).

**5. Query / RAG Layer**
Implements the retrieval chain: hybrid retrieval (dense vector + BM25) → reranking → Ollama LLM synthesis → citation assembly. Exposed as a Python SDK class (`BondIntelligence`). Returns `QueryResponse` with both structured field answers and narrative text, each backed by `Citation` objects.

---

### Data Flow

```
EDGAR EDGAR EDGAR (full-text search + filing archives)
    │
    ▼
[Ingestion] ──writes──► filing_registry.db (SQLite)
    │                    raw_filings/ (disk)
    │
    ▼
[Extraction] ──reads──► raw_filings/*.xml, *.pdf
    │           produces ExtractedDocument per filing
    │
    ▼
[Chunking] ──reads──► ExtractedDocument
    │         produces List[Chunk] (typed: section/clause/table)
    │         each Chunk carries full provenance metadata
    │
    ▼
[Indexing] ──embeds──► local sentence-transformer model
    │         upserts──► chroma_db/ (PersistentClient)
    │                    collection: "bond_filings"
    │
    ▼
[Query Layer]
    │  1. dense retrieval from Chroma (top-k=15)
    │  2. BM25 keyword retrieval (top-k=15)
    │  3. reciprocal rank fusion / reranking (cross-encoder, top-n=5)
    │  4. Ollama LLM synthesis with retrieved context
    │  5. citation assembly from chunk metadata
    │
    ▼
QueryResponse {
  narrative: str,          # LLM-generated answer
  structured_fields: dict, # extracted bond fields if applicable
  citations: List[Citation]
}
```

---

### Component Boundaries

| Component | Responsibility | Interfaces |
|-----------|----------------|------------|
| **IngestorClient** | EDGAR API calls, filing download, deduplication via SQLite registry | Input: query params (date range, filing type, CIK). Output: `FilingRecord` list + files on disk |
| **FilingRegistry** | SQLite store tracking download status, accession numbers, file paths | Read/write by Ingestor. Read by Extractor to find unprocessed filings |
| **FormatRouter** | Inspects filing type + file extension, delegates to correct extractor | Input: `FilingRecord`. Output: `ExtractedDocument` |
| **XBRLParser** | Parses iXBRL/XBRL namespace, extracts tagged bond fields | Input: `.xml`/`.htm` file path. Output: `structured_fields` dict |
| **PDFExtractor** | Text + layout extraction from PDF, preserves page numbers | Input: `.pdf` file path. Output: `text_blocks` list |
| **TableExtractor** | Isolates and parses tabular regions from PDF pages | Input: `.pdf` file path. Output: `tables` list |
| **SectionChunker** | Header-based document segmentation | Input: `ExtractedDocument`. Output: `List[Chunk]` with `chunk_type=section` |
| **ClauseChunker** | Sentence-boundary semantic splitting within sections | Input: section text. Output: `List[Chunk]` with `chunk_type=clause` |
| **TableChunker** | Table serialization to self-contained text chunks | Input: `Table`. Output: `List[Chunk]` with `chunk_type=table` |
| **ChunkPipeline** | Orchestrates all three chunkers per document | Input: `ExtractedDocument`. Output: `List[Chunk]` |
| **Indexer** | Embeds chunks in batch, upserts into Chroma collection | Input: `List[Chunk]`. Output: persisted Chroma collection |
| **HybridRetriever** | Dense + BM25 fusion retrieval from Chroma + docstore | Input: query string + filters. Output: ranked `List[Chunk]` |
| **Reranker** | Cross-encoder reranking of retrieved candidates | Input: `List[Chunk]` + query. Output: top-N `List[Chunk]` |
| **RAGEngine** | Assembles prompt, calls Ollama, parses response | Input: query + reranked chunks. Output: `QueryResponse` |
| **CitationAssembler** | Maps response references back to chunk metadata → source filings | Input: source nodes. Output: `List[Citation]` |
| **BondIntelligence (SDK)** | Public API class. Single entry point for callers | Input: natural language query, optional filters. Output: `QueryResponse` |

---

## Suggested Build Order

### Phase 1: Ingestion + Registry (foundation)
Build the EDGAR downloader and SQLite filing registry first. This gives you a real corpus to work with throughout all other phases. Everything downstream depends on having actual filings on disk.

- EDGAR full-text search API integration (search by form type: S-1, 424B, 10-K, etc.)
- Filing archive download with rate limiting (EDGAR allows 10 req/sec)
- SQLite registry: `accession_number`, `cik`, `form_type`, `filing_date`, `file_path`, `status` (downloaded/extracted/indexed)
- Idempotency: skip already-downloaded filings on re-run

**Why first:** Without filings, every other component has nothing to operate on. The registry pattern also establishes the incremental update mechanism that all later phases rely on.

### Phase 2: Extraction Layer (get text out of files)
Build extraction before chunking because chunking quality depends entirely on extraction quality. Test extraction on a sample of 100 filings before proceeding.

- XBRL parser for structured fields (lxml + arelle or manual namespace walking)
- PDF text extractor (pdfplumber recommended: handles multi-column layouts better than PyMuPDF for regulatory docs)
- Table extractor (pdfplumber's `extract_tables()` for simple tables; fallback to unstructured.io for complex layouts)
- Format router
- Output: canonical `ExtractedDocument` objects, optionally cached to disk as JSON

**Why second:** Extraction bugs propagate into chunks and embeddings. Fix them at this layer before committing to an index schema.

### Phase 3: Chunking Layer (structure-aware)
Build all three chunkers together since they share the `Chunk` and `ChunkMetadata` schema.

- Define `ChunkMetadata` schema first (see Citation Architecture)
- `SectionChunker`: regex-based header detection tuned to bond prospectus structure
- `ClauseChunker`: sentence splitter with 10–15% token overlap
- `TableChunker`: table-to-markdown serialization
- `ChunkPipeline`: orchestrates chunkers, assembles final chunk list per document

**Why third:** The chunk schema defines the shape of everything that goes into Chroma. Finalize it before building the index.

### Phase 4: Indexing + Local Embedding (get vectors into Chroma)
With chunks in hand, build the embedding + Chroma ingestion pipeline.

- Local embedding model selection (BAAI/bge-small-en-v1.5 for speed; bge-large for accuracy — benchmark on a 1000-chunk sample)
- Batch embedding loop (batches of 500 to avoid OOM)
- Chroma `PersistentClient` setup, collection creation
- Upsert logic keyed on `chunk_id` for incremental updates
- Verify collection `.count()` matches expected chunk count after ingestion

**Why fourth:** Indexing is the most time-consuming step at scale. Get it right with a small corpus first (1000 filings), then run the full corpus.

### Phase 5: RAG Query Engine + Ollama
Build retrieval and generation once the index is populated.

- Dense retrieval from Chroma (similarity_top_k=15)
- BM25 retrieval from in-memory or docstore-backed index (BM25Retriever from llama-index-retrievers-bm25)
- Reciprocal Rank Fusion to merge dense and sparse results
- Cross-encoder reranker (SentenceTransformerRerank with `cross-encoder/ms-marco-MiniLM-L6-v2`, local — no API calls)
- Ollama LLM integration (`llama_index.llms.ollama.Ollama`)
- Response synthesis with citation assembly

**Why fifth:** Building on a real populated index lets you evaluate retrieval quality against actual queries.

### Phase 6: Python SDK + Citation API
Wrap the RAG engine in the public `BondIntelligence` SDK class. Design the `QueryResponse` and `Citation` types to be the stable public interface.

- `BondIntelligence(chroma_path, ollama_model, embedding_model)` constructor
- `.query(text, filters=None) -> QueryResponse`
- `QueryResponse` dataclass with `narrative`, `structured_fields`, `citations`
- `Citation` dataclass (see Citation Architecture)
- Input validation, error handling, logging

---

## Key Architectural Decisions

| Decision | Options | Recommendation | Rationale |
|----------|---------|----------------|-----------|
| **Extraction framework** | pdfplumber, PyMuPDF, unstructured.io | pdfplumber for primary text/tables; unstructured.io `UnstructuredElementNodeParser` pattern for complex layouts | pdfplumber handles multi-column regulatory PDF layouts better; unstructured.io for table detection in complex documents. Both are local, no API needed. |
| **Chunking approach** | Fixed-size tokens, semantic, hierarchical, structure-aware | Structure-aware with three typed chunkers (section/clause/table) | Financial/legal documents have explicit structural markers. Token-fixed chunking destroys document structure and degrades RAG quality for covenant-level questions. |
| **Orchestration framework** | LlamaIndex IngestionPipeline, LangChain, custom | LlamaIndex IngestionPipeline + custom pipeline for chunking | LlamaIndex has first-class support for ingestion pipelines, metadata extraction, Chroma, Ollama, BM25, and citation query engines. Avoid LangChain for this project — heavier abstraction with less direct control over chunk metadata. |
| **Retrieval strategy** | Dense-only, BM25-only, hybrid | Hybrid (dense + BM25) with cross-encoder reranking | Financial documents contain exact terminology (bond covenants, CUSIP numbers, rate definitions) where keyword matching outperforms semantic search. Hybrid fusion combines both signals. Cross-encoder reranking is essential at scale — improves precision significantly at top-5. |
| **Chroma collection structure** | Single collection, per-filing-type collections, per-source collections | Single collection `bond_filings` with rich metadata for filtering | Simpler to manage; metadata filters (`filing_type`, `cik`, `date_range`) handle all scoping needs. Multiple collections add operational complexity without retrieval benefit for this corpus size. |
| **Registry backend** | SQLite, JSON files, PostgreSQL | SQLite (`filing_registry.db`) | No infrastructure overhead. Sufficient for tens of thousands of rows. Supports concurrent reads. Easy to inspect and back up. |
| **Incremental update strategy** | Full re-index, upsert by chunk_id, append-only | Upsert by `chunk_id` (deterministic hash of `filing_id + chunk_index`) | Allows re-running the pipeline on updated filings without blowing away the entire index. Chroma's `collection.upsert()` supports this pattern natively. |
| **Embedding model** | OpenAI text-embedding-3, sentence-transformers, BGE | BAAI/bge-small-en-v1.5 or BAAI/bge-base-en-v1.5 (local) | Best performance/speed ratio for financial text among freely available local models. BGE models consistently rank at the top of MTEB financial domain benchmarks. No API calls required. |
| **Reranker** | Cohere (API), cross-encoder local, colbert | `cross-encoder/ms-marco-MiniLM-L6-v2` (local SentenceTransformerRerank) | Fully local. LlamaIndex `SentenceTransformerRerank` supports it natively. Provides meaningful precision improvement at top-5 without API dependency. |

---

## Chroma at Scale

**Verified against:** LlamaIndex Chroma integration docs (official), Chroma cookbook (official)

### Scale Characteristics
Chroma's `PersistentClient` uses SQLite + HNSWLIB under the hood. At tens of thousands of documents with 3–10 chunks per document, expect 100k–500k vectors in the collection. Chroma handles this range reliably on local hardware.

**Practical limits:** Chroma with HNSW starts showing query latency degradation beyond ~1M vectors on consumer hardware. For this project's scope (tens of thousands of filings), you are well within the safe operating range.

### Collection Strategy
Use a **single collection** named `bond_filings` with metadata-based scoping:

```python
db = chromadb.PersistentClient(path="./chroma_db")
collection = db.get_or_create_collection(
    name="bond_filings",
    metadata={"hnsw:space": "cosine"}  # cosine similarity for sentence embeddings
)
```

Do NOT create per-filing or per-type collections. Metadata filters are more efficient and avoid the operational overhead of managing hundreds of collections.

### Persistence Pattern
Use the cache-hit pattern to avoid re-embedding on startup:

```python
existing = [c.name for c in chroma_client.list_collections()]
if "bond_filings" in existing:
    collection = chroma_client.get_collection("bond_filings")
    index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
else:
    # build and persist
```

### Incremental Indexing
Use `collection.upsert()` with deterministic chunk IDs. Never `collection.add()` without first checking for existence — it will raise on duplicate IDs. The upsert pattern handles both new filings and re-ingested filings cleanly:

```python
collection.upsert(
    ids=[chunk.chunk_id for chunk in chunks],
    embeddings=[chunk.embedding for chunk in chunks],
    documents=[chunk.text for chunk in chunks],
    metadatas=[chunk.metadata.to_dict() for chunk in chunks]
)
```

### Metadata Filtering at Query Time
Chroma supports `where` clause filtering on metadata fields. Design metadata fields to support the most common filter patterns:

```python
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=15,
    where={
        "$and": [
            {"filing_type": {"$eq": "424B5"}},
            {"filing_date": {"$gte": "2023-01-01"}}
        ]
    }
)
```

### Backup and Recovery
Chroma `PersistentClient` writes to a directory. Back up by copying the directory. The SQLite file (`chroma.sqlite3`) contains the full index state. No special export needed.

### Migration Path
If the corpus grows beyond ~1M chunks, migrate to Qdrant (self-hosted, Docker) which has native hybrid search (dense + BM25 sparse) built in, eliminating the need for a separate BM25 index. LlamaIndex has a `QdrantVectorStore` integration that is a near drop-in replacement.

---

## Citation Architecture

Citation tracking is a first-class design concern, not an afterthought. Every chunk must carry enough metadata to reconstruct a full citation at query time.

### ChunkMetadata Schema
Define this schema before writing any chunker. It is the contract between the ingestion pipeline and the query layer.

```python
@dataclass
class ChunkMetadata:
    # Identity
    chunk_id: str          # deterministic: sha256(filing_id + str(chunk_index))
    chunk_index: int       # position within filing's chunk list
    chunk_type: str        # "section" | "clause" | "table"

    # Source document
    filing_id: str         # EDGAR accession number (e.g. "0001234567-23-000001")
    cik: str               # SEC CIK number
    company_name: str      # issuer name
    filing_type: str       # "S-1", "424B5", "10-K", etc.
    filing_date: str       # ISO date string "YYYY-MM-DD"
    filing_url: str        # canonical EDGAR URL for the filing

    # Location within document
    source_file: str       # filename within the filing (e.g. "prospectus.pdf")
    page_number: int       # PDF page number (None for XBRL chunks)
    section_title: str     # nearest ancestor section header
    section_number: str    # section number if present (e.g. "3.2.1")

    # For tables
    table_caption: str     # table title if detected (None for non-table chunks)
    table_index: int       # table number within filing (None for non-table chunks)

    def to_dict(self) -> dict:
        # flatten for Chroma metadata (Chroma requires flat dict, string/int/float values only)
        ...
```

### Citation Flow at Query Time

```
User query
    │
    ▼
HybridRetriever → top-15 chunks (each has full ChunkMetadata)
    │
    ▼
Reranker → top-5 chunks
    │
    ▼
RAGEngine → sends chunk text to Ollama
    │         instructs LLM to reference chunks by index [1], [2], etc.
    │
    ▼
CitationAssembler
    │  for each source_node in response.source_nodes:
    │      metadata = source_node.node.metadata  (the ChunkMetadata dict)
    │      build Citation object
    │
    ▼
Citation {
    reference_index: int        # [1], [2] as used in narrative
    chunk_id: str
    chunk_type: str             # "section" | "clause" | "table"
    filing_id: str              # EDGAR accession number
    company_name: str
    filing_type: str
    filing_date: str
    filing_url: str             # direct link to EDGAR filing
    section_title: str
    page_number: int            # None if XBRL-sourced
    excerpt: str                # first 300 chars of chunk text
}
```

### Citation-Aware Query Engine
LlamaIndex's `CitationQueryEngine` provides in-line citations `[1]`, `[2]` in LLM responses natively. Use it as the base query engine:

```python
from llama_index.core.query_engine import CitationQueryEngine

query_engine = CitationQueryEngine.from_args(
    index,
    similarity_top_k=5,
    citation_chunk_size=512,
)
response = query_engine.query("What is the coupon rate?")
# response.source_nodes contains NodeWithScore objects
# each has .node.metadata = ChunkMetadata.to_dict()
```

### Source Document Traceability Table
Maintain this SQLite table alongside the vector index:

```sql
CREATE TABLE chunk_registry (
    chunk_id TEXT PRIMARY KEY,
    filing_id TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    section_title TEXT,
    page_number INTEGER,
    table_caption TEXT,
    created_at TEXT,
    FOREIGN KEY (filing_id) REFERENCES filing_registry(accession_number)
);
```

This enables citation lookups without round-tripping to Chroma metadata, and supports audit queries ("which filings is this answer drawn from?").

---

## Architecture Anti-Patterns to Avoid

**1. Mixing chunk types in a single chunker pass**
Section, clause, and table chunking have fundamentally different logic. Implementing them as a single pass leads to either missed table boundaries or incorrectly split sections. Keep three separate chunker classes with a pipeline orchestrator.

**2. Storing chunk metadata only in Chroma**
Chroma metadata is not easily queryable for analytics (which filings are indexed? what is the coverage?). Store authoritative metadata in SQLite; use Chroma metadata as a cache for query-time filtering only.

**3. Fixed-size token chunking for regulatory documents**
Bond prospectuses have clear structural boundaries (articles, sections, definitions sections, covenant schedules). Fixed-size chunking cuts across these boundaries and returns contextually incomplete chunks on retrieval. Structure-aware chunking is non-negotiable for this domain.

**4. Dense-only retrieval**
Bond covenant text contains specific legal terms and defined terms (e.g. "Consolidated EBITDA", "Permitted Investments") that are semantically similar to many other terms but must match exactly. BM25 keyword retrieval handles this reliably; dense-only retrieval misses exact-match critical clauses.

**5. Building the SDK before the RAG engine works**
The SDK is a thin wrapper. Build and validate the RAG engine end-to-end first (with a temporary test harness), then wrap it in the SDK. Inverting this order creates a debugging nightmare.

**6. Re-embedding the entire corpus on re-runs**
Design for incremental ingestion from Phase 1. The upsert-by-chunk-id pattern means new filings can be added to the index without re-processing the existing 50k filings. Missing this means every update takes hours.

---

## Sources

- LlamaIndex ingestion pipeline documentation: https://github.com/run-llama/llama_index (official, HIGH confidence)
- LlamaIndex Chroma integration examples: ChromaIndexDemo.ipynb, local_rag_with_chroma_and_ollama.ipynb (official, HIGH confidence)
- LlamaIndex Ollama + local RAG: privacy.md, faq.mdx (official, HIGH confidence)
- LlamaIndex CitationQueryEngine: citation_query_engine.ipynb, pdf_page_reference.ipynb (official, HIGH confidence)
- LlamaIndex HierarchicalNodeParser + UnstructuredElementNodeParser: modules.md, llava_demo.ipynb (official, HIGH confidence)
- LlamaIndex BM25 hybrid retrieval: contextual_retrieval.ipynb, reciprocal_rerank_fusion.ipynb (official, HIGH confidence)
- LlamaIndex SentenceTransformerRerank (local reranking): privacy.md (official, HIGH confidence)
- Llama Cookbook: langgraph_rag_agent_local.ipynb, Example_FinancialReport_RAG.ipynb (official, HIGH confidence)
- LlamaIndex metadata extraction for SEC 10-K filings: MetadataExtractionSEC.ipynb (official, HIGH confidence)
