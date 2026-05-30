# Graph Report - .  (2026-05-30)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 74 nodes · 93 edges · 9 communities (8 shown, 1 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 9 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `36936d6b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]

## God Nodes (most connected - your core abstractions)
1. `Global Bond Intelligence` - 7 edges
2. `ChunkMetadata Schema` - 7 edges
3. `workflow` - 6 edges
4. `Two-Track Answer Architecture` - 6 edges
5. `Ingestion Layer` - 6 edges
6. `Extraction Layer` - 6 edges
7. `Chunking Layer` - 6 edges
8. `Indexing Layer` - 6 edges
9. `Query / RAG Layer` - 6 edges
10. `Phase 2: Extraction and Chunking` - 5 edges

## Surprising Connections (you probably didn't know these)
- `Global Bond Intelligence` --implements--> `Chunking Layer`  [EXTRACTED]
  README.md → .planning/research/ARCHITECTURE.md
- `Global Bond Intelligence` --implements--> `Extraction Layer`  [EXTRACTED]
  README.md → .planning/research/ARCHITECTURE.md
- `Global Bond Intelligence` --implements--> `Indexing Layer`  [EXTRACTED]
  README.md → .planning/research/ARCHITECTURE.md
- `Global Bond Intelligence` --implements--> `Query / RAG Layer`  [EXTRACTED]
  README.md → .planning/research/ARCHITECTURE.md
- `prefect 3.4.x` --orchestrates--> `Global Bond Intelligence`  [EXTRACTED]
  .planning/research/STACK.md → README.md

## Hyperedges (group relationships)
- **Structure-Aware Chunking Pipeline** — arch_section_chunker, arch_clause_chunker, arch_table_chunker, arch_chunking_layer [EXTRACTED 1.00]
- **Core Pydantic Data Schema (must be frozen)** — project_chunk_metadata_schema, project_bond_term_model, project_citation_model, project_query_response_model [EXTRACTED 1.00]
- **Two-Track Architecture Enforcement** — project_two_track_answer_architecture, req_xbrl_direct_numerics, pitfall_numeric_hallucination, arch_xbrl_parser, arch_rag_engine [INFERRED 0.85]

## Communities (9 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.14
Nodes (13): commit_docs, granularity, graphify, enabled, mode, model_profile, parallelization, workflow (+5 more)

### Community 1 - "Community 1"
Cohesion: 0.22
Nodes (11): Extraction Layer, FormatRouter, PDFExtractor Component, TableExtractor Component, XBRLParser Component, Structured Bond Field Extraction, PDF Table Extraction Garbage Chunks, XBRL Namespace Collision (Silent Data Loss) (+3 more)

### Community 2 - "Community 2"
Cohesion: 0.29
Nodes (11): Chunking Layer, ClauseChunker, SectionChunker, TableChunker, Verbatim Source Citation, Covenant Query (Table Stakes), ChunkMetadata Schema, ChunkMetadata Schema Frozen Before Phase 2 (CHUNK-01) (+3 more)

### Community 3 - "Community 3"
Cohesion: 0.25
Nodes (9): CitationAssembler, Query / RAG Layer, RAGEngine, Confidence Scoring per Extracted Field, RAG Numeric Hallucination, Two-Track Answer Architecture, XBRL Direct Numeric Path — No LLM (RAG-03), langchain-core 0.3.x + langchain-ollama 0.2.x (+1 more)

### Community 4 - "Community 4"
Cohesion: 0.25
Nodes (8): Filing Registry (SQLite), Ingestion Layer, EDGAR IP Ban Risk, Global Bond Intelligence, EDGAR User-Agent Header Requirement, httpx 0.27.x, prefect 3.4.x, sec-edgar-downloader 5.x

### Community 5 - "Community 5"
Cohesion: 0.33
Nodes (6): HybridRetriever, Null / Not-Found Handling, Embedding Model Domain Mismatch, Hybrid Dense+BM25 Retrieval (RAG-01), BAAI/bge-large-en-v1.5, rank-bm25 (BM25 Retrieval)

### Community 6 - "Community 6"
Cohesion: 0.33
Nodes (6): BondTerm Pydantic Model, Citation Pydantic Model, QueryResponse Pydantic Model, BondIntelligence SDK, Phase 3: Indexing, Retrieval, and RAG Engine, Phase 4: Python SDK and Citation API

### Community 7 - "Community 7"
Cohesion: 0.47
Nodes (6): Deterministic chunk_id (sha256), Indexing Layer, Chroma Collection Collapse at Scale, Vector Store Abstraction Interface, Vector Store Interface Abstraction (INDEX-04), chromadb 0.6.x PersistentClient

## Knowledge Gaps
- **28 isolated node(s):** `allow`, `mode`, `granularity`, `parallelization`, `commit_docs` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Global Bond Intelligence` connect `Community 4` to `Community 1`, `Community 2`, `Community 3`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.272) - this node is a cross-community bridge._
- **Why does `Query / RAG Layer` connect `Community 3` to `Community 4`, `Community 5`, `Community 6`?**
  _High betweenness centrality (0.190) - this node is a cross-community bridge._
- **Why does `Extraction Layer` connect `Community 1` to `Community 2`, `Community 4`?**
  _High betweenness centrality (0.132) - this node is a cross-community bridge._
- **What connects `allow`, `mode`, `granularity` to the rest of the system?**
  _32 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._