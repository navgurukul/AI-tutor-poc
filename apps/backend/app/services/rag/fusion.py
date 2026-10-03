"""rag-engine/src/fusion.ts -- Reciprocal Rank Fusion.

Uses only each item's rank within each list, so cosine distance and BM25 score
never need putting on one scale.
"""

from typing import Dict, List, Sequence, Tuple


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[Tuple[int, str]]], k: int = 60
) -> List[Dict]:
    """`ranked_lists` is [[(id, source), ...], ...], best first within a list.

    Returns [{id, score, matched_via}] best first. Ties keep first-seen order,
    as the TypeScript's stable sort does.
    """
    scores: Dict[int, float] = {}
    sources: Dict[int, List[str]] = {}
    for items in ranked_lists:
        for rank, (item_id, source) in enumerate(items):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
            seen = sources.setdefault(item_id, [])
            if source not in seen:
                seen.append(source)
    fused = [
        {"id": item_id, "score": score, "matched_via": sources.get(item_id, [])}
        for item_id, score in scores.items()
    ]
    fused.sort(key=lambda f: -f["score"])
    return fused
