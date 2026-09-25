from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class ProjektStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projekt (
                    id INTEGER PRIMARY KEY,
                    titel TEXT NOT NULL,
                    klausurtext TEXT NOT NULL DEFAULT '',
                    aufgaben_json TEXT NOT NULL DEFAULT '[]',
                    erstellt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(projekt)")}
            if "anhaenge_json" not in columns:
                conn.execute("ALTER TABLE projekt ADD COLUMN anhaenge_json TEXT NOT NULL DEFAULT '{}'")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan (
                    id INTEGER PRIMARY KEY,
                    projekt_id INTEGER NOT NULL,
                    pfad TEXT NOT NULL,
                    ocr_text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'offen',
                    FOREIGN KEY(projekt_id) REFERENCES projekt(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vorschlag (
                    id INTEGER PRIMARY KEY,
                    scan_id INTEGER NOT NULL,
                    aufgabe TEXT NOT NULL,
                    punkte REAL,
                    begruendung TEXT NOT NULL,
                    unsicherheiten TEXT NOT NULL DEFAULT '',
                    erstellt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(scan_id) REFERENCES scan(id)
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(vorschlag)")}
            if "seite" not in columns:
                conn.execute("ALTER TABLE vorschlag ADD COLUMN seite INTEGER")
            if "textstelle" not in columns:
                conn.execute("ALTER TABLE vorschlag ADD COLUMN textstelle TEXT NOT NULL DEFAULT ''")
            if "max_punkte" not in columns:
                conn.execute("ALTER TABLE vorschlag ADD COLUMN max_punkte REAL")
            if "kriterien_json" not in columns:
                conn.execute("ALTER TABLE vorschlag ADD COLUMN kriterien_json TEXT NOT NULL DEFAULT '[]'")

    def _connect(self):
        return sqlite3.connect(self.database)

    def create_project(self, titel: str, klausurtext: str, aufgaben: list[dict]) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO projekt(titel, klausurtext, aufgaben_json) VALUES (?, ?, ?)",
                (titel, klausurtext, json.dumps(aufgaben, ensure_ascii=False)),
            )
            return int(cursor.lastrowid)

    def delete_project(self, project_id: int) -> None:
        with self._connect() as conn:
            scan_ids = [row[0] for row in conn.execute("SELECT id FROM scan WHERE projekt_id = ?", (project_id,))]
            for scan_id in scan_ids:
                conn.execute("DELETE FROM vorschlag WHERE scan_id = ?", (scan_id,))
            conn.execute("DELETE FROM scan WHERE projekt_id = ?", (project_id,))
            conn.execute("DELETE FROM projekt WHERE id = ?", (project_id,))

    def delete_scan(self, scan_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM vorschlag WHERE scan_id = ?", (scan_id,))
            conn.execute("DELETE FROM scan WHERE id = ?", (scan_id,))
    def projects(self) -> list[tuple]:
        with self._connect() as conn:
            return conn.execute("SELECT id, titel FROM projekt ORDER BY id DESC").fetchall()

    def project(self, project_id: int) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT id, titel, klausurtext, aufgaben_json, anhaenge_json FROM projekt WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise KeyError(project_id)
        return {"id": row[0], "titel": row[1], "klausurtext": row[2], "aufgaben": json.loads(row[3]), "anhaenge": json.loads(row[4] or "{}")}

    def update_attachments(self, project_id: int, attachments: dict[str, str]) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE projekt SET anhaenge_json = ? WHERE id = ?", (json.dumps(attachments, ensure_ascii=False), project_id))

    def add_scan(self, project_id: int, path: str, text: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute("INSERT INTO scan(projekt_id, pfad, ocr_text) VALUES (?, ?, ?)", (project_id, path, text))
            return int(cursor.lastrowid)

    def scans(self, project_id: int) -> list[tuple]:
        with self._connect() as conn:
            return conn.execute("SELECT id, pfad, status FROM scan WHERE projekt_id = ? ORDER BY id", (project_id,)).fetchall()

    def scan(self, scan_id: int) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT id, pfad, ocr_text FROM scan WHERE id = ?", (scan_id,)).fetchone()
        if not row:
            raise KeyError(scan_id)
        return {"id": row[0], "pfad": row[1], "ocr_text": row[2]}

    def update_scan_status(self, scan_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE scan SET status = ? WHERE id = ?", (status, scan_id))

    def replace_suggestions(self, scan_id: int, suggestions: list[dict]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM vorschlag WHERE scan_id = ?", (scan_id,))
            conn.executemany(
                "INSERT INTO vorschlag(scan_id, aufgabe, punkte, max_punkte, begruendung, unsicherheiten, seite, textstelle, kriterien_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(scan_id, item["aufgabe"], item.get("punkte"), item.get("max_punkte"), item["begruendung"], item.get("unsicherheiten", ""), item.get("seite"), item.get("textstelle", ""), json.dumps(item.get("kriterien", []), ensure_ascii=False)) for item in suggestions],
            )
            conn.execute("UPDATE scan SET status = 'in Prüfung' WHERE id = ?", (scan_id,))

    def suggestions(self, scan_id: int) -> list[tuple]:
        with self._connect() as conn:
            return conn.execute("SELECT aufgabe, punkte, begruendung, unsicherheiten FROM vorschlag WHERE scan_id = ? ORDER BY id", (scan_id,)).fetchall()

    def suggestion_details(self, scan_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT aufgabe, punkte, max_punkte, begruendung, unsicherheiten, seite, textstelle, kriterien_json FROM vorschlag WHERE scan_id = ? ORDER BY id", (scan_id,)).fetchall()
        return [
            {"aufgabe": row[0], "punkte": row[1], "max_punkte": row[2], "begruendung": row[3], "unsicherheiten": row[4], "seite": row[5], "textstelle": row[6], "kriterien": json.loads(row[7] or "[]")}
            for row in rows
        ]

    def suggestion_anchors(self, scan_id: int) -> dict[str, tuple[int | None, str]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT aufgabe, seite, textstelle FROM vorschlag WHERE scan_id = ? ORDER BY id", (scan_id,)).fetchall()
        return {row[0]: (row[1], row[2]) for row in rows}

    def update_suggestion(self, scan_id: int, aufgabe: str, punkte: float, begruendung: str, unsicherheiten: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE vorschlag SET punkte = ?, begruendung = ?, unsicherheiten = ? WHERE scan_id = ? AND aufgabe = ?",
                (punkte, begruendung, unsicherheiten, scan_id, aufgabe),
            )

