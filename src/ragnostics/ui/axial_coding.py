"""Phase 2 — axial coding.

Open coding produced free-text observations. This phase turns them into a set of
actionable failure modes and assigns the observations to them.

Proposal and assignment are two separate model calls on purpose. The categories and
their definitions are reviewed and corrected first, and only then used as the rubric
for assignment, so the assignment is made against definitions a human approved rather
than against whatever the model had in mind while inventing them.

"None of the above" is always appended to the rubric. Open codes landing there are the
gap signal: they show where the category set fails to cover the material.
"""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit
from collections import Counter
from typing import Any

import pandas as pd
import streamlit as st

from ..adapters.base import Adapter
from ..config import ProjectConfig
from ..schema import Record
from ..storage import AnnotationStore

DEFAULT_MODEL = "gpt-4o-mini"

NONE_CODE = "None of the above"
NONE_DEFINITION = (
    "The observation fits none of the categories above. Assign this rather than "
    "forcing a poor fit, so the gap becomes visible."
)

CATEGORY_PROMPT = """You are analysing open codes from a qualitative evaluation of a
retrieval-augmented generation system.

Each open code below is a human observation on one question-answer-pair, written while
comparing the system answer against a reference answer and, where the benchmark
provides one, against the reference passage. Some observations were made
on records without ground truth.

Propose 4-6 axial categories that:
1. name a failure mode, not a description ("Answer Ignores Retrieved Evidence", not
"answer problems")
2. each name the one thing that would have to change to fix it
3. are NOT mutually exclusive, one observation may carry several
4. are collectively exhaustive over the observations below

Not every observation is a system failure. Some report a defect in the benchmark item
itself, for example a question too vague to have one correct source, or an answer that
is correct despite the intended source never being retrieved. Give those their own
category and set "fix_target" to the dataset, not to a system component. Do not force
them into a retrieval or generation failure mode.

"what_failed" is also the rubric a later step uses to assign open codes to categories,
so state in it which observations belong to this category and which do not, naming the
category to use instead where two are easily confused.

Return JSON only:
{
  "axial_codes": [
    {"code": "...", "what_failed": "...", "fix_target": "...", "examples": ["..."]}
  ]
}

OPEN CODES:
{{open_codes}}
"""

ASSIGN_PROMPT = """You are assigning one open code from a qualitative evaluation to a
fixed set of failure mode categories. Decide strictly against the definitions below.
Do not invent categories and do not rename them.

A single open code may belong to 1, 2, or more categories. Assign every category whose
definition the observation satisfies. If none of them fits, assign exactly
"None of the above" and nothing else.

CATEGORIES:
{{definitions}}

OPEN CODE:
{{open_code}}

Return JSON:
{"failure_modes": ["category name", "..."]}
"""

ASSIGN_BATCH_PROMPT = """You are assigning open codes from a qualitative evaluation to a
fixed set of failure mode categories. Decide strictly against the definitions below.
Do not invent categories and do not rename them.

A single open code may belong to 1, 2, or more categories. Assign every category whose
definition the observation satisfies. If none of them fits, assign exactly
"None of the above" and nothing else.

Return one entry for every open code, in the order given, using the open code text
verbatim.

CATEGORIES:
{{definitions}}

OPEN CODES:
{{open_codes}}

Return JSON only:
{
  "assignments": [
    {"open_code": "...", "failure_modes": ["..."]}
  ]
}
"""


def _show_prompt(label: str, text: str) -> None:
    """Show a prompt in a collapsed expander, as a code block with Streamlit's
    built-in copy control, so a long prompt does not fill the page."""
    with st.expander(label):
        st.code(text, language=None, wrap_lines=True)


def _collect(
    records: list[Record], store: AnnotationStore, ids: list[str]
) -> list[dict[str, Any]]:
    by_id = {r.id: r for r in records}
    rows: list[dict[str, Any]] = []
    for record_id in ids:
        record = by_id.get(record_id)
        if record is None:
            continue
        note = (store.get(record_id).get("note") or "").strip()
        if not note:
            continue
        rows.append({"source": record.source_type, "open_code": note, "id": record_id})
    return rows


def _sidebar_model(cfg: ProjectConfig) -> tuple[str, float, str | None]:
    st.sidebar.divider()
    st.sidebar.subheader("Model")
    model = st.sidebar.text_input("Model", value=cfg.llm.get("model", DEFAULT_MODEL))
    temperature = st.sidebar.slider(
        "Temperature", 0.0, 1.0, float(cfg.llm.get("temperature", 0.2)), 0.1
    )
    st.sidebar.caption(f"Endpoint: `{_endpoint_label(cfg.llm.get('base_url'))}`")
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        st.sidebar.caption("API key from `OPENAI_API_KEY`.")
    else:
        key = (
            st.sidebar.text_input(
                "OpenAI API key",
                type="password",
                value=st.session_state.get("axial_api_key", ""),
                help="Held in this session only, never written to the project file.",
            )
            or None
        )
        if key:
            st.session_state["axial_api_key"] = key
    return model, temperature, key


# Endpoints (keyed by base URL) that rejected ``response_format={"type": "json_object"}``.
# Module level so that it also works outside a Streamlit run.
_NO_JSON_FORMAT: dict[str, bool] = {}


def _endpoint_key(base_url: str | None) -> str:
    return base_url or os.environ.get("OPENAI_BASE_URL") or ""


def _endpoint_label(base_url: str | None) -> str:
    """Host of the endpoint in use, without credentials or path."""
    url = _endpoint_key(base_url)
    if not url:
        return "OpenAI default"
    parts = urlsplit(url)
    return parts.netloc.rpartition("@")[2] or url


def _first_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply (which may carry prose or fences)."""
    start = text.find("{")
    if start < 0:
        raise ValueError("model reply contains no JSON object")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("model reply is not a JSON object")
    return obj


def _call(
    prompt: str,
    model: str,
    temperature: float,
    key: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    """One model call that must return a JSON object.

    Without ``base_url`` the client's own ``OPENAI_BASE_URL`` handling applies.
    If the endpoint rejects the JSON response format, or the reply is not valid
    JSON, the call is retried once without it, and endpoints that reject the format
    are remembered so later calls skip the first attempt.
    """
    from openai import BadRequestError, OpenAI

    client = OpenAI(api_key=key, base_url=base_url) if base_url else OpenAI(api_key=key)
    endpoint = _endpoint_key(base_url)
    messages = [{"role": "user", "content": prompt}]

    if not _NO_JSON_FORMAT.get(endpoint):
        try:
            completion = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=messages,
            )
            return json.loads(completion.choices[0].message.content or "{}")
        except BadRequestError:
            _NO_JSON_FORMAT[endpoint] = True
        except json.JSONDecodeError:
            pass

    completion = client.chat.completions.create(
        model=model, temperature=temperature, messages=messages
    )
    return _first_json_object(completion.choices[0].message.content or "")


def _with_none(codebook: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rubric as used for assignment: the reviewed categories plus the escape."""
    if any(e.get("code") == NONE_CODE for e in codebook):
        return codebook
    return codebook + [{"code": NONE_CODE, "what_failed": NONE_DEFINITION}]


def _definitions_block(codebook: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {e.get('code', '')}: {e.get('what_failed') or '(no rubric given)'}"
        for e in _with_none(codebook)
    )


def _normalise_assignments(
    entries: Any, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Bring a mapping into the canonical shape, whatever form it arrived in.

    Models answer this task in three shapes: a list of objects carrying the open
    code, a flat list of category names positional to the open codes, or a list of
    lists for multilabel. Positional forms are aligned against ``rows`` in order,
    which is the order the batch prompt hands the open codes over in.

    Also runs on read, so a mapping stored in an older or odder shape renders
    instead of crashing the page.
    """
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if isinstance(entry, dict):
            modes = entry.get("failure_modes")
            modes = [modes] if isinstance(modes, str) else list(modes or [])
            fallback = rows[index] if index < len(rows) else {}
            out.append(
                {
                    "open_code": entry.get("open_code") or fallback.get("open_code", ""),
                    "source_type": entry.get("source_type") or fallback.get("source", ""),
                    "id": entry.get("id") or fallback.get("id", ""),
                    "failure_modes": [str(m) for m in modes],
                }
            )
            continue
        if index >= len(rows):
            continue  # more entries than open codes, nothing to align them to
        modes = entry if isinstance(entry, list) else [entry]
        out.append(
            {
                "open_code": rows[index]["open_code"],
                "source_type": rows[index]["source"],
                "id": rows[index]["id"],
                "failure_modes": [str(m) for m in modes],
            }
        )
    return out


def _metrics(store: AnnotationStore, sample: list[str], notes: int) -> None:
    coded = store.coded_count(sample)
    clean = sum(1 for i in sample if store.get(i).get("no_issues"))
    outside = sum(
        1 for i in store.data["annotations"] if i not in set(sample) and store.is_coded(i)
    )
    a, b, c, d = st.columns(4)
    a.metric("Sample coded", f"{coded}/{len(sample)}")
    b.metric("Open codes", notes, help="Records carrying a free-text observation")
    c.metric("No issues", clean, help="Coded as showing no failure")
    d.metric("Outside sample", outside, help="Annotated while browsing all records")
    if coded < len(sample):
        st.warning(
            f"{len(sample) - coded} sample records are still uncoded. Finish phase 1 "
            "first, otherwise the codebook is built on a partial sample."
        )


def render(
    records: list[Record], adapter: Adapter, store: AnnotationStore, cfg: ProjectConfig
) -> None:
    model, temperature, key = _sidebar_model(cfg)

    sample = store.sample_ids()
    rows = _collect(records, store, sample)
    st.subheader("Phase 2 · Axial coding")
    _metrics(store, sample, len(rows))
    if not rows:
        st.info("No free-text observations yet. Code some records in phase 1 first.")
        return

    frozen_at = store.codebook_frozen_at()
    frozen = bool(frozen_at)
    codebook = store.codebook()
    assignments = _normalise_assignments(store.assignments(), rows)

    # ---- 1 material ----------------------------------------------------
    with st.expander(f"1 · Material — {len(rows)} open codes", expanded=not codebook):
        st.dataframe(
            pd.DataFrame(rows)[["source", "open_code", "id"]],
            width="stretch",
            hide_index=True,
        )

    # ---- 2 propose categories -----------------------------------------
    st.markdown("##### 2 · Analyse open codes as axial codes")
    category_prompt = store.axial_prompt(CATEGORY_PROMPT)
    with st.expander("Category prompt — edit only if the grouping misses something"):
        edited_prompt = st.text_area(
            "Category prompt", value=category_prompt, height=320,
            label_visibility="collapsed",
        )
        if st.button("Save category prompt"):
            store.set_axial_prompt(edited_prompt)
            st.success("Saved.")
        category_prompt = edited_prompt

    block = "\n".join(f"- [{r['source']}] {r['open_code']}" for r in rows)
    rendered = category_prompt.replace("{{open_codes}}", block)

    run, copy, hint = st.columns([1, 1, 2])
    if run.button("Create Axial Codes", type="primary", disabled=not key or frozen):
        with st.spinner(f"Analysing {len(rows)} open codes ..."):
            try:
                result = _call(rendered, model, temperature, key, cfg.llm.get("base_url"))
            except Exception as exc:
                st.error(f"Model call failed: {exc}")
            else:
                store.set_codebook(result.get("axial_codes") or [])
                store.set_assignments([])
                st.rerun()
    with copy:
        _show_prompt("Full prompt (copy)", rendered)
    if not key:
        hint.caption("Set an API key in the sidebar to enable this.")
    elif codebook:
        hint.caption("Creating again replaces the categories and clears the assignments.")

    if not codebook:
        return

    # ---- 3 review categories ------------------------------------------
    st.markdown(f"##### 3 · Review — {len(codebook)} failure modes")
    st.caption(
        f"Edit the codebook directly as JSON. `{NONE_CODE}` is appended automatically "
        "for the assignment step and is not part of this document."
    )
    document = json.dumps(
        {"axial_codes": codebook, "assignments": assignments},
        indent=2,
        ensure_ascii=False,
    )
    draft = st.text_area(
        "Codebook JSON",
        value=document,
        height=420,
        label_visibility="collapsed",
        disabled=frozen,
        key="axial_json",
    )
    if not frozen and st.button("Save codebook"):
        try:
            parsed = json.loads(draft)
        except json.JSONDecodeError as exc:
            st.error(f"Not valid JSON: {exc}")
        else:
            # Only touch what the pasted document actually carries, so pasting a
            # mapping alone cannot wipe the categories it refers to.
            if "axial_codes" in parsed:
                store.set_codebook(parsed.get("axial_codes") or [])
            if "assignments" in parsed:
                store.set_assignments(
                    _normalise_assignments(parsed.get("assignments") or [], rows)
                )
            if "axial_codes" not in parsed and "assignments" not in parsed:
                st.error("Nothing to save: no `axial_codes` and no `assignments` key.")
            else:
                st.rerun()

    bad = [e.get("fix_target") for e in codebook if str(e.get("fix_target") or "").strip().lower() == "system"]
    if bad:
        st.warning(
            f"{len(bad)} categories use `system` as fix_target. That names no "
            "component, so the failure mode is not actionable."
        )

    missing = [e.get("code") for e in codebook if not (e.get("what_failed") or "").strip()]
    if missing:
        st.warning(
            "No `what_failed` yet for: " + ", ".join(f"`{m}`" for m in missing)
            + ". Step 4 assigns open codes against exactly that text."
        )

    # ---- 4 assign -------------------------------------------------------
    st.markdown("##### 4 · Use LLM to map open codes to refined axial codes")
    st.caption(
        "Each open code is judged on its own against the refined `what_failed` rubrics. "
        "This is also where you spot an open code that is not detailed enough: if it "
        f"carries too little to decide on, it lands in `{NONE_CODE}`."
    )
    assign_prompt = store.assign_prompt(ASSIGN_PROMPT)
    with st.expander("Assignment prompt"):
        edited_assign = st.text_area(
            "Assignment prompt", value=assign_prompt, height=240,
            label_visibility="collapsed",
        )
        if st.button("Save assignment prompt"):
            store.set_assign_prompt(edited_assign)
            st.success("Saved.")
        assign_prompt = edited_assign

    batch_prompt = store.assign_batch_prompt(ASSIGN_BATCH_PROMPT)
    with st.expander("Batch assignment prompt (the one the copy button hands over)"):
        edited_batch = st.text_area(
            "Batch assignment prompt", value=batch_prompt, height=240,
            label_visibility="collapsed",
        )
        if st.button("Save batch assignment prompt"):
            store.set_assign_batch_prompt(edited_batch)
            st.success("Saved.")
        batch_prompt = edited_batch

    current_names = [e.get("code") for e in codebook]
    if assignments and store.assignments_for() != current_names:
        st.warning(
            "The failure modes changed after these assignments were made. "
            "Re-run the assignment so the two match again."
        )

    go, copy_assign, note = st.columns([1, 1, 2])
    if go.button("Evaluate Axial Codes", type="primary", disabled=not key or frozen):
        definitions = _definitions_block(codebook)
        results: list[dict[str, Any]] = []
        progress = st.progress(0.0, text="Assigning ...")
        failed = 0
        for position, row in enumerate(rows, start=1):
            prompt = assign_prompt.replace("{{definitions}}", definitions).replace(
                "{{open_code}}", row["open_code"]
            )
            try:
                result = _call(prompt, model, temperature, key, cfg.llm.get("base_url"))
                modes = [str(m) for m in (result.get("failure_modes") or [])]
            except Exception:
                modes = []
                failed += 1
            results.append(
                {
                    "open_code": row["open_code"],
                    "source_type": row["source"],
                    "id": row["id"],
                    "failure_modes": modes,
                }
            )
            progress.progress(position / len(rows), text=f"Assigning {position}/{len(rows)} ...")
        progress.empty()
        store.set_assignments(results)
        store.set_assignments_for(current_names)
        if failed:
            st.error(f"{failed} of {len(rows)} calls failed and were left unassigned.")
        st.rerun()
    batch = batch_prompt.replace(
        "{{definitions}}", _definitions_block(codebook)
    ).replace("{{open_codes}}", "\n".join(f"- {r['open_code']}" for r in rows))
    with copy_assign:
        _show_prompt("Batch prompt (copy)", batch)
    note.caption(
        f"{len(rows)} calls in the tool, one per open code. The copied prompt is the "
        "batch variant for running the mapping on another model."
    )

    with st.expander("Paste a mapping produced elsewhere"):
        st.caption(
            "Accepts the batch response, either `{\"assignments\": [...]}` or a bare "
            "array. Categories are checked against the codebook; nothing else is "
            "touched."
        )
        pasted = st.text_area(
            "Mapping JSON", height=200, label_visibility="collapsed", key="paste_map"
        )
        if st.button("Store mapping", disabled=frozen):
            try:
                parsed = json.loads(pasted)
            except json.JSONDecodeError as exc:
                st.error(f"Not valid JSON: {exc}")
            else:
                entries = parsed.get("assignments") if isinstance(parsed, dict) else parsed
                if not isinstance(entries, list):
                    st.error("Expected an `assignments` array.")
                else:
                    entries = _normalise_assignments(entries, rows)
                    if len(entries) != len(rows):
                        st.warning(
                            f"{len(entries)} entries for {len(rows)} open codes. "
                            "A positional mapping must have one entry per open code."
                        )
                    known = {e.get("code") for e in codebook} | {NONE_CODE}
                    unknown = sorted(
                        {
                            mode
                            for entry in entries
                            for mode in (entry.get("failure_modes") or [])
                            if mode not in known
                        }
                    )
                    store.set_assignments(entries)
                    store.set_assignments_for(current_names)
                    if unknown:
                        st.warning(
                            "Stored, but these categories are not in the codebook: "
                            + ", ".join(f"`{u}`" for u in unknown)
                            + ". They will count as their own rows in the overview."
                        )
                    else:
                        st.rerun()

    if not assignments:
        return

    with st.expander(f"Assignments — {len(assignments)} open codes mapped"):
        st.dataframe(
            pd.DataFrame(assignments)[["source_type", "open_code", "failure_modes"]],
            width="stretch",
            hide_index=True,
        )

    # ---- 5 overview -----------------------------------------------------
    st.markdown("##### 5 · Overview")
    counts: Counter[str] = Counter()
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        for mode in assignment.get("failure_modes") or []:
            counts[mode] += 1
    unassigned = sum(1 for a in assignments if not (a.get("failure_modes") or []))

    listed = [
        {
            "failure_mode": entry.get("code"),
            "fix_target": entry.get("fix_target", ""),
            "open_codes": counts.get(entry.get("code"), 0),
        }
        for entry in _with_none(codebook)
    ]
    # A mapping pasted from elsewhere may name categories the codebook does not have.
    # Show them rather than dropping them, otherwise the totals silently disagree.
    known = {entry.get("code") for entry in _with_none(codebook)}
    listed += [
        {"failure_mode": name, "fix_target": "not in codebook", "open_codes": total}
        for name, total in counts.items()
        if name not in known
    ]
    overview = pd.DataFrame(listed).sort_values("open_codes", ascending=False)
    st.dataframe(overview, width="stretch", hide_index=True)
    st.bar_chart(overview.set_index("failure_mode")["open_codes"])

    gaps = counts.get(NONE_CODE, 0)
    if gaps:
        st.warning(
            f"{gaps} open codes landed in `{NONE_CODE}`. Read each one before acting: "
            "either the category set misses a failure mode, or the open code itself is "
            "too thin to classify and the record needs recoding in phase 1."
        )
    if unassigned:
        st.error(f"{unassigned} open codes came back with no category at all.")

    # ---- 6 finalise -----------------------------------------------------
    st.markdown("##### 6 · Finalise")
    if frozen:
        st.success(f"Frozen {frozen_at}.")
        if st.button("Unlock for further iteration"):
            store.freeze_codebook(False)
            st.rerun()
    else:
        st.caption(
            "Freezing records the codebook as final, so iteration stops somewhere explicit."
        )
        if st.button("Log final codebook", type="primary"):
            store.freeze_codebook(True)
            st.rerun()
