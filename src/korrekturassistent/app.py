from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .codex_provider import CodexProvider
from .ocr import extract_pdf_text
from .store import ProjektStore
from .grade import ihk_note
from .review_window import ReviewWindow


class KorrekturApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Korrekturassistent")
        self.geometry("1240x800")
        root = Path(__file__).resolve().parents[2]
        self.store = ProjektStore(root / "data" / "korrekturassistent.sqlite")
        self.provider = CodexProvider()
        self.project_id: int | None = None
        self.scan_id: int | None = None
        self._build()
        self.refresh_projects()

    def _build(self) -> None:
        header = ttk.Frame(self, padding=10)
        header.pack(fill="x")
        self.header_title = ttk.Label(header, text="Korrekturassistent", font=("Segoe UI", 18, "bold"))
        self.header_title.pack(side="left")
        text = "ChatGPT-Plus / Codex bereit" if self.provider.available() else "Codex nicht gefunden – Anmeldung über Codex CLI erforderlich"
        ttk.Label(header, text=text).pack(side="right")
        layout = ttk.Panedwindow(self, orient="horizontal")
        self.layout = layout
        layout.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        left, right = ttk.Frame(layout, padding=8), ttk.Frame(layout, padding=8)
        self.sidebar = left
        layout.add(left, weight=1)
        layout.add(right, weight=3)
        ttk.Button(left, text="Neues Klausurprojekt", command=self.new_project).pack(fill="x")
        ttk.Label(left, text="Klausurprojekte", padding=(0, 10, 0, 2)).pack(anchor="w")
        self.projects = tk.Listbox(left, exportselection=False)
        self.projects.pack(fill="both", expand=True)
        self.projects.bind("<<ListboxSelect>>", self.select_project)
        ttk.Button(left, text="Klausurprojekt löschen", command=self.delete_project).pack(fill="x", pady=(5, 0))
        ttk.Label(left, text="Geladene Klausuren", padding=(0, 10, 0, 2)).pack(anchor="w")
        self.scans = tk.Listbox(left, height=10, exportselection=False)
        self.scans.pack(fill="x")
        self.scans.bind("<<ListboxSelect>>", self.select_scan)
        ttk.Button(left, text="Ausgewählte Klausur löschen", command=self.delete_scan).pack(fill="x", pady=(5, 0))
        ttk.Button(left, text="OCR-PDFs laden", command=self.add_scans).pack(fill="x", pady=(5, 0))
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)
        self.project_tab, self.suggestion_tab = (ttk.Frame(self.notebook, padding=12) for _ in range(2))
        self.notebook.add(self.project_tab, text="Klausur und Erwartungshorizont")
        self.notebook.add(self.suggestion_tab, text="Korrekturvorschlag")
        self._build_project_tab()
        self._build_suggestion_tab()

    def _build_project_tab(self) -> None:
        ttk.Label(self.project_tab, text="Projektunterlagen", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(self.project_tab, text="Aufgabenstellung und Erwartungshorizont sind als verknüpfte Word- oder PDF-Dateien hinterlegt. Die KI liest sie beim Erstellen des Korrekturvorschlags aus.", wraplength=1000).pack(anchor="w", pady=(4, 12))
        self.project_details = ttk.Label(self.project_tab, text="Noch keine Projektunterlagen verknüpft.", justify="left", wraplength=1000)
        self.project_details.pack(anchor="w", pady=(4, 0))

    def _build_suggestion_tab(self) -> None:
        controls = ttk.Frame(self.suggestion_tab)
        controls.pack(fill="x")
        ttk.Label(controls, text="OCR-Klausur:").pack(side="left")
        self.scan_selector = ttk.Combobox(controls, state="readonly", width=36)
        self.scan_selector.pack(side="left", padx=(5, 10))
        self.scan_selector.bind("<<ComboboxSelected>>", self.select_scan_from_selector)
        self.grade_button = ttk.Button(controls, text="Korrekturvorschlag erzeugen", command=self.grade)
        self.grade_button.pack(side="left")
        ttk.Button(controls, text="Korrekturarbeitsplatz öffnen", command=self.open_review).pack(side="left", padx=(8, 0))
        self.result_status = ttk.Label(controls, text="Wählen Sie eine geladene Klausur aus.")
        self.result_status.pack(side="left", padx=10)
        ttk.Label(self.suggestion_tab, text="Nach dem Erzeugen öffnet sich die Korrekturansicht automatisch. Dort bearbeiten und diskutieren Sie jeden einzelnen Korrekturhinweis direkt neben der PDF-Seite.", wraplength=1050).pack(anchor="w", pady=(18, 8))
        self.grade_summary = ttk.Label(self.suggestion_tab, text="Notenberechnung: Noch keine Korrekturvorschläge vorhanden.", font=("Segoe UI", 10, "bold"))
        self.grade_summary.pack(anchor="w", pady=(4, 0))

    def new_project(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Neues Klausurprojekt")
        dialog.geometry("680x200")
        dialog.transient(self)
        ttk.Label(dialog, text="Titel der Klausur").pack(anchor="w", padx=12, pady=(16, 4))
        title = ttk.Entry(dialog)
        title.pack(fill="x", padx=12)
        ttk.Label(dialog, text="Nach dem Anlegen verknüpfen Sie Aufgabenstellung und Erwartungshorizont als Word- oder PDF-Datei im geöffneten Projekt.", wraplength=620).pack(anchor="w", padx=12, pady=(12, 8))
        def save() -> None:
            if not title.get().strip():
                messagebox.showerror("Projekt", "Bitte geben Sie einen Klausurtitel ein.", parent=dialog)
                return
            new_project_id = self.store.create_project(title.get().strip(), "", [])
            dialog.destroy()
            self.refresh_projects()
            self.show_project(new_project_id)
        ttk.Button(dialog, text="Projekt anlegen", command=save).pack(anchor="e", padx=12, pady=12)
    def delete_project(self) -> None:
        if self.project_id is None:
            messagebox.showinfo("Löschen", "Wählen Sie zuerst ein Klausurprojekt aus.")
            return
        if not messagebox.askyesno("Klausurprojekt löschen", "Projekt, geladene Klausuren und Korrekturvorschläge wirklich löschen?"):
            return
        self.store.delete_project(self.project_id)
        self.project_id = None; self.scan_id = None
        self.refresh_projects(); self.refresh_scans(); self.show_suggestions()

    def delete_scan(self) -> None:
        if self.scan_id is None:
            messagebox.showinfo("Löschen", "Wählen Sie zuerst eine geladene Klausur aus.")
            return
        if not messagebox.askyesno("Klausur löschen", "Die ausgewählte OCR-Klausur und ihre Korrekturvorschläge wirklich löschen?"):
            return
        self.store.delete_scan(self.scan_id)
        self.scan_id = None
        self.refresh_scans(); self.show_suggestions()
    def refresh_projects(self) -> None:
        self.projects.delete(0, "end")
        self.project_rows = self.store.projects()
        for project_id, title in self.project_rows:
            self.projects.insert("end", f"{project_id}: {title}")

    def select_project(self, _event=None) -> None:
        choice = self.projects.curselection()
        if not choice: return
        self.show_project(self.project_rows[choice[0]][0])

    def show_project(self, project_id: int) -> None:
        self.project_id = project_id
        project = self.store.project(self.project_id)
        attachments = project.get("anhaenge", {})
        task = Path(attachments.get("aufgabenstellung", "")).name or "nicht verknüpft"
        horizon = Path(attachments.get("erwartungshorizont", "")).name or "nicht verknüpft"
        self.project_details.configure(text=f"Aufgabenstellung: {task}\nErwartungshorizont: {horizon}")
        self.refresh_scans()

    def refresh_scans(self) -> None:
        self.scans.delete(0, "end")
        self.scan_rows = self.store.scans(self.project_id) if self.project_id else []
        for scan_id, path, status in self.scan_rows:
            self.scans.insert("end", f"{scan_id}: {Path(path).name} [{status}]")
        if hasattr(self, "scan_selector"):
            self.scan_selector["values"] = [f"{Path(path).name} [{status}]" for _scan_id, path, status in self.scan_rows]
            if self.scan_id is None:
                self.scan_selector.set("")

    def add_scans(self) -> None:
        if self.project_id is None:
            messagebox.showinfo("Klausurprojekt", "Legen Sie zuerst ein Klausurprojekt an und wählen Sie es aus.")
            return
        for path in filedialog.askopenfilenames(title="Anonymisierte OCR-PDFs auswählen", filetypes=[("PDF-Dateien", "*.pdf")]):
            try: self.store.add_scan(self.project_id, path, extract_pdf_text(path))
            except Exception as exc: messagebox.showwarning("OCR-PDF", f"{Path(path).name}: {exc}")
        self.refresh_scans()

    def select_scan_from_selector(self, _event=None) -> None:
        index = self.scan_selector.current()
        if index < 0:
            return
        self.scan_id = self.scan_rows[index][0]
        self.show_suggestions()
    def select_scan(self, _event=None) -> None:
        choice = self.scans.curselection()
        if not choice: return
        self.scan_id = self.scan_rows[choice[0]][0]
        self.show_suggestions()

    def show_suggestions(self) -> None:
        if not self.scan_id or not self.project_id:
            self.grade_summary.configure(text="Notenberechnung: Noch keine Korrekturvorschläge vorhanden.")
            return
        suggestions = self.store.suggestions(self.scan_id)
        if not suggestions:
            self.grade_summary.configure(text="Notenberechnung: Noch keine Korrekturvorschläge vorhanden.")
            return
        total = sum(float(points or 0) for _task, points, _reason, _unclear in suggestions)
        maximum = sum(float(task["max_punkte"]) for task in self.store.project(self.project_id)["aufgaben"])
        if maximum <= 0:
            self.grade_summary.configure(text=f"Zwischenstand: {total:.1f} Punkte. Die maximale Punktzahl wird erst angezeigt, wenn sie aus dem Erwartungshorizont übernommen wurde.")
            return
        percent, grade = ihk_note(total, maximum)
        self.grade_summary.configure(text=f"Zwischenstand: {total:.1f} von {maximum:.1f} Punkten ({percent:.1f} %) – {grade}")

    def open_review(self) -> None:
        if self.scan_id is None:
            messagebox.showinfo("Visuelle Prüfung", "Wählen Sie zuerst eine geladene Klausur aus.")
            return
        scan = self.store.scan(self.scan_id)
        ReviewWindow(self, scan["pfad"], self.store.suggestions(self.scan_id), self.store.suggestion_anchors(self.scan_id), Path(__file__).resolve().parents[2] / "data")
    def grade(self) -> None:
        if self.project_id is None or self.scan_id is None:
            messagebox.showinfo("Korrekturvorschlag", "Laden Sie zuerst eine OCR-Klausur über Datei > OCR-PDFs laden und wählen Sie sie oben aus.")
            return
        if not self.provider.available():
            messagebox.showerror("Codex", "Codex wurde nicht gefunden. Melden Sie sich mit 'codex login' bei Ihrem ChatGPT-Plus-Konto an.")
            return
        self.grade_button.configure(state="disabled")
        self.result_status.configure(text="Korrekturvorschlag wird erstellt …")
        def work() -> None:
            try:
                suggestion = self.provider.grade(self.store.project(self.project_id), self.store.scan(self.scan_id)["ocr_text"])
                self.store.replace_suggestions(self.scan_id, suggestion)
                self.after(0, self._graded)
            except Exception as exc: self.after(0, self._error, "Korrekturvorschlag", str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _graded(self) -> None:
        self.grade_button.configure(state="normal")
        self.result_status.configure(text="Vorschlag erstellt – bitte fachlich prüfen.")
        self.refresh_scans(); self.show_suggestions()
        self.after(200, self.open_review)

    def _error(self, title: str, detail: str) -> None:
        self.grade_button.configure(state="normal")
        self.result_status.configure(text="Korrekturvorschlag nicht erstellt.")
        messagebox.showerror(title, detail)

def main() -> None:
    KorrekturApp().mainloop()

if __name__ == "__main__": main()













