import streamlit as st

# Backend import — graceful fallback before Phase 4 is complete
try:
    from bond_intelligence import BondIntelligence
    from bond_intelligence.models import QueryResponse
    _BACKEND_READY = True
except ImportError:
    _BACKEND_READY = False

st.set_page_config(
    page_title="Global Bond Intelligence",
    page_icon="📊",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Configuration")

    st.subheader("Model")
    ollama_model = st.selectbox(
        "Local LLM",
        ["llama3.1:8b", "qwen2.5:14b"],
        help="Model served by Ollama for narrative answers",
    )

    st.subheader("Retrieval")
    top_k = st.slider("Top-K chunks", min_value=3, max_value=20, value=5)
    hybrid = st.toggle("Hybrid retrieval (dense + BM25)", value=True)

    st.divider()
    st.subheader("Corpus")
    if _BACKEND_READY:
        try:
            bi = BondIntelligence(model=ollama_model)
            stats = bi.corpus_stats()
            st.metric("Filings indexed", stats.get("filing_count", 0))
            st.metric("Chunks in vector DB", stats.get("chunk_count", 0))
        except Exception as e:
            st.warning(f"Backend error: {e}")
    else:
        st.info("Backend not yet available. Complete Phases 1–4 to connect.")
        st.metric("Filings indexed", "—")
        st.metric("Chunks in vector DB", "—")

    st.divider()
    st.caption("Local-only · No external APIs · Chroma + Ollama")

# ── Main ─────────────────────────────────────────────────────────────────────

st.title("📊 Global Bond Intelligence")
st.caption("Ask questions about SEC EDGAR bond filings and get cited, structured answers.")

query = st.text_input(
    "Query",
    placeholder="e.g. What is the coupon rate and negative pledge covenant for CUSIP 123456789?",
    label_visibility="collapsed",
)

run = st.button("Search", type="primary", disabled=not _BACKEND_READY)

if not _BACKEND_READY:
    st.info(
        "**Backend not connected.** "
        "The query engine will be available after Phases 1–4 are complete. "
        "Run `python -m bond_intelligence.pipeline` to ingest and index filings first."
    )

if run and query and _BACKEND_READY:
    with st.spinner("Retrieving…"):
        try:
            bi = BondIntelligence(model=ollama_model)
            response: QueryResponse = bi.query(query, top_k=top_k, hybrid=hybrid)
        except Exception as e:
            st.error(f"Query failed: {e}")
            st.stop()

    # ── Structured bond terms (XBRL direct — no LLM) ─────────────────────
    st.subheader("Structured fields")
    terms = response.bond_terms
    cols = st.columns(4)
    cols[0].metric("Coupon rate", terms.coupon_rate or "—")
    cols[1].metric("Maturity", str(terms.maturity_date) if terms.maturity_date else "—")
    cols[2].metric("Principal", terms.principal_amount or "—")
    cols[3].metric("CUSIP", terms.cusip or "—")

    extra_cols = st.columns(4)
    extra_cols[0].metric("ISIN", terms.isin or "—")
    extra_cols[1].metric("Issuer", terms.issuer_name or "—")
    extra_cols[2].metric("Debt ranking", terms.debt_ranking or "—")
    extra_cols[3].metric("Governing law", terms.governing_law or "—")

    confidence_color = "green" if response.source_confidence == "xbrl_direct" else "orange"
    st.markdown(
        f"**Source confidence:** :{confidence_color}[{response.source_confidence}]"
    )

    st.divider()

    # ── Narrative answer + citations (RAG) ───────────────────────────────
    st.subheader("Answer")
    st.markdown(response.answer)

    if response.citations:
        st.subheader(f"Citations ({len(response.citations)})")
        for i, citation in enumerate(response.citations, 1):
            with st.expander(f"{i}. {citation.section_title} — {citation.accession_number}"):
                st.markdown(f"> {citation.verbatim_passage}")
                st.caption(
                    f"Page {citation.page_number} · "
                    f"[View on EDGAR]({citation.edgar_url})"
                )
