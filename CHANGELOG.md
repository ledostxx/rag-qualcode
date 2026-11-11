# Changelog

## Change policy

The public API is `Record` and its parts, `Adapter` with its hooks and attributes, the keys of the project file, and the `ragnostics` commands. Before version 1.0, a minor version (0.1 to 0.2) may change any of them. Every change is listed here. New fields and hooks always get defaults, so an existing adapter keeps working when it does not use them. See [docs/adapters.md](docs/adapters.md).

## 0.2.0 - 2026-11-11

Renamed from rag-qualcode to Ragnostics. Nothing else changed.

- Package and import name: `rag_qualcode` is now `ragnostics`. Adapters that import from `rag_qualcode` must change the import.
- Command: `qualcode` is now `ragnostics` (`ragnostics validate ...`).
- Files: `qualcode.example.yaml` is now `ragnostics.example.yaml`, the demo project file is `examples/demo/ragnostics.yaml`, the default project file is `ragnostics.yaml`. Existing project and annotation files keep working under any name.
- Environment variable: `QUALCODE_PROJECT` is now `RAGNOSTICS_PROJECT`.
- Skill: `skills/rag-qualcode-adapter` is now `skills/ragnostics-adapter`.
- Repository: `github.com/ledostxx/rag-qualcode` is now `github.com/ledostxx/ragnostics` (the old address redirects).

## 0.1.0 - 2026-11-11

First public version.

### Features

- Open coding: a stratified sample, one record at a time, free-text notes, a "No issues" flag, keyboard navigation.
- Axial coding: an LLM proposes failure categories from all notes, you edit them, one call per note assigns it to a category or to "None of the above", the codebook can be frozen. Works with any OpenAI-compatible endpoint (`OPENAI_BASE_URL` or `llm.base_url`).
- Your own adapter as one Python file, loaded by file path: `adapter: ./my_adapter.py:MyAdapter`.
- `ragnostics validate` checks an adapter and prints counts and records for comparison with the raw log.
- Adapter hooks `trace_signals`, `signal_level` and `blind_metrics`, so diagnostics, badge colours and hidden metrics come from the adapter and the app knows no system.
- A demo project with 20 invented records, and an example adapter to copy.
- An experimental agent skill that writes an adapter from your logs, and `AGENTS.md`.
- A reference adapter for the GRAINS system.
- Documentation in `docs/`.

### Changes to the GRAINS adapter

- The signal "Ground-truth source" is renamed "Ground-truth document".
- New signals "Ground-truth passage" (delivered at position N, or not delivered) and "Ground-truth candidate" (dropped before generation, or absent from all candidates). They are decided on chunk text and need the optional `gold_chunk_texts` file.
- Prompts that were already saved in an annotation file keep their old wording. Only prompts that were never saved use the new defaults. To use the new defaults, clear the saved prompt in the annotation file.

### Known limitations

- A note in open coding is saved only when the field loses focus or on Ctrl+Enter.
- A project file runs its adapter code. Open only projects you trust.
- Axial coding retries once without the JSON response format when an endpoint rejects it or the reply is not valid JSON. A model that cannot produce JSON still fails.
- Axial coding sends all notes in one prompt, and stores assignments only when a run ends.
- One annotation file per project, for one coder at a time.
- An adapter is a single file.
- No upper limits on dependency versions. The weekly CI run covers the newest versions while the repo is active.
- macOS and Linux only.

### Skill test

Skill test: a fresh agent used the skill on the 1,000-question log of an agentic RAG system (PydanticAI agent with web and paper search tools; results JSONL plus a 24 MB trace file). `ragnostics validate` exited 0 on the first run, 0 hand corrections; a check of 50 random records against the raw log found no mismatch. The six gaps it reported in the skill and docs are fixed in this release.
