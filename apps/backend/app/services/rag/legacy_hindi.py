# -*- coding: utf-8 -*-
"""Legacy 8-bit Hindi fonts (Walkman-Chanakya, Kruti Dev) -> Unicode Devanagari.

NCERT still typesets its Hindi-medium Social Science books in Walkman-
Chanakya905: the PDF stores Latin letters and symbols, and the font draws them
as Devanagari. Extracted, "भारत" comes out as "Hkkjr" and "हमारे पर्यावरण में
उपलब्ध प्रत्येक वस्तु" as "gekjs i;kZoj.k eas miyCèk izR;sd oLrq" -- measured
2026-09-11 on the 2024-25 reprint of समकालीन भारत-2 downloaded from
ncert.nic.in: 0 Devanagari characters in 12 pages. Embedded as-is, a book like
that matches no Hindi question (best hit 0.56-0.64 against a 0.50 ceiling), so
the tutor answers from memory and cites nothing.

The mapping is deterministic, so the text is converted during upload, span by
span, and only for spans whose font is one of these -- PyMuPDF reports the font
of every span, so Arial digits and real English in the same book are never
touched.

Written from the character correspondences of the font, not from the GPL-3.0
converters (IIT Delhi Assistech, LTRC kru2uni) that exist for it, so the
project takes on no licence obligations. Every glyph below was checked in
context against the book it was built for; tests/test_legacy_hindi.py pins
~40 real phrases.

Two things make this more than a table lookup:

  * The short i-matra (ि) is typed BEFORE the consonant it follows in speech,
    because that is where it is drawn: "fodkl" is f-o-d-k-l, ि व क ा स, and
    has to become विकास. It moves to after the whole consonant cluster
    ("fLFkfr" -> स्थिति, not स्ि थ).

  * The reph (र् above a letter) is typed AFTER the syllable it sits on:
    "i;kZoj.k" is प य ा र् व र ण and has to become पर्यावरण. It moves to before
    the preceding consonant cluster, past any vowel signs.
"""

import re
import unicodedata

# Fragments of legacy font names, compared lowercased with separators removed.
# "WalkmanChanakya901Normal", "BMNCFG+Walkman-Chanakya905Bold", "Kruti Dev 010",
# "DevLys 010" all match; "NeoMitra"/"NeoNatraj" (SCERT Telangana) do not --
# a different encoding, and guessing would only produce confident nonsense.
_LEGACY_FONT_MARKERS = ("chanakya", "krutidev", "devlys")

# Private-use placeholders for marks that have to be repositioned after mapping.
_PRE_I = "\ue000"   # i-matra, typed before its consonant cluster
_PRE_RI = "\ue001"  # reph + i-matra (one glyph), typed before the cluster
_PRE_IM = "\ue002"  # i-matra + anusvara (one glyph), typed before the cluster
_POST_R = "\ue003"  # reph, typed after its syllable
_POST_RM = "\ue004" # reph + anusvara (one glyph), typed after its syllable
_COLON = "\ue005"   # a free-standing % is a colon, not a visarga

# Longest keys are tried first. Checked in context against समकालीन भारत-2
# (Walkman-Chanakya905); where Chanakya differs from Kruti Dev it is noted.
_MAP = {
    # --- three characters ---
    "vkS": "औ", "vks": "ओ", "vkW": "ऑ",
    "îók": "ड्डा", "Mhó": "ड्डी",
    # --- two characters ---
    "vk": "आ", ",s": "ऐ", "bZ": "ई", "b±": "ईं",
    "Ùk": "त्त", "èk": "ध", "[k": "ख", "{k": "क्ष", "=k": "त्र", "?k": "घ",
    "Fk": "थ", "'k": "श", '"k': "ष", "Hk": "भ", ".k": "ण", "”k": "ज़",
    "Ük": "श", "×k": "ङ",
    "Xk": "ग", "Dk": "क", "Rk": "त", "Uk": "न", "Ik": "प", "Ck": "ब",
    "Ek": "म", "Yk": "ल", "Ok": "व", "Lk": "स", "Pk": "च", "Tk": "ज",
    "kW": "ॉ", "ks": "ो", "kS": "ौ",
    "M+": "ड़", "<+": "ढ़",
    "êð": "ट्ट", "êò": "ट्ठ",
    # --- independent vowels ---
    "v": "अ", "b": "इ", "m": "उ", "Å": "ऊ", ",": "ए", "Í": "ऋ",
    # --- consonants (full, then half forms) ---
    "d": "क", "D": "क्", "[": "ख्", "x": "ग", "X": "ग्", "?": "घ्",
    "p": "च", "P": "च्", "N": "छ", "t": "ज", "T": "ज्", ">": "झ", "¥": "ञ",
    "V": "ट", "B": "ठ", "M": "ड", "<": "ढ", ".": "ण्",
    "r": "त", "R": "त्", "F": "थ्", "n": "द",
    # Chanakya: "/" is the FULL ध ("lokZf/dkj" = सर्वाधिकार, "fof/" = विधि)
    # and "è" the half ध् ("vuqlaèkku" = अनुसंधान). Kruti Dev has "/k" for ध.
    "/": "ध", "è": "ध्",
    "u": "न", "U": "न्", "i": "प", "I": "प्", "Q": "फ", "Ý": "फ्",
    "c": "ब", "C": "ब्", "H": "भ्", "e": "म", "E": "म्", ";": "य",
    "j": "र", "y": "ल", "Y": "ल्", "o": "व", "O": "व्",
    "'": "श्", '"': "ष्", "l": "स", "L": "स्", "g": "ह",
    # --- conjunct glyphs ---
    "Ù": "त्त्", "{": "क्ष्", "=": "त्र्", "K": "ज्ञ", "J": "श्र", "}": "द्व",
    "|": "द्य", "Ñ": "कृ", "Ø": "क्र", "í": "द्द", "æ": "द्र", "¼": "द्ध",
    "ß": "ह्र", "Ï": "स्र", "É": "ह्न", "á": "ह्य", "ã": "ह्म", "â": "हृ",
    "ç": "प्र", "Ä": "घ", "#": "रु", ":": "रू",
    "ê": "ट्", "ð": "ट", "ò": "ठ", "î": "ड्", "ó": "ड", "Ü": "श्",
    "”": "ज़्", "×": "ङ",
    # --- vowel signs and marks ---
    "k": "ा", "h": "ी", "q": "ु", "w": "ू", "`": "ृ", "s": "े", "S": "ै",
    "a": "ं", "¡": "ँ", "%": "ः", "~": "्", "z": "्र", "ª": "्र",
    "W": "ॅ", "+": "़",
    "f": _PRE_I, "£": _PRE_RI, "¯": _PRE_IM, "Z": _POST_R, "±": _POST_RM,
    # --- punctuation (Chanakya) ---
    "A": "।", "]": ",", "-": ".", "&": "-", "µ": "—", "\\": "?",
    "^": "‘", "*": "’", "@": "/", "_": ";", "¶": "“", "¸": "”",
}
_MAX_KEY = max(len(k) for k in _MAP)

# Chanakya draws क and फ as a stem plus a separate hook glyph "Q", with any
# vowel sign or reph typed between them: "osQ" = के, "oqQ" = कु, "oZQ" = र्क,
# "iQkYxqu" = फाल्गुन. Folded to the single-glyph forms before mapping.
_HOOK_MARKS = "sSqw`aZ¡"
_KA_HOOK = re.compile("o([" + re.escape(_HOOK_MARKS) + "]*)Q")
_PHA_HOOK = re.compile("i([" + re.escape(_HOOK_MARKS) + "]*)Q")
# The extractor sometimes splits the फ glyph pair as "i- Q" ("i- Qjojh" is
# फरवरी, not "प. फरवरी").
_SPLIT_PHA = re.compile(r"i-\s+Q")
# A % with nothing attached before it is a colon ("iQksu % 011" = फोन : 011).
_FREE_PERCENT = re.compile(r"(^|\s)%")

_CONS = "[\u0915-\u0939\u0958-\u095f]\u093c?"
_CLUSTER = _CONS + "(?:्" + _CONS + ")*"
_SIGNS = "[\u093e-\u094c\u0962\u0963\u0901\u0902]*"
_PRE_RE = re.compile("([" + _PRE_I + _PRE_RI + _PRE_IM + "])(" + _CLUSTER + ")")
_POST_RE = re.compile("(" + _CLUSTER + ")(" + _SIGNS + ")([" + _POST_R + _POST_RM + "])")
# An anusvara typed before the vowel sign it belongs after: "eas" = में.
_NASAL_BEFORE_SIGN = re.compile("([\u0901\u0902])([\u093e-\u094c])")

_CLEANUPS = (
    ("अा", "आ"), ("अो", "ओ"), ("अौ", "औ"), ("अॉ", "ऑ"),
    ("ाे", "ो"), ("ाै", "ौ"),
    ("्र्र", "्र"),
)


def is_legacy_font(name: str) -> bool:
    """True for a legacy 8-bit Devanagari font this module can convert."""
    key = re.sub(r"[\s\-_]", "", (name or "").lower())
    return any(marker in key for marker in _LEGACY_FONT_MARKERS)


def _map(text: str) -> str:
    out = []
    i = 0
    while i < len(text):
        for size in range(min(_MAX_KEY, len(text) - i), 0, -1):
            piece = text[i:i + size]
            if piece in _MAP:
                out.append(_MAP[piece])
                i += size
                break
        else:
            out.append(text[i])  # digits, spaces, brackets, unknown glyphs
            i += 1
    return "".join(out)


def _place_pre(match: "re.Match") -> str:
    mark, cluster = match.group(1), match.group(2)
    if mark == _PRE_RI:
        return "र्" + cluster + "ि"
    if mark == _PRE_IM:
        return cluster + "िं"
    return cluster + "ि"


def _place_post(match: "re.Match") -> str:
    cluster, signs, mark = match.group(1), match.group(2), match.group(3)
    return "र्" + cluster + signs + ("ं" if mark == _POST_RM else "")


def to_unicode(text: str) -> str:
    """Convert one run of legacy-font text to Unicode Devanagari."""
    if not text:
        return text
    text = _SPLIT_PHA.sub("iQ", text)
    text = text.replace("Z±", "±")  # the combined glyph already carries the reph
    text = _KA_HOOK.sub(r"d\1", text)
    text = _PHA_HOOK.sub(r"Q\1", text)
    text = _FREE_PERCENT.sub(lambda m: m.group(1) + _COLON, text)

    text = _map(text)
    text = _PRE_RE.sub(_place_pre, text)
    text = _POST_RE.sub(_place_post, text)
    # A mark with no consonant to attach to: keep the sound, drop the position.
    text = (text.replace(_PRE_I, "ि").replace(_PRE_IM, "िं").replace(_PRE_RI, "र्ि")
                .replace(_POST_R, "र्").replace(_POST_RM, "र्ं").replace(_COLON, ":"))
    text = _NASAL_BEFORE_SIGN.sub(r"\2\1", text)
    for old, new in _CLEANUPS:
        text = text.replace(old, new)
    return unicodedata.normalize("NFC", text)
