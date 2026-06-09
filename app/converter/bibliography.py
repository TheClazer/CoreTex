r"""BibTeX extraction (v2 roadmap: full BibTeX extraction).

Word stores managed references in a Sources part — either
``word/bibliography/sources.xml`` or a ``customXml`` item — using the
``http://schemas.openxmlformats.org/officeDocument/2006/bibliography``
namespace. Each ``b:Source`` carries a ``b:Tag`` (the citation key Word uses
internally) plus typed fields (author, title, year, publisher, …).

This module turns that part into:
  * a real ``.bib`` file (so the v1 "plain-text fallback" becomes proper
    ``\cite{key}`` + a bibliography), and
  * a ``{tag: bibkey}`` map the parser uses to resolve each in-text
    ``CITATION`` field to its key.

Everything degrades gracefully: a document with no Sources part yields an
empty result and the renderer keeps its plain-text citation behaviour.
"""

from __future__ import annotations

import logging
import zipfile
from io import BytesIO
from typing import Dict, List, Optional

from lxml import etree

logger = logging.getLogger(__name__)

_B_NS = "http://schemas.openxmlformats.org/officeDocument/2006/bibliography"


def _b(tag: str) -> str:
    return f"{{{_B_NS}}}{tag}"


# Word SourceType -> BibTeX entry type. Word's vocabulary is small and fixed.
_TYPE_MAP = {
    "JournalArticle": "article",
    "ArticleInAPeriodical": "article",
    "Book": "book",
    "BookSection": "incollection",
    "ConferenceProceedings": "inproceedings",
    "Report": "techreport",
    "Thesis": "phdthesis",
    "DocumentFromInternetSite": "misc",
    "InternetSite": "misc",
    "Misc": "misc",
    "Patent": "misc",
}


def _clean_key(raw: str, used: set) -> str:
    """Make a unique, BibTeX-legal citation key from Word's tag."""
    key = "".join(ch for ch in (raw or "") if ch.isalnum() or ch in "-_") or "ref"
    # BibTeX keys can't start with a digit comfortably; prefix if so.
    if key[0].isdigit():
        key = f"ref{key}"
    candidate = key
    n = 2
    while candidate in used:
        candidate = f"{key}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def _authors(source) -> str:
    """Render the b:Author/b:NameList into 'Last, First and Last, First'."""
    names: List[str] = []
    author_el = source.find(_b("Author"))
    if author_el is None:
        return ""
    # Could be Author/Author/NameList, or Author/Corporate.
    corporate = author_el.find(f".//{_b('Corporate')}")
    if corporate is not None and corporate.text:
        return f"{{{corporate.text.strip()}}}"
    for person in author_el.findall(f".//{_b('Person')}"):
        last = person.find(_b("Last"))
        first = person.find(_b("First"))
        middle = person.find(_b("Middle"))
        last_t = (last.text or "").strip() if last is not None else ""
        first_parts = [
            p.text.strip()
            for p in (first, middle)
            if p is not None and p.text and p.text.strip()
        ]
        first_t = " ".join(first_parts)
        if last_t and first_t:
            names.append(f"{last_t}, {first_t}")
        elif last_t:
            names.append(last_t)
    return " and ".join(names)


def _field(source, *tags) -> Optional[str]:
    for tag in tags:
        el = source.find(_b(tag))
        if el is not None and el.text and el.text.strip():
            return el.text.strip()
    return None


def _escape_bib(value: str) -> str:
    """Minimal BibTeX value escaping (braces balanced by callers)."""
    return value.replace("\\", r"\textbackslash{}").replace("{", r"\{").replace("}", r"\}")


class BibEntry:
    __slots__ = ("key", "entry_type", "fields")

    def __init__(self, key: str, entry_type: str, fields: Dict[str, str]):
        self.key = key
        self.entry_type = entry_type
        self.fields = fields

    def to_bibtex(self) -> str:
        lines = [f"@{self.entry_type}{{{self.key},"]
        for name, value in self.fields.items():
            if value:
                lines.append(f"  {name} = {{{value}}},")
        lines.append("}")
        return "\n".join(lines)


class Bibliography:
    """Result of extracting Word sources: entries + tag→key resolution."""

    def __init__(self) -> None:
        self.entries: List[BibEntry] = []
        self._tag_to_key: Dict[str, str] = {}

    @property
    def is_empty(self) -> bool:
        return not self.entries

    def key_for_tag(self, tag: Optional[str]) -> Optional[str]:
        if not tag:
            return None
        return self._tag_to_key.get(tag)

    def to_bibtex(self) -> str:
        return "\n\n".join(e.to_bibtex() for e in self.entries) + ("\n" if self.entries else "")


def _find_sources_xml(docx_bytes: bytes) -> Optional[bytes]:
    """Locate the bibliography sources XML inside the .docx zip."""
    with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
        names = zf.namelist()
        # Canonical location first.
        for candidate in ("word/bibliography/sources.xml",):
            if candidate in names:
                return zf.read(candidate)
        # Otherwise scan customXml items for the bibliography namespace.
        for name in names:
            if name.startswith("customXml/") and name.endswith(".xml"):
                try:
                    blob = zf.read(name)
                except KeyError:
                    continue
                if _B_NS.encode() in blob:
                    return blob
    return None


def extract_bibliography(docx_bytes: bytes) -> Bibliography:
    """Parse Word's Sources part into a Bibliography (empty if absent)."""
    bib = Bibliography()
    try:
        sources_xml = _find_sources_xml(docx_bytes)
    except (zipfile.BadZipFile, OSError) as e:  # pragma: no cover - defensive
        logger.warning("Could not read .docx for bibliography: %s", e)
        return bib
    if not sources_xml:
        return bib

    try:
        root = etree.fromstring(sources_xml)
    except etree.XMLSyntaxError as e:  # pragma: no cover - defensive
        logger.warning("Bibliography XML did not parse: %s", e)
        return bib

    used_keys: set = set()
    for source in root.findall(f".//{_b('Source')}"):
        tag = _field(source, "Tag")
        key = _clean_key(tag or _field(source, "Title") or "ref", used_keys)
        if tag:
            bib._tag_to_key[tag] = key

        src_type = _field(source, "SourceType") or "Misc"
        entry_type = _TYPE_MAP.get(src_type, "misc")

        fields: Dict[str, str] = {}
        authors = _authors(source)
        if authors:
            fields["author"] = authors
        title = _field(source, "Title", "BookTitle")
        if title:
            fields["title"] = _escape_bib(title)
        journal = _field(source, "JournalName", "PeriodicalTitle")
        if journal:
            fields["journal"] = _escape_bib(journal)
        booktitle = _field(source, "ConferenceName", "BookTitle")
        if booktitle and entry_type in ("inproceedings", "incollection"):
            fields["booktitle"] = _escape_bib(booktitle)
        year = _field(source, "Year")
        if year:
            fields["year"] = year
        publisher = _field(source, "Publisher")
        if publisher:
            fields["publisher"] = _escape_bib(publisher)
        volume = _field(source, "Volume")
        if volume:
            fields["volume"] = volume
        number = _field(source, "Issue")
        if number:
            fields["number"] = number
        pages = _field(source, "Pages")
        if pages:
            fields["pages"] = pages.replace("-", "--")
        doi = _field(source, "DOI")
        if doi:
            fields["doi"] = doi
        url = _field(source, "URL")
        if url:
            fields["url"] = url

        bib.entries.append(BibEntry(key=key, entry_type=entry_type, fields=fields))

    if bib.entries:
        logger.info("Extracted %d bibliography source(s)", len(bib.entries))
    return bib
