"""Oxx' FaceSwap – grafische Oberfläche (Tkinter, keine Zusatz-Dependencies).

Start:  python faceswap_gui.py   (oder "Oxx' FaceSwap.bat" doppelklicken)

Besonderheiten:
  * Strg+V fügt ein Bild aus der Zwischenablage in das aktive Panel ein
  * Quelle lässt sich bequem aus dem Ordner heads/ wählen
  * Das Ergebnis kann mit einem Klick in die Zwischenablage kopiert werden
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from faceswap.clipboard import clipboard_content, copy_image_to_clipboard
from faceswap.engine import (
    FaceSwapEngine,
    HEADS_DIR,
    ModelMissingError,
    annotate_faces,
    list_head_images,
    load_image,
    save_image,
    unique_output_path,
)

BG = "#0f1319"
PANEL = "#171d27"
PANEL_LIGHT = "#1f2734"
BORDER = "#2a3446"
TEXT = "#e7edf6"
MUTED = "#8b98ad"
ACCENT = "#3ddc84"
ACCENT_DARK = "#2bb96c"
INFO = "#4aa8ff"
ERROR = "#ff6b6b"

IMAGE_FILETYPES = [
    ("Bilder", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
    ("Alle Dateien", "*.*"),
]

HEAD_CHOICE_EMPTY = "– heads/ ist leer –"


def bgr_to_pil(image_bgr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))


def pil_to_bgr(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)


class ImagePane(ttk.Frame):
    """Panel mit Titel, Buttons, Dateiname und Bildvorschau."""

    def __init__(self, master, title: str, on_pick, on_paste, on_activate) -> None:
        super().__init__(master, style="Panel.TFrame", padding=14)
        self._pil: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._resize_job: str | None = None
        self.on_activate = on_activate
        self.placeholder = "Klicken, „Wählen…“ oder Strg+V zum Einfügen"

        header = ttk.Frame(self, style="Panel.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text=title, style="PaneTitle.TLabel").pack(side="left")
        ttk.Button(
            header, text="Wählen…", command=on_pick, style="Ghost.TButton"
        ).pack(side="right")
        ttk.Button(
            header,
            text="Einfügen",
            command=on_paste,
            style="Ghost.TButton",
        ).pack(side="right", padx=(0, 6))

        self.filename = ttk.Label(
            self, text="– keine Datei –", style="Muted.TLabel", anchor="w"
        )
        self.filename.pack(fill="x", pady=(8, 8))

        self.extra = ttk.Frame(self, style="Panel.TFrame")
        self.extra.pack(fill="x")

        self.canvas = tk.Canvas(
            self,
            bg="#0b0f15",
            highlightthickness=2,
            highlightbackground=BORDER,
            height=380,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True, pady=(8, 0))
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Button-1>", self._activate)
        self.canvas.bind("<Double-Button-1>", lambda _event: on_pick())

    def _activate(self, _event=None) -> None:
        self.on_activate()

    def set_active(self, active: bool) -> None:
        self.canvas.configure(
            highlightbackground=ACCENT if active else BORDER,
            highlightthickness=2 if active else 1,
        )

    def set_image(self, pil_image: Image.Image | None, filename: str | None = None):
        self._pil = pil_image
        if filename is not None:
            self.filename.configure(text=filename)
        self._render()

    def set_filename(self, text: str):
        self.filename.configure(text=text)

    def _on_configure(self, _event) -> None:
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._render)

    def _render(self) -> None:
        self._resize_job = None
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)

        if self._pil is None:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text=self.placeholder,
                fill="#43506a",
                font=("Segoe UI", 12),
                width=max(width - 40, 120),
                justify="center",
            )
            return

        ratio = min(width / self._pil.width, height / self._pil.height)
        target = (
            max(1, int(self._pil.width * ratio)),
            max(1, int(self._pil.height * ratio)),
        )
        resized = self._pil.resize(target, Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(resized)
        self.canvas.create_image(width / 2, height / 2, image=self._photo)


class OxxFaceSwapApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Oxx' FaceSwap – lokaler Face Swap")
        self.configure(bg=BG)
        self.geometry("1160x950")
        self.minsize(980, 720)
        self._set_icon()

        self.engine = FaceSwapEngine()
        self._queue: queue.Queue = queue.Queue()
        self._busy = False
        self._jobs = 0
        self._scan_token = 0

        self.source_path: Path | None = None
        self.target_path: Path | None = None
        self.source_bgr: np.ndarray | None = None
        self.target_bgr: np.ndarray | None = None
        self.result_bgr: np.ndarray | None = None
        self.source_faces: list = []
        self.target_faces: list = []
        self.head_images: list[Path] = []
        self.active_pane = "source"
        self.show_result = tk.BooleanVar(value=False)
        self.show_boxes = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar(value="Bereit. Links Spenderbild, rechts Zielbild – oder Strg+V zum Einfügen.")
        self.status_color = MUTED

        self._build_styles()
        self._build_layout()
        self._bind_keys()
        self._refresh_heads()
        self._set_active("source")
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ------------------------------------------------------------------ Setup
    def _set_icon(self) -> None:
        icon = Path(__file__).resolve().parent / "assets" / "icon.ico"
        if icon.is_file():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Bar.TFrame", background=BG)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 20))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("PaneTitle.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 11))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("FieldLabel.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=PANEL_LIGHT, foreground=MUTED, font=("Segoe UI", 9), padding=(10, 6))
        style.configure("Hint.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))

        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#06140c",
            font=("Segoe UI Semibold", 11),
            padding=(18, 11),
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_DARK), ("disabled", "#26313f")],
            foreground=[("disabled", "#5f6b7c")],
        )
        style.configure(
            "Ghost.TButton",
            background=PANEL_LIGHT,
            foreground=TEXT,
            padding=(12, 6),
            borderwidth=0,
        )
        style.map("Ghost.TButton", background=[("active", BORDER)])
        style.configure(
            "Info.TButton",
            background=INFO,
            foreground="#04121f",
            font=("Segoe UI Semibold", 11),
            padding=(18, 10),
            borderwidth=0,
        )
        style.map(
            "Info.TButton",
            background=[("active", "#2f92e6"), ("disabled", "#26313f")],
            foreground=[("disabled", "#5f6b7c")],
        )
        style.configure(
            "GhostAction.TButton",
            background=PANEL_LIGHT,
            foreground=TEXT,
            font=("Segoe UI Semibold", 11),
            padding=(18, 10),
            borderwidth=0,
        )
        style.map(
            "GhostAction.TButton",
            background=[("active", BORDER), ("disabled", "#26313f")],
            foreground=[("disabled", "#5f6b7c")],
        )
        style.configure("TCheckbutton", background=BG, foreground=TEXT, focuscolor=BG)
        style.map("TCheckbutton", background=[("active", BG)], foreground=[("disabled", MUTED)])
        style.configure(
            "TCombobox",
            fieldbackground=PANEL_LIGHT,
            background=PANEL_LIGHT,
            foreground=TEXT,
            arrowcolor=TEXT,
        )
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_LIGHT)])
        style.configure(
            "Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor=PANEL_LIGHT,
            borderwidth=0,
        )
        style.configure(
            "Slim.Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor=PANEL_LIGHT,
            borderwidth=0,
            thickness=4,
        )

    def _build_layout(self) -> None:
        header = ttk.Frame(self, style="Bar.TFrame", padding=(20, 16, 20, 8))
        header.pack(fill="x")
        ttk.Label(header, text="⚡ Oxx' FaceSwap", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Gesichter lokal tauschen – Bilder per Strg+V einfügen, Ergebnis mit einem Klick kopieren.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        # Untere Leisten zuerst packen: Sie behalten ihre volle Höhe,
        # der Bildbereich darüber bekommt den restlichen Platz.
        self._build_status()
        self._build_actions()
        self._build_options()

        body = ttk.Frame(self, style="Bar.TFrame", padding=(20, 8, 20, 8))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="pane")
        body.columnconfigure(1, weight=1, uniform="pane")
        body.rowconfigure(0, weight=1)

        self.source_pane = ImagePane(
            body,
            "Quellbild · Spender",
            self.pick_source,
            lambda: self.paste_into("source"),
            lambda: self._set_active("source"),
        )
        self.source_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.target_pane = ImagePane(
            body,
            "Zielbild · Empfänger",
            self.pick_target,
            lambda: self.paste_into("target"),
            lambda: self._set_active("target"),
        )
        self.target_pane.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_heads_selector()

    def _build_heads_selector(self) -> None:
        row = self.source_pane.extra
        ttk.Label(row, text="Aus heads/:", style="Muted.TLabel").pack(side="left")
        self.heads_combo = ttk.Combobox(
            row, state="disabled", width=26, values=[HEAD_CHOICE_EMPTY]
        )
        self.heads_combo.current(0)
        self.heads_combo.pack(side="left", padx=(6, 6))
        self.heads_combo.bind("<<ComboboxSelected>>", self._on_head_selected)
        ttk.Button(
            row, text="↻", width=3, style="Ghost.TButton", command=self._refresh_heads
        ).pack(side="left")

    def _build_options(self) -> None:
        options = ttk.Frame(self, style="Bar.TFrame", padding=(20, 4, 20, 4))
        options.pack(fill="x", side="bottom")

        ttk.Label(options, text="Spender-Gesicht", style="FieldLabel.TLabel").pack(side="left")
        self.source_face_combo = ttk.Combobox(
            options, state="disabled", width=18, values=["Größtes Gesicht"]
        )
        self.source_face_combo.current(0)
        self.source_face_combo.pack(side="left", padx=(6, 18))

        ttk.Label(options, text="Zielgesichter", style="FieldLabel.TLabel").pack(side="left")
        self.target_face_combo = ttk.Combobox(
            options, state="disabled", width=18, values=["Alle Gesichter"]
        )
        self.target_face_combo.current(0)
        self.target_face_combo.pack(side="left", padx=(6, 18))

        ttk.Checkbutton(
            options,
            text="Boxen anzeigen",
            variable=self.show_boxes,
            command=self._refresh_previews,
        ).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(
            options,
            text="Ergebnis anzeigen",
            variable=self.show_result,
            command=self._refresh_previews,
        ).pack(side="left")

    def _build_actions(self) -> None:
        actions = ttk.Frame(self, style="Bar.TFrame", padding=(20, 8, 20, 8))
        actions.pack(fill="x", side="bottom")

        # Ein gemeinsames Grid mit gleichen Spaltenbreiten sorgt dafür,
        # dass alle Aktionsbuttons exakt gleich groß sind.
        buttons = ttk.Frame(actions, style="Bar.TFrame")
        buttons.pack(side="left")
        for column in range(4):
            buttons.columnconfigure(column, weight=1, uniform="action")

        self.swap_button = ttk.Button(
            buttons,
            text="⚡ Gesichter tauschen",
            style="Accent.TButton",
            command=self.start_swap,
        )
        self.swap_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.save_button = ttk.Button(
            buttons,
            text="Speichern unter…",
            style="Info.TButton",
            command=self.save_result,
            state="disabled",
        )
        self.save_button.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        self.copy_icon = self._load_copy_icon()
        self.copy_button = ttk.Button(
            buttons,
            text="Kopieren",
            style="Info.TButton",
            command=self.copy_result,
            state="disabled",
        )
        if self.copy_icon is not None:
            self.copy_button.configure(image=self.copy_icon, compound="left")
        self.copy_button.grid(row=0, column=2, sticky="ew", padx=(0, 8))

        ttk.Button(
            buttons,
            text="Zurücksetzen",
            style="GhostAction.TButton",
            command=self.reset,
        ).grid(row=0, column=3, sticky="ew")

    def _build_status(self) -> None:
        status_frame = ttk.Frame(self, style="Bar.TFrame", padding=(20, 0, 20, 14))
        status_frame.pack(fill="x", side="bottom")
        self.status_label = ttk.Label(
            status_frame, textvariable=self.status_text, style="Status.TLabel", anchor="w"
        )
        self.status_label.pack(fill="x")

        self.progress = ttk.Progressbar(
            status_frame,
            mode="indeterminate",
            style="Slim.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x", pady=(6, 0))
        self.progress.pack_forget()

        self.hint_label = ttk.Label(
            status_frame,
            text=(
                "Strg+V fügt in das aktive Bild ein (grüner Rahmen) · "
                "Eigene Spenderbilder in den Ordner „heads“ legen. "
                "Nur mit Einverständnis der abgebildeten Personen verwenden – "
                "die InsightFace-Modelle sind für nicht-kommerzielle Forschung lizenziert."
            ),
            style="Hint.TLabel",
            wraplength=1090,
            justify="left",
        )
        self.hint_label.pack(anchor="w", pady=(6, 0))

    def _load_copy_icon(self):
        path = Path(__file__).resolve().parent / "assets" / "copy.png"
        if not path.is_file():
            return None
        try:
            image = Image.open(path).convert("RGBA")
            image = image.resize((18, 18), Image.LANCZOS)
            photo = ImageTk.PhotoImage(image)
        except (OSError, tk.TclError):
            return None
        # Referenz behalten, sonst verschwindet das Bild aus dem Button.
        self._copy_icon_photo = photo
        return photo

    def _bind_keys(self) -> None:
        self.bind("<Control-o>", lambda _e: self.pick_source())
        self.bind("<Control-t>", lambda _e: self.pick_target())
        self.bind("<Control-s>", lambda _e: self.save_result())
        self.bind("<Control-c>", lambda _e: self.copy_result())
        self.bind("<Control-v>", lambda _e: self.paste_to_active())
        self.bind("<F5>", lambda _e: self.start_swap())

    # ------------------------------------------------------------------ Status
    def set_status(self, text: str, color: str = MUTED) -> None:
        self.status_text.set(text)
        self.status_label.configure(foreground=color)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.swap_button.configure(state=state)
        if busy:
            if not self.progress.winfo_ismapped():
                self.progress.pack(fill="x", pady=(6, 0), before=self.hint_label)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.configure(value=0)
            self.progress.pack_forget()

    def _set_active(self, pane: str) -> None:
        self.active_pane = pane
        self.source_pane.set_active(pane == "source")
        self.target_pane.set_active(pane == "target")

    # ------------------------------------------------------------- Async-Helfer
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, callback, payload = self._queue.get_nowait()
                self._jobs = max(0, self._jobs - 1)
                self.set_busy(self._jobs > 0)
                if kind == "ok":
                    callback(payload)
                else:
                    self._handle_error(payload)
        except queue.Empty:
            pass
        self.after(60, self._poll_queue)

    def _submit(self, work, on_done) -> None:
        self._jobs += 1
        self.set_busy(True)

        def runner() -> None:
            try:
                result = work()
            except Exception as error:  # noqa: BLE001 – an die UI weitergeben
                self._queue.put(("error", on_done, error))
            else:
                self._queue.put(("ok", on_done, result))

        threading.Thread(target=runner, daemon=True).start()

    def _handle_error(self, error: Exception) -> None:
        if isinstance(error, ModelMissingError):
            self.set_status("Modelle fehlen.", ERROR)
            messagebox.showerror(
                "Modelle fehlen",
                f"{error}\n\nFühre einmalig install.ps1 aus.",
                parent=self,
            )
        else:
            self.set_status(f"Fehler: {error}", ERROR)
            messagebox.showerror("Fehler", str(error), parent=self)

    # ------------------------------------------------------------- heads-Ordner
    def _refresh_heads(self) -> None:
        self.head_images = list_head_images()
        if self.head_images:
            names = [
                str(path.relative_to(HEADS_DIR)) for path in self.head_images
            ]
            values = ["– Bild aus heads/ –"] + names
            self.heads_combo.configure(values=values, state="readonly")
            self.heads_combo.current(0)
            if not HEADS_DIR.is_dir():
                HEADS_DIR.mkdir(parents=True, exist_ok=True)
        else:
            HEADS_DIR.mkdir(parents=True, exist_ok=True)
            self.heads_combo.configure(values=[HEAD_CHOICE_EMPTY], state="disabled")
            self.heads_combo.current(0)

    def _on_head_selected(self, _event=None) -> None:
        index = self.heads_combo.current()
        if index <= 0 or index - 1 >= len(self.head_images):
            return
        path = self.head_images[index - 1]
        try:
            self.load_source(path)
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Bild konnte nicht geladen werden", str(error), parent=self)

    # ------------------------------------------------------------------- Bilder
    def pick_source(self) -> None:
        path = filedialog.askopenfilename(title="Spenderbild wählen", filetypes=IMAGE_FILETYPES)
        if path:
            self.load_source(Path(path))

    def pick_target(self) -> None:
        path = filedialog.askopenfilename(title="Zielbild wählen", filetypes=IMAGE_FILETYPES)
        if path:
            self.load_target(Path(path))

    # -------------------------------------------------------- Zwischenablage
    def paste_into(self, pane: str) -> None:
        content = clipboard_content()
        if content is None:
            self.set_status(
                "In der Zwischenablage ist kein Bild. Erst ein Bild kopieren (z. B. Screenshot).",
                ERROR,
            )
            return
        kind, value = content
        try:
            if kind == "path":
                if pane == "source":
                    self.load_source(Path(value))
                else:
                    self.load_target(Path(value))
                self.set_status(f"Aus der Zwischenablage geladen: {Path(value).name}", ACCENT)
                return

            image_bgr = pil_to_bgr(value)
            label = f"Zwischenablage · {image_bgr.shape[1]}×{image_bgr.shape[0]}"
            if pane == "source":
                self._apply_source(image_bgr, label, path=None)
            else:
                self._apply_target(image_bgr, label, path=None)
            self.set_status("Bild aus der Zwischenablage eingefügt.", ACCENT)
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Einfügen fehlgeschlagen", str(error), parent=self)

    def paste_to_active(self) -> None:
        self.paste_into(self.active_pane)

    def copy_result(self) -> None:
        if self.result_bgr is None:
            return
        try:
            copy_image_to_clipboard(bgr_to_pil(self.result_bgr))
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Kopieren fehlgeschlagen", str(error), parent=self)
            return
        self.set_status(
            "Ergebnis in der Zwischenablage – jetzt z. B. in WhatsApp mit Strg+V einfügen. 📋",
            ACCENT,
        )

    # ------------------------------------------------------------------ Laden
    def load_source(self, path: Path) -> None:
        image_bgr = load_image(path)
        label = f"{path.name} · {image_bgr.shape[1]}×{image_bgr.shape[0]}"
        self._apply_source(image_bgr, label, path=path)

    def load_target(self, path: Path) -> None:
        image_bgr = load_image(path)
        label = f"{path.name} · {image_bgr.shape[1]}×{image_bgr.shape[0]}"
        self._apply_target(image_bgr, label, path=path)

    def _apply_source(self, image_bgr: np.ndarray, label: str, path: Path | None) -> None:
        self.source_path = path
        self.source_bgr = image_bgr
        self.source_faces = []
        self.source_pane.set_filename(label)
        self._reset_source_combo()
        self.show_result.set(False)
        self._refresh_previews()
        self._set_active("source")
        self._start_scan()

    def _apply_target(self, image_bgr: np.ndarray, label: str, path: Path | None) -> None:
        self.target_path = path
        self.target_bgr = image_bgr
        self.target_faces = []
        self.result_bgr = None
        self.save_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.target_pane.set_filename(label)
        self._reset_target_combo()
        self.show_result.set(False)
        self._refresh_previews()
        self._set_active("target")
        self._start_scan()

    def _reset_source_combo(self) -> None:
        self.source_face_combo.configure(state="disabled")
        self.source_face_combo.configure(values=["Größtes Gesicht"])
        self.source_face_combo.current(0)

    def _reset_target_combo(self) -> None:
        self.target_face_combo.configure(state="disabled")
        self.target_face_combo.configure(values=["Alle Gesichter"])
        self.target_face_combo.current(0)

    def _refresh_previews(self) -> None:
        if self.source_bgr is not None:
            preview = self.source_bgr
            if self.show_boxes.get() and self.source_faces:
                preview = annotate_faces(preview, self.source_faces)
            self.source_pane.set_image(bgr_to_pil(preview))

        if self.target_bgr is not None:
            if self.show_result.get() and self.result_bgr is not None:
                self.target_pane.set_image(bgr_to_pil(self.result_bgr))
            else:
                preview = self.target_bgr
                if self.show_boxes.get() and self.target_faces:
                    preview = annotate_faces(
                        preview, self.target_faces, self._selected_target_indices()
                    )
                self.target_pane.set_image(bgr_to_pil(preview))

    # -------------------------------------------------------------------- Scan
    def _start_scan(self) -> None:
        self._scan_token += 1
        token = self._scan_token
        source_bgr = self.source_bgr
        target_bgr = self.target_bgr

        self.set_status("Lade KI-Modelle und suche Gesichter… (nur beim ersten Mal etwas länger)")

        def work():
            self.engine.load()
            result = {"source": None, "target": None}
            if source_bgr is not None:
                result["source"] = self.engine.detect(source_bgr)
            if target_bgr is not None:
                result["target"] = self.engine.detect(target_bgr)
            return result

        def done(result) -> None:
            if token != self._scan_token:
                return
            if result["source"] is not None:
                self.source_faces = result["source"]
                self._fill_source_combo()
            if result["target"] is not None:
                self.target_faces = result["target"]
                self._fill_target_combo()
            self._refresh_previews()
            self._report_faces()

        self._submit(work, done)

    def _fill_source_combo(self) -> None:
        count = len(self.source_faces)
        values = ["Größtes Gesicht"] + [f"Gesicht {i}" for i in range(1, count + 1)]
        self.source_face_combo.configure(values=values)
        self.source_face_combo.current(0)
        self.source_face_combo.configure(state="readonly" if count else "disabled")

    def _fill_target_combo(self) -> None:
        count = len(self.target_faces)
        values = ["Alle Gesichter"] + [f"Gesicht {i}" for i in range(1, count + 1)]
        self.target_face_combo.configure(values=values)
        self.target_face_combo.current(0)
        self.target_face_combo.configure(state="readonly" if count else "disabled")

    def _report_faces(self) -> None:
        parts = []
        if self.source_bgr is not None:
            parts.append(f"Spender: {len(self.source_faces)} Gesicht(er)")
        if self.target_bgr is not None:
            parts.append(f"Ziel: {len(self.target_faces)} Gesicht(er)")
        device = self.engine.active_device if self.engine.ready else "–"
        self.set_status(f"{' · '.join(parts)}   |   Gerät: {device}", MUTED)

    def _selected_target_indices(self) -> list[int]:
        selection = self.target_face_combo.current()
        if selection <= 0:
            return list(range(len(self.target_faces)))
        return [selection - 1]

    def _selected_source_index(self) -> int | None:
        selection = self.source_face_combo.current()
        return None if selection <= 0 else selection

    # -------------------------------------------------------------------- Swap
    def start_swap(self) -> None:
        if self._busy:
            return
        if self.source_bgr is None or self.target_bgr is None:
            messagebox.showinfo(
                "Bilder fehlen",
                "Bitte sowohl ein Spender- als auch ein Zielbild wählen "
                "(oder mit Strg+V einfügen).",
                parent=self,
            )
            return
        if not self.source_faces or not self.target_faces:
            messagebox.showinfo(
                "Keine Gesichter",
                "Es wurden nicht in beiden Bildern Gesichter gefunden.",
                parent=self,
            )
            return

        source_index = self._selected_source_index()
        target_indices = self._selected_target_indices()
        target_path = self.target_path
        source_bgr = self.source_bgr
        target_bgr = self.target_bgr

        self.set_status(f"Tausche {len(target_indices)} Gesicht(er)…")
        self.show_result.set(False)

        def work():
            self.engine.load()
            source_faces = self.source_faces or self.engine.detect(source_bgr)
            target_faces = self.target_faces or self.engine.detect(target_bgr)
            indices = [i for i in target_indices if i < len(target_faces)]
            if not indices:
                raise RuntimeError("Keine passenden Zielgesichter gefunden.")
            source_face = self.engine.pick_source_face(source_faces, source_index)
            result = self.engine.swap_faces(target_bgr, target_faces, source_face, indices)
            name = target_path if target_path is not None else Path("Zwischenablage.jpg")
            auto_save = save_image(result, unique_output_path(name))
            return result, auto_save

        def done(payload) -> None:
            result, auto_save = payload
            self.result_bgr = result
            self.show_result.set(True)
            self.show_boxes.set(False)
            self._refresh_previews()
            self.save_button.configure(state="normal")
            self.copy_button.configure(state="normal")
            self.set_status(
                f"Fertig! ⚡ Gespeichert: {auto_save} – oder „Kopieren“ für WhatsApp & Co.",
                ACCENT,
            )

        self._submit(work, done)

    def save_result(self) -> None:
        if self.result_bgr is None:
            return
        default_name = "swapped.jpg"
        if self.target_path is not None:
            default_name = f"{self.target_path.stem}_swapped.jpg"
        path = filedialog.asksaveasfilename(
            title="Ergebnis speichern",
            defaultextension=".jpg",
            initialfile=default_name,
            filetypes=[
                ("JPEG", "*.jpg"),
                ("PNG (verlustfrei)", "*.png"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not path:
            return
        save_image(self.result_bgr, Path(path))
        self.set_status(f"Gespeichert: {path}", ACCENT)

    def reset(self) -> None:
        self.source_path = self.target_path = None
        self.source_bgr = self.target_bgr = self.result_bgr = None
        self.source_faces = self.target_faces = []
        self.save_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.show_result.set(False)
        self._reset_source_combo()
        self._reset_target_combo()
        self.source_pane.set_image(None, "– keine Datei –")
        self.target_pane.set_image(None, "– keine Datei –")
        self.set_status("Zurückgesetzt. Wähle neue Bilder oder füge mit Strg+V ein.")


def main() -> None:
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 – unter Linux/macOS nicht vorhanden
        pass
    app = OxxFaceSwapApp()
    app.mainloop()


if __name__ == "__main__":
    main()
