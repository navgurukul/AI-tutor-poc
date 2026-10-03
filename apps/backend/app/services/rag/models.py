"""rag-engine/src/types.ts"""

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional


@dataclass
class Chunk:
    id: int
    doc_id: str
    seq: int
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Fused RRF score, higher is better; 1.0 for a whole-section hit.
    score: float = 0.0
    matched_via: List[str] = field(default_factory=list)
    # Cosine distance, set only on chunks the dense search itself returned.
    distance: Optional[float] = None

    def with_(self, **changes: Any) -> "Chunk":
        return replace(self, **changes)


@dataclass
class SectionInfo:
    doc_id: str
    level: str  # "chapter" | "topic" | "subtopic"
    id: int
    title: str
