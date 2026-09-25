from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import fitz

from .pdf_review import page_count, render_page


class ReviewWindow(tk.Toplevel):
    """PDF-Korrekturarbeitsplatz mit Bewertungsraster und aufgabenbezogenem Chat."""

    def __init__(self, master, ocr_path: str, suggestions: list[dict], output_folder: Path) -> None:
        super().__init__(master)
        self.title("Korrekturarbeitsplatz")
        self.geometry("1540x960")
        self.ocr_path = ocr_path
        self.suggestions = suggestions
        self.output_folder = output_folder
        self.pages = page_count(ocr_path)
        self.page = tk.IntVar(value=1)
        self.zoom_factor = 1.0
        self.current_tasks: list[dict] = []
        self.marker_states: dict[int, str] = {}
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
        self.zoom_label = ttk.Label(controls, text="Ansicht: Seitenbreite")
        self.zoom_label.pack(side="left", padx=(24, 0))
        ttk.Label(controls, text="Mausrad: Seite wechseln · Strg + Mausrad: Zoom · Markierungen verändern die Datei nicht.").pack(side="right")

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
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.focus_set()

        sidebar = ttk.Frame(split, padding=12)
        split.add(sidebar, weight=2)
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(sidebar, text="Korrekturen auf dieser Seite", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.corrections = tk.Listbox(sidebar, height=3, exportselection=False, font=("Segoe UI", 10))
        self.corrections.grid(row=1, column=0, sticky="ew", pady=(5, 7))
        self.corrections.bind("<<ListboxSelect>>", self.select_correction)
        self.location = ttk.Label(sidebar, text="Wählen Sie eine Korrektur aus.", wraplength=480)
        self.location.grid(row=2, column=0, sticky="ew", pady=(0, 6))

        points_line = ttk.Frame(sidebar)
        points_line.grid(row=3, column=0, sticky="ew")
        ttk.Label(points_line, text="Punkte:").pack(side="left")
        self.points = ttk.Entry(points_line, width=10)
        self.points.pack(side="left", padx=(8, 0))
        self.maximum = ttk.Label(points_line, text="von ? Punkten")
        self.maximum.pack(side="left", padx=(7, 0))

        ttk.Label(sidebar, text="Bewertungsraster", font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(9, 3))
        rubric_frame = ttk.Frame(sidebar)
        rubric_frame.grid(row=5, column=0, sticky="ew")
        rubric_frame.columnconfigure(0, weight=1)
        self.rubric = tk.Text(rubric_frame, height=5, wrap="word", state="disabled", font=("Segoe UI", 10), background="#f7f7f7", relief="solid", borderwidth=1)
        rubric_scroll = ttk.Scrollbar(rubric_frame, orient="vertical", command=self.rubric.yview)
        self.rubric.configure(yscrollcommand=rubric_scroll.set)
        self.rubric.grid(row=0, column=0, sticky="ew")
        rubric_scroll.grid(row=0, column=1, sticky="ns")

        ttk.Label(sidebar, text="Begründung", font=("Segoe UI", 10, "bold")).grid(row=6, column=0, sticky="w", pady=(9, 3))
        reason_frame = ttk.Frame(sidebar)
        reason_frame.grid(row=7, column=0, sticky="nsew")
        reason_frame.columnconfigure(0, weight=1)
        self.reason = tk.Text(reason_frame, height=9, wrap="word", font=("Segoe UI", 10), spacing1=2, spacing3=7)
        reason_scroll = ttk.Scrollbar(reason_frame, orient="vertical", command=self.reason.yview)
        self.reason.configure(yscrollcommand=reason_scroll.set)
        self.reason.grid(row=0, column=0, sticky="nsew")
        reason_scroll.grid(row=0, column=1, sticky="ns")

        ttk.Label(sidebar, text="Unsicherheiten", font=("Segoe UI", 10, "bold")).grid(row=8, column=0, sticky="w", pady=(8, 3))
        unclear_frame = ttk.Frame(sidebar)
        unclear_frame.grid(row=9, column=0, sticky="ew")
        unclear_frame.columnconfigure(0, weight=1)
        self.unclear = tk.Text(unclear_frame, height=3, wrap="word", font=("Segoe UI", 10))
        unclear_scroll = ttk.Scrollbar(unclear_frame, orient="vertical", command=self.unclear.yview)
        self.unclear.configure(yscrollcommand=unclear_scroll.set)
        self.unclear.grid(row=0, column=0, sticky="ew")
        unclear_scroll.grid(row=0, column=1, sticky="ns")
        ttk.Button(sidebar, text="Korrektur speichern", command=self.save_correction).grid(row=10, column=0, sticky="e", pady=(6, 9))

        ttk.Separator(sidebar).grid(row=11, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(sidebar, text="Chat zur ausgewählten Korrektur", font=("Segoe UI", 11, "bold")).grid(row=12, column=0, sticky="w")
        self.chat = tk.Text(sidebar, height=7, wrap="word", state="disabled", font=("Segoe UI", 10))
        self.chat.grid(row=13, column=0, sticky="nsew", pady=(5, 6))
        sidebar.rowconfigure(13, weight=1)
        row = ttk.Frame(sidebar)
        row.grid(row=14, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)
        self.question = ttk.Entry(row)
        self.question.grid(row=0, column=0, sticky="ew")
        self.question.bind("<Return>", lambda _event: self.discuss())
        ttk.Button(row, text="Senden", command=self.discuss).grid(row=0, column=1, padx=(6, 0))

    def resize_reader(self, _event=None) -> None:
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(180, self.show_page)

    def on_mousewheel(self, event) -> str:
        if event.state & 0x0004:
            self.zoom_factor = min(3.0, self.zoom_factor * 1.15) if event.delta > 0 else max(0.55, self.zoom_factor / 1.15)
            self.show_page()
        else:
            self.change_page(-1 if event.delta > 0 else 1)
        return "break"

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
        fit_zoom = 1.2 if available_width < 250 else max(0.8, (available_width - 28) / page_width)
        zoom = fit_zoom * self.zoom_factor
        self.zoom_label.configure(text="Ansicht: Seitenbreite" if self.zoom_factor == 1.0 else f"Zoom: {self.zoom_factor * 100:.0f} %")
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
        self.current_tasks = [item for item in self.suggestions if item.get("seite") in (None, page_number)]
        self.marker_states = {index: "unprueft" for index in range(len(self.current_tasks))}
        self.corrections.delete(0, "end")
        for index, item in enumerate(self.current_tasks):
            self.corrections.insert("end", self.task_label(item))
            self.corrections.itemconfig(index, foreground=self.marker_color(item))
        self.clear_editor()
        if self.current_tasks:
            self.corrections.selection_set(0)
            self.select_correction()

    @staticmethod
    def max_text(item: dict) -> str:
        maximum = item.get("max_punkte")
        return "?" if maximum is None else f"{float(maximum):g}"

    def task_label(self, item: dict, state: str | None = None) -> str:
        state = state or "unprueft"
        label = f"Aufgabe {item['aufgabe']}: {float(item.get('punkte') or 0):g} / {self.max_text(item)} Punkte"
        if item.get("unsicherheiten"):
            label += " · prüfen"
        if state == "nicht_gefunden":
            label += " · Textstelle nicht automatisch markierbar"
        elif state == "mehrdeutig":
            label += " · Textstelle mehrdeutig – bitte manuell prüfen"
        return label

    @staticmethod
    def marker_color(item: dict, state: str | None = None) -> str:
        if state in ("nicht_gefunden", "mehrdeutig"):
            return "#5c2d91"
        if item.get("unsicherheiten"):
            return "#b36b00"
        return "#b00020" if float(item.get("punkte") or 0) == 0 else "#137333"

    def draw_markers(self, page_number: int) -> None:
        if not self.image:
            return
        document = fitz.open(self.ocr_path)
        try:
            page = document.load_page(page_number - 1)
            scale_x = self.image.width() / page.rect.width
            scale_y = self.image.height() / page.rect.height
            for index, item in enumerate(self.current_tasks):
                rect, state = self.find_anchor_rect(page, item.get("textstelle", ""))
                self.set_marker_state(index, state)
                if rect is not None:
                    self.draw_task_marker(index, item, rect, scale_x, scale_y)
                self.draw_criterion_markers(index, item, page, scale_x, scale_y)
        finally:
            document.close()
        if self.current_tasks:
            self.corrections.selection_clear(0, "end")
            self.corrections.selection_set(0)
            self.select_correction()

    def draw_task_marker(self, index: int, item: dict, rect, scale_x: float, scale_y: float) -> None:
        x0, y0 = rect.x0 * scale_x, rect.y0 * scale_y
        x1, y1 = rect.x1 * scale_x, rect.y1 * scale_y
        color = self.marker_color(item)
        tag = f"correction-{index}"
        self.canvas.create_rectangle(x0 - 3, y0 - 3, x1 + 3, y1 + 3, outline=color, width=3, fill=color, stipple="gray25", tags=(tag,))
        self.canvas.create_text(x0, max(10, y0 - 10), text=f"{float(item.get('punkte') or 0):g} / {self.max_text(item)} P.", anchor="sw", fill=color, font=("Segoe UI", 10, "bold"), tags=(tag,))
        self.canvas.tag_bind(tag, "<Button-1>", lambda _event, selected=index: self.select_index(selected))

    def draw_criterion_markers(self, index: int, item: dict, page, scale_x: float, scale_y: float) -> None:
        for criterion in item.get("kriterien", []):
            status = criterion.get("status")
            if status not in ("erfüllt", "teilweise"):
                continue
            rect, state = self.find_anchor_rect(page, criterion.get("textstelle", ""))
            if rect is None:
                continue
            x = rect.x0 * scale_x - 8
            y = rect.y0 * scale_y + 4
            symbol, color = ("✓", "#137333") if status == "erfüllt" else ("~", "#b36b00")
            tag = f"criterion-{index}"
            self.canvas.create_text(x, y, text=symbol, anchor="e", fill=color, font=("Segoe UI", 13, "bold"), tags=(tag,))
            self.canvas.tag_bind(tag, "<Button-1>", lambda _event, selected=index: self.select_index(selected))

    @staticmethod
    def find_anchor_rect(page, anchor: str):
        words = anchor.replace("#", " ").split()
        candidates = [anchor] if anchor.strip() else []
        if len(words) > 8:
            candidates.append(" ".join(words[:8]))
        ambiguous = False
        for candidate in candidates:
            matches = page.search_for(candidate)
            if len(matches) == 1:
                return matches[0], "gefunden"
            if len(matches) > 1:
                ambiguous = True
        return None, "mehrdeutig" if ambiguous else "nicht_gefunden"

    def set_marker_state(self, index: int, state: str) -> None:
        self.marker_states[index] = state
        item = self.current_tasks[index]
        self.corrections.delete(index)
        self.corrections.insert(index, self.task_label(item, state))
        self.corrections.itemconfig(index, foreground=self.marker_color(item, state))

    def select_index(self, index: int) -> None:
        self.corrections.selection_clear(0, "end")
        self.corrections.selection_set(index)
        self.corrections.see(index)
        self.select_correction()

    def selected(self) -> dict | None:
        selection = self.corrections.curselection()
        return self.current_tasks[selection[0]] if selection else None

    def clear_editor(self) -> None:
        self.location.configure(text="Wählen Sie eine Korrektur aus.")
        self.points.delete(0, "end")
        self.maximum.configure(text="von ? Punkten")
        self.replace_text(self.rubric, "")
        self.reason.delete("1.0", "end")
        self.unclear.delete("1.0", "end")

    def select_correction(self, _event=None) -> None:
        item = self.selected()
        if not item:
            return
        text = f"Aufgabe {item['aufgabe']} · Seite {item.get('seite') or 'nicht bestimmt'}"
        if item.get("textstelle"):
            text += f"\nTextstelle: „{item['textstelle']}“"
        self.location.configure(text=text)
        self.points.delete(0, "end")
        self.points.insert(0, item.get("punkte") or 0)
        self.maximum.configure(text=f"von {self.max_text(item)} Punkten")
        self.show_rubric(item.get("kriterien", []))
        self.reason.delete("1.0", "end")
        self.reason.insert("1.0", self.format_reason(item.get("begruendung", "")))
        self.unclear.delete("1.0", "end")
        self.unclear.insert("1.0", item.get("unsicherheiten", ""))

    def show_rubric(self, criteria: list[dict]) -> None:
        symbols = {"erfüllt": "✓", "teilweise": "~", "fehlt": "✕", "unklar": "?"}
        lines = [f"{symbols.get(item.get('status'), '•')} {item.get('kriterium', '')}" for item in criteria]
        self.replace_text(self.rubric, "\n".join(lines) if lines else "Noch keine Einzelkriterien vorhanden.")

    @staticmethod
    def format_reason(text: str) -> str:
        text = text.strip()
        if "\n\n" in text:
            return text
        sentences = [sentence.strip() for sentence in text.split(". ") if sentence.strip()]
        return "\n\n".join(sentences) if len(sentences) > 1 else text

    @staticmethod
    def replace_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

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
        self.master.store.update_suggestion(self.master.scan_id, item["aufgabe"], points, self.reason.get("1.0", "end").strip(), self.unclear.get("1.0", "end").strip())
        self.suggestions = self.master.store.suggestion_details(self.master.scan_id)
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
        self._append_chat(f"Sie: {question}\n\n")
        add_chat = getattr(self.master, "_add_chat", None)
        if callable(add_chat):
            add_chat(f"Sie (Aufgabe {item['aufgabe']}): {question}\n\n")
        context = json.dumps({"projekt": self.master.store.project(self.master.project_id), "korrektur": item}, ensure_ascii=False)
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
        add_chat = getattr(self.master, "_add_chat", None)
        if callable(add_chat):
            add_chat(f"Assistent (Aufgabe): {answer}\n\n")

    def _append_chat(self, text: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", text)
        self.chat.see("end")
        self.chat.configure(state="disabled")
