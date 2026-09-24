from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

from .ocr import extract_pdf_text


def extract_source_text(path: str) -> str:
    source = Path(path)
    if source.suffix.lower() == ".pdf":
        return extract_pdf_text(str(source))
    if source.suffix.lower() == ".docx":
        with ZipFile(source) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for paragraph in root.iter(namespace + "p"):
            text = "".join(node.text or "" for node in paragraph.iter(namespace + "t"))
            if text.strip():
                paragraphs.append(text.strip())
        return "\n".join(paragraphs)
    raise ValueError("Erlaubt sind PDF- und Word-Dateien (.docx).")
