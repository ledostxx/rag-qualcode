# Coding workflow

The app has two phases, selected in the sidebar. Phase 1 produces free-text notes. Phase 2 turns the notes into a codebook of failure categories.

## Phase 1: open coding

**Sample.** The first time you open a project, the sidebar shows "Draw stratified sample". The draw takes `sample.per_source_type` records from each `source_type` and uses `sample.seed`, so the same records and seed always give the same sample (see [project-file.md](project-file.md)). The sample is stored in the annotation file. The "Scope" radio switches between the sample and all records. A second filter selects source types, and a third shows only coded or only uncoded records.

**One record at a time.** The main view shows one record: the question, the reference answer, the ground-truth passage if the adapter provides one, the system answer, the sources each retrieval event returned, and the raw trace. The trace is loaded when you open the record, not at startup. The badges at the top show the record's source type and its signals. Metrics named in the adapter's `blind_metrics` are hidden during open coding. [schema.md](schema.md) explains where each part of a record appears.

The reason for one record at a time is that you follow the whole chain from question to retrieved sources to answer for one case with full attention. See [design-principles.md](design-principles.md).

**Notes.** You write what happened in your own words in the text field at the bottom. There is no list of codes to pick from. The note is saved when the field loses focus or when you press Ctrl+Enter, not while you type. A note that you type and then abandon by closing the tab is lost. The checkbox "No issues" marks a record that you read and found nothing wrong. A record counts as coded when it has a note or "No issues" ticked.

**Navigation.** The buttons "Prev" and "Next" and the Left and Right arrow keys move between records. The arrow keys do not move while a text field has focus, so they can move the cursor in your note. "Next uncoded" jumps to the next record without a note or flag. The dropdown jumps to any record in the current filter, and marks coded records with a tick. The sidebar shows how many records of the sample and of the current scope are coded.

When every record of the sample is coded, a "COMPLETED" overlay points to phase 2. "Keep reviewing records" dismisses it.

## Phase 2: axial coding

Phase 2 uses the notes of the sample records. It needs an LLM endpoint, see the README for the key and the endpoint settings. The sidebar sets the model name and temperature. Their defaults come from `llm.model` and `llm.temperature` in the project file.

1. **Material.** A table of all notes.
2. **Propose categories.** "Create Axial Codes" sends all notes in one prompt. The model returns failure categories, each with a code name, a `what_failed` definition and a `fix_target`, the part of the system or data that would have to change. The prompt is shown and can be edited. "Full prompt (copy)" shows it in a form you can copy and use in another tool. Creating categories again replaces the current ones and clears the assignments.
3. **Review.** You edit the categories as JSON and save them. The app warns when a category has no `what_failed`, because the assignment step uses that text as its rubric, and when `fix_target` is just "system", which names no component.
4. **Assign.** "Evaluate Axial Codes" makes one call per note, which maps the note to one or more of the reviewed categories. The app adds the category "None of the above" to the rubric. A note that lands there did not fit any category. Many such notes mean the categories miss something, or the note is too thin to classify. Calls that fail leave their note unassigned. The assignments are written to the annotation file when the whole run ends. A batch version of the prompt, which sends all notes in one call, can be copied for use with another model. "Paste a mapping produced elsewhere" stores the reply.
5. **Overview.** A table and a bar chart show how many notes each category received, with its `fix_target`. If you change the categories after assigning, the app warns that the assignments were made against the old ones.
6. **Finalise.** "Log final codebook" freezes the codebook, which records the time and disables the editing and the model calls. "Unlock for further iteration" undoes it.

The category prompt, the assignment prompt and the batch prompt are stored in the annotation file once you save them, so you can see later what was sent. Prompts saved earlier keep their wording when the tool's default prompts change.

## The annotation file

Each project has one JSON file, set by `annotations` in the project file. It holds:

| Key | Content |
|---|---|
| `version` | Format version, currently 1. |
| `annotations` | One entry per record id: `note`, `no_issues`, `updated` (UTC time), and `codes`. |
| `sample` | The ids drawn for open coding. |
| `codebook` | The categories from phase 2. |
| `axial_assignments` | Which note was assigned to which categories. |
| `assignments_for` | The category names the assignments were made against. |
| `codebook_frozen_at` | The time the codebook was frozen, or null. |
| `axial_prompt`, `assign_prompt`, `assign_batch_prompt` | The saved prompts. |
| `code_vocabulary`, and `codes` in each annotation | Legacy, see below. |

Earlier versions of the tool offered a list of codes to pick during open coding. The fields `codes` and `code_vocabulary` stay in the format so that old files load. The app no longer writes codes. New annotations have an empty `codes` list.

Every save writes a temporary file next to the annotation file and then renames it over the old one, so a crash during a save leaves the old file intact. The file is plain JSON and works in git. It is meant for one coder at a time.
