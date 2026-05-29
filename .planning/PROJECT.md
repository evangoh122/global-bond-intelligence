# Global Bond Intelligence

## What This Is

An end-to-end pipeline that collects bond filings from SEC Edgar (v1), EDINET, ESMA, and HKEX; extracts structured data via XBRL parsing and PDF text extraction; chunks documents with section, clause, and table awareness; and exposes a Python SDK backed by a RAG layer for intelligent retrieval and citation over regulatory fixed income data. Serves both human analysts running ad-hoc queries and programmatic downstream systems that need structured bond data as context.

## Core Value

An analyst or downstream system can ask a question about a bond filing and receive a cited, structured answer with direct pointers back to source document sections.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Ingest bond filings from SEC EDGAR (full-text search API + EDGAR filing archives)
- [ ] Parse XBRL-tagged bond data into structured fields (coupon, maturity, covenants, etc.)
- [ ] Extract text from PDF filings with layout preservation
- [ ] Chunk documents with structure-awareness: section headers, semantic clauses, and tabular data handled separately
- [ ] Embed chunks and store in Chroma vector database (local)
- [ ] Python SDK that accepts natural language queries and returns cited answers
- [ ] RAG responses include both structured field extraction AND cited narrative answers
- [ ] Support tens of thousands of filings at scale (Chroma + local LLM via Ollama)
- [ ] All bond filing types in scope: prospectuses, offering memoranda, periodic reports, covenants

### Out of Scope

- Web UI / chat interface — Python SDK only in v1
- EDINET, ESMA, HKEX — deferred to v2 (SEC Edgar first)
- Cloud vector DB (Pinecone, Weaviate) — using local Chroma for v1
- External LLM API calls (OpenAI, Anthropic) — local model via Ollama only in v1
- Real-time / streaming ingestion — batch pipeline only

## Context

- The pipeline targets the regulatory fixed income data space: bond prospectuses, offering memoranda, and periodic reports filed with regulators globally.
- SEC EDGAR is the first source: it has well-documented APIs (EDGAR full-text search, company search, filing archives) and the largest corpus.
- XBRL is available for many structured filings but not all; PDF is the fallback and primary format for narrative/covenant sections.
- "Structure-aware chunking" means: (1) section-level chunking by document headers, (2) clause/provision-level semantic chunking, and (3) table-aware chunking that preserves tabular data integrity (pricing tables, covenant schedules).
- Local LLM via Ollama keeps data on-premises and avoids external API costs at scale.
- Chroma chosen for simplicity in v1; scale implications (tens of thousands of docs) should be validated against Chroma's limits and migration path to a more scalable store designed in.

## Constraints

- **LLM**: Local model via Ollama — no external LLM API calls (cost + data privacy)
- **Vector Store**: Chroma (local) — no managed cloud vector DB in v1
- **Data Source**: SEC EDGAR only in v1
- **Interface**: Python SDK only — no web UI, REST API, or CLI in v1
- **Filing Types**: All bond filings (prospectuses, offering docs, periodic reports, covenants)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SEC Edgar first | Largest corpus, best-documented APIs, establishes pipeline pattern for other regulators | — Pending |
| Local Chroma vector store | No infra complexity, good for dev, but may need migration at scale | — Pending |
| Local LLM via Ollama | Data privacy + cost control at tens-of-thousands scale | — Pending |
| Python SDK (not REST API) | Primary users are analysts/developers — library interface preferred over HTTP | — Pending |
| All three chunk types | Sections + clauses + tables each need different extraction logic | — Pending |
| XBRL preferred, PDF fallback | XBRL gives structured fields; PDF handles narrative and when XBRL unavailable | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-29 after initialization*
