from __future__ import annotations

from pathlib import Path
import pymupdf


def page_count(path: str) -> int:
    document = pymupdf.open(path)
    try:
        return len(document)
    finally:
        document.close()


def render_page(path: str, page_number: int, target: Path, zoom: float = 1.35) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(path)
    try:
        page = document.load_page(page_number - 1)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        pixmap.save(target)
        return target
    finally:
        document.close()
