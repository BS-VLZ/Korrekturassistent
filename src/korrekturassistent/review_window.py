from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import fitz

from .pdf_review import page_count, render_page


class ReviewWindow(tk.Toplevel):
    """Der gesamte Korrekturarbeitsplatz: PDF links, Bearbeitung und Chat rechts."""

    def __init__(self, master, ocr_path: str, suggestions: list[tuple], anchors: dict[str, tuple[int | None, str]], output_folder: Path) -> None:
        super().__init__(master)
        self.title("Korrekturarbeitsplatz")
        self.geometry("1540x960")
        self.ocr_path = ocr_path
        self.suggestions = suggestions
        self.anchors = anchors
        self.output_folder = output_folder
        self.pages = page_count(ocr_path)
        self.page = tk.IntVar(value=1)
        self.current_tasks: list[tuple] = []
        self.image: tk.PhotoImage | None = None
        self._resize_after: str | None = None
        self._build()
        self.show_page()

    def _build(self) -> None:
        controls = ttk.Frame(self, padding=(12, 10))
        controls.pack(fill="x")
        ttk.Button(controls, text="‹ Vorherige Seite", command=lambda: self.change_page(-1)).pack(side="left")
        ttk.Label(controls, text="Seite").pack(side="left", padx=(14, 4))
        self.page_picker = ttk.Spinbox(controls, from_=1, to=self.pages, width=6, textvariable=self.page, command=self.show_page)
        self.page_picker.pack(side="left")
        ttk.Label(controls, text=f"von {self.pages}").pack(side="left", padx=(4, 10))
        ttk.Button(controls, text="Nächste Seite ›", command=lambda: self.change_page(1)).pack(side="left")
        ttk.Label(controls, text="Markierungen verändern die Datei nicht.").pack(side="right")

        split = ttk.Panedwindow(self, orient="horizontal")
        split.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        reader = ttk.Frame(split, padding=2)
        split.add(reader, weight=3)
        self.canvas = tk.Canvas(reader, background="#5e5e5e", highlightthickness=0)
        yscroll = ttk.Scrollbar(reader, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=yscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        reader.rowconfigure(0, weight=1)
        reader.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", self.resize_reader)

        sidebar = ttk.Frame(split, padding=12)
        split.add(sidebar, weight=2)
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(sidebar, text="Korrekturen auf dieser Seite", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.corrections = tk.Listbox(sidebar, height=6, exportselection=False)
        self.corrections.grid(row=1, column=0, sticky="ew", pady=(5, 8))
        self.corrections.bind("<<ListboxSelect>>", self.select_correction)
        self.location = ttk.Label(sidebar, text="Wählen Sie eine Korrektur aus.", wraplength=470)
        self.location.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        points_line = ttk.Frame(sidebar)
        points_line.grid(row=3, column=0, sticky="ew")
        ttk.Label(points_line, text="Punkte:").pack(side="left")
        self.points = ttk.Entry(points_line, width=10)
        self.points.pack(side="left", padx=(8, 0))
        ttk.Label(sidebar, text="Begründung:").grid(row=4, column=0, sticky="w", pady=(8, 3))
        self.reason = tk.Text(sidebar, height=5, wrap="word")
        self.reason.grid(row=5, column=0, sticky="ew")
        ttk.Label(sidebar, text="Unsicherheiten:").grid(row=6, column=0, sticky="w", pady=(8, 3))
        self.unclear = tk.Text(sidebar, height=3, wrap="word")
        self.unclear.grid(row=7, column=0, sticky="ew")
        ttk.Button(sidebar, text="Korrektur speichern", command=self.save_correction).grid(row=8, column=0, sticky="e", pady=(6, 10))
        ttk.Separator(sidebar).grid(row=9, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(sidebar, text="Chat zur ausgewählten Korrektur", font=("Segoe UI", 11, "bold")).grid(row=10, column=0, sticky="w")
        self.chat = tk.Text(sidebar, height=8, wrap="word", state="disabled")
        self.chat.grid(row=11, column=0, sticky="nsew", pady=(5, 6))
        sidebar.rowconfigure(11, weight=1)
        row = ttk.Frame(sidebar)
        row.grid(row=12, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        self.question = ttk.Entry(row)
        self.question.grid(row=0, column=0, sticky="ew")
        self.question.bind("<Return>", lambda _event: self.discuss())
        ttk.Button(row, text="Senden", command=self.discuss).grid(row=0, column=1, padx=(6, 0))

    def resize_reader(self, _event=None) -> None:
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(180, self.show_page)

    def change_page(self, delta: int) -> None:
        self.page.set(max(1, min(self.pages, self.page.get() + delta)))
        self.show_page()

    def show_page(self) -> None:
        try:
            page_number = max(1, min(int(self.page.get()), self.pages))
        except tk.TclError:
            return
        self.page.set(page_number)
        target = self.output_folder / "rendered" / f"reader-{page_number}.png"
        available_width = self.canvas.winfo_width()
        document = fitz.open(self.ocr_path)
        try:
            page_width = document.load_page(page_number - 1).rect.width
        finally:
            document.close()
        zoom = 1.2 if available_width < 250 else max(0.8, (available_width - 28) / page_width)
        image_path = render_page(self.ocr_path, page_number, target, zoom=zoom)
        self.image = tk.PhotoImage(file=str(image_path))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.image)
        self.canvas.configure(scrollregion=(0, 0, self.image.width(), self.image.height()))
        self.show_corrections(page_number)
        self.draw_markers(page_number)
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def show_corrections(self, page_number: int) -> None:
        self.current_tasks = []
        self.corrections.delete(0, "end")
        for item in self.suggestions:
            task, points, _reason, uncertain = item
            anchor_page, _anchor = self.anchors.get(task, (None, ""))
            if anchor_page == page_number or anchor_page is None:
                self.current_tasks.append(item)
                label = f"Aufgabe {task}: {points} Punkte"
                if uncertain:
                    label += " · prüfen"
                self.corrections.insert("end", label)
                index = len(self.current_tasks) - 1
                self.corrections.itemconfig(index, foreground=self.marker_color(item))
        self.clear_editor()
        if self.current_tasks:
            self.corrections.selection_set(0)
            self.select_correction()

    def marker_color(self, item: tuple) -> str:
        _task, points, _reason, uncertain = item
        if uncertain:
            return "#b36b00"
        return "#b00020" if float(points or 0) == 0 else "#137333"

    def draw_markers(self, page_number: int) -> None:
        if not self.image:
            return
        document = fitz.open(self.ocr_path)
        try:
            page = document.load_page(page_number - 1)
            scale_x = self.image.width() / page.rect.width
            scale_y = self.image.height() / page.rect.height
            for index, item in enumerate(self.current_tasks):
                task, points, _reason, _uncertain = item
                _anchor_page, anchor = self.anchors.get(task, (None, ""))
                if not anchor:
                    continue
                matches = page.search_for(anchor)
                if not matches:
                    continue
                rect = matches[0]
                x0, y0 = rect.x0 * scale_x, rect.y0 * scale_y
                x1, y1 = rect.x1 * scale_x, rect.y1 * scale_y
                color = self.marker_color(item)
                tag = f"correction-{index}"
                self.canvas.create_rectangle(x0 - 3, y0 - 3, x1 + 3, y1 + 3, outline=color, width=3, fill=color, stipple="gray25", tags=(tag,))
                self.canvas.create_text(x0, max(10, y0 - 10), text=f"Aufgabe {task}: {points}", anchor="sw", fill=color, font=("Segoe UI", 10, "bold"), tags=(tag,))
                self.canvas.tag_bind(tag, "<Button-1>", lambda _event, selected=index: self.select_index(selected))
        finally:
            document.close()

    def select_index(self, index: int) -> None:
        self.corrections.selection_clear(0, "end")
        self.corrections.selection_set(index)
        self.corrections.see(index)
        self.select_correction()

    def selected(self) -> tuple | None:
        selection = self.corrections.curselection()
        return self.current_tasks[selection[0]] if selection else None

    def clear_editor(self) -> None:
        self.location.configure(text="Wählen Sie eine Korrektur aus.")
        self.points.delete(0, "end")
        self.reason.delete("1.0", "end")
        self.unclear.delete("1.0", "end")

    def select_correction(self, _event=None) -> None:
        item = self.selected()
        if not item:
            return
        task, points, reason, uncertain = item
        page, anchor = self.anchors.get(task, (None, ""))
        text = f"Aufgabe {task} · Seite {page or 'nicht bestimmt'}"
        if anchor:
            text += f"\nTextstelle: „{anchor}“"
        self.location.configure(text=text)
        self.points.delete(0, "end")
        self.points.insert(0, points)
        self.reason.delete("1.0", "end")
        self.reason.insert("1.0", reason)
        self.unclear.delete("1.0", "end")
        self.unclear.insert("1.0", uncertain)

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
        self.show_page()
        self._append_chat("Korrektur gespeichert.\n\n")

    def discuss(self) -> None:
        item = self.selected()
        question = self.question.get().strip()
        if not item or not question:
            return
        if not self.master.provider.available():
            messagebox.showerror("Chat", "Codex wurde nicht gefunden.", parent=self)
            return
        self.question.delete(0, "end")
        task, points, reason, uncertain = item
        page, anchor = self.anchors.get(task, (None, ""))
        self._append_chat(f"Sie: {question}\n\n")
        self.master._add_chat(f"Sie (Aufgabe {task}): {question}\n\n")
        context = json.dumps({"projekt": self.master.store.project(self.master.project_id), "korrektur": {"aufgabe": task, "punkte": points, "begruendung": reason, "unsicherheiten": uncertain, "seite": page, "textstelle": anchor}}, ensure_ascii=False)
        model_box = getattr(self.master, "model", None)
        model = None if model_box is None or model_box.get() == "Standard" else model_box.get()
        def work() -> None:
            try:
                answer = self.master.provider.discuss(context, question, model)
                self.after(0, lambda: self.discussion_answer(answer))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Chat", str(exc), parent=self))
        threading.Thread(target=work, daemon=True).start()

    def discussion_answer(self, answer: str) -> None:
        self._append_chat(f"Assistent: {answer}\n\n")
        self.master._add_chat(f"Assistent (Aufgabe): {answer}\n\n")

    def _append_chat(self, text: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", text)
        self.chat.see("end")
        self.chat.configure(state="disabled")
