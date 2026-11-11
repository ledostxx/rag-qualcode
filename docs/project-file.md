# Project file

A project is one YAML file. `qualcode <file>` starts the app on it, and `qualcode validate <file>` checks it. Without an argument both look for `qualcode.yaml` in the current folder. [qualcode.example.yaml](../qualcode.example.yaml) is a commented template, and [examples/demo/qualcode.yaml](../examples/demo/qualcode.yaml) is the demo project.

**A project file runs code.** When `adapter` is a file path, that Python file is executed when the app or `qualcode validate` opens the project. A shared or downloaded project folder can contain malicious code. Treat a project file like a script, and open only projects you trust.

## Keys

| Key | Required | Default | Meaning |
|---|---|---|---|
| `name` | yes | none | Name shown in the sidebar. |
| `adapter` | yes | none | A built-in adapter by name (`grains`), or your own as `<file>.py:<ClassName>`. See [adapters.md](adapters.md). |
| `data` | yes | none | Mapping of keys to paths. The adapter defines which keys it reads. |
| `annotations` | yes | none | Path of the annotation file, see [workflow.md](workflow.md). The file and its folder are created on the first save. |
| `sample.per_source_type` | no | 20 | Records drawn per source type for open coding. |
| `sample.seed` | no | 42 | Random seed for the draw. |
| `llm.model` | no | `gpt-4o-mini` | Model for axial coding. Can be changed in the sidebar. |
| `llm.temperature` | no | 0.2 | Temperature for axial coding. Can be changed in the sidebar. |
| `llm.base_url` | no | none | URL of an OpenAI-compatible endpoint. Without it, the `OPENAI_BASE_URL` environment variable applies, and without that the OpenAI default. |
| `seed_codes` | no | empty | Accepted so that old project files load, and ignored. Open coding is free text and has no code list. |

A missing required key stops the app with a message that names the key.

The API key is never part of the project file. Set `OPENAI_API_KEY` in the environment, or type it into the sidebar, where it is kept for the session only. A local server that needs no key still needs `OPENAI_API_KEY` set to any value.

## How paths are resolved

Values under `data` and the `annotations` value are resolved against the folder of the project file, not the current folder:

- `~` at the start expands to your home folder.
- An absolute path stays as it is.
- A relative path is joined to the project file's folder.

A `data` value is treated as a path only if it contains a `/`, starts with `.` or `~`, or names a file that exists next to the project file. Other values, for example a plain word, are passed to the adapter unchanged. Values that are not strings (numbers, lists) are also passed unchanged.

For `adapter: ./my_adapter.py:MyAdapter`, the file part is resolved against the project file's folder in the same way.

## Example

```yaml
name: demo
adapter: ./demo_adapter.py:DemoAdapter
data:
  logs: ./logs.jsonl
annotations: ./annotations/demo.json
sample:
  per_source_type: 5
  seed: 42
llm:
  model: gpt-4o-mini
```
