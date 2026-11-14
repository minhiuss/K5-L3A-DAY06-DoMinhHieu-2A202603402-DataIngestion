"""Read and normalize source data. TODO: implement functions."""
from pathlib import Path
from pypdf import PdfReader
from .models import DocumentPage
import unicodedata


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical page; keep its page number and source.

    Detect and record pages with no text. OCR, when needed, is a separate step.
    """

    pages = []
    empty = []
    with PdfReader(path) as reader:
        for number, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ""
            if not extracted:
                empty.append(number)
            pages.append(
                DocumentPage(
                    document_id=document_id,
                    source=source,
                    page=number,
                    text=extracted,
                )
            )
    print(f"{len(pages)} pages read, empty: {empty}")
    return pages

def normalize_text(text: str) -> str:
    """TODO: normalize Unicode and whitespace without discarding useful structure."""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("’", "'").replace("‘", "'").replace('“', '"').replace('”', '"')
    clean = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if line == "Access for free at openstax.org": 
            continue
        clean.append(line)
    return "\n".join(clean)


SECTIONS = {
    "3.1 Navigating Microsoft Word": "microsoft_word",
    "3.2 Formatting Document Layout in Microsoft Word": "microsoft_word",
    "3.3 Formatting Document Content in Microsoft Word": "microsoft_word",
    "3.4 Collaborative Editing and Reviewing in Microsoft Word": "microsoft_word",
    "3.5 Document Design": "general",
    "3.6 Navigating Google Docs": "google_docs",
    "3.7 Formatting Layout and Content in Google Docs": "google_docs",
    "3.8 Collaborative Editing and Reviewing in Google Docs": "google_docs",
    "3.9 Versions and Version History": "general",
}


def add_section_metadata(pages: list[DocumentPage]) -> list[DocumentPage]:
    """Split pages at section headings and tag each part with its section and platform.

    Expects pages that are already normalized. A page holding two sections becomes
    two parts with the same page number.
    """
    parts = []
    section, platform = "intro", "general"
    for page in pages:
        lines = []
        for line in page.text.splitlines():
            if line in SECTIONS:
                if lines:
                    parts.append(DocumentPage(
                        document_id=page.document_id,
                        source=page.source,
                        page=page.page,
                        text="\n".join(lines),
                        metadata={"section": section, "platform": platform},
                    ))
                    lines = []
                section = line[:3]
                platform = SECTIONS[line]
            lines.append(line)
        if lines:
            parts.append(DocumentPage(
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text="\n".join(lines),
                metadata={"section": section, "platform": platform},
            ))
    return parts



    
