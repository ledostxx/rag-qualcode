# Record format

The app shows one format, the record. An adapter converts one system's logs into records, and the app knows nothing else about the system. The fields and their exact meaning are documented in the docstrings of [src/rag_qualcode/schema.py](../src/rag_qualcode/schema.py), which is the single source. This page explains the concepts and where the app shows each part. It does not repeat the field descriptions.

## Record

A `Record` is one benchmark question with the system's answer and everything the app can show about it. Its fields are `id`, `source_type`, `question`, `system_answer`, `reference_answer`, `status`, `retrieval_events`, `citations`, `metrics`, `signals`, `ground_truth` and `extras`.

- `id` must be unique and not empty. The annotation file refers to records by it.
- `source_type` is the kind of source the question was made from. The sample for open coding is stratified by it, and the sidebar filters by it.
- `question` must not be empty. `system_answer` and `reference_answer` appear side by side in the main view. `reference_answer` may be missing.
- `status` is the outcome the system or test harness reported. The open coding view does not show it, so the coder is not influenced by it. The adapter's own `signals` are shown instead.
- `retrieval_events` is the list of retrieval steps. `citations` are the sources the answer names, shown under the answer.
- `ground_truth` is optional. When it has `chunk_text`, the view has a "Ground-truth chunk" section.
- `extras` is for anything that has no field. The view shows it as a collapsible "System-specific extras" JSON section. Empty values are left out.

`qualcode validate` rejects a list of records that is empty, and records with an empty or duplicate `id` or an empty `question`.

## Retrieval event and source

A `RetrievalEvent` is one retrieval step: a tool call, an API query or one fused retrieval pass. It has a `channel` (the name of the retriever or tool), the `query` that was sent, its `sources` and `extras`. A system that retrieves in several ways gives one event per way. A system that retrieves once gives one event.

Each event appears as a collapsed section "Retrieved sources" with the channel name and the number of sources. Inside, a table lists the sources in the order the system delivered them, and a card per source shows its text.

A `RetrievedSource` has `id`, `title`, `snippet`, `score`, `rank`, `url`, `doc_type` and `extras`. The card shows the full text of the source when the adapter's `chunk_texts` hook returns text for its `id`, and the `snippet` otherwise. So `id` must match the keys that `chunk_texts` returns. The table shows the position in the list next to `rank`, which is the rank the system reported. They differ when the system reorders its candidates.

## Ground truth

`GroundTruth` is what the benchmark says the right answer source is: `chunk_text` (the passage that answers the question), `title`, `url`, `expected_channel` (which retriever should have found it, if the benchmark says) and `extras`. The app shows the passage, title and URL in the "Ground-truth chunk" section. The other fields are not shown by the generic view, but adapters can use them in diagnostics. A record may have no ground truth. Then `ground_truth` is `None`, and the adapter should not invent a signal about it.

## Signals, metrics and badges

**Signals** are short text diagnostics, shown as coloured badges in the line at the top of the record, for example `evidence: hit`. They come from two places:

- `Record.signals`, set when the adapter loads the records. These are cheap to compute and exist for every record.
- The adapter's `trace_signals(record, trace)` hook, called each time a record is shown, after its trace is loaded. Use it for diagnostics that need the trace.

Both are merged into one set of badges. When both return the same key, the `trace_signals` value wins, and each key is shown once.

**Colour** is decided by the adapter's `signal_level(key, value)` hook. It returns `"good"` (green), `"warn"` (orange), `"bad"` (red) or `"neutral"` (grey). If it returns `None`, which is the default, the app falls back to a word list on the whole lower-cased value:

| Colour | Values |
|---|---|
| green | hit, ok, correct, success, cited, answer |
| orange | partial, warning, decline, follow-up |
| red | miss, error, wrong, failure, failed, timeout |
| grey | anything else |

`neutral` forces grey even for a word on the list.

**Metrics** are numeric per-record values such as latency or a similarity score. They appear in small text under the badges. Names listed in the adapter's `blind_metrics` are hidden during open coding, so an automatic score does not influence the coder. They stay in the data. `qualcode validate` warns if a name in `blind_metrics` occurs in no record.

## Where each part appears

| Part | Where in the app |
|---|---|
| `source_type`, `signals` | Badges at the top of the record |
| `metrics` | Line under the badges, except `blind_metrics` |
| `question`, `reference_answer`, `system_answer`, `citations` | Main view |
| `ground_truth` | "Ground-truth chunk" section |
| `retrieval_events`, sources | "Retrieved sources" sections |
| the trace from `load_trace` | "Full trace (raw)" section, one collapsed JSON block per top-level key |
| `extras` | "System-specific extras" section |
