"""
Entry points for the Avid Transcription Plugin.

  GUI mode:   avid-transcription
  CLI mode:   avid-transcription --cli  <file> [options]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="avid-transcription",
        description="Avid Media Composer transcription & subtitle plugin",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in headless CLI mode (no GUI).",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Media file path(s) to transcribe (CLI mode).",
    )
    parser.add_argument("--model", default="base", choices=[
        "tiny", "tiny.en", "base", "base.en", "small", "small.en",
        "medium", "medium.en", "large", "large-v2", "large-v3",
    ])
    parser.add_argument(
        "--language", default=None,
        help="Force a language code (e.g. 'en', 'fr'). Default: auto-detect.",
    )
    parser.add_argument(
        "--task", choices=["transcribe", "translate"], default="transcribe",
    )
    parser.add_argument(
        "--formats", nargs="+", default=["srt", "vtt"],
        choices=["srt", "vtt", "csv", "avid_markers"],
        help="Output format(s).",
    )
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--audio-track", type=int, default=0)
    parser.add_argument(
        "--no-faster-whisper", action="store_true",
        help="Force original openai-whisper backend.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.cli:
        _run_cli(args)
    else:
        _run_gui()


def _run_cli(args) -> None:
    if not args.files:
        print("Error: provide at least one media file in CLI mode.", file=sys.stderr)
        sys.exit(1)

    from .config import TranscriptionConfig
    from .pipeline import TranscriptionPipeline

    cfg = TranscriptionConfig()
    cfg.whisper_model = args.model
    cfg.language = args.language
    cfg.task = args.task
    cfg.output_formats = args.formats
    cfg.output_directory = args.output_dir
    cfg.use_faster_whisper = not args.no_faster_whisper

    pipeline = TranscriptionPipeline(cfg)

    for path in args.files:
        path = Path(path)
        print(f"\n▶  Processing: {path}")

        def _progress(frac: float, msg: str) -> None:
            bar_len = 30
            filled = int(frac * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\r  [{bar}] {frac*100:5.1f}%  {msg:<50}", end="", flush=True)

        result = pipeline.process_file(
            path,
            fps=args.fps,
            audio_track=args.audio_track,
            progress=_progress,
        )
        print()  # newline after progress bar

        for fmt, out_path in result.output_files.items():
            print(f"  ✔  {fmt.upper():14s} → {out_path}")

        print(
            f"\n  Language: {result.transcription.language}"
            f"  |  Segments: {len(result.transcription.segments)}"
            f"  |  Duration: {result.transcription.duration:.1f}s"
            f"  |  Elapsed: {result.transcription.elapsed:.1f}s"
        )


def _run_gui() -> None:
    try:
        import tkinter as tk  # noqa: F401
    except ImportError:
        print(
            "Tkinter is not available. Run with --cli for headless operation.",
            file=sys.stderr,
        )
        sys.exit(1)

    from .gui import TranscriptionApp

    app = TranscriptionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
