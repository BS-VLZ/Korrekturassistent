from __future__ import annotations

import json
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .app import KorrekturApp
from .source_text import extract_source_text
from .agent_profile import load_profile, save_profile, profile_path


class ProjektApp(KorrekturApp):
    def __init__(self) -> None:
        self.attachments = {"aufgabenstellung": "", "erwartungshorizont": ""}
        self.attachment_text = {"aufgabenstellung": "", "erwartungshorizont": ""}
        self.chat_log: list[tuple[str, str]] = []
        super().__init__()

    def _build(self) -> None:
        super()._build()
        self.layout.forget(self.sidebar)
        menu = __import__("tkinter").Menu(self)
        file_menu = __import__("tkinter").Menu(menu, tearoff=False)
        file_menu.add_command(label="Neues Klausurprojekt ...", command=self.new_project)
        file_menu.add_command(label="OCR-PDFs laden ...", command=self.add_scans)
        file_menu.add_separator()
        file_menu.add_command(label="Projektdatei öffnen ...", command=self.open_project_file)
        file_menu.add_command(label="Projektdatei speichern unter ...", command=self.save_project_file)
        file_menu.add_command(label="Projekt beenden und archivieren", command=self.archive_project)
        menu.add_cascade(label="Datei", menu=file_menu)
        settings_menu = __import__("tkinter").Menu(menu, tearoff=False)
        settings_menu.add_command(label="KI-Modell auswählen ...", command=self.edit_model)
        settings_menu.add_command(label="Agentenauftrag und Verhalten ...", command=self.edit_agent_profile)
        menu.add_cascade(label="Optionen", menu=settings_menu)
        self.configure(menu=menu)
        line = ttk.Frame(self.project_tab)
        line.pack(fill="x", before=self.project_details)
        ttk.Button(line, text="Aufgabenstellung aus Word/PDF verknüpfen", command=lambda: self.choose_attachment("aufgabenstellung")).pack(side="left")
        ttk.Button(line, text="Erwartungshorizont aus Word/PDF verknüpfen", command=lambda: self.choose_attachment("erwartungshorizont")).pack(side="left", padx=8)
        ttk.Button(line, text="Verknüpfungen entfernen", command=self.clear_attachments).pack(side="left")
        self.model = __import__("tkinter").StringVar(value="Standard")

    def edit_model(self) -> None:
        dialog = __import__("tkinter").Toplevel(self)
        dialog.title("KI-Modell")
        dialog.geometry("360x150")
        ttk.Label(dialog, text="Modell für Korrektur und Diskussion").pack(anchor="w", padx=12, pady=(14, 5))
        choice = ttk.Combobox(dialog, state="readonly", values=("Standard", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"), textvariable=self.model, width=24)
        choice.pack(anchor="w", padx=12)
        ttk.Button(dialog, text="Übernehmen", command=dialog.destroy).pack(anchor="e", padx=12, pady=14)

    def edit_agent_profile(self) -> None:
        dialog = __import__("tkinter").Toplevel(self)
        dialog.title("Agentenauftrag und Verhalten")
        dialog.geometry("820x620")
        ttk.Label(dialog, text="Diese Vorgaben gelten für Chat und Korrekturvorschläge. Sie werden lokal in agent.md gespeichert.", wraplength=760).pack(anchor="w", padx=12, pady=(12, 6))
        editor = __import__("tkinter").Text(dialog, wrap="word")
        editor.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        editor.insert("1.0", load_profile())
        def save() -> None:
            save_profile(editor.get("1.0", "end"))
            dialog.destroy()
            messagebox.showinfo("Agentenauftrag", f"Gespeichert in {profile_path()}")
        ttk.Button(dialog, text="Speichern", command=save).pack(anchor="e", padx=12, pady=(0, 12))
    def clear_attachments(self) -> None:
        if not messagebox.askyesno("Verknüpfungen entfernen", "Aufgabenstellung und Erwartungshorizont aus Word/PDF wirklich aus diesem Projekt entfernen?"):
            return
        self.attachments = {"aufgabenstellung": "", "erwartungshorizont": ""}
        self.attachment_text = {"aufgabenstellung": "", "erwartungshorizont": ""}
        if self.project_id is not None:
            self.store.update_attachments(self.project_id, self.attachments)
            self.show_project(self.project_id)
        messagebox.showinfo("Verknüpfungen", "Die Dateiverknüpfungen wurden entfernt. Die Originaldateien bleiben erhalten.")
    def choose_attachment(self, kind: str) -> None:
        path = filedialog.askopenfilename(title="Datei auswählen", filetypes=[("Word oder PDF", "*.docx *.pdf")])
        if not path: return
        try:
            self.attachment_text[kind] = extract_source_text(path)
            self.attachments[kind] = path
            if self.project_id is not None:
                self.store.update_attachments(self.project_id, self.attachments)
                self.show_project(self.project_id)
            messagebox.showinfo("Verknüpfung", f"{Path(path).name} wurde ausgelesen und mit diesem Projekt verknüpft.")
        except Exception as exc: messagebox.showerror("Datei", str(exc))

    def show_project(self, project_id: int) -> None:
        project = self.store.project(project_id)
        self.attachments = {"aufgabenstellung": "", "erwartungshorizont": ""} | project.get("anhaenge", {})
        self.attachment_text = {"aufgabenstellung": "", "erwartungshorizont": ""}
        for kind, linked in self.attachments.items():
            if linked and Path(linked).exists():
                try:
                    self.attachment_text[kind] = extract_source_text(linked)
                except Exception:
                    self.attachment_text[kind] = ""
        super().show_project(project_id)
        self.header_title.configure(text=f"Korrekturassistent - {project['titel']}")
    def save_project_file(self) -> None:
        if self.project_id is None:
            messagebox.showinfo("Projektdatei", "Wählen Sie zuerst ein Klausurprojekt aus.")
            return
        project = self.store.project(self.project_id)
        base = Path(__file__).resolve().parents[2] / "data" / "Projekte" / "".join(char if char.isalnum() or char in " _-" else "_" for char in project["titel"])
        base.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(title="Projektdatei speichern", initialdir=base, initialfile="projekt.korrproj", defaultextension=".korrproj", filetypes=[("Korrekturprojekt", "*.korrproj")])
        if not path: return
        data = {"version": 1, "projekt": self.store.project(self.project_id), "scans": [{"pfad": row[1]} for row in self.store.scans(self.project_id)], "anhaenge": self.attachments, "chat": self.chat_log}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        Path(path).with_suffix(".chat.md").write_text("\n\n".join(f"## {role}\n\n{text}" for role, text in self.chat_log), encoding="utf-8")
        messagebox.showinfo("Projektdatei", "Projektdatei und Chat-Verlauf wurden gespeichert.")

    def archive_project(self) -> None:
        if self.project_id is None:
            messagebox.showinfo("Archiv", "Wählen Sie zuerst ein Klausurprojekt aus.")
            return
        project = self.store.project(self.project_id)
        name = "".join(char if char.isalnum() or char in " _-" else "_" for char in project["titel"])
        folder = Path(__file__).resolve().parents[2] / "data" / "Archiv" / name
        folder.mkdir(parents=True, exist_ok=True)
        report = [f"# Archiv {project['titel']}", "", "## Aufgaben", ""]
        for task in project["aufgaben"]:
            report.append(f"- Aufgabe {task['nummer']}: maximal {task['max_punkte']} Punkte, Bewertung {task['gewichtung']}")
        report.extend(["", "## Korrekturvorschläge", ""])
        for scan_id, path, status in self.store.scans(self.project_id):
            report.append(f"### {Path(path).name} - {status}")
            for task, points, reason, unclear in self.store.suggestions(scan_id):
                report.append(f"- Aufgabe {task}: {points} Punkte - {reason}" + (f" (Prüfhinweis: {unclear})" if unclear else ""))
        (folder / "abschlussbericht.md").write_text("\n".join(report), encoding="utf-8")
        (folder / "chat.md").write_text("\n\n".join(f"## {role}\n\n{text}" for role, text in self.chat_log), encoding="utf-8")
        self.chat_log = []
        messagebox.showinfo("Archiv", "Abschlussbericht und Chat-Verlauf wurden im Archiv gespeichert. Der laufende Chat wurde geleert.")
    def open_project_file(self) -> None:
        path = filedialog.askopenfilename(title="Projektdatei öffnen", filetypes=[("Korrekturprojekt", "*.korrproj")])
        if not path: return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        project = data["projekt"]
        self.project_id = self.store.create_project(project["titel"], project["klausurtext"], project["aufgaben"])
        self.attachments = data.get("anhaenge", self.attachments)
        self.store.update_attachments(self.project_id, self.attachments)
        for kind, linked in self.attachments.items():
            if linked and Path(linked).exists(): self.attachment_text[kind] = extract_source_text(linked)
        for scan in data.get("scans", []):
            if Path(scan["pfad"]).exists(): self.store.add_scan(self.project_id, scan["pfad"], __import__("korrekturassistent.ocr", fromlist=["extract_pdf_text"]).extract_pdf_text(scan["pfad"]))
        self.chat_log = [tuple(entry) for entry in data.get("chat", [])]
        for role, text in self.chat_log: self._add_chat(f"{role}: {text}\n\n", save=False)
        self.refresh_projects(); self.show_project(self.project_id)

    def grade_payload(self) -> dict:
        project = self.store.project(self.project_id)
        project["klausurtext"] += "\n\nVerknüpfte Aufgabenstellung:\n" + self.attachment_text["aufgabenstellung"] + "\n\nVerknüpfter Erwartungshorizont:\n" + self.attachment_text["erwartungshorizont"]
        return project

    def grade_model(self) -> str | None:
        return None if self.model.get() == "Standard" else self.model.get()
    def _add_chat(self, text: str, save: bool = True) -> None:
        if save and ": " in text:
            role, body = text.strip().split(": ", 1)
            self.chat_log.append((role, body))

def main() -> None:
    ProjektApp().mainloop()


if __name__ == "__main__":
    main()
