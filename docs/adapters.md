# Writing an adapter

An adapter is a Python class that reads one system's benchmark logs and returns a list of records in the [common record format](schema.md). The app and `qualcode validate` only ever see those records.

## Start from the demo

[examples/demo/demo_adapter.py](../examples/demo/demo_adapter.py) is a complete small adapter for a flat JSONL log. Copy it, rename the class, and change every place marked `CHANGE`. The minimum is a subclass of `Adapter` with a `load()` method:

```python
from rag_qualcode.adapters.base import Adapter
from rag_qualcode.schema import Record, RetrievalEvent, RetrievedSource


class MyAdapter(Adapter):
    name = "my-system"

    def load(self):
        ...  # read self.data["logs"], return a list of Record
```

`self.data` is the `data:` mapping of the project file, with path-like values already resolved. Choose the keys yourself and read them in your adapter.

## Load it by file path

Name the adapter in the project file as `<file>.py:<ClassName>`:

```yaml
adapter: ./my_adapter.py:MyAdapter
data:
  logs: ./my_logs.jsonl
```

The file path is resolved against the project file's folder. The app and `qualcode validate` import the file, so everything at the top level of the file runs. The class must be a subclass of `Adapter`, or loading fails with a message that names the file and the class. Treat a project file like a script and open only projects you trust.

An adapter is one file. Helper files next to it cannot be imported, so put helper functions in the same file. If you edit the file while the app is open, the app reloads the records on the next interaction.

Built-in adapters are the other form: `adapter: grains` names the reference adapter shipped in the package. There is no documented way to register your own built-in adapter.

## What to implement

Only `load()` is required. The rest have defaults. Implement a hook when the matching part of the app would otherwise be empty.

| Hook or attribute | Default | Implement it when |
|---|---|---|
| `load()` | required | always. Returns the records. |
| `load_trace(record)` | `None` | the system has a full log per question (every candidate, every step) that you want to read in the app. It is called when a record is opened, so if the adapter loads traces lazily, large traces stay on disk until then. Return a dict. |
| `chunk_texts(trace)` | `{}` | the log has the full text of retrieved sources, and `RetrievedSource.snippet` is cut off or missing. Return a dict from source id to text. |
| `trace_signals(record, trace)` | `{}` | a useful diagnostic needs the trace. Return `dict[str, str]`. It runs every time a record is shown, so it must not read whole log files. |
| `signal_level(key, value)` | `None` | a badge should have a colour that the built-in word list does not give. Return `"good"`, `"warn"`, `"bad"`, `"neutral"` or `None`. |
| `blind_metrics` | empty | an automatic score would influence the coder during open coding. A set of metric names to hide. |

The details are in the docstrings of [src/rag_qualcode/adapters/base.py](../src/rag_qualcode/adapters/base.py). How signals become badges is in [schema.md](schema.md).

Things that go wrong often:

- Do not invent a field the log does not have. Leave `reference_answer` or `ground_truth` empty. A made-up value is worse than a gap.
- Decide whether the system found the right passage by comparing text, not ids. The same passage often exists under several ids. The demo adapter normalises case and whitespace and then checks whether the gold text is contained in a retrieved text.
- Traces: one file per record, or many small files, should be read lazily in `load_trace`. When all traces live in one large file (for example a JSON object keyed by record id), reading it once in `load()` and keeping it on the adapter instance is fine. Prefer lazy per-record loading when the file does not fit in memory or when loading it makes startup slow.
- Document-level ground truth: if the log only identifies the source document, fill `GroundTruth.title` and `GroundTruth.url` and leave `chunk_text` empty. The app then shows the document, and passage-level signals (such as whether the gold passage was retrieved) are not available.
- Retrieved versus cited: `RetrievalEvent.sources` holds everything the retrieval step returned. `Record.citations` holds the ids of the sources the answer cited. Do not merge the two.
- `RetrievedSource.id` must match the keys `chunk_texts` returns, or the app falls back to the snippet.

## Check it with `qualcode validate`

```bash
qualcode validate my_project.yaml --show 3
```

The command loads the project the same way the app does and exits with 0 when it found no problems, 1 otherwise. Counts, warnings and timings never change the exit code. With no project argument it uses `qualcode.yaml` in the current folder. `--traceback` adds the full Python traceback to adapter errors.

**Problems** (exit code 1):

- the adapter file or class cannot be found or imported, or `load()` raises
- no records, an empty id, a duplicate id, an empty question
- for the first `--show` records: `load_trace`, `chunk_texts` or `trace_signals` raise or return the wrong type
- `signal_level` raises or returns a value other than the five allowed ones

**Counts** show a wrong mapping that does not break anything. Read them against what you know about your logs:

| Count | What an odd value tells you |
|---|---|
| records, records per `source_type` | a wrong source type field gives one bucket, or one bucket per record |
| empty system answer | the answer field is mapped wrongly |
| missing reference answer | 100 % usually means a wrong field name, a benchmark without references gives the same number |
| zero retrieval events | the retrieval part of the log was not read |
| with ground truth | 0 % when the benchmark has ground truth means it was not mapped |
| metric keys, signal keys | names that you did not expect, or none |
| trace signal keys (shown records) | the keys `trace_signals` returned for the `--show` records. Empty when the hook is not implemented or finds nothing in the trace. Unlike the other counts it covers only the shown records. |

**Warnings** do not fail the command. For example, `blind_metrics` names a metric that no record has.

After the counts, the command prints the first `--show` records in full as JSON, with long text cut at 300 characters. Compare them with the raw log entries. This is the main check that the mapping is right.

## Use the skill

[skills/rag-qualcode-adapter/SKILL.md](../skills/rag-qualcode-adapter/SKILL.md) is an agent skill in the [Agent Skills](https://agentskills.io) format. It tells a coding agent to read a few log records, propose a mapping from log fields to record fields for you to confirm, write the adapter and the project file from the demo, and run `qualcode validate`. Point your agent at that file, or copy it into the skills folder of your agent. [AGENTS.md](../AGENTS.md) points agents that do not read skills to it.

The skill is experimental. Two cautions apply to every agent that does this work:

- The agent reads your log files, so their content reaches your LLM provider.
- Logs can contain third-party text, for example web pages, with instructions in it. The skill tells the agent to treat log content as data and to write only the adapter and the project file. Read the adapter before you run it, because running it executes it.

## The GRAINS adapter

[src/rag_qualcode/adapters/grains.py](../src/rag_qualcode/adapters/grains.py) is the adapter for the system the tool was first built for: a RAG system with keyword search, vector search and knowledge-graph retrieval, whose logs are one results file plus one trace file per question. It is the full example. It loads traces lazily, reads full chunk texts from the traces, matches the ground-truth passage by text, and implements `trace_signals`, `signal_level` and `blind_metrics`. Read it after the demo adapter when you need those hooks. You need the GRAINS logs to run it. The keys it reads from `data:` are in its module docstring and in [qualcode.example.yaml](../qualcode.example.yaml).

## Public API and change policy

The public API is `Record` and its parts, `Adapter` with its hooks and attributes, the keys of the project file, and the `qualcode` commands. Before version 1.0, a minor version (0.1 to 0.2) may change any of them. Every change is listed in [CHANGELOG.md](../CHANGELOG.md). New fields and hooks always get defaults, so an existing adapter keeps working when it does not use them.
