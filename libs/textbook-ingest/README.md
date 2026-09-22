# textbook-ingest

A school textbook PDF in, clean chunkable text out.

Built after running one pipeline over eight textbooks from two publishers
(MSCERT and NCERT, Classes 1–10) and measuring where it broke. The finding that
shaped the design:

> The rules that generalised were the **structural** ones — column measure,
> exercise density, blank runs. The rules that broke were every regex that
> encoded one publisher's vocabulary or typography.

So the surface patterns are **learned from the document at ingest time**, and
only the structure is hard-coded.

```bash
pip install -e "libs/textbook-ingest[pdf]"
```

```python
from textbook_ingest import ingest_dir

result = ingest_dir("data/PDF NCERT/Class09-Science")

print(result.stats["chunks"], "chunks")
for warning in result.warnings:
    print("!", warning)
for chunk in result.chunks:
    index(chunk.text, page=chunk.page_start)
```

Or from the shell, to see what a new book turns into before you embed it:

```bash
textbook-ingest "data/PDF NCERT/Class09-Science" --profile-only
textbook-ingest book.pdf --chunks 5 --json out.json
```

## What it does

```
extract → assess → vocabulary → repair → PROFILE → strip → reflow → chunk
```

| Stage | What it handles |
|---|---|
| `extract` | One source at a time. A chapter that cannot be parsed is **skipped and reported**, not fatal. |
| `fidelity` | Rejects text that cannot be read (fonts with no Unicode map, a scan) with a reason the user can act on. Repairs rather than rejects a book that prints a glyph where a space belongs. |
| `repair` | Rejoins words a stray space broke (`natur e`, `exter nal`), drop caps, display type extracted once per layer, reversed figure text. |
| `profile` | **Learns this book**: running-header templates, section labels, caption form, bullet token. |
| `strip` | Removes the furniture, including a header fused into the first sentence. |
| `reflow` | Rebuilds paragraphs from the PDF's hard line breaks. |
| `chunk` | Paragraph-aligned chunks; tables kept separate from prose. |

## Three things worth knowing

**The running header is fused to the page number.** NCERT prints `SCIENCE58`,
`SCIENCE60`, `THE FUNDAMENTAL UNIT OF LIFE 59` — every instance a different
string, so counting identical lines counts each once and finds nothing. The
profile normalises the number out and counts *templates*.

**The threshold has to be windowed.** A running header carrying the chapter
title appears on 8 of a 113-page book — 7%, and unmissably a header within its
own chapter. Density is measured over the span a template occupies, not over the
book.

**The breadcrumb is off by default.** Measured over 373 MSCERT chunks, prefixing
the heading injected *wrong* vocabulary into 47% of them and right vocabulary
into 43%. It is the caller's decision, and the library has no opinion about
grade or subject:

```python
chunk.embedding_text()                        # prose alone (default)
chunk.embedding_text(["Class 9", "Science"])  # prefixed, heading appended
```

Overlap is `0` by default for the same reason: rebuilding the corpus at 105 and
0 left all 39 gold answer phrases intact either way, and overlap cost 13%
duplicated text. It is still applied where a cut is *not* semantic — the forced
split of an over-long paragraph.

## Options

```python
from textbook_ingest import IngestOptions, ingest_paths

ingest_paths(paths, IngestOptions(
    chunk_chars=700,
    overlap_chars=0,
    filter_apparatus=True,     # drop exercises, activity boxes, fill-in-the-blanks
    exercise_page_ratio=0.40,
    repair_text=True,
    enforce_fidelity=True,     # False ingests an unreadable book anyway
    profile=None,              # supply one by hand to override detection
))
```

## Handling failure

`UnusableBook` is raised when there is nothing worth indexing, and carries a
`hint` the user can act on. Individual chapters that fail are **not** fatal —
they appear in `result.skipped` and `result.warnings`, so a book never silently
ingests with a hole in it.

```python
try:
    result = ingest_dir(path)
except UnusableBook as exc:
    print(exc.detail, "--", exc.hint)
else:
    if result.skipped:
        print("NOT in the corpus:", result.skipped)
```

## Tests

```bash
python -m pytest libs/textbook-ingest/tests -q
```

Every case is a real string from a real book, named in the test, so a change
that reintroduces a defect fails here rather than in a groundedness run three
weeks later.

## Measuring a change

`scripts/eval/ingest_comparison.py` runs this library and the POC's original
pipeline over all eight books and prints furniture caught, distinct headings,
broken-word rate and the gold answer-phrase check side by side. The
answer-phrase count is a hard gate: a filter that deletes a gold answer is a
regression whatever else improved.
