"""Reference-resolution tool backed by SGML metadata and Perseus canonical texts."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .registry import ToolSpec

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_NORMALIZATION_RE = re.compile(r"[.]+")
_NON_ALNUM_RE = re.compile(r"[^0-9A-Za-z]+")
_BIBLE_REFERENCE_RE = re.compile(
    r"^\s*(?:[1-3]\s*)?[A-Za-z][A-Za-z.\s]+?\s+\d+:\d+(?:[-,]\d+)?\s*$",
    re.IGNORECASE,
)
_CLASSICAL_REFERENCE_RE = re.compile(
    r"^\s*[A-Za-z][A-Za-z.\s]+?\s+\d+\.\d+(?:[-,]\d+)?\s*$",
    re.IGNORECASE,
)

_RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_PERSEUS_NS = "http://www.perseus.org/meta/perseus.rdfs#"
_TEI_NS = "http://www.tei-c.org/ns/1.0"
_TEI = {"tei": _TEI_NS}

_DEFAULT_REMOTE_TIMEOUT_SECONDS = 4.0
_DEFAULT_GREEKLIT_RAW_BASE_URL = (
    "https://raw.githubusercontent.com/PerseusDL/canonical-greekLit/master"
)

# Offline fixtures keep tests hermetic and give the live agent a small fallback
# when neither a local corpus nor the remote canonical XML is reachable.
_EMBEDDED_CANONICAL_XML: dict[str, str] = {
    "abo:tlg,0031,002": """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text xml:lang="grc">
    <body>
      <div type="edition" xml:lang="grc" n="urn:cts:greekLit:tlg0031.tlg002.perseus-grc2">
        <head>ΚΑΤΑ ΜΑΡΚΟΝ</head>
        <div type="textpart" subtype="chapter" n="1">
          <div type="textpart" subtype="verse" n="1">
            <p>ΑΡΧΗ τοῦ εὐαγγελίου Ἰησοῦ Χριστοῦ .</p>
          </div>
          <div type="textpart" subtype="verse" n="2">
            <p>Καθὼς γέγραπται ἐν τῷ Ἠσαίᾳ τῷ προφήτῃ.</p>
          </div>
        </div>
      </div>
    </body>
  </text>
</TEI>
""",
    "abo:tlg,0031,004": """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text xml:lang="grc">
    <body>
      <div type="edition" xml:lang="grc" n="urn:cts:greekLit:tlg0031.tlg004.perseus-grc2">
        <head>ΚΑΤΑ ΙΩΑΝΗΝ</head>
        <div type="textpart" subtype="chapter" n="1">
          <div type="textpart" subtype="verse" n="1">
            <p>ΕΝ ΑΡΧΗ ἦν ὁ λόγος, καὶ ὁ λόγος ἦν πρὸς τὸν θεόν, καὶ θεὸς ἦν ὁ λόγος.</p>
          </div>
          <div type="textpart" subtype="verse" n="2">
            <p>οὗτος ἦν ἐν ἀρχῇ πρὸς τὸν θεόν.</p>
          </div>
        </div>
      </div>
    </body>
  </text>
</TEI>
""",
    "abo:tlg,0012,001": """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text xml:lang="grc">
    <body>
      <div type="edition" n="urn:cts:greekLit:tlg0012.tlg001.perseus-grc2" xml:lang="grc">
        <div type="textpart" subtype="Book" n="1">
          <l n="1">μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος</l>
          <l n="2">οὐλομένην, ἣ μυρίʼ Ἀχαιοῖς ἄλγεʼ ἔθηκε,</l>
          <l n="3">πολλὰς δʼ ἰφθίμους ψυχὰς Ἄϊδι προΐαψεν</l>
        </div>
      </div>
    </body>
  </text>
</TEI>
""",
}

_EMBEDDED_PASSAGE_TRANSLATIONS: dict[str, str] = {
    "mark 1:1": "The beginning of the gospel of Jesus Christ.",
    "mark 1:2": "Just as it is written in Isaiah the prophet.",
    "john 1:1": "In the beginning was the Word, and the Word was with God, and the Word was God.",
    "john 1:2": "He was in the beginning with God.",
    "iliad 1.1": "Sing, goddess, of the wrath of Achilles son of Peleus.",
    "iliad 1.2": "The accursed wrath that brought countless sufferings upon the Achaeans.",
    "iliad 1.3": "And sent many valiant souls of heroes down to Hades.",
}


@dataclass(frozen=True)
class WorkMetadata:
    abo_id: str
    title: str
    creator: str | None


@dataclass(frozen=True)
class CatalogTextRecord:
    abo_id: str
    about: str
    book: str | None
    language: str | None
    local_rel_path: str | None


@dataclass(frozen=True)
class CatalogBundle:
    alias_to_abo: dict[str, str]
    works_by_abo: dict[str, WorkMetadata]
    records_by_abo: dict[str, tuple[CatalogTextRecord, ...]]


@dataclass(frozen=True)
class ParsedReference:
    citation_kind: str
    work_alias: str
    first: tuple[int, int]
    end: tuple[int, int] | None


def looks_like_reference_request(text: str) -> bool:
    compact = _compact_text(text)
    if not compact:
        return False
    return bool(_BIBLE_REFERENCE_RE.match(compact) or _CLASSICAL_REFERENCE_RE.match(compact))


def normalize_reference(reference: str, work: str | None = None) -> str:
    parsed = _parse_reference(reference, work=work)
    work_meta = _resolve_work_metadata(parsed.work_alias)
    label = _canonical_work_label(work_meta)

    start_major, start_minor = parsed.first
    if parsed.citation_kind == "chapter_verse":
        citation = f"{start_major}:{start_minor}"
        if parsed.end is not None:
            end_major, end_minor = parsed.end
            if end_major == start_major:
                citation = f"{citation}-{end_minor}"
            else:
                citation = f"{citation}-{end_major}:{end_minor}"
    else:
        citation = f"{start_major}.{start_minor}"
        if parsed.end is not None:
            end_major, end_minor = parsed.end
            if end_major == start_major:
                citation = f"{citation}-{end_minor}"
            else:
                citation = f"{citation}-{end_major}.{end_minor}"

    return f"{label} {citation}".strip()


def execute_resolve_reference_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    reference = str(arguments.get("reference", "")).strip()
    if not reference:
        raise ValueError("resolve_reference requires a non-empty 'reference' argument")

    work_value = arguments.get("work")
    work = str(work_value).strip() if work_value is not None else None
    preferred_translation_language_value = arguments.get("preferred_translation_language")
    preferred_translation_language = (
        str(preferred_translation_language_value).strip()
        if preferred_translation_language_value is not None
        else "English"
    )

    try:
        parsed = _parse_reference(reference, work=work)
        work_meta = _resolve_work_metadata(parsed.work_alias)
    except ValueError as exc:
        return {
            "tool": "resolve_reference",
            "status": "not_found",
            "reference": reference,
            "normalized_reference": _best_effort_normalized_reference(reference, work=work),
            "message": str(exc),
            "next_prompt": "Ask the learner to paste the passage text or show it on camera.",
        }

    normalized_reference = normalize_reference(reference, work=work)
    extracted = _resolve_passage_text(work_meta, parsed)
    if extracted is None:
        message = (
            f"I recognized {work_meta.title}, but I could not load {normalized_reference} from the "
            "available local or remote corpus sources."
        )
        return {
            "tool": "resolve_reference",
            "status": "not_found",
            "reference": reference,
            "normalized_reference": normalized_reference,
            "work": work_meta.title,
            "abo_id": work_meta.abo_id,
            "message": message,
            "next_prompt": "Ask the learner to paste the Greek text or show it on camera.",
        }

    cts_passage = _build_cts_passage_ref(parsed)
    cts_urn = f"{extracted['work_urn']}:{cts_passage}"
    return {
        "tool": "resolve_reference",
        "status": "ok",
        "reference": reference,
        "normalized_reference": normalized_reference,
        "work": work_meta.title,
        "creator": work_meta.creator,
        "abo_id": work_meta.abo_id,
        "source": extracted["source"],
        "source_detail": extracted["source_detail"],
        "passage_kind": _passage_kind_for_citation(parsed.citation_kind),
        "resolved_text": extracted["resolved_text"],
        "greek_text": extracted["resolved_text"],
        "translation": _EMBEDDED_PASSAGE_TRANSLATIONS.get(normalized_reference.casefold()),
        "preferred_translation_language": preferred_translation_language,
        "citation_confidence": "high",
        "cts_urn": cts_urn,
        "next_prompt": "Ask whether the learner wants the tutor to read it aloud or parse the first clause.",
    }


def build_reference_resolution_tool() -> ToolSpec:
    return ToolSpec(
        name="resolve_reference",
        description="Resolve a passage reference into actual source text for live tutoring.",
        notes=(
            "Uses the local SGML/Perseus metadata catalog for work resolution, then loads passage text "
            "from local texts when available or canonical Greek XML when necessary."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reference": {"type": "string"},
                "work": {"type": "string"},
                "preferred_translation_language": {"type": "string"},
            },
            "required": ["reference"],
        },
        status="ready",
    )


def _resolve_passage_text(work_meta: WorkMetadata, parsed: ParsedReference) -> dict[str, str] | None:
    for record in _candidate_catalog_records(work_meta.abo_id):
        for local_path in _candidate_local_paths(record):
            xml_text = _read_local_text(local_path)
            if xml_text is None:
                continue
            extracted = _extract_passage_from_xml(
                xml_text,
                parsed,
                source="sgml_local_texts",
                source_detail=str(local_path),
            )
            if extracted is not None:
                return extracted

    if _reference_remote_enabled():
        for url in _candidate_remote_urls(work_meta.abo_id):
            xml_text = _fetch_remote_text(url)
            if xml_text is None:
                continue
            extracted = _extract_passage_from_xml(
                xml_text,
                parsed,
                source="perseus_canonical_greeklit",
                source_detail=url,
            )
            if extracted is not None:
                return extracted

    embedded_xml = _EMBEDDED_CANONICAL_XML.get(work_meta.abo_id)
    if embedded_xml is not None:
        return _extract_passage_from_xml(
            embedded_xml,
            parsed,
            source="embedded_reference_fixture",
            source_detail=work_meta.abo_id,
        )

    return None


def _extract_passage_from_xml(
    xml_text: str,
    parsed: ParsedReference,
    *,
    source: str,
    source_detail: str,
) -> dict[str, str] | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    edition = root.find(".//tei:div[@type='edition']", _TEI)
    work_urn = edition.attrib.get("n", "") if edition is not None else ""
    if parsed.citation_kind == "chapter_verse":
        resolved_text = _extract_chapter_verse_text(root, parsed)
    else:
        resolved_text = _extract_book_line_text(root, parsed)

    if not resolved_text:
        return None

    return {
        "resolved_text": resolved_text,
        "source": source,
        "source_detail": source_detail,
        "work_urn": work_urn,
    }


def _extract_chapter_verse_text(root: ET.Element, parsed: ParsedReference) -> str | None:
    chapter, verse = parsed.first
    end_chapter, end_verse = parsed.end or parsed.first
    if end_chapter != chapter:
        return None

    chapter_node = root.find(
        f".//tei:div[@type='textpart'][@subtype='chapter'][@n='{chapter}']",
        _TEI,
    )
    if chapter_node is None:
        return None

    verses: list[str] = []
    for current_verse in range(verse, end_verse + 1):
        verse_node = chapter_node.find(
            f"./tei:div[@type='textpart'][@subtype='verse'][@n='{current_verse}']",
            _TEI,
        )
        if verse_node is None:
            return None
        verse_text = _collapse_xml_text(verse_node)
        if not verse_text:
            return None
        verses.append(verse_text)

    return "\n".join(verses)


def _extract_book_line_text(root: ET.Element, parsed: ParsedReference) -> str | None:
    book, line = parsed.first
    end_book, end_line = parsed.end or parsed.first
    if end_book != book:
        return None

    book_node = root.find(
        f".//tei:div[@type='textpart'][@n='{book}']",
        _TEI,
    )
    if book_node is None:
        return None

    lines: list[str] = []
    for current_line in range(line, end_line + 1):
        line_node = book_node.find(f".//tei:l[@n='{current_line}']", _TEI)
        if line_node is None:
            return None
        line_text = _collapse_xml_text(line_node)
        if not line_text:
            return None
        lines.append(line_text)

    return "\n".join(lines)


def _collapse_xml_text(node: ET.Element) -> str:
    compact = _compact_text("".join(text for text in node.itertext()))
    return re.sub(r"\s+([.,;:?!])", r"\1", compact)


def _parse_reference(reference: str, work: str | None = None) -> ParsedReference:
    compact = _compact_text(reference)
    if ":" in compact:
        match = re.match(
            r"^(?P<book>.+?)\s+(?P<chapter>\d+):(?P<verse>\d+)(?:-(?P<end>\d+))?$",
            compact,
        )
        if not match:
            raise ValueError(f"I could not parse '{reference}' as a chapter-and-verse reference.")
        work_alias = _resolve_alias(match.group("book"), work=work)
        end_value = match.group("end")
        return ParsedReference(
            citation_kind="chapter_verse",
            work_alias=work_alias,
            first=(int(match.group("chapter")), int(match.group("verse"))),
            end=(int(match.group("chapter")), int(end_value)) if end_value else None,
        )

    match = re.match(
        r"^(?P<book>.+?)\s+(?P<section>\d+)\.(?P<line>\d+)(?:-(?P<end>\d+))?$",
        compact,
    )
    if not match:
        raise ValueError(f"I could not parse '{reference}' as a supported passage reference.")

    work_alias = _resolve_alias(match.group("book"), work=work)
    end_value = match.group("end")
    return ParsedReference(
        citation_kind="book_line",
        work_alias=work_alias,
        first=(int(match.group("section")), int(match.group("line"))),
        end=(int(match.group("section")), int(end_value)) if end_value else None,
    )


def _resolve_alias(book_text: str, work: str | None = None) -> str:
    book_alias = _normalize_alias(book_text)
    if not book_alias and work:
        book_alias = _normalize_alias(work)
    if not book_alias:
        raise ValueError("I need a recognizable work name before I can resolve the reference.")
    return book_alias


def _resolve_work_metadata(work_alias: str) -> WorkMetadata:
    bundle = _load_catalog_bundle()
    abo_id = bundle.alias_to_abo.get(work_alias)
    if abo_id is None:
        raise ValueError(f"I could not match '{work_alias}' to a work in the SGML catalog.")

    work_meta = bundle.works_by_abo.get(abo_id)
    if work_meta is not None:
        return work_meta

    human_title = work_alias.title()
    return WorkMetadata(abo_id=abo_id, title=human_title, creator=None)


def _candidate_catalog_records(abo_id: str) -> tuple[CatalogTextRecord, ...]:
    bundle = _load_catalog_bundle()
    records = list(bundle.records_by_abo.get(abo_id, ()))
    records.sort(key=_catalog_record_rank)
    return tuple(records)


def _catalog_record_rank(record: CatalogTextRecord) -> tuple[int, int]:
    language_rank = 0
    if record.language == "greek":
        language_rank = 3
    elif record.language == "english":
        language_rank = 2
    elif record.language == "latin":
        language_rank = 1

    path_rank = 0
    local_path = (record.local_rel_path or "").lower()
    if "_gk" in local_path:
        path_rank = 2
    elif "_eng" in local_path:
        path_rank = 1

    return (language_rank, path_rank)


@lru_cache(maxsize=1)
def _load_catalog_bundle() -> CatalogBundle:
    classics_path = _sgml_root() / "xml" / "classics.xml"
    if not classics_path.exists():
        return CatalogBundle(alias_to_abo={}, works_by_abo={}, records_by_abo={})

    tree = ET.parse(classics_path)
    root = tree.getroot()

    works_by_abo: dict[str, WorkMetadata] = {}
    base_paths_by_about: dict[str, tuple[str | None, str | None]] = {}
    records_by_abo: dict[str, list[CatalogTextRecord]] = {}

    for description in root.findall(f".//{{{_RDF_NS}}}Description"):
        about = description.attrib.get(f"{{{_RDF_NS}}}about", "")
        title = _first_text(description, f"{{{_DC_NS}}}title")
        creator = _first_text(description, f"{{{_DC_NS}}}creator")
        if about.startswith("Perseus:abo:") and title:
            abo_id = about.replace("Perseus:", "", 1)
            works_by_abo[abo_id] = WorkMetadata(abo_id=abo_id, title=title, creator=creator)

        text_path = _first_text(description, f"{{{_PERSEUS_NS}}}text")
        is_version_of = _first_resource(description, f"{{{_DCTERMS_NS}}}isVersionOf")
        part_of_resources = _all_resources(description, f"{{{_DCTERMS_NS}}}isPartOf")
        language = _infer_language(part_of_resources, text_path)

        if about.startswith("Perseus:text:") and text_path:
            base_paths_by_about[about] = (text_path, language)

        if not about.startswith("Perseus:text:") or not is_version_of:
            continue

        abo_id = is_version_of.replace("Perseus:", "", 1)
        base_about, _, book_fragment = about.partition(":book=")
        inherited_path, inherited_language = base_paths_by_about.get(base_about, (None, None))
        records_by_abo.setdefault(abo_id, []).append(
            CatalogTextRecord(
                abo_id=abo_id,
                about=about,
                book=book_fragment or None,
                language=language or inherited_language,
                local_rel_path=text_path or inherited_path,
            )
        )

    alias_to_abo = _load_abbreviation_aliases()
    for abo_id, work_meta in works_by_abo.items():
        alias_to_abo.setdefault(_normalize_alias(work_meta.title), abo_id)
        if work_meta.creator:
            alias_to_abo.setdefault(
                _normalize_alias(f"{work_meta.creator} {work_meta.title}"),
                abo_id,
            )
            alias_to_abo.setdefault(
                _normalize_alias(f"{work_meta.creator}, {work_meta.title}"),
                abo_id,
            )

    finalized_records = {
        abo_id: tuple(records)
        for abo_id, records in records_by_abo.items()
    }
    return CatalogBundle(
        alias_to_abo=alias_to_abo,
        works_by_abo=works_by_abo,
        records_by_abo=finalized_records,
    )


@lru_cache(maxsize=1)
def _load_abbreviation_aliases() -> dict[str, str]:
    alias_to_abo: dict[str, str] = {}
    for abb_dir in _abbreviation_directories():
        for file_name in ("bible.abb", "perseus.abb"):
            abb_path = abb_dir / file_name
            if not abb_path.exists():
                continue
            for raw_line in abb_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = raw_line.split("\t")
                if len(parts) < 3:
                    continue
                raw_alias, display_title, raw_abo_id = (
                    parts[0].strip(),
                    parts[1].strip(),
                    parts[2].strip(),
                )
                if not raw_abo_id.startswith("abo:"):
                    continue
                alias_to_abo.setdefault(_normalize_alias(raw_alias.replace("|", " ")), raw_abo_id)
                alias_to_abo.setdefault(_normalize_alias(display_title), raw_abo_id)
    return alias_to_abo


def _candidate_local_paths(record: CatalogTextRecord) -> tuple[Path, ...]:
    if not record.local_rel_path:
        return ()

    rel_path = Path(record.local_rel_path)
    sgml_root = _sgml_root()
    candidates = [
        sgml_root / "texts" / rel_path,
        sgml_root / "xml" / "texts" / rel_path,
    ]
    seen: set[Path] = set()
    unique_candidates: list[Path] = []
    for candidate in candidates:
        normalized = candidate.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_candidates.append(candidate)
    return tuple(unique_candidates)


def _candidate_remote_urls(abo_id: str) -> tuple[str, ...]:
    parsed = re.match(r"^abo:tlg,(?P<group>\d{4}),(?P<work>\d{3})$", abo_id)
    if parsed is None:
        return ()

    group = parsed.group("group")
    work = parsed.group("work")
    base_url = _remote_greeklit_raw_base_url().rstrip("/")
    candidate_suffixes = ("perseus-grc2", "perseus-grc1")
    return tuple(
        f"{base_url}/data/tlg{group}/tlg{work}/tlg{group}.tlg{work}.{suffix}.xml"
        for suffix in candidate_suffixes
    )


@lru_cache(maxsize=32)
def _fetch_remote_text(url: str) -> str | None:
    timeout = _reference_remote_timeout_seconds()
    request = Request(url, headers={"User-Agent": "ancient-greek-live-tutor/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError):
        return None


def _read_local_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _first_text(node: ET.Element, tag: str) -> str | None:
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _first_resource(node: ET.Element, tag: str) -> str | None:
    child = node.find(tag)
    if child is None:
        return None
    value = child.attrib.get(f"{{{_RDF_NS}}}resource", "").strip()
    return value or None


def _all_resources(node: ET.Element, tag: str) -> list[str]:
    resources: list[str] = []
    for child in node.findall(tag):
        resource = child.attrib.get(f"{{{_RDF_NS}}}resource", "").strip()
        if resource:
            resources.append(resource)
    return resources


def _infer_language(part_of_resources: list[str], text_path: str | None) -> str | None:
    lowered = " ".join(resource.lower() for resource in part_of_resources)
    path_lower = (text_path or "").lower()
    if "greek texts" in lowered or "_gk" in path_lower:
        return "greek"
    if "latin texts" in lowered or "_latin" in path_lower:
        return "latin"
    if "english" in path_lower or "_eng" in path_lower:
        return "english"
    return None


def _build_cts_passage_ref(parsed: ParsedReference) -> str:
    start_major, start_minor = parsed.first
    start_ref = f"{start_major}.{start_minor}"
    if parsed.end is None:
        return start_ref
    end_major, end_minor = parsed.end
    return f"{start_ref}-{end_major}.{end_minor}"


def _passage_kind_for_citation(citation_kind: str) -> str:
    if citation_kind == "chapter_verse":
        return "scripture"
    return "classical"


def _canonical_work_label(work_meta: WorkMetadata) -> str:
    return _compact_text(work_meta.title).lower()


def _best_effort_normalized_reference(reference: str, work: str | None = None) -> str:
    compact = _compact_text(reference).lower()
    compact = _PUNCT_NORMALIZATION_RE.sub(".", compact)
    return compact if work is None else f"{_compact_text(work).lower()} {compact}".strip()


def _compact_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _normalize_alias(text: str) -> str:
    compact = _NON_ALNUM_RE.sub(" ", text.replace("|", " ").replace(".", " ").lower())
    return _compact_text(compact)


def _sgml_root() -> Path:
    configured = os.getenv("TUTOR_REFERENCE_SGML_ROOT", "").strip()
    if configured:
        root = Path(configured).expanduser()
        if root.is_absolute():
            return root
        return (_project_root() / root).resolve()
    return _project_root() / "sgml"


def _abbreviation_directories() -> tuple[Path, ...]:
    bundled_dir = Path(__file__).resolve().parents[2] / "data" / "abbreviations"
    legacy_dir = _sgml_root() / "reading" / "properties" / "abbreviations"

    directories: list[Path] = []
    seen: set[Path] = set()
    for candidate in (bundled_dir, legacy_dir):
        normalized = candidate.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        directories.append(candidate)
    return tuple(directories)


def _project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "sgml").exists():
            return parent
    return current.parents[3]


def _reference_remote_enabled() -> bool:
    raw = os.getenv("TUTOR_REFERENCE_REMOTE_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _reference_remote_timeout_seconds() -> float:
    raw = os.getenv(
        "TUTOR_REFERENCE_REMOTE_TIMEOUT_SECONDS",
        str(_DEFAULT_REMOTE_TIMEOUT_SECONDS),
    ).strip()
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_REMOTE_TIMEOUT_SECONDS


def _remote_greeklit_raw_base_url() -> str:
    return os.getenv(
        "TUTOR_REFERENCE_GREEKLIT_RAW_BASE_URL",
        _DEFAULT_GREEKLIT_RAW_BASE_URL,
    ).strip() or _DEFAULT_GREEKLIT_RAW_BASE_URL
