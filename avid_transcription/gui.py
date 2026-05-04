"""
Tkinter GUI for the Avid Transcription Plugin.

Layout:
  ┌─────────────────────────────────────────────────┐
  │  Avid Transcription Plugin  v1.0                │
  ├─────────────────────────────────────────────────┤
  │  [File(s)]  path/to/clip.mxf     [Browse]       │
  │  [Output]   /output/dir          [Browse]        │
  ├──────────────── Settings ───────────────────────┤
  │  Model: [base ▾]  Language: [auto ▾]            │
  │  Task:  [transcribe ▾]   FPS: [25.0]            │
  │  Audio track: [0]                               │
  │  Formats: [x] SRT  [x] VTT  [ ] CSV  [ ] Markers│
  │  [ ] Export AAF markers                         │
  ├─────────────────────────────────────────────────┤
  │  [          Transcribe           ]               │
  │  ──────────────────── 42% ───────               │
  │  Status: Transcribed 12.3s / 29.4s              │
  ├─────────────────────────────────────────────────┤
  │  Transcript preview:                            │
  │  ┌──────────────────────────────────────────┐  │
  │  │ 00:00:03,200 --> 00:00:06,800            │  │
  │  │ Hello and welcome to the show.           │  │
  │  └──────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from .config import (
    SUBTITLE_FORMATS,
    WHISPER_MODELS,
    TranscriptionConfig,
)
from .pipeline import TranscriptionPipeline
from .subtitle_generator import SubtitleGenerator

logger = logging.getLogger(__name__)

LANGUAGES = [
    "auto", "en", "fr", "de", "es", "it", "pt", "nl", "pl", "ru",
    "zh", "ja", "ko", "ar", "hi", "sv", "da", "fi", "no", "tr",
    "uk", "cs", "ro", "hu", "bg", "el", "hr", "sk", "sl", "lt",
    "lv", "et", "vi", "id", "ms", "th", "fa", "he", "ur",
]

APP_TITLE = "Avid Transcription Plugin"
APP_VERSION = "v1.0"
WINDOW_MIN_WIDTH = 620
WINDOW_MIN_HEIGHT = 700

PAD = 8


class TranscriptionApp(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  {APP_VERSION}")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resizable(True, True)

        self._config = TranscriptionConfig.load()
        self._file_paths: List[Path] = []
        self._result_queue: queue.Queue = queue.Queue()
        self._running = False

        self._build_ui()
        self._apply_config_to_ui()
        self._poll_queue()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=PAD)
        main.pack(fill=tk.BOTH, expand=True)

        # ── Header ──
        header = ttk.Label(
            main,
            text=f"{APP_TITLE}  {APP_VERSION}",
            font=("Helvetica", 14, "bold"),
        )
        header.pack(pady=(0, PAD))

        # ── Input / Output ──
        io_frame = ttk.LabelFrame(main, text="Media", padding=PAD)
        io_frame.pack(fill=tk.X, pady=(0, PAD))
        self._build_io_section(io_frame)

        # ── Settings ──
        settings_frame = ttk.LabelFrame(main, text="Transcription Settings", padding=PAD)
        settings_frame.pack(fill=tk.X, pady=(0, PAD))
        self._build_settings_section(settings_frame)

        # ── Output formats ──
        fmt_frame = ttk.LabelFrame(main, text="Output Formats", padding=PAD)
        fmt_frame.pack(fill=tk.X, pady=(0, PAD))
        self._build_formats_section(fmt_frame)

        # ── AAF export ──
        aaf_frame = ttk.LabelFrame(main, text="Avid AAF Integration", padding=PAD)
        aaf_frame.pack(fill=tk.X, pady=(0, PAD))
        self._build_aaf_section(aaf_frame)

        # ── Transcribe button ──
        self._transcribe_btn = ttk.Button(
            main, text="Transcribe", command=self._start_transcription, width=20
        )
        self._transcribe_btn.pack(pady=(0, PAD))

        # ── Progress ──
        progress_frame = ttk.Frame(main)
        progress_frame.pack(fill=tk.X, pady=(0, PAD))
        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress_bar = ttk.Progressbar(
            progress_frame, variable=self._progress_var, maximum=100
        )
        self._progress_bar.pack(fill=tk.X)
        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(progress_frame, textvariable=self._status_var).pack(anchor=tk.W, pady=(2, 0))

        # ── Transcript preview ──
        preview_frame = ttk.LabelFrame(main, text="Transcript Preview", padding=PAD)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        self._preview_text = tk.Text(
            preview_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Courier", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
        )
        scroll = ttk.Scrollbar(preview_frame, command=self._preview_text.yview)
        self._preview_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._preview_text.pack(fill=tk.BOTH, expand=True)

    def _build_io_section(self, parent: ttk.Frame) -> None:
        # Files row
        ttk.Label(parent, text="Media file(s):").grid(row=0, column=0, sticky=tk.W)
        self._files_var = tk.StringVar(value="(none selected)")
        ttk.Label(parent, textvariable=self._files_var, relief="sunken", width=45).grid(
            row=0, column=1, padx=PAD, sticky=tk.EW
        )
        ttk.Button(parent, text="Browse…", command=self._browse_files).grid(row=0, column=2)

        # Output dir row
        ttk.Label(parent, text="Output folder:").grid(row=1, column=0, sticky=tk.W, pady=(PAD, 0))
        self._output_var = tk.StringVar(value="(same as input)")
        ttk.Label(parent, textvariable=self._output_var, relief="sunken", width=45).grid(
            row=1, column=1, padx=PAD, sticky=tk.EW, pady=(PAD, 0)
        )
        ttk.Button(parent, text="Browse…", command=self._browse_output).grid(
            row=1, column=2, pady=(PAD, 0)
        )
        parent.columnconfigure(1, weight=1)

    def _build_settings_section(self, parent: ttk.Frame) -> None:
        # Model
        ttk.Label(parent, text="Whisper model:").grid(row=0, column=0, sticky=tk.W)
        self._model_var = tk.StringVar()
        model_combo = ttk.Combobox(
            parent, textvariable=self._model_var, values=WHISPER_MODELS,
            state="readonly", width=14,
        )
        model_combo.grid(row=0, column=1, padx=(PAD, PAD * 3), sticky=tk.W)

        # Language
        ttk.Label(parent, text="Language:").grid(row=0, column=2, sticky=tk.W)
        self._language_var = tk.StringVar(value="auto")
        lang_combo = ttk.Combobox(
            parent, textvariable=self._language_var, values=LANGUAGES,
            state="readonly", width=8,
        )
        lang_combo.grid(row=0, column=3, padx=PAD, sticky=tk.W)

        # Task
        ttk.Label(parent, text="Task:").grid(row=1, column=0, sticky=tk.W, pady=(PAD, 0))
        self._task_var = tk.StringVar(value="transcribe")
        task_combo = ttk.Combobox(
            parent, textvariable=self._task_var,
            values=["transcribe", "translate"], state="readonly", width=14,
        )
        task_combo.grid(row=1, column=1, padx=(PAD, PAD * 3), sticky=tk.W, pady=(PAD, 0))

        # FPS
        ttk.Label(parent, text="FPS:").grid(row=1, column=2, sticky=tk.W, pady=(PAD, 0))
        self._fps_var = tk.StringVar(value="25.0")
        ttk.Combobox(
            parent, textvariable=self._fps_var,
            values=["23.976", "24", "25", "29.97", "30", "50", "59.94", "60"],
            width=8,
        ).grid(row=1, column=3, padx=PAD, sticky=tk.W, pady=(PAD, 0))

        # Audio track
        ttk.Label(parent, text="Audio track:").grid(row=2, column=0, sticky=tk.W, pady=(PAD, 0))
        self._audio_track_var = tk.StringVar(value="0")
        ttk.Spinbox(
            parent, from_=0, to=31, textvariable=self._audio_track_var, width=4
        ).grid(row=2, column=1, padx=PAD, sticky=tk.W, pady=(PAD, 0))

        # VAD filter
        self._vad_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            parent, text="Voice activity filter (VAD)", variable=self._vad_var
        ).grid(row=2, column=2, columnspan=2, sticky=tk.W, pady=(PAD, 0))

        # Word timestamps
        self._word_ts_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            parent, text="Word-level timestamps", variable=self._word_ts_var
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        # faster-whisper backend
        self._faster_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            parent, text="Use faster-whisper backend", variable=self._faster_var
        ).grid(row=3, column=2, columnspan=2, sticky=tk.W, pady=(4, 0))

    def _build_formats_section(self, parent: ttk.Frame) -> None:
        self._fmt_vars: dict[str, tk.BooleanVar] = {}
        labels = {"srt": "SRT", "vtt": "WebVTT", "csv": "CSV", "avid_markers": "Avid Markers"}
        for col, (key, label) in enumerate(labels.items()):
            var = tk.BooleanVar(value=key in ("srt", "vtt"))
            self._fmt_vars[key] = var
            ttk.Checkbutton(parent, text=label, variable=var).grid(
                row=0, column=col, padx=PAD, sticky=tk.W
            )

    def _build_aaf_section(self, parent: ttk.Frame) -> None:
        self._aaf_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parent, text="Export markers into AAF file", variable=self._aaf_var,
            command=self._toggle_aaf,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W)

        ttk.Label(parent, text="AAF path:").grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        self._aaf_path_var = tk.StringVar(value="")
        self._aaf_entry = ttk.Entry(parent, textvariable=self._aaf_path_var, width=40, state=tk.DISABLED)
        self._aaf_entry.grid(row=1, column=1, padx=PAD, sticky=tk.EW, pady=(4, 0))
        self._aaf_browse_btn = ttk.Button(
            parent, text="Browse…", command=self._browse_aaf, state=tk.DISABLED
        )
        self._aaf_browse_btn.grid(row=1, column=2, pady=(4, 0))
        parent.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------

    def _browse_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select media file(s)",
            filetypes=[
                ("All media", "*.mxf *.mov *.mp4 *.avi *.mts *.m2ts *.mkv *.wav *.mp3 *.aac"),
                ("MXF", "*.mxf"),
                ("QuickTime", "*.mov"),
                ("MP4", "*.mp4"),
                ("Audio", "*.wav *.mp3 *.aac *.flac"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            self._file_paths = [Path(p) for p in paths]
            if len(self._file_paths) == 1:
                self._files_var.set(str(self._file_paths[0]))
            else:
                self._files_var.set(f"{len(self._file_paths)} files selected")

    def _browse_output(self) -> None:
        directory = filedialog.askdirectory(title="Select output folder")
        if directory:
            self._output_var.set(directory)

    def _browse_aaf(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Avid AAF file",
            filetypes=[("AAF files", "*.aaf"), ("All files", "*.*")],
        )
        if path:
            self._aaf_path_var.set(path)

    def _toggle_aaf(self) -> None:
        state = tk.NORMAL if self._aaf_var.get() else tk.DISABLED
        self._aaf_entry.configure(state=state)
        self._aaf_browse_btn.configure(state=state)

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def _build_config_from_ui(self) -> TranscriptionConfig:
        cfg = TranscriptionConfig()
        cfg.whisper_model = self._model_var.get()
        lang = self._language_var.get()
        cfg.language = None if lang == "auto" else lang
        cfg.task = self._task_var.get()
        cfg.vad_filter = self._vad_var.get()
        cfg.word_timestamps = self._word_ts_var.get()
        cfg.use_faster_whisper = self._faster_var.get()
        cfg.output_formats = [k for k, v in self._fmt_vars.items() if v.get()]
        out = self._output_var.get()
        cfg.output_directory = None if out == "(same as input)" else out
        cfg.export_to_aaf = self._aaf_var.get()
        cfg.avid_project_path = self._aaf_path_var.get() or None
        return cfg

    def _start_transcription(self) -> None:
        if not self._file_paths:
            messagebox.showwarning("No files", "Please select at least one media file.")
            return
        if self._running:
            return

        config = self._build_config_from_ui()
        config.save()

        if not config.output_formats:
            messagebox.showwarning("No formats", "Please select at least one output format.")
            return

        self._running = True
        self._transcribe_btn.configure(state=tk.DISABLED, text="Transcribing…")
        self._set_preview("")
        self._progress_var.set(0)
        self._status_var.set("Starting…")

        fps = float(self._fps_var.get() or "25")
        audio_track = int(self._audio_track_var.get() or "0")

        thread = threading.Thread(
            target=self._transcription_worker,
            args=(self._file_paths, config, fps, audio_track),
            daemon=True,
        )
        thread.start()

    def _transcription_worker(
        self,
        files: List[Path],
        config: TranscriptionConfig,
        fps: float,
        audio_track: int,
    ) -> None:
        try:
            pipeline = TranscriptionPipeline(config)
            total = len(files)

            all_preview_lines: List[str] = []

            for idx, path in enumerate(files):
                def _progress(frac: float, msg: str, _idx=idx) -> None:
                    overall = (_idx + frac) / total * 100
                    self._result_queue.put(("progress", overall, msg))

                result = pipeline.process_file(
                    path, fps=fps, audio_track=audio_track, progress=_progress
                )

                # Build preview for this file
                generator = SubtitleGenerator(config)
                srt_text = generator.to_srt(result.transcription.segments)
                all_preview_lines.append(f"── {path.name} ──\n{srt_text}")

            self._result_queue.put(("done", "\n\n".join(all_preview_lines)))
        except Exception as exc:
            logger.exception("Transcription error")
            self._result_queue.put(("error", str(exc)))

    # ------------------------------------------------------------------
    # Async queue polling
    # ------------------------------------------------------------------

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._result_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, pct, msg = item
                    self._progress_var.set(pct)
                    self._status_var.set(msg)
                elif kind == "done":
                    _, preview = item
                    self._progress_var.set(100)
                    self._status_var.set("Transcription complete.")
                    self._set_preview(preview)
                    self._running = False
                    self._transcribe_btn.configure(state=tk.NORMAL, text="Transcribe")
                elif kind == "error":
                    _, msg = item
                    self._status_var.set(f"Error: {msg}")
                    messagebox.showerror("Transcription Error", msg)
                    self._running = False
                    self._transcribe_btn.configure(state=tk.NORMAL, text="Transcribe")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_preview(self, text: str) -> None:
        self._preview_text.configure(state=tk.NORMAL)
        self._preview_text.delete("1.0", tk.END)
        self._preview_text.insert(tk.END, text)
        self._preview_text.configure(state=tk.DISABLED)

    def _apply_config_to_ui(self) -> None:
        cfg = self._config
        self._model_var.set(cfg.whisper_model)
        self._language_var.set(cfg.language or "auto")
        self._task_var.set(cfg.task)
        self._vad_var.set(cfg.vad_filter)
        self._word_ts_var.set(cfg.word_timestamps)
        self._faster_var.set(cfg.use_faster_whisper)
        for key, var in self._fmt_vars.items():
            var.set(key in cfg.output_formats)
        if cfg.output_directory:
            self._output_var.set(cfg.output_directory)
        if cfg.export_to_aaf:
            self._aaf_var.set(True)
            self._toggle_aaf()
            if cfg.avid_project_path:
                self._aaf_path_var.set(cfg.avid_project_path)
