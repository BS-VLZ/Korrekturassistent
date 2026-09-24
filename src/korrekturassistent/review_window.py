from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .pdf_review import export_comment_pdf, page_count, render_page


class ReviewWindow(tk.Toplevel):
    """Arbeitsbereich: eine PDF-Seite links, Korrektur und Chat rechts."""

    def __init__(self, master, ocr_path: str, suggestions: list[tuple], anchors: dict[str, tuple[int | None, str]], output_folder: Path) -> None:
        super().__init__(master)
        self.title("Korrekturarbeitsplatz")
        self.geometry("1500x950")
        self.ocr_path = ocr_path
        self.suggestions = suggestions
        self.anchors = anchors
        self.output_folder = output_folder
        self.original_path: str | None = None
        self.ocr_pages = page_count(ocr_path)
        self.original_pages = 0
        self.display = tk.StringVar(value="OCR-PDF")
        self.page = tk.IntVar(value=1)
        self.current_tasks: list[tuple] = []
        self._images: list[tk.PhotoImage] = []
        self._build()
        self.show_page()

    def _build(self) -> None:
        controls = ttk.Frame(self, padding=10)
        controls.pack(fill="x")
        ttk.Button(controls, text="Original-PDF auswählen", command=self.choose_original).pack(side="left")
        ttk.Radiobutton(controls, text="OCR-PDF", variable=self.display, value="OCR-PDF", command=self.show_page).pack(side="left", padx=(16, 2))
        ttk.Radiobutton(controls, text="Original-PDF", variable=self.display, value="Original-PDF", command=self.show_page).pack(side="left")
        ttk.Label(controls, text="Seite").pack(side="left", padx=(16, 4))
        self.page_picker = ttk.Spinbox(controls, from_=1, to=self.ocr_pages, width=6, textvariable=self.page, command=self.show_page)
        self.page_picker.pack(side="left")
        ttk.Button(controls, text="Anzeigen", command=self.show_page).pack(side="left", padx=6)
        ttk.Button(controls, text="Kommentar-PDF exportieren", command=self.export).pack(side="right")
        self.info = ttk.Label(controls, text=f"OCR-PDF: {self.ocr_pages} Seiten")
        self.info.pack(side="right", padx=12)

        content = ttk.Panedwindow(self, orient="horizontal")
        content.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        page_frame = ttk.Frame(content, padding=6)
        ttk.Label(page_frame, text="PDF-Seite", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.page_panel = ttk.Label(page_frame, text="PDF-Seite wird geladen", anchor="center")
        self.page_panel.pack(fill="both", expand=True)
        content.add(page_frame, weight=3)

        sidebar = ttk.Frame(content, padding=8)
        content.add(sidebar, weight=2)
        ttk.Label(sidebar, text="Korrekturen auf dieser Seite", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.corrections = tk.Listbox(sidebar, height=7, exportselection=False)
        self.corrections.pack(fill="x", pady=(5, 8))
        self.corrections.bind("<<ListboxSelect>>", self.select_correction)

        self.anchor_label = ttk.Label(sidebar, text="Wählen Sie einen Korrekturhinweis aus.", wraplength=500)
        self.anchor_label.pack(anchor="w", pady=(0, 6))
        points_line = ttk.Frame(sidebar)
        points_line.pack(fill="x")
        ttk.Label(points_line, text="Punkte:").pack(side="left")
        self.points = ttk.Entry(points_line, width=10)
        self.points.pack(side="left", padx=(8, 0))
        ttk.Label(sidebar, text="Begründung:").pack(anchor="w", pady=(8, 3))
        self.reason = tk.Text(sidebar, height=7, wrap="word")
        self.reason.pack(fill="x")
        ttk.Label(sidebar, text="Unsicherheiten:").pack(anchor="w", pady=(8, 3))
        self.unclear = tk.Text(sidebar, height=4, wrap="word")
        self.unclear.pack(fill="x")
        ttk.Button(sidebar, text="Änderungen speichern", command=self.save_correction).pack(anchor="e", pady=(6, 12))

        ttk.Separator(sidebar).pack(fill="x", pady=(0, 10))
        ttk.Label(sidebar, text="Diskussion zur ausgewählten Korrektur", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.chat = tk.Text(sidebar, height=12, wrap="word", state="disabled")
        self.chat.pack(fill="both", expand=True, pady=(5, 6))
        chat_line = ttk.Frame(sidebar)
        chat_line.pack(fill="x")
        self.question = ttk.Entry(chat_line)
        self.question.pack(side="left", fill="x", expand=True)
        self.question.bind("<Return>", lambda _event: self.discuss())
        ttk.Button(chat_line, text="Senden", command=self.discuss).pack(side="left", padx=(6, 0))

    def choose_original(self) -> None:
        path = filedialog.askopenfilename(title="Handschriftliches Original-PDF auswählen", filetypes=[("PDF-Dateien", "*.pdf")])
        if not path:
            return
        self.original_path = path
        self.original_pages = page_count(path)
        self.info.configure(text=f"Original: {self.original_pages} Seiten | OCR: {self.ocr_pages} Seiten")
        self.display.set("Original-PDF")
        self.show_page()

    def show_page(self) -> None:
        try:
            page = max(1, min(int(self.page.get()), self.ocr_pages))
        except tk.TclError:
            return
        self.page.set(page)
        path, label = self.ocr_path, "OCR-PDF"
        if self.display.get() == "Original-PDF":
            if not self.original_path:
                self.display.set("OCR-PDF")
            elif page <= self.original_pages:
                path, label = self.original_path, "Original-PDF"
            else:
                self.page_panel.configure(image="", text="Diese Seite ist im Original-PDF nicht vorhanden.")
                self.show_corrections(page)
                return
        cache = self.output_folder / "rendered"
        image_path = render_page(path, page, cache / f"{label.lower().replace('-', '_')}-{page}.png", zoom=1.75)
        self._set_image(image_path, f"{label} – Seite {page}")
        self.show_corrections(page)

    def _set_image(self, path: Path, label: str) -> None:
        image = tk.PhotoImage(file=str(path))
        self._images.append(image)
        self._images = self._images[-3:]
        self.page_panel.configure(image=image, text=label, compound="top")

    def show_corrections(self, page: int) -> None:
        self.current_tasks = []
        self.corrections.delete(0, "end")
        for item in self.suggestions:
            task, points, reason, uncertain = item
            anchor_page, _anchor = self.anchors.get(task, (None, ""))
            if anchor_page == page or anchor_page is None:
                self.current_tasks.append(item)
                label = f"Aufgabe {task}: {points} Punkte"
                if anchor_page is None:
                    label += " (Seite noch offen)"
                self.corrections.insert("end", label)
        self.clear_detail()
        if self.current_tasks:
            self.corrections.selection_set(0)
            self.select_correction()

    def clear_detail(self) -> None:
        self.anchor_label.configure(text="Wählen Sie einen Korrekturhinweis aus.")
        for field in (self.points, self.reason, self.unclear):
            field.delete("1.0", "end") if isinstance(field, tk.Text) else field.delete(0, "end")

    def selected(self) -> tuple | None:
        selection = self.corrections.curselection()
        return self.current_tasks[selection[0]] if selection else None

    def select_correction(self, _event=None) -> None:
        item = self.selected()
        if not item:
            return
        task, points, reason, uncertain = item
        page, anchor = self.anchors.get(task, (None, ""))
        location = f"Seite {page}" if page else "Seite noch nicht bestimmt"
        if anchor:
            location += f" · Textstelle: „{anchor}“"
        self.anchor_label.configure(text=location)
        self.points.delete(0, "end")
        self.points.insert(0, points)
        for field, value in ((self.reason, reason), (self.unclear, uncertain)):
            field.delete("1.0", "end")
            field.insert("1.0", value)

    def save_correction(self) -> None:
        item = self.selected()
        if not item:
            messagebox.showinfo("Korrektur", "Wählen Sie zuerst eine Korrektur aus.", parent=self)
            return
        try:
            points = float(self.points.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Korrektur", "Bitte geben Sie eine gültige Punktzahl ein.", parent=self)
            return
        task = item[0]
        self.master.store.update_suggestion(self.master.scan_id, task, points, self.reason.get("1.0", "end").strip(), self.unclear.get("1.0", "end").strip())
        self.suggestions = self.master.store.suggestions(self.master.scan_id)
        self.master.show_suggestions()
        self.show_corrections(self.page.get())
        self._append_chat("Korrektur wurde gespeichert.\n\n")

    def discuss(self) -> None:
        item = self.selected()
        question = self.question.get().strip()
        if not item or not question:
            return
        if not self.master.provider.available():
            messagebox.showerror("Diskussion", "Codex wurde nicht gefunden.", parent=self)
            return
        self.question.delete(0, "end")
        task, points, reason, uncertain = item
        page, anchor = self.anchors.get(task, (None, ""))
        self._append_chat(f"Sie: {question}\n\n")
        if hasattr(self.master, "_add_chat"):
            self.master._add_chat(f"Sie (Aufgabe {task}): {question}\n\n")
        context = json.dumps({"projekt": self.master.store.project(self.master.project_id), "korrektur": {"aufgabe": task, "punkte": points, "begruendung": reason, "unsicherheiten": uncertain, "seite": page, "textstelle": anchor}}, ensure_ascii=False)
        model_box = getattr(self.master, "model", None)
        model = None if model_box is None or model_box.get() == "Standard" else model_box.get()
        def work() -> None:
            try:
                answer = self.master.provider.discuss(context, question, model)
                self.after(0, lambda: self._discussion_answer(answer))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Diskussion", str(exc), parent=self))
        threading.Thread(target=work, daemon=True).start()

    def _discussion_answer(self, answer: str) -> None:
        self._append_chat(f"Assistent: {answer}\n\n")
        if hasattr(self.master, "_add_chat"):
            self.master._add_chat(f"Assistent (Aufgabe): {answer}\n\n")

    def _append_chat(self, text: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", text)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def export(self) -> None:
        suggested = Path(self.ocr_path).stem + "_korrekturvorschlag.pdf"
        destination = filedialog.asksaveasfilename(title="Kommentar-PDF speichern", initialdir=self.output_folder, initialfile=suggested, defaultextension=".pdf", filetypes=[("PDF-Dateien", "*.pdf")])
        if not destination:
            return
        try:
            export_comment_pdf(self.ocr_path, self.suggestions, self.anchors, Path(destination))
            messagebox.showinfo("Export", "Die Seiten wurden unverändert übernommen. Korrekturhinweise sind als Kommentar-Ebene ergänzt.", parent=self)
        except Exception as exc:
            messagebox.showerror("Export", str(exc), parent=self)
