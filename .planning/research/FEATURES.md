# Features Research — Global Bond Intelligence

**Domain:** Bond / Fixed Income Regulatory Document Intelligence (RAG Pipeline)
**Researched:** 2026-05-29
**Overall confidence:** MEDIUM-HIGH (training data; no live web access during this session)

---

## Table Stakes (Must Have)

These are the minimum features users will expect. Missing any of these makes the product
feel incomplete compared to even a basic grep over EDGAR filings.

### Structured Field Extraction

- **Core bond terms extraction**: Coupon rate, coupon frequency, maturity date, principal
  amount, currency, ISIN/CUSIP/ticker, issuer name, governing law, ranking (senior/
  subordinated/secured). Every bond intelligence tool from Bloomberg DES to a simple
  screener surfaces these. An analyst cannot do anything without them.
  - Complexity: Medium (XBRL covers these when tagged; PDF extraction is the hard part)

- **Offering metadata**: Filing date, effective date, offering price, underwriter(s),
  use of proceeds (summary). These appear on the cover page of every 424B2/424B3/424B5
  prospectus. Analysts use them to reconstruct the deal timeline.
  - Complexity: Low-Medium (usually on page 1 of prospectus; high-confidence extraction)

- **Call/put schedule extraction**: Callable/putable bond provisions with exact dates and
  redemption prices. Critical for yield-to-call calculations. Bloomberg YAS screen treats
  this as mandatory. Without it, yield analytics cannot be performed correctly.
  - Complexity: Medium (tables in indenture supplements; requires table-aware chunking)

- **Credit rating extraction**: Moody's, S&P, Fitch ratings at time of issuance (often
  appear in cover page and risk factors). Not real-time (that requires paid data feeds),
  but at-issuance rating is in the filing itself.
  - Complexity: Low (pattern-match; ratings are standardized strings)

### Document Navigation and Retrieval

- **Section-level retrieval**: Ability to answer "show me the covenant section" or "what
  does the indenture say about change of control?" by routing to the correct document
  section. Analysts using EDGAR directly have to scroll 200-page PDFs manually; this is
  the core RAG value proposition.
  - Complexity: Medium (requires accurate section header detection in chunking)

- **Filing type awareness**: The system must distinguish between prospectuses (424B*),
  offering memoranda, indenture supplements, 8-K bond-related disclosures, ABS filings
  (ABS-EE), and periodic reports. Conflating these returns wrong context — a covenant
  query against a 10-K instead of the indenture produces misleading answers.
  - Complexity: Medium (EDGAR filing type taxonomy is well-defined; parser must use it)

- **Multi-document query**: A single bond deal often has multiple filings (preliminary
  prospectus, final prospectus, indenture, supplement, 8-K announcing pricing). Queries
  must be resolvable across the document set for that deal, not just single files.
  - Complexity: High (requires deal-level entity linking across filing accession numbers)

- **Filing version tracking**: EDGAR has amended filings (S-1/A, 424B3 superseding
  424B2). Users must always query the most current version of a document. Serving stale
  data from a superseded filing is a compliance risk.
  - Complexity: Medium (EDGAR API exposes amendment chains; must be modeled in metadata)

### Citation and Attribution

- **Verbatim source passage with citation**: Every answer must include the exact quoted
  passage from the source document, the filing accession number, document section name,
  and page reference. This is non-negotiable for compliance-aware users (sell-side
  research, buy-side compliance). Without citations, the output cannot be used in any
  investment decision workflow — it becomes unverifiable and therefore useless.
  - Complexity: Medium (RAG architecture naturally supports this; metadata schema must
    be designed carefully from the start)

- **Filing accession number linkback**: Citations must link directly to the EDGAR filing
  URL (https://www.sec.gov/Archives/edgar/data/{CIK}/{accession}/...). Analysts verify
  source material as standard practice.
  - Complexity: Low (EDGAR URLs are deterministic from accession number)

- **Section and page-level granularity**: "Section 4.2, page 47" is more useful than
  "somewhere in the document." Bloomberg's document viewer shows this; analysts expect it.
  - Complexity: Medium-High (PDF page tracking through extraction pipeline)

### Query Behaviors

- **Covenant query**: "What are the negative covenants on this bond?" is the single
  most common analyst question about bond indentures. Financial covenant analysis
  (debt incurrence test, restricted payments, change of control, cross-default) must
  be addressable by the system. This is what makes fixed income due diligence painful
  manually.
  - Complexity: High (covenants are scattered across indenture sections; requires
    multi-chunk synthesis)

- **Comparison query across filings**: "How does this issuer's change-of-control
  provision compare to its 2021 bond?" Analysts routinely do this to track covenant
  drift across an issuer's capital structure.
  - Complexity: High (requires entity-level indexing by issuer + deal date)

- **Null/not-found handling**: If a provision does not exist in the filing (e.g.,
  asking for a put option on a non-putable bond), the system must confidently return
  "not found in this document" rather than hallucinating an answer. This is a hard
  correctness requirement in financial contexts.
  - Complexity: Medium (retrieval confidence thresholds + abstention logic)

### Data Freshness

- **Incremental ingestion of new EDGAR filings**: Analysts need access to filings within
  hours of submission. EDGAR's full-text search API and RSS feeds make this achievable.
  A system that only holds historical data ages out quickly.
  - Complexity: Medium (EDGAR provides daily index files and real-time RSS; polling
    pipeline is well-understood)

- **Ingestion timestamp metadata**: Every chunk must carry the filing date AND the date
  the chunk was ingested. Queries against "recent" filings depend on this.
  - Complexity: Low (metadata field; must be designed in from day one)

---

## Differentiators (Competitive Advantage)

These features are not available in general-purpose tools and set this product apart
from both Bloomberg (which is expensive and does not do RAG over full indenture text)
and raw EDGAR search (which has no intelligence layer).

### Extraction Intelligence

- **Covenant clause decomposition**: Rather than returning the whole covenant section
  as a blob, decompose it into typed clauses: debt incurrence test (with ratio), basket
  sizes, carve-outs, grower baskets, restricted payment capacity. FactSet Covenant Review
  and Covenant Review (now Moody's Analytics CovLite) charge premium prices for this.
  Doing it via LLM extraction from the source text is a genuine differentiator.
  - Complexity: High

- **Cross-reference resolution**: Bond indentures are full of references like "as defined
  in Section 1.01" or "subject to the exceptions in clause (iv) of the definition of
  Permitted Debt." Resolving these cross-references so the answer is self-contained is
  very hard manually and rarely done by any automated tool.
  - Complexity: Very High (recursive chunk resolution; careful not to loop)

- **Pricing term sheet extraction**: For structured products (CLOs, CMBS, ABS), term
  sheets contain tranche-level data: class, principal balance, coupon, WAL, rating,
  subordination level. No open-source tool extracts this reliably from PDF term sheets.
  - Complexity: High (table extraction in non-standard layouts)

- **Change detection between filing versions**: "What changed between the preliminary
  and final prospectus?" Automatic diff of material provisions between filing versions
  (pricing, covenant changes, risk factor updates) is high-value for analysts who
  monitor deal syndication.
  - Complexity: High (requires version-aware document alignment)

### Query Intelligence

- **Multi-hop reasoning over indenture cross-references**: A user asks "what is the
  maximum amount the issuer can pay as a restricted payment?" The answer requires
  reading the restricted payments covenant, resolving the "Restricted Payment Capacity"
  basket definition, and reading the grower basket formula — three separate sections.
  Current RAG pipelines fail at this without explicit multi-hop support.
  - Complexity: Very High

- **Structured answer schema alongside narrative**: Return both a JSON-serializable
  structured extract (machine-readable: `{"coupon": 5.25, "maturity": "2031-03-15",
  "call_schedule": [...]}`) and a natural language narrative answer with citations.
  This serves programmatic downstream consumers (portfolio systems, risk engines) that
  cannot consume prose.
  - Complexity: Medium (schema definition is the hard part; generation is straightforward
    once schema is defined)

- **Confidence scoring per extracted field**: "Coupon: 5.25% [HIGH confidence — XBRL
  tagged]" vs "Coupon: 5.25% [MEDIUM confidence — PDF pattern match]". Bloomberg
  and Refinitiv do not expose extraction confidence. This is trust-building for
  analysts who need to know when to verify manually.
  - Complexity: Medium

- **Negative covenant screening**: "Show me all bonds in the corpus where the debt
  incurrence covenant uses a Fixed Charge Coverage Ratio test below 2.0x." This is
  a portfolio-level screening query across all ingested filings — a screener Bloomberg
  does not offer for covenant terms (only for financial metrics from periodic reports).
  - Complexity: High (requires structured covenant field extraction at corpus scale)

### Data and Attribution

- **Provenance chain**: For every extracted field, the system can return not just the
  source citation but the full provenance chain: raw text passage → chunk ID → document
  section → filing accession → CIK → issuer. This enables audit trails for compliance
  purposes.
  - Complexity: Medium (metadata schema design; no new ML needed)

- **XBRL vs PDF source flagging**: Distinguish fields extracted from XBRL tags (higher
  confidence, machine-readable) from fields extracted via PDF/LLM (lower confidence,
  needs review). Analysts need to know which fields to trust without verification.
  - Complexity: Low (tag the extraction method in metadata at ingestion time)

- **Multi-regulator harmonization** (v2 scope, design for it now): When EDINET/ESMA
  filings are added, the same field ("maturity date") may come from different XBRL
  taxonomies (US-GAAP vs IFRS vs ESMA ESEF). Designing a harmonized internal schema
  now prevents a painful migration later.
  - Complexity: High (schema design decision; low cost if done at the start)

### Developer / Programmatic Experience

- **Typed Python SDK return objects**: Instead of raw dict responses, return Pydantic
  models (`BondTerm`, `CovenantClause`, `RAGAnswer`) so downstream code can rely on
  type-safe field access. This is the differentiator for programmatic consumers.
  - Complexity: Low-Medium (schema definition; Pydantic generation)

- **Async query support**: Corpus-level screening queries (scan all 50,000 filings for
  a covenant pattern) must be non-blocking. Synchronous-only SDK is a friction point
  for pipeline integrations.
  - Complexity: Medium

- **Batch ingestion API with progress reporting**: For initial corpus loads and
  incremental updates, analysts/engineers need to know ingestion status per filing
  (success, failure reason, fields extracted count). Silent failures are dangerous
  when the corpus is the source of truth.
  - Complexity: Medium

---

## Anti-Features (Scope Traps for v1)

These are features that seem related but would consume disproportionate engineering
effort for v1 with little validated return. Defer deliberately.

- **Real-time bond pricing / BVAL equivalent**: Bloomberg BVAL is a pricing service
  backed by contributed dealer quotes and complex matrix pricing models. Building even
  a shadow of this requires market data feeds, pricing models, and regulatory licensing.
  Completely out of scope — we are a document intelligence tool, not a pricing service.

- **Credit rating predictions / scoring models**: Training an ML model to predict
  credit quality from document text (a la Moody's or S&P internal models) requires
  labeled training data, model validation, and regulatory treatment of the output.
  This is a multi-year research project, not a v1 feature.

- **Portfolio analytics / DV01 / duration calculations**: Yield analytics require
  market data (yield curves, swap rates) and financial math libraries (QuantLib).
  These are downstream uses of bond data, not document intelligence. Provide the
  structured data; let the user's analytics layer do the math.

- **Web UI / chat interface**: Deferred per PROJECT.md. A web interface introduces
  auth, hosting, session management, and UX engineering with no clear v1 user need.
  Python SDK first; validate what analysts actually query before building a UI.

- **REST API / microservice packaging**: Wrapping the SDK in a FastAPI service is
  straightforward later but adds deployment complexity now. The SDK-first approach
  lets the API contract stabilize before it is exposed externally.

- **Real-time streaming ingestion (webhooks / Kafka)**: EDGAR's filing volume does
  not justify streaming infrastructure in v1. Polling the daily index every 15-60
  minutes is sufficient. Streaming can be added when proven necessary.

- **Alerting and monitoring UI**: "Alert me when a new filing matches criteria X"
  is a useful feature but requires notification infrastructure (email, Slack, webhooks).
  Defer; the polling pipeline can write to a queue that a future alerting system reads.

- **Entity resolution across issuers** (e.g., parent-subsidiary hierarchies): Knowing
  that "Apple Inc." and "Apple Inc. (Ireland)" are related entities requires a corporate
  hierarchy database (S&P Capital IQ, Bureau van Dijk). This is sourced data, not
  document intelligence — too expensive to build from scratch in v1.

- **Regulatory compliance report generation**: Generating FINRA/MiFID-compliant research
  reports from query results involves legal/compliance sign-off beyond engineering.
  Generate cited raw answers; let the human analyst write the compliant report.

- **Non-English document translation**: EDINET (Japanese) and ESMA (multi-language)
  filings require translation pipelines before extraction. Deferred to v2 with
  those data sources.

- **Historical pricing tables reconstruction**: Some prospectuses include historical
  comparable bond pricing. Extracting and normalizing this into time series is
  extremely noisy from PDF and of marginal value until corpus scale justifies it.

---

## Feature Dependencies

These dependencies must be respected in phase ordering:

- **Structured field extraction** requires **filing type classification** — you cannot
  correctly extract a coupon from a 10-K narrative the same way you extract it from
  a 424B5 prospectus cover page.

- **Covenant query** requires **section-level chunking** — flat chunking by token
  count destroys covenant clause boundaries and makes synthesis impossible.

- **Multi-document query** requires **deal-level entity linking** — you must first
  group filings by issuer + deal before querying across them.

- **Comparison query across filings** requires **multi-document query** to be stable.

- **Covenant clause decomposition** requires **cross-reference resolution** to be
  meaningful — otherwise the extracted clause is incomplete.

- **Negative covenant screening** (corpus-level) requires **structured field
  extraction** at ingestion time (not query time) — you cannot scan 50,000 filings
  at query time with an LLM.

- **XBRL vs PDF source flagging** requires **extraction pipeline metadata tracking**
  — must be built into the ingestion pipeline, not retrofitted.

- **Null/not-found handling** requires **retrieval confidence thresholds** — the
  abstention logic depends on having a calibrated similarity score.

- **Incremental ingestion** requires **filing version tracking** (amendment chain
  awareness) — otherwise incremental runs re-ingest superseded filings and
  produce stale answers.

- **Typed Python SDK return objects** (Pydantic models) requires **structured answer
  schema** to be finalized — schema changes break downstream consumers.

---

## Confidence Notes

| Area | Confidence | Basis |
|------|------------|-------|
| SEC EDGAR filing taxonomy | HIGH | Well-documented public knowledge |
| Bloomberg/Refinitiv feature set | MEDIUM | Training data; not verified against live product docs in this session |
| Open-source RAG project patterns | MEDIUM | Training data through Aug 2025; ecosystem moves fast |
| Analyst workflow patterns | MEDIUM-HIGH | CFA curriculum + sell-side research workflow literature |
| Covenant analysis requirements | HIGH | Standard fixed income practice; well-documented in credit training materials |
| Citation/attribution standards | HIGH | Sell-side compliance requirements are well-known |

> Note: WebSearch and WebFetch were unavailable in this research session. Findings are
> based on training data (knowledge cutoff August 2025). Recommend validating the
> Bloomberg/Refinitiv feature set comparisons against current product documentation
> before finalizing the roadmap.
