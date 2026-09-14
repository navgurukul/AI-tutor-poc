# -*- coding: utf-8 -*-
"""Walkman-Chanakya -> Unicode, pinned on real phrases from समकालीन भारत-2.

Every left-hand string below was extracted from the NCERT Class 10 Hindi
Geography PDF; every right-hand string is what the page shows.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.legacy_hindi import is_legacy_font, to_unicode  # noqa: E402

CASES = [
    # title page and imprint
    ("lkekftd foKku", "सामाजिक विज्ञान"),
    ("d{kk 10 osQ fy, Hkwxksy", "कक्षा 10 के लिए भूगोल"),
    ("dh ikB~;iqLrd", "की पाठ्यपुस्तक"),
    ("izFke laLdj.k", "प्रथम संस्करण"),
    ("Hkkjr&2", "भारत-2"),
    (",u-lh-bZ-vkj-Vh-", "एन.सी.ई.आर.टी."),
    ("}kjk izdkf'kr", "द्वारा प्रकाशित"),
    ("Jh vj¯on ekxZ] u;h fnYyh", "श्री अरविंद मार्ग, नयी दिल्ली"),
    ("lokZf/dkj lqjf{kr", "सर्वाधिकार सुरक्षित"),
    ("vuqlaèkku vkSj izf'k{k.k ifj\"kn~", "अनुसंधान और प्रशिक्षण परिषद्"),
    ("jk\"Vªh; 'kSf{kd", "राष्ट्रीय शैक्षिक"),
    ("okVjekoZQ", "वाटरमार्क"),
    ("fizaV", "प्रिंट"),
    ("IykWV", "प्लॉट"),
    ("lsDVj&37", "सेक्टर-37"),
    ("i- Qjojh", "फरवरी"),
    ("iQkYxqu", "फाल्गुन"),
    ("dkfrZd", "कार्तिक"),
    # the i-matra moves after the whole cluster, the reph before its syllable
    ("fodkl", "विकास"),
    ("i;kZoj.k", "पर्यावरण"),
    ("miyCèk", "उपलब्ध"),
    ("izR;sd oLrq", "प्रत्येक वस्तु"),
    ("eas", "में"),
    ("ÅtkZ", "ऊर्जा"),
    ("{ks=k", "क्षेत्र"),
    ("izkpk;ks±", "प्राचार्यों"),
    ("vkn'kks±", "आदर्शों"),
    ("ok£\"kd", "वार्षिक"),
    ("vk£Fkd", "आर्थिक"),
    # conjunct glyphs
    ("NÙkhlx<+", "छत्तीसगढ़"),
    ("Ñf\"k", "कृषि"),
    ("m|ksx", "उद्योग"),
    ("pêðkuksa", "चट्टानों"),
    ("mís';", "उद्देश्य"),
    ("fcØh", "बिक्री"),
    ("fpfÉr", "चिह्नित"),
    ("áwel", "ह्यूमस"),
    ("czãiq=k", "ब्रह्मपुत्र"),
    ("ân;", "हृदय"),
    ("Írq", "ऋतु"),
    ("eq[;r%", "मुख्यतः"),
    ("lalkèku", "संसाधन"),
    ("MªSxuÝykbZ", "ड्रैगनफ्लाई"),
]


@pytest.mark.parametrize("legacy,expected", CASES)
def test_book_phrases_convert(legacy, expected):
    assert to_unicode(legacy) == expected


def test_a_free_standing_percent_is_a_colon():
    assert to_unicode("iQksu % 011") == "फोन : 011"


def test_font_detection():
    assert is_legacy_font("BMNCFG+Walkman-Chanakya905Normal")
    assert is_legacy_font("WalkmanChanakya901Normal")
    assert is_legacy_font("Kruti Dev 010")
    assert not is_legacy_font("Arial")
    assert not is_legacy_font("BMNCFG+NeoMitraBold")
    assert not is_legacy_font("")
