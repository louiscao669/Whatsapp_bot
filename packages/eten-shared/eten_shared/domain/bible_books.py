"""Bible book names: normalisation and lookup from QA items.

Regular passage translations are stored per (language, name, chapter); the
book was implicit because the regular flow only ever carried Luke. Once QA
items from other books (the tier-1 pilot set: Judges, Kings, Acts, ...) share
the qa_items table, matching on chapter:verse alone pairs e.g. a Judges 9
question with a Luke 9 translation. These helpers give both sides a comparable
book code.

Canonical code = the English book name in lower case ("luke", "2 kings").
"""

import re

# A translation uploaded before ``passage_translations.book`` existed has no
# book. The regular (non-experiment) flow only ever carried Luke, so a NULL
# book is read as Luke.
LEGACY_TRANSLATION_BOOK = "luke"

# (canonical name, USFM code, extra aliases used in this project / common usage)
_BOOKS = [
    ("genesis", "gen", ["gn"]), ("exodus", "exo", ["exod", "ex"]),
    ("leviticus", "lev", []), ("numbers", "num", []), ("deuteronomy", "deu", ["deut", "dt"]),
    ("joshua", "jos", ["josh"]), ("judges", "jdg", ["judg", "jdgs"]), ("ruth", "rut", ["rth"]),
    ("1 samuel", "1sa", ["1sam"]), ("2 samuel", "2sa", ["2sam"]),
    ("1 kings", "1ki", ["1kgs", "1kin"]), ("2 kings", "2ki", ["2kgs", "2kin"]),
    ("1 chronicles", "1ch", ["1chr", "1chron"]), ("2 chronicles", "2ch", ["2chr", "2chron"]),
    ("ezra", "ezr", []), ("nehemiah", "neh", []), ("esther", "est", ["esth"]),
    ("job", "job", []), ("psalms", "psa", ["ps", "psalm", "pss"]), ("proverbs", "pro", ["prov", "prv"]),
    ("ecclesiastes", "ecc", ["eccl", "qoh"]), ("song of songs", "sng", ["song", "songofsolomon", "sos"]),
    ("isaiah", "isa", []), ("jeremiah", "jer", []), ("lamentations", "lam", []),
    ("ezekiel", "ezk", ["ezek"]), ("daniel", "dan", []), ("hosea", "hos", []), ("joel", "jol", []),
    ("amos", "amo", []), ("obadiah", "oba", ["obad"]), ("jonah", "jon", []), ("micah", "mic", []),
    ("nahum", "nam", ["nah"]), ("habakkuk", "hab", []), ("zephaniah", "zep", ["zeph"]),
    ("haggai", "hag", []), ("zechariah", "zec", ["zech"]), ("malachi", "mal", []),
    ("matthew", "mat", ["matt", "mt"]), ("mark", "mrk", ["mk", "mar"]), ("luke", "luk", ["lk"]),
    ("john", "jhn", ["jn", "joh"]), ("acts", "act", []), ("romans", "rom", []),
    ("1 corinthians", "1co", ["1cor"]), ("2 corinthians", "2co", ["2cor"]),
    ("galatians", "gal", []), ("ephesians", "eph", []), ("philippians", "php", ["phil"]),
    ("colossians", "col", []), ("1 thessalonians", "1th", ["1thess"]),
    ("2 thessalonians", "2th", ["2thess"]), ("1 timothy", "1ti", ["1tim"]),
    ("2 timothy", "2ti", ["2tim"]), ("titus", "tit", []), ("philemon", "phm", ["phlm"]),
    ("hebrews", "heb", []), ("james", "jas", []), ("1 peter", "1pe", ["1pet"]),
    ("2 peter", "2pe", ["2pet"]), ("1 john", "1jn", ["1john"]), ("2 john", "2jn", ["2john"]),
    ("3 john", "3jn", ["3john"]), ("jude", "jud", []), ("revelation", "rev", ["rv"]),
]


def _squash(value):
    return re.sub(r"[\s._\-]+", "", str(value or "").strip().lower())


_ALIASES = {}
for _name, _usfm, _extra in _BOOKS:
    for _alias in (_name, _usfm, *_extra):
        _ALIASES[_squash(_alias)] = _name
# Roman-numeral and "first/second" spellings of numbered books.
for _name, _, _ in _BOOKS:
    if _name[0] in "123" and _name[1] == " ":
        _rest = _squash(_name[2:])
        for _prefix in {"1": ("i", "first"), "2": ("ii", "second"), "3": ("iii", "third")}[_name[0]]:
            _ALIASES.setdefault(_prefix + _rest, _name)


def normalize_book(value):
    """Canonical book name for a name/abbreviation, or None if unknown."""
    key = _squash(value)
    if not key:
        return None
    return _ALIASES.get(key)


_REFERENCE_BOOK = re.compile(r"^(?P<book>.*?\S)\s+\d+:\d+")
_PASSAGE_ID_BOOK = re.compile(r"^(?P<book>\d?[a-z]+)")


def qa_item_book(qa_item):
    """Book of a QA item from its reference ("Judges 9:1-57") or passage id.

    Passage ids seen in this project: ``luke2``, ``luke-2-4``, ``t1_judg9``,
    ``uw-t1_2kgs6_7:sz5j``, ``hard66/t1_judg9``. Returns None when neither
    names a known book (e.g. a bare "2:4" reference with an opaque id).
    """
    reference = str(getattr(qa_item, "passage_reference", None) or "").strip()
    match = _REFERENCE_BOOK.match(reference)
    if match:
        book = normalize_book(match.group("book"))
        if book:
            return book

    passage_id = str(getattr(qa_item, "passage_id", None) or "").strip().lower()
    passage_id = passage_id.rsplit("/", 1)[-1]
    for prefix in ("uw-", "t1_"):
        if passage_id.startswith(prefix):
            passage_id = passage_id[len(prefix):]
    match = _PASSAGE_ID_BOOK.match(passage_id)
    if match:
        return normalize_book(match.group("book"))
    return None
