"""rag-engine/src/context-merge.ts

Merges chunks that are adjacent (or overlapping) in the same document into
single contiguous spans, stripping the chunker's overlap so the model never
reads the same sentence twice.
"""

from typing import Dict, List

from app.services.rag.models import Chunk


def _longest_overlap_words(a: str, b: str, max_words: int = 80) -> int:
    """Longest word run that is both a suffix of `a` and a prefix of `b`."""
    a_words = a.split()
    b_words = b.split()
    longest = min(len(a_words), len(b_words), max_words)
    for length in range(longest, 3, -1):
        if a_words[len(a_words) - length :] == b_words[:length]:
            return length
    return 0


def _append_deduped(text: str, next_text: str) -> str:
    overlap = _longest_overlap_words(text, next_text)
    if overlap == 0:
        return "{} {}".format(text, next_text).strip()
    return "{} {}".format(text, " ".join(next_text.split()[overlap:])).strip()


def merge_adjacent_chunks(chunks: List[Chunk]) -> List[Chunk]:
    by_doc: Dict[str, List[Chunk]] = {}
    for chunk in chunks:
        by_doc.setdefault(chunk.doc_id, []).append(chunk)

    merged: List[Chunk] = []
    for doc_chunks in by_doc.values():
        doc_chunks.sort(key=lambda c: c.seq)
        run = None
        for chunk in doc_chunks:
            if run is not None and chunk.seq <= run.seq + 1:
                if chunk.seq > run.seq:
                    run = run.with_(
                        seq=chunk.seq,
                        text=_append_deduped(run.text, chunk.text),
                        score=max(run.score, chunk.score),
                        matched_via=list(dict.fromkeys(run.matched_via + chunk.matched_via)),
                    )
                continue
            if run is not None:
                merged.append(run)
            run = chunk.with_()
        if run is not None:
            merged.append(run)

    merged.sort(key=lambda c: -c.score)
    return merged
