from __future__ import annotations

from pathlib import Path
import fitz


def extract_pdf_text(path: str) -> str:
    document = fitz.open(Path(path))
    try:
        parts: list[str] = []
        for page_number, page in enumerate(document, start=1):
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda item: (round(item[1], 1), item[0]))
            content = "\n".join(block[4].strip() for block in blocks if block[4].strip())
            parts.append(f"[Seite {page_number}]\n{content}")
        return "\n\n".join(parts)
    finally:
        document.close()

