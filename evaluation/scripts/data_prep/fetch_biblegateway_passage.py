#!/usr/bin/env python3
"""Download one English passage into the MCQ passage dataset.

Example:
    python evaluation/scripts/data_prep/fetch_biblegateway_passage.py "Micah 5:4-20"

The default output for that command is
``evaluation/datasets/mcq/passages/mich_5_4-20.txt``. BibleGateway does not
offer a public API, so this script reads the passage page intended for a web
browser. If BibleGateway changes its markup, the script fails instead of
silently writing an empty or unrelated page.

``--version BSB`` uses the Berean Bible project's official verse-by-verse text
download instead. BibleGateway does not currently host BSB; passing BSB to its
``version`` parameter silently falls back to an empty NIV lookup page.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


PASSAGE_RE = re.compile(
    r"^\s*(?P<book>(?:[1-3]\s*)?[A-Za-z]+(?:\s+[A-Za-z]+)*)\s+"
    r"(?P<chapter>\d+)\s*:\s*(?P<start>\d+)"
    r"(?:\s*[-–—]\s*(?:(?P<end_chapter>\d+)\s*:\s*)?(?P<end>\d+))?\s*$"
)
URL = "https://www.biblegateway.com/passage/"
BSB_URL = "https://bereanbible.com/bsb.txt"
DEFAULT_OUT_DIR = Path("evaluation/datasets/mcq/passages")

# Filename abbreviations are deliberately explicit and stable. The Micah
# spelling follows the dataset convention requested for this script.
BOOK_ABBREVIATIONS = {
    "genesis": "gen", "exodus": "exod", "leviticus": "lev",
    "numbers": "num", "deuteronomy": "deut", "joshua": "josh",
    "judges": "judg", "ruth": "ruth", "1 samuel": "1sam",
    "2 samuel": "2sam", "1 kings": "1kgs", "2 kings": "2kgs",
    "1 chronicles": "1chr", "2 chronicles": "2chr", "ezra": "ezra",
    "nehemiah": "neh", "esther": "esth", "job": "job", "psalm": "ps",
    "psalms": "ps", "proverbs": "prov", "ecclesiastes": "eccl",
    "song of solomon": "song", "song of songs": "song", "isaiah": "isa",
    "jeremiah": "jer", "lamentations": "lam", "ezekiel": "ezek",
    "daniel": "dan", "hosea": "hos", "joel": "joel", "amos": "amos",
    "obadiah": "obad", "jonah": "jonah", "micah": "mich", "nahum": "nah",
    "habakkuk": "hab", "zephaniah": "zeph", "haggai": "hag",
    "zechariah": "zech", "malachi": "mal", "matthew": "matt",
    "mark": "mark", "luke": "luke", "john": "john", "acts": "acts",
    "romans": "rom", "1 corinthians": "1cor", "2 corinthians": "2cor",
    "galatians": "gal", "ephesians": "eph", "philippians": "phil",
    "colossians": "col", "1 thessalonians": "1thess",
    "2 thessalonians": "2thess", "1 timothy": "1tim", "2 timothy": "2tim",
    "titus": "titus", "philemon": "phlm", "hebrews": "heb", "james": "jas",
    "1 peter": "1pet", "2 peter": "2pet", "1 john": "1john",
    "2 john": "2john", "3 john": "3john", "jude": "jude",
    "revelation": "rev",
}


def parse_reference(reference: str) -> tuple[str, int, int, int, int]:
    match = PASSAGE_RE.fullmatch(reference)
    if not match:
        raise ValueError('reference must look like "Micah 5:4-20"')
    book = re.sub(r"\s+", " ", match.group("book")).lower()
    if book not in BOOK_ABBREVIATIONS:
        raise ValueError(f"unknown Bible book: {match.group('book')}")
    chapter = int(match.group("chapter"))
    start = int(match.group("start"))
    end_chapter = int(match.group("end_chapter") or chapter)
    end = int(match.group("end") or start)
    if chapter < 1 or start < 1 or end_chapter < chapter or end < 1:
        raise ValueError("chapters and verses must be positive and in ascending order")
    if end_chapter == chapter and end < start:
        raise ValueError("ending verse must not precede starting verse")
    return book, chapter, start, end_chapter, end


def output_name(book: str, chapter: int, start: int, end_chapter: int, end: int) -> str:
    if chapter == end_chapter:
        verses = str(start) if start == end else f"{start}-{end}"
        return f"{BOOK_ABBREVIATIONS[book]}_{chapter}_{verses}.txt"
    return f"{BOOK_ABBREVIATIONS[book]}_{chapter}_{start}-{end_chapter}_{end}.txt"


class PassageParser(HTMLParser):
    """Collect visible text from BibleGateway's passage-content container."""

    BLOCK_TAGS = {"br", "div", "h1", "h2", "h3", "h4", "p"}
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    SKIP_CLASSES = {
        "crossreference", "crossrefs", "footnote", "footnotes", "full-chap-link", "passage-other-trans",
        "passage-tools", "publisher-info-bottom", "translation-name",
    }
    END_SECTIONS = {"footnotes", "cross references"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.container_depth = 0
        self.skip_depth = 0
        self.finished = False
        self.parts: list[str] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = dict(attrs).get("class") or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        if self.finished:
            return
        if not self.container_depth and "passage-content" in classes:
            self.container_depth = 1
            return
        if not self.container_depth:
            return
        if tag not in self.VOID_TAGS:
            self.container_depth += 1
        if self.skip_depth:
            if tag not in self.VOID_TAGS:
                self.skip_depth += 1
            return
        if classes & self.SKIP_CLASSES or (tag == "sup" and "versenum" not in classes):
            self.skip_depth = 1
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.container_depth and tag in self.BLOCK_TAGS and not self.skip_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.finished or not self.container_depth:
            return
        if self.skip_depth:
            self.skip_depth -= 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        self.container_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.container_depth and not self.skip_depth:
            if data.strip().lower() in self.END_SECTIONS:
                self.finished = True
                return
            self.parts.append(data)

    def text(self) -> str:
        raw = html.unescape("".join(self.parts)).replace("\xa0", " ")
        lines = []
        for line in raw.splitlines():
            line = re.sub(r"[ \t]+", " ", line).strip()
            if line:
                lines.append(line)
        return "\n\n".join(lines).strip() + "\n" if lines else ""


def fetch(reference: str, version: str, timeout: float) -> tuple[str, str]:
    query = urllib.parse.urlencode({"search": reference, "version": version})
    url = f"{URL}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "eten-evaluation-passage-fetch/1.0",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode(response.headers.get_content_charset() or "utf-8")
    parser = PassageParser()
    parser.feed(body)
    text = parser.text()
    if not text:
        raise RuntimeError("BibleGateway returned no passage text; its page markup may have changed")
    return text, url


def fetch_bsb_corpus(timeout: float) -> str:
    """Download the official public-domain BSB verse-by-verse text."""
    request = urllib.request.Request(
        BSB_URL,
        headers={"User-Agent": "eten-evaluation-passage-fetch/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")


def parse_bsb_corpus(text: str) -> dict[tuple[str, int, int], str]:
    """Index ``Book C:V<TAB>text`` rows from the official BSB text file."""
    verses: dict[tuple[str, int, int], str] = {}
    row_re = re.compile(r"^(.+?)\s+(\d+):(\d+)\t(.+)$")
    for line in text.splitlines():
        match = row_re.match(line.strip())
        if not match:
            continue
        book = re.sub(r"\s+", " ", match.group(1)).lower()
        key = (book, int(match.group(2)), int(match.group(3)))
        if key in verses:
            raise RuntimeError(f"duplicate verse in BSB corpus: {match.group(1)} {match.group(2)}:{match.group(3)}")
        verses[key] = match.group(4).strip()
    if len(verses) < 30_000:
        raise RuntimeError(
            f"official BSB download yielded only {len(verses)} verse rows"
        )
    return verses


def extract_bsb_passage(
    reference: str, verses: dict[tuple[str, int, int], str]
) -> tuple[str, str]:
    """Render a requested range in the numeric format used by Tier-1 parsers."""
    book, chapter, start, end_chapter, end = parse_reference(reference)
    selected = [
        (ch, verse, value)
        for (row_book, ch, verse), value in verses.items()
        if row_book == book
        and (ch > chapter or verse >= start)
        and (ch < end_chapter or verse <= end)
        and chapter <= ch <= end_chapter
    ]
    selected.sort(key=lambda row: (row[0], row[1]))
    if not selected:
        raise RuntimeError(f"official BSB download contains no verses for {reference}")
    if selected[0][:2] != (chapter, start) or selected[-1][:2] != (end_chapter, end):
        raise RuntimeError(
            f"incomplete BSB range for {reference}: "
            f"got {selected[0][0]}:{selected[0][1]}-{selected[-1][0]}:{selected[-1][1]}"
        )

    rendered = []
    previous_chapter = None
    for ch, verse, value in selected:
        # BibleGateway prints a chapter number in place of verse 1. The Tier-1
        # verse indexers deliberately understand that format, including chapter
        # restarts in cross-chapter passages.
        marker = str(ch) if verse == 1 and ch != previous_chapter else str(verse)
        rendered.append(f"{marker} {value}")
        previous_chapter = ch
    return "\n\n".join(rendered) + "\n", BSB_URL


def references_from_csv(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "reference" not in reader.fieldnames:
            raise ValueError(f"{path} must contain a 'reference' column")
        references = [(row.get("reference") or "").strip() for row in reader]
    if not references or any(not reference for reference in references):
        raise ValueError(f"{path} contains no references or has a blank reference")
    return references


def destination_for(reference: str, out_dir: Path) -> Path:
    book, chapter, start, end_chapter, end = parse_reference(reference)
    return out_dir / output_name(book, chapter, start, end_chapter, end)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", nargs="?", help='Bible reference, e.g. "Micah 5:4-20"')
    parser.add_argument("--csv", type=Path, dest="csv_path",
                        help="fetch every value in the CSV's 'reference' column")
    parser.add_argument("--version", default="NIV", help="BibleGateway version (default: NIV)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--force", action="store_true", help="overwrite an existing passage")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="seconds between CSV requests (default: 1.0)")
    args = parser.parse_args()
    if bool(args.reference) == bool(args.csv_path):
        parser.error("provide either one reference or --csv, but not both")
    if args.sleep < 0:
        parser.error("--sleep cannot be negative")

    try:
        references = references_from_csv(args.csv_path) if args.csv_path else [args.reference]
        # Validate the entire input before making any network requests.
        destinations = [destination_for(reference, args.out_dir) for reference in references]
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = skipped = failed = 0
    bsb_verses = None
    if args.version.upper() == "BSB":
        try:
            bsb_verses = parse_bsb_corpus(fetch_bsb_corpus(args.timeout))
        except (OSError, RuntimeError, urllib.error.URLError) as exc:
            print(f"error: could not download official BSB text: {exc}", file=sys.stderr)
            return 1
    for index, (reference, destination) in enumerate(zip(references, destinations)):
        if destination.exists() and not args.force:
            print(f"skip: {destination} (already exists)")
            skipped += 1
            continue
        if index and args.csv_path and args.sleep:
            time.sleep(args.sleep)
        try:
            if bsb_verses is not None:
                passage, source_url = extract_bsb_passage(reference, bsb_verses)
            else:
                passage, source_url = fetch(reference, args.version, args.timeout)
            destination.write_text(passage, encoding="utf-8")
        except (OSError, RuntimeError, urllib.error.URLError) as exc:
            print(f"error: {reference}: {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"wrote: {destination}")
        print(f"source: {source_url}")
        written += 1

    if args.csv_path:
        print(f"done: {written} written, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
