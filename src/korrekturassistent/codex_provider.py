from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .agent_profile import load_profile


SYSTEM = """Sie sind ein fachlicher Korrekturassistent. Sie erstellen nur Vorschläge, keine endgültigen Noten. Bewerten Sie ausschließlich anhand des Erwartungshorizonts. Berücksichtigen Sie alternative fachlich richtige Formulierungen. OCR-Unklarheiten führen nicht zu einem Punktabzug, sondern zu einer Unsicherheit. Antworten Sie ausschließlich als JSON-Array: [{\"aufgabe\": \"...\", \"punkte\": Zahl, \"begruendung\": \"...\", \"unsicherheiten\": \"...\"}]."""


class CodexProvider:
    def executable(self) -> str | None:
        # Die npm-CLI läuft unsichtbar im Hintergrund. Die Desktop-Datei codex.exe kann ein störendes Fenster öffnen.
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
        return [executable, "exec", "--sandbox", "read-only"]

    def grade(self, project: dict, ocr_text: str, model: str | None = None) -> list[dict]:
        payload = {
            "klausur": project["klausurtext"],
            "erwartungshorizont": project["aufgaben"],
            "schuelerantwort": ocr_text,
        }
        prompt = load_profile() + "\n\nSpezielle Vorgabe für Korrekturvorschläge:\n" + SYSTEM + "\n\nDaten:\n" + json.dumps(payload, ensure_ascii=False)
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "aufgabe": {"type": "string"}, "punkte": {"type": "number"},
                    "begruendung": {"type": "string"}, "unsicherheiten": {"type": "string"},
                    "seite": {"type": "integer", "minimum": 1}, "textstelle": {"type": "string"},
                },
                "required": ["aufgabe", "punkte", "begruendung", "unsicherheiten", "seite", "textstelle"],
                "additionalProperties": False,
            },
        }
        with tempfile.TemporaryDirectory(prefix="korrekturassistent-") as directory:
            work = Path(directory)
            schema_path = work / "schema.json"
            output_path = work / "vorschlag.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = self.command_prefix() + (["-m", model] if model else []) + ["--output-schema", str(schema_path), "-o", str(output_path), "-"]
            completed = subprocess.run(command, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=600, cwd=Path(__file__).resolve().parents[2], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or "Codex konnte keinen Korrekturvorschlag erstellen.")
            return json.loads(output_path.read_text(encoding="utf-8"))

    def discuss(self, context: str, instruction: str, model: str | None = None) -> str:
        prompt = load_profile() + "\n\nVerfügbarer Kontext:\n" + context + "\n\nNachricht:\n" + instruction
        completed = subprocess.run(self.command_prefix() + (["-m", model] if model else []) + ["-"], input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=600, cwd=Path(__file__).resolve().parents[2], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Codex konnte die Frage nicht beantworten.")
        return completed.stdout.strip()







