"""
Adobe Symbol font, decoded to Unicode.

Maths in a PDF is often set in the Symbol font, which predates
Unicode and carries no ToUnicode map. PyMuPDF extracts its glyphs
into the private-use area, so a physics chapter arrives with
U+F0B5 where it means ∝ and U+F8EC where a large bracket was
drawn. Neither renders, neither embeds, and neither is searchable.

Two ranges matter:

  U+F020-U+F0FF   the Symbol character set, offset by 0xF000.
                  Greek letters and maths operators. Recoverable.

  U+F8E5-U+F8FF   the pieces large brackets are assembled from
                  (top hook, vertical extension, bottom hook).
                  Purely visual: a two-line fraction linearises
                  into a single line of text where they mean
                  nothing, so they are dropped.
"""

from __future__ import annotations

# Symbol code point (low byte) -> Unicode. Only the entries that
# appear in running text are listed; anything absent falls through
# to the ASCII-compatible interpretation below.
_SYMBOL: dict[int, str] = {
    # Operators and relations
    0x22: "∀", 0x24: "∃", 0x27: "∋", 0x2A: "∗",
    0x2D: "−", 0x40: "≅",
    0x5C: "∴", 0x5E: "⊥",
    0x7E: "∼",
    0xA1: "ϒ", 0xA2: "′", 0xA3: "≤", 0xA4: "⁄",
    0xA5: "∞", 0xA6: "ƒ",
    0xAB: "↔", 0xAC: "←", 0xAD: "↑", 0xAE: "→",
    0xAF: "↓",
    0xB0: "°", 0xB1: "±", 0xB2: "″", 0xB3: "≥",
    0xB4: "×", 0xB5: "∝", 0xB6: "∂", 0xB7: "•",
    0xB8: "÷", 0xB9: "≠", 0xBA: "≡", 0xBB: "≈",
    0xBC: "…",
    0xC4: "⊗", 0xC5: "⊕", 0xC6: "∅", 0xC7: "∩",
    0xC8: "∪", 0xC9: "⊃", 0xCA: "⊇", 0xCB: "⊄",
    0xCC: "⊂", 0xCD: "⊆", 0xCE: "∈", 0xCF: "∉",
    0xD0: "∠", 0xD1: "∇", 0xD5: "∏", 0xD6: "√",
    0xD7: "⋅", 0xD8: "¬", 0xD9: "∧", 0xDA: "∨",
    0xDB: "⇔", 0xDC: "⇐", 0xDD: "⇑", 0xDE: "⇒",
    0xDF: "⇓",
    0xE5: "∑", 0xF2: "∫",

    # Uppercase Greek
    0x41: "Α", 0x42: "Β", 0x43: "Χ", 0x44: "Δ",
    0x45: "Ε", 0x46: "Φ", 0x47: "Γ", 0x48: "Η",
    0x49: "Ι", 0x4A: "ϑ", 0x4B: "Κ", 0x4C: "Λ",
    0x4D: "Μ", 0x4E: "Ν", 0x4F: "Ο", 0x50: "Π",
    0x51: "Θ", 0x52: "Ρ", 0x53: "Σ", 0x54: "Τ",
    0x55: "Υ", 0x56: "ς", 0x57: "Ω", 0x58: "Ξ",
    0x59: "Ψ", 0x5A: "Ζ",

    # Lowercase Greek
    0x61: "α", 0x62: "β", 0x63: "χ", 0x64: "δ",
    0x65: "ε", 0x66: "φ", 0x67: "γ", 0x68: "η",
    0x69: "ι", 0x6A: "ϕ", 0x6B: "κ", 0x6C: "λ",
    0x6D: "μ", 0x6E: "ν", 0x6F: "ο", 0x70: "π",
    0x71: "θ", 0x72: "ρ", 0x73: "σ", 0x74: "τ",
    0x75: "υ", 0x76: "ϖ", 0x77: "ω", 0x78: "ξ",
    0x79: "ψ", 0x7A: "ζ",
}

# Characters that pass through unchanged: in Symbol these hold
# their ASCII meaning.
_PASSTHROUGH = set("0123456789 !#%&()+,./:;<=>?[]_{|}")

SYMBOL_START, SYMBOL_END = 0xF020, 0xF0FF

# Large-bracket assembly pieces. Visual scaffolding only.
BRACKET_START, BRACKET_END = 0xF8E5, 0xF8FF


def decode_char(char: str) -> str:
    """Decode one private-use character; '' means drop it."""
    code = ord(char)

    if BRACKET_START <= code <= BRACKET_END:
        return ""

    if SYMBOL_START <= code <= SYMBOL_END:
        low = code - 0xF000
        if low in _SYMBOL:
            return _SYMBOL[low]
        ascii_char = chr(low)
        return ascii_char if ascii_char in _PASSTHROUGH else ""

    return char


def decode(text: str) -> str:
    """
    Replace Symbol-font private-use characters with real Unicode.

    Anything outside the two known ranges is left alone, so a
    private-use character from some other font is not silently
    mangled -- it stays visible and the validator can reject it.
    """
    if not text:
        return text

    # Fast path: most text has no private-use characters at all.
    if not any("" <= char <= "" for char in text):
        return text

    return "".join(
        decode_char(char) if "" <= char <= "" else char
        for char in text
    )
