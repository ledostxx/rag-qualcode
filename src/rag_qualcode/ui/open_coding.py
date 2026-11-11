"""Phase 1 — Open coding.

Single-trace focus view: one record at a time with prev/next navigation and a
pure free-text observation field pinned to the bottom edge, with per-record
persistence. No code picker — this is inductive open coding (D-004); code
emergence is deferred to LLM-assisted grouping in the axial phase. Heavy traces
load lazily.
"""

from __future__ import annotations

import streamlit as st

from ..adapters.base import Adapter
from ..config import ProjectConfig
from ..sampling import stratified_sample
from ..schema import Record
from ..storage import AnnotationStore
from . import components


def _save_current(store: AnnotationStore, record_id: str) -> None:
    store.set(
        record_id,
        codes=list(st.session_state.get(f"codes::{record_id}", [])),
        note=str(st.session_state.get(f"note::{record_id}", "")),
        no_issues=bool(st.session_state.get(f"noissues::{record_id}", False)),
    )


def _inject_layout_css() -> None:
    """Keep the coding panel permanently visible without viewport-pinning tricks:
    the record content scrolls inside its own fixed-height pane, so the page never
    grows past the viewport and the coding panel stays anchored just below it.
    Robust to sidebar open/closed and to window height (unlike position:sticky,
    which Streamlit's tightly-wrapped containers defeat). Both panes are cards so
    unavoidable whitespace (e.g. the shorter left column) reads as intentional."""
    st.markdown(
        """
        <style>
        /* everything (nav + reading card + coding card) fits in one viewport;
           only the reading pane scrolls internally. No page scroll. */
        section[data-testid="stMain"] { overflow: hidden; }
        /* trim Streamlit's oversized default top padding */
        [data-testid="stMainBlockContainer"] {
            padding-top: 3.75rem;
            padding-bottom: 0.75rem;
        }
        /* scrollable reading pane — one card holding question / answer / trace.
           Height reserves room for the nav row above and the coding card below;
           tuned so the whole page fits without a page scrollbar. */
        .st-key-record_pane {
            max-height: calc(100vh - 22rem);
            overflow-y: auto;
            padding: 0.9rem 1.25rem;
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 0.75rem;
            background: rgba(130, 130, 150, 0.03);
        }
        /* coding card — the primary action, a clean bordered panel */
        .st-key-coding_bar {
            background: transparent; /* follows the Streamlit theme, light or dark */
            border: 1px solid rgba(128, 128, 128, 0.4);
            border-radius: 0.75rem;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
            padding: 0.7rem 1.25rem 0.5rem;
            margin-top: 0.75rem;
        }
        .st-key-coding_bar textarea { font-size: 0.9rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _sidebar_filters(
    records: list[Record], store: AnnotationStore, cfg: ProjectConfig
) -> list[Record]:
    st.sidebar.divider()
    st.sidebar.subheader("Open coding")

    sample_ids = store.sample_ids()
    if not sample_ids:
        st.sidebar.caption(
            f"No sample drawn yet. Stratified draw: {cfg.sample.per_source_type} per "
            f"source type, seed {cfg.sample.seed}."
        )
        if st.sidebar.button("Draw stratified sample", type="primary"):
            drawn = stratified_sample(records, cfg.sample.per_source_type, cfg.sample.seed)
            store.set_sample(drawn)
            # The scope radio keeps its old value across reruns because only its
            # options change, not its key. Select the new sample explicitly.
            st.session_state["oc_scope"] = f"Sample ({len(store.sample_ids())})"
            st.rerun()

    scope_options = ["All records"]
    if sample_ids:
        scope_options.insert(0, f"Sample ({len(sample_ids)})")
    scope = st.sidebar.radio("Scope", scope_options, key="oc_scope")

    pool = records
    if scope.startswith("Sample"):
        in_sample = set(sample_ids)
        pool = [r for r in records if r.id in in_sample]

    source_types = sorted({r.source_type for r in records})
    chosen_types = st.sidebar.multiselect("Source type", source_types, default=source_types)
    pool = [r for r in pool if r.source_type in chosen_types]

    coded_filter = st.sidebar.radio("Coding status", ["All", "Uncoded", "Coded"], key="oc_coded")
    if coded_filter == "Uncoded":
        pool = [r for r in pool if not store.is_coded(r.id)]
    elif coded_filter == "Coded":
        pool = [r for r in pool if store.is_coded(r.id)]

    scope_ids = [r.id for r in (records if scope == "All records" else pool)]
    if sample_ids:
        st.sidebar.progress(
            store.coded_count(sample_ids) / max(len(sample_ids), 1),
            text=f"Sample coded: {store.coded_count(sample_ids)}/{len(sample_ids)}",
        )
    st.sidebar.caption(f"Coded {store.coded_count(scope_ids)}/{len(scope_ids)} in scope")
    return pool


def _navigation(pool: list[Record], store: AnnotationStore) -> Record:
    pos = int(st.session_state.get("oc_pos", 0))

    # Prev pinned far left, Next pinned far right (matches the ← / → shortcuts).
    # Labels carry no arrow: Streamlit appends the shortcut hint to the button.
    # the uncoded jump and the record picker sit between them.
    col_prev, col_uncoded, col_jump, col_next = st.columns([1.1, 1.7, 5, 1.1])
    if col_prev.button("Prev", disabled=pos <= 0, width="stretch", shortcut="Left"):
        pos -= 1
    if col_uncoded.button("Next uncoded ↷", width="stretch"):
        for offset in range(1, len(pool) + 1):
            candidate = (pos + offset) % len(pool)
            if not store.is_coded(pool[candidate].id):
                pos = candidate
                break
    if col_next.button(
        "Next", disabled=pos >= len(pool) - 1, width="stretch", shortcut="Right"
    ):
        pos += 1

    pos = max(0, min(pos, len(pool) - 1))

    def _label(r: Record) -> str:
        mark = "✓" if store.is_coded(r.id) else "·"
        return f"{mark} [{r.source_type}] {r.question[:70]}"

    selected = col_jump.selectbox(
        "Jump to record",
        pool,
        index=pos,
        format_func=_label,
        label_visibility="collapsed",
    )
    if selected.id != pool[pos].id:
        pos = pool.index(selected)

    st.session_state["oc_pos"] = pos
    st.caption(f"Record {pos + 1} of {len(pool)} — id `{pool[pos].id}` · ← / → to navigate")
    return pool[pos]


def _render_record(record: Record, adapter: Adapter) -> None:
    # Blind the coder to the adapter's evaluative metrics during open coding so
    # they don't anchor the reading; they stay in the data for later.
    # The trace is loaded once per view, before the badges are drawn, because the
    # adapter may derive signals from it. It is cached in session state: traces are
    # large and a per-record on-demand load is cheap that way.
    trace_key = f"trace::{record.id}"
    if trace_key not in st.session_state:
        st.session_state[trace_key] = adapter.load_trace(record)
    trace = st.session_state[trace_key]

    components.render_header(
        record,
        {**record.signals, **adapter.trace_signals(record, trace)},
        adapter.signal_level,
        show_status=False,
        hide_metrics=adapter.blind_metrics,
    )

    left, right = st.columns(2)
    with left:
        st.markdown("##### Question")
        st.markdown(record.question)
        if record.reference_answer:
            st.markdown("##### Reference answer")
            st.markdown(record.reference_answer)
        if record.ground_truth and record.ground_truth.chunk_text:
            with st.expander("Ground-truth chunk"):
                if record.ground_truth.title:
                    st.markdown(f"**{record.ground_truth.title}**")
                st.markdown(record.ground_truth.chunk_text)
                if record.ground_truth.url:
                    st.caption(record.ground_truth.url)
    with right:
        st.markdown("##### System answer")
        st.markdown(record.system_answer)
        if record.citations:
            st.caption("Citations: " + ", ".join(record.citations))

    chunk_texts = adapter.chunk_texts(trace)

    for event in record.retrieval_events:
        with st.expander(f"Retrieved sources — {event.channel} ({len(event.sources)})"):
            components.render_retrieval_event(event, chunk_texts)

    with st.expander("Full trace (raw)"):
        if trace is None:
            st.caption("No trace available for this record.")
        else:
            components.render_trace(trace)

    if any(v for v in record.extras.values()):
        with st.expander("System-specific extras"):
            st.json({k: v for k, v in record.extras.items() if v}, expanded=False)


def _coding_panel(record: Record, store: AnnotationStore) -> None:
    """Pure inductive open coding (D-004): free-text observations only. No code
    picker — code emergence is deferred to LLM-assisted grouping in the axial
    phase. Rendered just below the scrollable record pane so it stays visible
    without scrolling the page."""
    ann = store.get(record.id)
    note_key = f"note::{record.id}"
    noissues_key = f"noissues::{record.id}"
    if note_key not in st.session_state:
        st.session_state[note_key] = ann["note"]
    if noissues_key not in st.session_state:
        st.session_state[noissues_key] = ann["no_issues"]

    with st.container(key="coding_bar"):
        st.markdown("**Open coding** — free-text observations")
        note_col, flag_col = st.columns([6, 1])
        note_col.text_area(
            "Observations",
            key=note_key,
            on_change=_save_current,
            args=(store, record.id),
            placeholder="Read the trace openly and note what happened in your own words — "
            "retrieval, grounding, generation. Codes come later, in the axial phase.",
            height=72,
            label_visibility="collapsed",
        )
        note_col.caption("Saved when you click outside the field or press Ctrl+Enter.")
        flag_col.checkbox(
            "No issues",
            key=noissues_key,
            on_change=_save_current,
            args=(store, record.id),
        )


def _inject_completed_overlay(total: int, notes: int) -> None:
    """Blur the reading pane and state plainly that the sample is fully coded.

    Phase 1 ends silently otherwise: the coder reaches the last record with no
    signal that the pass is done and nothing pointing at the next phase.
    """
    st.markdown(
        f"""
        <style>
        .st-key-record_pane {{
            filter: blur(6px);
            pointer-events: none;
            user-select: none;
        }}
        .qc-complete {{
            position: fixed;
            inset: 0;
            z-index: 999;
            display: flex;
            align-items: center;
            justify-content: center;
            pointer-events: none;
        }}
        .qc-complete-card {{
            text-align: center;
            padding: 2rem 3.25rem;
            border-radius: 1rem;
            background: rgba(18, 20, 26, 0.88);
            color: #fff;
            box-shadow: 0 12px 44px rgba(0, 0, 0, 0.38);
            animation: qc-pop 0.45s cubic-bezier(0.2, 0.8, 0.2, 1) both;
        }}
        .qc-complete-card h1 {{
            margin: 0;
            font-size: 2.6rem;
            letter-spacing: 0.2em;
            font-weight: 600;
        }}
        .qc-complete-card p {{
            margin: 0.6rem 0 0;
            opacity: 0.82;
        }}
        @keyframes qc-pop {{
            from {{ opacity: 0; transform: scale(0.92); }}
            to {{ opacity: 1; transform: none; }}
        }}
        </style>
        <div class="qc-complete"><div class="qc-complete-card">
          <h1>COMPLETED</h1>
          <p>{total} of {total} sample records coded · {notes} open codes</p>
          <p>Continue in phase 2 · Axial coding</p>
        </div></div>
        """,
        unsafe_allow_html=True,
    )


def render(
    records: list[Record], adapter: Adapter, store: AnnotationStore, cfg: ProjectConfig
) -> None:
    _inject_layout_css()
    pool = _sidebar_filters(records, store, cfg)
    if not pool:
        st.info("No records match the current filters.")
        return

    sample = store.sample_ids()
    finished = bool(sample) and store.coded_count(sample) == len(sample)
    show_overlay = finished and not st.session_state.get("oc_complete_dismissed")
    if show_overlay:
        notes = sum(1 for i in sample if (store.get(i).get("note") or "").strip())
        _inject_completed_overlay(len(sample), notes)

    record = _navigation(pool, store)
    with st.container(key="record_pane"):
        _render_record(record, adapter)

    if show_overlay:
        # The overlay is pointer-events:none so the sidebar stays usable; this is
        # the way back into the records without leaving phase 1.
        if st.button("Keep reviewing records", width="stretch"):
            st.session_state["oc_complete_dismissed"] = True
            st.rerun()
    else:
        _coding_panel(record, store)
