from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß0-9]+", text.lower())


def find_similarity_hints(scans: list[tuple[int, str, str]], length: int = 12) -> list[dict]:
    """Findet längere wortgleiche Passagen. Häufige Klausurteile in mehr als zwei Arbeiten werden ignoriert."""
    shingles: dict[str, set[int]] = defaultdict(set)
    names: dict[int, str] = {}
    for scan_id, name, text in scans:
        names[scan_id] = name
        words = _words(text)
        for index in range(max(0, len(words) - length + 1)):
            shingles[" ".join(words[index:index + length])].add(scan_id)
    pairs: dict[tuple[int, int], str] = {}
    for passage, owners in shingles.items():
        if len(owners) != 2:
            continue
        left, right = sorted(owners)
        key = (left, right)
        if key not in pairs:
            pairs[key] = passage
    return [
        {"left_id": left, "right_id": right, "left_name": names[left], "right_name": names[right], "passage": passage, "words": len(passage.split())}
        for (left, right), passage in pairs.items()
    ]
