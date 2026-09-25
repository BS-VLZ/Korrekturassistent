from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .codex_provider import CodexProvider
from .grade import ihk_note
from .ocr import extract_pdf_text
from .review_window import ReviewWindow
from .similarity import find_similarity_hints
from .store import ProjektStore


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
        self._bulk_queue: list[int] = []
        self._bulk_errors: list[str] = []
        self._bulk_running = False
        self._build()
        self.refresh_projects()

    def _build(self) -> None:
        header = ttk.Frame(self, padding=10)
        header.pack(fill="x")
        self.header_title = ttk.Label(header, text="Korrekturassistent", font=("Segoe UI", 18, "bold"))
        self.header_title.pack(side="left")
        text = "ChatGPT-Plus / Codex bereit" if self.provider.available() else "Codex nicht gefunden – Anmeldung über Codex CLI erforderlich"
        ttk.Label(header, text=text).pack(side="right")
        self.layout = ttk.Panedwindow(self, orient="horizontal")
        self.layout.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        left, right = ttk.Frame(self.layout, padding=8), ttk.Frame(self.layout, padding=8)
        self.sidebar = left
        self.layout.add(left, weight=1)
        self.layout.add(right, weight=3)
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
        self.notebook.add(self.suggestion_tab, text="Klausuren korrigieren")
        self._build_project_tab()
        self._build_suggestion_tab()

    def _build_project_tab(self) -> None:
        ttk.Label(self.project_tab, text="Projektunterlagen", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(self.project_tab, text="Aufgabenstellung und Erwartungshorizont sind als verknüpfte Word- oder PDF-Dateien hinterlegt. Die KI liest sie beim Erstellen des Korrekturvorschlags aus.", wraplength=1000).pack(anchor="w", pady=(4, 12))
        self.project_details = ttk.Label(self.project_tab, text="Noch keine Projektunterlagen verknüpft.", justify="left", wraplength=1000)
        self.project_details.pack(anchor="w", pady=(4, 0))

    def _build_suggestion_tab(self) -> None:
        controls = ttk.Frame(self.suggestion_tab)
        controls.pack(fill="x", pady=(0, 8))
        self.grade_button = ttk.Button(controls, text="Ausgewählte korrigieren", command=self.grade)
        self.grade_button.pack(side="left")
        self.bulk_button = ttk.Button(controls, text="Alle Klausuren korrigieren", command=self.grade_all)
        self.bulk_button.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Ähnlichkeit prüfen", command=self.show_similarity_hints).pack(side="left", padx=(8, 0))
        self.review_button = ttk.Button(controls, text="✎ Korrekturarbeitsplatz öffnen", command=self.open_review)
        self.review_button.pack(side="left", padx=(8, 0))
        self.result_status = ttk.Label(controls, text="Laden Sie OCR-Klausuren über Datei > OCR-PDFs laden.")
        self.result_status.pack(side="left", padx=12)
        ttk.Label(self.suggestion_tab, text="Wählen Sie eine Klausur. Der Rotstift öffnet ihre PDF-Ansicht mit allen Korrekturhinweisen. Mehrere Arbeitsplätze können gleichzeitig geöffnet bleiben.", wraplength=1050).pack(anchor="w", pady=(0, 7))
        table_frame = ttk.Frame(self.suggestion_tab)
        table_frame.pack(fill="both", expand=True)
        columns = ("klausur", "status", "punkte", "note", "rotstift")
        self.scan_table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {"klausur": "Klausur", "status": "Status", "punkte": "Punkte", "note": "Vorläufige Note", "rotstift": "Korrektur"}
        widths = {"klausur": 420, "status": 130, "punkte": 145, "note": 190, "rotstift": 180}
        for key in columns:
            self.scan_table.heading(key, text=headings[key])
            self.scan_table.column(key, width=widths[key], anchor="w")
        self.scan_table.tag_configure("review", foreground="#a40000")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.scan_table.yview)
        self.scan_table.configure(yscrollcommand=yscroll.set)
        self.scan_table.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.scan_table.bind("<<TreeviewSelect>>", self.select_scan_from_table)
        self.scan_table.bind("<Double-1>", self.table_click)
        self.grade_summary = ttk.Label(self.suggestion_tab, text="Notenberechnung: Noch keine Korrekturvorschläge vorhanden.", font=("Segoe UI", 10, "bold"))
        self.grade_summary.pack(anchor="w", pady=(8, 0))

    def new_project(self) -> None:
        dialog = tk.Toplevel(self); dialog.title("Neues Klausurprojekt"); dialog.geometry("680x200"); dialog.transient(self)
        ttk.Label(dialog, text="Titel der Klausur").pack(anchor="w", padx=12, pady=(16, 4))
        title = ttk.Entry(dialog); title.pack(fill="x", padx=12)
        ttk.Label(dialog, text="Nach dem Anlegen verknüpfen Sie Aufgabenstellung und Erwartungshorizont als Word- oder PDF-Datei im geöffneten Projekt.", wraplength=620).pack(anchor="w", padx=12, pady=(12, 8))
        def save() -> None:
            if not title.get().strip():
                messagebox.showerror("Projekt", "Bitte geben Sie einen Klausurtitel ein.", parent=dialog); return
            new_project_id = self.store.create_project(title.get().strip(), "", [])
            dialog.destroy(); self.refresh_projects(); self.show_project(new_project_id)
            save_project = getattr(self, "save_project_file", None)
            if callable(save_project):
                self.after(0, save_project)
        ttk.Button(dialog, text="Projekt anlegen", command=save).pack(anchor="e", padx=12, pady=12)

    def delete_project(self) -> None:
        if self.project_id is None:
            messagebox.showinfo("Löschen", "Wählen Sie zuerst ein Klausurprojekt aus."); return
        if not messagebox.askyesno("Klausurprojekt löschen", "Projekt, geladene Klausuren und Korrekturvorschläge wirklich löschen?"): return
        self.store.delete_project(self.project_id); self.project_id = None; self.scan_id = None
        self.refresh_projects(); self.refresh_scans(); self.show_suggestions()

    def delete_scan(self) -> None:
        if self.scan_id is None:
            messagebox.showinfo("Löschen", "Wählen Sie zuerst eine geladene Klausur aus."); return
        if not messagebox.askyesno("Klausur löschen", "Die ausgewählte OCR-Klausur und ihre Korrekturvorschläge wirklich löschen?"): return
        self.store.delete_scan(self.scan_id); self.scan_id = None; self.refresh_scans(); self.show_suggestions()

    def refresh_projects(self) -> None:
        self.projects.delete(0, "end"); self.project_rows = self.store.projects()
        for project_id, title in self.project_rows: self.projects.insert("end", f"{project_id}: {title}")

    def select_project(self, _event=None) -> None:
        choice = self.projects.curselection()
        if choice: self.show_project(self.project_rows[choice[0]][0])

    def show_project(self, project_id: int) -> None:
        self.project_id = project_id
        project = self.store.project(project_id); attachments = project.get("anhaenge", {})
        task = Path(attachments.get("aufgabenstellung", "")).name or "nicht verknüpft"
        horizon = Path(attachments.get("erwartungshorizont", "")).name or "nicht verknüpft"
        self.project_details.configure(text=f"Aufgabenstellung: {task}\nErwartungshorizont: {horizon}")
        self.refresh_scans()

    def _result_text(self, scan_id: int) -> tuple[str, str]:
        details = self.store.suggestion_details(scan_id)
        if not details: return "–", "–"
        total = sum(float(item.get("punkte") or 0) for item in details)
        maximum = sum(float(item.get("max_punkte") or 0) for item in details)
        if maximum <= 0 and self.project_id:
            maximum = sum(float(task.get("max_punkte") or 0) for task in self.store.project(self.project_id)["aufgaben"])
        if maximum <= 0: return f"{total:.1f}", "max. Punkte fehlen"
        percent, grade = ihk_note(total, maximum)
        return f"{total:.1f} / {maximum:.1f}", f"{grade} ({percent:.1f} %)"

    def refresh_scans(self) -> None:
        self.scans.delete(0, "end"); self.scan_rows = self.store.scans(self.project_id) if self.project_id else []
        for scan_id, path, status in self.scan_rows: self.scans.insert("end", f"{scan_id}: {Path(path).name} [{status}]")
        if not hasattr(self, "scan_table"): return
        selected = str(self.scan_id) if self.scan_id else ""
        self.scan_table.delete(*self.scan_table.get_children())
        for scan_id, path, status in self.scan_rows:
            points, note = self._result_text(scan_id)
            self.scan_table.insert("", "end", iid=str(scan_id), values=(Path(path).name, status, points, note, "✎ Öffnen"), tags=("review",))
        if selected and self.scan_table.exists(selected):
            self.scan_table.selection_set(selected); self.scan_table.focus(selected)

    def select_scan_from_table(self, _event=None) -> None:
        selected = self.scan_table.selection()
        if selected:
            self.scan_id = int(selected[0]); self.show_suggestions()

    def table_click(self, event) -> None:
        row = self.scan_table.identify_row(event.y)
        if not row: return
        self.scan_table.selection_set(row); self.scan_id = int(row)
        if self.scan_table.identify_column(event.x) == "#5": self.open_review()

    def select_scan(self, _event=None) -> None:
        choice = self.scans.curselection()
        if choice:
            self.scan_id = self.scan_rows[choice[0]][0]; self.show_suggestions()

    def add_scans(self) -> None:
        if self.project_id is None:
            messagebox.showinfo("Klausurprojekt", "Legen Sie zuerst ein Klausurprojekt an."); return
        for path in filedialog.askopenfilenames(title="Anonymisierte OCR-PDFs auswählen", filetypes=[("PDF-Dateien", "*.pdf")]):
            try: self.store.add_scan(self.project_id, path, extract_pdf_text(path))
            except Exception as exc: messagebox.showwarning("OCR-PDF", f"{Path(path).name}: {exc}")
        self.refresh_scans()

    def show_suggestions(self) -> None:
        if not self.scan_id or not self.project_id:
            self.grade_summary.configure(text="Notenberechnung: Noch keine Korrekturvorschläge vorhanden."); return
        points, note = self._result_text(self.scan_id)
        if points == "–": self.grade_summary.configure(text="Notenberechnung: Noch keine Korrekturvorschläge vorhanden.")
        else: self.grade_summary.configure(text=f"Zwischenstand dieser Klausur: {points} Punkte – {note}")

    def open_review(self) -> None:
        if self.scan_id is None:
            messagebox.showinfo("Korrekturarbeitsplatz", "Wählen Sie zuerst eine Klausur aus."); return
        scan = self.store.scan(self.scan_id)
        if not self.store.suggestion_details(self.scan_id):
            messagebox.showinfo("Korrekturarbeitsplatz", "Erzeugen Sie zuerst einen Korrekturvorschlag für diese Klausur."); return
        ReviewWindow(self, scan["pfad"], self.store.suggestion_details(self.scan_id), Path(__file__).resolve().parents[2] / "data")

    def grade_payload(self) -> dict:
        return self.store.project(self.project_id)

    def grade_model(self) -> str | None:
        return None

    def grade(self) -> None:
        if self.scan_id is None: messagebox.showinfo("Korrekturvorschlag", "Wählen Sie zuerst eine OCR-Klausur aus."); return
        self._grade_one(self.scan_id, open_after=True)

    def _grade_one(self, scan_id: int, open_after: bool = False, done=None) -> None:
        if self.project_id is None: return
        if not self.provider.available():
            messagebox.showerror("Codex", "Codex wurde nicht gefunden. Melden Sie sich mit 'codex login' bei Ihrem ChatGPT-Plus-Konto an."); return
        self.grade_button.configure(state="disabled"); self.bulk_button.configure(state="disabled")
        self.store.update_scan_status(scan_id, "Korrektur läuft")
        self.refresh_scans(); self.result_status.configure(text="Korrekturvorschlag wird erstellt …")
        project, scan, model = self.grade_payload(), self.store.scan(scan_id), self.grade_model()
        def work() -> None:
            try:
                proposal = self.provider.grade(project, scan["ocr_text"], model)
                self.store.replace_suggestions(scan_id, proposal)
                self.after(0, lambda: self._grade_finished(scan_id, open_after, done))
            except Exception as exc:
                self.after(0, lambda: self._grade_failed(scan_id, str(exc), done))
        threading.Thread(target=work, daemon=True).start()

    def _grade_finished(self, scan_id: int, open_after: bool, done) -> None:
        self.grade_button.configure(state="normal"); self.bulk_button.configure(state="normal")
        self.result_status.configure(text="Vorschlag erstellt – bitte fachlich prüfen.")
        self.refresh_scans(); self.show_suggestions()
        if open_after:
            self.scan_id = scan_id; self.after(120, self.open_review)
        if done: done()

    def _grade_failed(self, scan_id: int, detail: str, done) -> None:
        self.store.update_scan_status(scan_id, "Fehler")
        self.grade_button.configure(state="normal"); self.bulk_button.configure(state="normal")
        self.refresh_scans()
        if self._bulk_running:
            self._bulk_errors.append(f"{Path(self.store.scan(scan_id)['pfad']).name}: {detail}")
            if done: done()
        else:
            self.result_status.configure(text="Korrekturvorschlag nicht erstellt.")
            messagebox.showerror("Korrekturvorschlag", detail)

    def grade_all(self) -> None:
        if not self.project_id or not self.scan_rows:
            messagebox.showinfo("Alle korrigieren", "Laden Sie zuerst mindestens eine OCR-Klausur."); return
        if not self.provider.available():
            messagebox.showerror("Codex", "Codex wurde nicht gefunden. Melden Sie sich zuerst über Codex CLI an."); return
        self._bulk_queue = [row[0] for row in self.scan_rows]
        self._bulk_errors = []
        self._bulk_running = True
        self._grade_next()

    def _grade_next(self) -> None:
        if not self._bulk_queue:
            self._bulk_running = False
            if self._bulk_errors:
                self.result_status.configure(text=f"Sammelkorrektur beendet: {len(self._bulk_errors)} Klausur(en) mit Fehler.")
                messagebox.showwarning("Sammelkorrektur", "Die Sammelkorrektur ist beendet. Fehler:\n\n" + "\n".join(self._bulk_errors))
            else:
                self.result_status.configure(text="Sammelkorrektur beendet – bitte fachlich prüfen.")
            self.refresh_scans(); return
        scan_id = self._bulk_queue.pop(0)
        self.result_status.configure(text=f"Sammelkorrektur: noch {len(self._bulk_queue) + 1} Klausur(en) …")
        self._grade_one(scan_id, done=self._grade_next)

    def show_similarity_hints(self) -> None:
        if not self.project_id or len(self.scan_rows) < 2:
            messagebox.showinfo("Ähnlichkeit prüfen", "Für die Prüfung werden mindestens zwei OCR-Klausuren benötigt."); return
        scans = [(scan_id, Path(path).name, self.store.scan(scan_id)["ocr_text"]) for scan_id, path, _status in self.scan_rows]
        hints = find_similarity_hints(scans)
        dialog = tk.Toplevel(self); dialog.title("Ähnlichkeitshinweise"); dialog.geometry("900x560")
        ttk.Label(dialog, text="Die Prüfung läuft vollständig lokal. Ein Hinweis ist keine Betrugsfeststellung; prüfen Sie die Textstellen fachlich und im Kontext.", wraplength=840).pack(anchor="w", padx=14, pady=(14, 8))
        output = tk.Text(dialog, wrap="word", padx=10, pady=8); output.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        if not hints:
            output.insert("1.0", "Keine auffälligen längeren, wortgleichen Textpassagen gefunden.")
        else:
            for hint in hints:
                output.insert("end", f"{hint['left_name']}  ↔  {hint['right_name']}\n")
                output.insert("end", f"Gemeinsame wortgleiche Passage ({hint['words']} Wörter):\n„{hint['passage']}“\n\n")
        output.configure(state="disabled")


def main() -> None:
    KorrekturApp().mainloop()


if __name__ == "__main__":
    main()

