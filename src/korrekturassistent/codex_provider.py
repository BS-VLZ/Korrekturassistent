from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .agent_profile import load_profile


SYSTEM = """Sie sind ein fachlicher Korrekturassistent. Sie erstellen begründete Vorschläge, keine endgültigen Noten. Bewerten Sie ausschließlich anhand des vorgegebenen Bewertungsrasters und berücksichtigen Sie fachlich richtige Alternativen. OCR-Unklarheiten führen nicht zu einem Punktabzug, sondern zu einer Unsicherheit.

Bewerten Sie jede Aufgabe des Bewertungsrasters genau einmal. Übernehmen Sie die maximale Punktzahl exakt aus dem Raster. Bewerten Sie inhaltlich, nicht nach bloßem Wortlaut: Konkrete, sinngleiche Schülerformulierungen zählen als erfüllt, wenn sie einen Aspekt des Erwartungshorizonts fachlich treffen. Beispiel: „Beteiligung im Angebot“ kann den Grad der Selbstständigkeit und Verantwortungsübernahme der Gruppe belegen. Führen Sie die bewerteten Teilkriterien einzeln auf: Status erfüllt, teilweise, fehlt oder unklar; eine kurze Bezeichnung; optional eine wortwörtliche Textstelle aus der OCR. Für erfüllte oder teilweise erfüllte Kriterien muss textstelle höchstens 8 Wörter lang sein und exakt aus dem OCR-Text stammen. Für den Aufgabenanker gilt dasselbe Wortlaut-Prinzip mit höchstens 18 Wörtern. Begruendung enthält zwei bis vier kurze Absätze mit Leerzeilen, die Punkteentscheidung nachvollziehbar erklären."""


class CodexProvider:
    def executable(self) -> str | None:
        npm = Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd"
        if npm.exists():
            return str(npm)
        for name in ("codex.cmd", "codex"):
            found = shutil.which(name)
            if found:
                return found
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
        if local.exists():
            candidates = sorted(local.glob("*/codex.exe"), reverse=True)
            if candidates:
                return str(candidates[0])
        return None

    def available(self) -> bool:
        return self.executable() is not None

    def command_prefix(self) -> list[str]:
        executable = self.executable()
        if not executable:
            raise RuntimeError("Codex wurde auf diesem Rechner nicht gefunden. Starten Sie Codex einmal und melden Sie sich mit 'codex login' an.")
        path = Path(executable)
        if path.suffix.lower() == ".cmd":
            script = path.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            node = shutil.which("node.exe") or shutil.which("node")
            if node and script.exists():
                return [node, str(script), "exec", "--sandbox", "read-only"]
        return [executable, "exec", "--sandbox", "read-only"]

    def _structured(self, prompt: str, schema: dict, model: str | None, filename: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="korrekturassistent-") as directory:
            work = Path(directory)
            schema_path, output_path = work / "schema.json", work / filename
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = self.command_prefix() + (["-m", model] if model else []) + ["--output-schema", str(schema_path), "-o", str(output_path), "-"]
            completed = subprocess.run(command, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=600, cwd=Path(__file__).resolve().parents[2], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or "Codex konnte keinen Korrekturvorschlag erstellen.")
            return json.loads(output_path.read_text(encoding="utf-8"))

    def prepare_rubric(self, task_text: str, horizon_text: str, model: str | None = None) -> list[dict]:
        schema = {
            "type": "object",
            "properties": {"aufgaben": {"type": "array", "minItems": 1, "items": {
                "type": "object",
                "properties": {
                    "nummer": {"type": "string"},
                    "max_punkte": {"type": "number", "exclusiveMinimum": 0},
                    "erwartung": {"type": "string"},
                    "gewichtung": {"type": "string", "enum": ["leicht", "standard", "streng"]},
                },
                "required": ["nummer", "max_punkte", "erwartung", "gewichtung"],
                "additionalProperties": False,
            }}},
            "required": ["aufgaben"],
            "additionalProperties": False,
        }
        prompt = (
            "Prüfen Sie Aufgabenstellung und Erwartungshorizont für eine spätere Klausurkorrektur. "
            "Erstellen Sie eine vollständige Liste aller bewertbaren Aufgaben. Übernehmen Sie alle im Erwartungshorizont genannten möglichen Inhalte als zulässige Aspekte; kürzen oder streichen Sie keine Alternativen. Jede Aufgabe muss ihre maximale Punktzahl "
            "exakt aus dem Erwartungshorizont übernehmen. Erfinden Sie keine Punkte. Wenn keine Maximalpunkte eindeutig "
            "erkennbar sind, liefern Sie keine Aufgabenliste.\n\nAufgabenstellung:\n" + task_text +
            "\n\nErwartungshorizont:\n" + horizon_text
        )
        tasks = self._structured(prompt, schema, model, "bewertungsraster.json")["aufgaben"]
        if not tasks or sum(float(task.get("max_punkte") or 0) for task in tasks) <= 0:
            raise RuntimeError("Im Erwartungshorizont wurden keine bewertbaren Aufgaben mit Maximalpunkten erkannt.")
        return tasks

    def grade(self, project: dict, ocr_text: str, model: str | None = None) -> list[dict]:
        payload = {
            "aufgabenstellung": project.get("aufgabenstellung", project["klausurtext"]),
            "bewertungsraster": project["aufgaben"],
            "erwartungshorizont_original": project.get("erwartungshorizont_text", ""),
            "schuelerantwort": ocr_text,
        }
        prompt = load_profile() + "\n\nSpezielle Vorgabe für Korrekturvorschläge:\n" + SYSTEM + "\n\nDaten:\n" + json.dumps(payload, ensure_ascii=False)
        criterion_schema = {
            "type": "object",
            "properties": {"kriterium": {"type": "string"}, "status": {"type": "string", "enum": ["erfüllt", "teilweise", "fehlt", "unklar"]}, "textstelle": {"type": "string"}},
            "required": ["kriterium", "status", "textstelle"], "additionalProperties": False,
        }
        suggestion_schema = {
            "type": "object",
            "properties": {
                "aufgabe": {"type": "string"}, "punkte": {"type": "number"}, "max_punkte": {"type": "number", "minimum": 0},
                "begruendung": {"type": "string"}, "unsicherheiten": {"type": "string"}, "seite": {"type": "integer", "minimum": 1},
                "textstelle": {"type": "string"}, "kriterien": {"type": "array", "items": criterion_schema},
            },
            "required": ["aufgabe", "punkte", "max_punkte", "begruendung", "unsicherheiten", "seite", "textstelle", "kriterien"],
            "additionalProperties": False,
        }
        schema = {"type": "object", "properties": {"vorschlaege": {"type": "array", "minItems": 1, "items": suggestion_schema}}, "required": ["vorschlaege"], "additionalProperties": False}
        suggestions = self._structured(prompt, schema, model, "vorschlag.json")["vorschlaege"]
        expected = sum(float(task.get("max_punkte") or 0) for task in project["aufgaben"])
        reported = sum(float(item.get("max_punkte") or 0) for item in suggestions)
        if len(suggestions) != len(project["aufgaben"]) or expected <= 0 or abs(expected - reported) > 0.1:
            raise RuntimeError(f"Die KI hat den Bewertungsraster unvollständig übernommen ({len(suggestions)} statt {len(project['aufgaben'])} Aufgaben; {reported:g} statt {expected:g} Maximalpunkte).")
        return suggestions

    def discuss(self, context: str, instruction: str, model: str | None = None) -> str:
        prompt = load_profile() + "\n\nVerfügbarer Kontext:\n" + context + "\n\nNachricht:\n" + instruction
        completed = subprocess.run(self.command_prefix() + (["-m", model] if model else []) + ["-"], input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=600, cwd=Path(__file__).resolve().parents[2], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Codex konnte die Frage nicht beantworten.")
        return completed.stdout.strip()
