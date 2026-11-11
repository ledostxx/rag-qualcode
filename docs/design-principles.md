# Design principles

The tool came out of a qualitative evaluation of a RAG system, where a person read hundreds of benchmark traces and grouped what went wrong. These seven principles shaped it. They explain choices that may look odd, so you can decide if they suit your own evaluation.

## 1. One core, one adapter per system

The app knows one record format and no system. Everything specific to a system lives in an adapter, a single Python file that translates that system's logs into records. A new system means a new adapter, never a change to the app. Diagnostics that depend on a system's pipeline, such as "the right passage was retrieved but dropped before generation", are produced by the adapter too, as signals with a colour. The app only draws them. The cost is that every system needs an adapter. The benefit is that the coding workflow stays the same across systems, so results are comparable.

## 2. Open coding is free text

During open coding you write what you see in your own words. There is no list of codes to click. A fixed list makes you look for the failures it names and miss the others. A list built up while coding makes early notes steer later ones. Free-text notes keep the first pass inductive. Grouping comes in the second phase, where an LLM proposes categories from all notes together and you review them.

## 3. One trace at a time

The view shows one record with its question, answers, retrieved sources and raw trace. It has no table of many records and no aggregate chart in the coding phase. To say which component failed, you need to follow one case from the question through retrieval to the answer, and that takes full attention for that one case. Aggregates come after the categories exist. Metrics that already judge the answer can be hidden (`blind_metrics`) so they do not anchor your reading.

## 4. Match on text, not on ids

When an adapter decides whether the system found the right passage, it should compare the text of the passages. Identifiers do not settle this. The same passage can appear under several document ids, for example a patent published by several offices or an article syndicated by several outlets. An id comparison then reports a miss although the right text was delivered. The reference adapter compares normalised text and falls back to containment. The demo adapter does the same in a few lines. This is a rule for adapter authors, and the app does not enforce it.

## 5. Fix the codebook before you scale

The codebook is the product of phase 2. The app lets you freeze it, which records the time and stops further edits. The point is that the categories are final before they are applied to anything else. If you want to apply them to every record, not only the coded sample, the categories must not move while you do. Changing them afterwards makes counts from before and after incomparable. This tool covers coding and building the codebook. Applying a frozen codebook to all records is outside it. The "None of the above" bucket is the check that the categories cover the material: if many notes land there, do not freeze yet.

## 6. Keyboard first

Reading hundreds of traces is repetitive. The Left and Right arrow keys move between records, "Next uncoded" skips what you have done, and Ctrl+Enter saves a note. The coding field stays visible next to the record, so you do not scroll back and forth. The arrow keys do nothing while a text field has focus, so they never move you away from a note you are typing.

## 7. A note is lost if it is not saved: know when saving happens

The note field saves when it loses focus or on Ctrl+Enter, not on every keystroke. That is how the text field of the UI framework works, and it has a cost: a note typed and abandoned by closing the tab is lost, and the field looks the same whether it is saved or not. This happened once during the original coding, when a corrected note never reached the file. The app now says under the field when it saves. The limitation is listed in the README. If you code in the app, press Ctrl+Enter or click outside the field before you leave a record.
