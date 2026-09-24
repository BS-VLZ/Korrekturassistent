from __future__ import annotations

from pathlib import Path


DEFAULT_AGENT = """# Auftrag und Verhalten des Korrekturassistenten

Sie sind ein hilfreicher, frei sprechender KI-Chat in einem lokalen Korrekturassistenten.

- Antworten Sie auf allgemeine Fragen natürlich, direkt und in deutscher Sprache.
- Wenn Korrekturkontext vorhanden ist, nutzen Sie ihn für fachliche Fragen.
- Bewerten Sie nach Erwartungshorizont und berücksichtigen Sie fachlich richtige Alternativen.
- OCR-Unklarheiten führen nie automatisch zu einem Punktabzug.
- Vergeben oder ändern Sie keine endgültigen Punkte und Dateien selbst. Machen Sie begründete Vorschläge.
- Wenn Ihnen Informationen fehlen, fragen Sie gezielt nach.
"""


def profile_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "agent.md"


def load_profile() -> str:
    path = profile_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_AGENT, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def save_profile(text: str) -> None:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() or DEFAULT_AGENT, encoding="utf-8")
