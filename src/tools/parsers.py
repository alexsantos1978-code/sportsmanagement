from __future__ import annotations
from pathlib import Path
from pypdf import PdfReader
from docx import Document


def extract_text_from_pdf(path: str) -> str:
    reader = PdfReader(path)
    chunks = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def extract_text_from_docx(path: str) -> str:
    doc = Document(path)
    return "\n".join([p.text for p in doc.paragraphs]).strip()


def extract_text_from_file(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    if ext == ".docx":
        return extract_text_from_docx(path)
    if ext == ".txt":
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported contract format: {ext}")