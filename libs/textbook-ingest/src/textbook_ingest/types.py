"""The values that move between stages.

Everything here is plain data. A caller that wants to skip a stage -- supply its
own extraction, or its own profile -- can build these directly.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set


@dataclass
class Source:
    """One input file. A book is a list of these, in reading order.

    NCERT ships one PDF per chapter, so a book is usually many sources; a
    single-file book is a list of one. Keeping the name lets a chunk say which
    file it came from, which matters when one chapter fails to parse and the
    rest must still ingest.
    """

    name: str
    data: bytes


@dataclass
class Page:
    """One page, tracked from raw extraction through to cleaned paragraphs."""

    index: int                        # 0-based, across the whole book
    source: str                       # the Source.name it came from
    raw: str                          # exactly what the extractor returned
    text: str = ""                    # after repair, stripping and reflow
    number: Optional[int] = None      # printed page number, when one was found
    paragraphs: List[str] = field(default_factory=list)


@dataclass
class BookProfile:
    """What was learned about this particular book.

    The whole point of the redesign: the rules that vary by publisher are
    derived here, from the document, instead of being hard-coded. A profile is
    serialisable, so it can be inspected, stored beside a corpus, or supplied by
    hand for a book the detector gets wrong.
    """

    # Running header/footer templates, page number already normalised out.
    furniture: Set[str] = field(default_factory=set)
    # Section labels this book uses ("QUESTIONS", "Let's try this.").
    labels: Set[str] = field(default_factory=set)
    # "prefixed" (Fig. 8.3:), "numeric" (10.8 :), or "none".
    caption_style: str = "none"
    # Tokens that open a list item in this book ("l", "/square6", "•").
    bullets: Set[str] = field(default_factory=set)
    # The character this book uses where a space belongs, if it is not " ".
    space_substitute: Optional[str] = None
    # Words the book uses, for the split-repair pass. Counts, not just presence.
    vocabulary: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {
            "furniture": sorted(self.furniture),
            "labels": sorted(self.labels),
            "caption_style": self.caption_style,
            "bullets": sorted(self.bullets),
            "space_substitute": self.space_substitute,
            "vocabulary_size": len(self.vocabulary),
        }


@dataclass
class Chunk:
    """A unit of retrievable text."""

    ordinal: int
    text: str
    heading: str
    page_start: int                   # printed number when known, else index+1
    page_end: int
    source: str = ""
    kind: str = "prose"               # prose | table | summary

    def embedding_text(self, breadcrumb: Optional[Sequence[str]] = None) -> str:
        """What to embed.

        `breadcrumb` is supplied by the caller (["Class 6", "Science"]), not
        built here -- the library has no opinion about grade or subject. Passing
        None embeds the prose alone, which is the default after measuring that
        the heading was wrong about as often as it was right.
        """
        if not breadcrumb:
            return self.text
        crumbs = [c for c in breadcrumb if c]
        if self.heading:
            crumbs.append(self.heading)
        if not crumbs:
            return self.text
        return "{}\n\n{}".format(" > ".join(crumbs), self.text)


@dataclass
class Warning_:
    """Something the caller needs to be told about, that is not fatal."""

    code: str
    detail: str
    source: str = ""

    def __str__(self) -> str:
        where = " ({})".format(self.source) if self.source else ""
        return "{}{}: {}".format(self.code, where, self.detail)


@dataclass
class IngestResult:
    chunks: List[Chunk] = field(default_factory=list)
    pages: List[Page] = field(default_factory=list)
    profile: BookProfile = field(default_factory=BookProfile)
    warnings: List[Warning_] = field(default_factory=list)
    stats: Dict[str, object] = field(default_factory=dict)
    # Sources that could not be read at all. The book still ingests without
    # them; silently dropping a chapter is the one outcome to avoid.
    skipped: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.chunks)
