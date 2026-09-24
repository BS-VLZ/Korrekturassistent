from __future__ import annotations

from pathlib import Path
import fitz


def page_count(path: str) -> int:
    document = fitz.open(path)
    try:
        return len(document)
    finally:
        document.close()


def render_page(path: str, page_number: int, target: Path, zoom: float = 1.35) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open(path)
    try:
        page = document.load_page(page_number - 1)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pixmap.save(target)
        return target
    finally:
        document.close()


def export_comment_pdf(ocr_path: str, suggestions: list[tuple], anchors: dict[str, tuple[int | None, str]], destination: Path) -> Path:
    """Erstellt eine seitenidentische PDF mit anklickbaren Kommentaren als eigene PDF-Ebene."""
    document = fitz.open(ocr_path)
    try:
        for task, points, reason, uncertain in suggestions:
            page_number, text_anchor = anchors.get(task, (None, ""))
            if not page_number or not 1 <= page_number <= len(document):
                continue
            page = document.load_page(page_number - 1)
            location = fitz.Point(18, 18)
            if text_anchor:
                matches = page.search_for(text_anchor)
                if matches:
                    location = matches[0].tl
            note = f"Aufgabe {task}: {points} Punkte\n\n{reason}"
            if uncertain:
                note += f"\n\nPrüfhinweis: {uncertain}"
            annotation = page.add_text_annot(location, note, icon="Comment")
            annotation.set_info(title=f"Korrekturvorschlag – Aufgabe {task}", subject="Korrekturhinweis")
            annotation.update()
        destination.parent.mkdir(parents=True, exist_ok=True)
        document.save(destination, garbage=4, deflate=True)
        return destination
    finally:
        document.close()

