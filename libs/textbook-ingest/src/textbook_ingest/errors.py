"""Failures a caller has to distinguish.

Two kinds. `ExtractionError` is about one source and is survivable -- the book
ingests without that chapter, and the caller is told. `UnusableBook` is about
the whole input and means there is nothing worth indexing; it carries a `hint`
because the user can usually act on it (run OCR, find a different edition).
"""


class TextbookIngestError(Exception):
    """Base class, so a caller can catch everything this library raises."""


class ExtractionError(TextbookIngestError):
    """One source could not be read. Survivable: skip it and carry on."""

    def __init__(self, detail: str, source: str = ""):
        super().__init__(detail)
        self.detail = detail
        self.source = source


class UnusableBook(TextbookIngestError):
    """The whole book has no text worth indexing."""

    def __init__(self, detail: str, hint: str = "", code: str = "unusable"):
        super().__init__(detail)
        self.detail = detail
        self.hint = hint
        self.code = code
