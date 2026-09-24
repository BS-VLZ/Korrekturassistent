from __future__ import annotations


IHK_BEREICHE = (
    (92.0, "Note 1 - sehr gut"),
    (81.0, "Note 2 - gut"),
    (67.0, "Note 3 - befriedigend"),
    (50.0, "Note 4 - ausreichend"),
    (30.0, "Note 5 - mangelhaft"),
    (0.0, "Note 6 - ungenügend"),
)


def ihk_note(erreichte_punkte: float, maximale_punkte: float) -> tuple[float, str]:
    if maximale_punkte <= 0:
        raise ValueError("Die maximale Punktzahl muss größer als null sein.")
    prozent = max(0.0, min(100.0, erreichte_punkte / maximale_punkte * 100.0))
    for grenze, note in IHK_BEREICHE:
        if prozent >= grenze:
            return prozent, note
    raise AssertionError("Notenbereich fehlt")
