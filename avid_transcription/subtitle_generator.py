"""
Convert TranscriptionResult into subtitle/caption files.

Supported output formats:
  * SRT  – SubRip (universal, importable into Avid via Boris Continuum / Nexis)
  * VTT  – WebVTT (web players, some NLEs)
  * CSV  – spreadsheet-friendly transcript with timecodes
  * avid_markers – Avid tab-delimited marker import format
"""

from __future__ import annotations

import csv
import io
import textwrap
from pathlib import Path
from typing import List, Optional

from .config import TranscriptionConfig
from .transcriber import TranscriptSegment, TranscriptionResult


class SubtitleGeneratorError(Exception):
    pass


def _seconds_to_srt_timecode(seconds: float) -> str:
    """Convert float seconds → HH:MM:SS,mmm"""
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _seconds_to_vtt_timecode(seconds: float) -> str:
    """Convert float seconds → HH:MM:SS.mmm"""
    return _seconds_to_srt_timecode(seconds).replace(",", ".")


def _seconds_to_avid_timecode(seconds: float, fps: float = 25.0) -> str:
    """Convert float seconds → HH:MM:SS:FF  (Avid drop-frame notation optional)."""
    total_frames = int(round(seconds * fps))
    ff = total_frames % int(fps)
    total_seconds = total_frames // int(fps)
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}:{ff:02d}"


def _wrap_text(text: str, max_chars: int, max_lines: int) -> str:
    """Wrap *text* to *max_chars* columns with at most *max_lines* lines."""
    lines = textwrap.wrap(text, width=max_chars)
    return "\n".join(lines[:max_lines])


def _merge_short_segments(
    segments: List[TranscriptSegment],
    min_duration_ms: int,
    max_gap_ms: int,
) -> List[TranscriptSegment]:
    """
    Merge consecutive segments that are too short or separated by a tiny gap.
    Returns a new list; original objects are not mutated.
    """
    if not segments:
        return []

    merged: List[TranscriptSegment] = []
    current = TranscriptSegment(
        id=segments[0].id,
        start=segments[0].start,
        end=segments[0].end,
        text=segments[0].text,
        words=list(segments[0].words),
        language=segments[0].language,
        avg_logprob=segments[0].avg_logprob,
        no_speech_prob=segments[0].no_speech_prob,
    )

    for seg in segments[1:]:
        gap_ms = (seg.start - current.end) * 1000
        curr_dur_ms = (current.end - current.start) * 1000

        if gap_ms <= max_gap_ms and curr_dur_ms < min_duration_ms:
            current.end = seg.end
            current.text = (current.text + " " + seg.text).strip()
            current.words.extend(seg.words)
        else:
            merged.append(current)
            current = TranscriptSegment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                text=seg.text,
                words=list(seg.words),
                language=seg.language,
                avg_logprob=seg.avg_logprob,
                no_speech_prob=seg.no_speech_prob,
            )

    merged.append(current)
    return merged


class SubtitleGenerator:
    """Generate subtitle files from a TranscriptionResult."""

    def __init__(self, config: Optional[TranscriptionConfig] = None):
        self.config = config or TranscriptionConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        result: TranscriptionResult,
        output_dir: Optional[str | Path] = None,
        stem: str = "transcript",
        fps: float = 25.0,
    ) -> dict[str, Path]:
        """
        Generate all configured output formats.

        Returns:
            Dict mapping format name → output file path.
        """
        output_dir = Path(output_dir) if output_dir else Path.cwd()
        output_dir.mkdir(parents=True, exist_ok=True)

        segments = _merge_short_segments(
            result.segments,
            min_duration_ms=self.config.min_duration_ms,
            max_gap_ms=self.config.max_gap_ms,
        )

        outputs: dict[str, Path] = {}

        for fmt in self.config.output_formats:
            fmt = fmt.lower()
            if fmt == "srt":
                path = output_dir / f"{stem}.srt"
                path.write_text(self.to_srt(segments), encoding="utf-8")
                outputs["srt"] = path
            elif fmt == "vtt":
                path = output_dir / f"{stem}.vtt"
                path.write_text(self.to_vtt(segments), encoding="utf-8")
                outputs["vtt"] = path
            elif fmt == "csv":
                path = output_dir / f"{stem}.csv"
                path.write_text(self.to_csv(segments), encoding="utf-8")
                outputs["csv"] = path
            elif fmt == "avid_markers":
                path = output_dir / f"{stem}_avid_markers.txt"
                path.write_text(self.to_avid_markers(segments, fps=fps), encoding="utf-8")
                outputs["avid_markers"] = path

        return outputs

    # ------------------------------------------------------------------
    # Format renderers
    # ------------------------------------------------------------------

    def to_srt(self, segments: List[TranscriptSegment]) -> str:
        """Render segments as SRT."""
        blocks = []
        for i, seg in enumerate(segments, start=1):
            text = _wrap_text(
                seg.text,
                self.config.max_chars_per_line,
                self.config.max_lines,
            )
            blocks.append(
                f"{i}\n"
                f"{_seconds_to_srt_timecode(seg.start)} --> "
                f"{_seconds_to_srt_timecode(seg.end)}\n"
                f"{text}\n"
            )
        return "\n".join(blocks)

    def to_vtt(self, segments: List[TranscriptSegment]) -> str:
        """Render segments as WebVTT."""
        lines = ["WEBVTT\n"]
        for i, seg in enumerate(segments, start=1):
            text = _wrap_text(
                seg.text,
                self.config.max_chars_per_line,
                self.config.max_lines,
            )
            lines.append(
                f"{i}\n"
                f"{_seconds_to_vtt_timecode(seg.start)} --> "
                f"{_seconds_to_vtt_timecode(seg.end)}\n"
                f"{text}\n"
            )
        return "\n".join(lines)

    def to_csv(self, segments: List[TranscriptSegment]) -> str:
        """Render segments as CSV (id, start_tc, end_tc, duration, text)."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["#", "Start (s)", "End (s)", "Duration (s)", "Text"])
        for seg in segments:
            writer.writerow([
                seg.id,
                f"{seg.start:.3f}",
                f"{seg.end:.3f}",
                f"{seg.end - seg.start:.3f}",
                seg.text,
            ])
        return buf.getvalue()

    def to_avid_markers(
        self,
        segments: List[TranscriptSegment],
        fps: float = 25.0,
        color: str = "Red",
    ) -> str:
        """
        Render as Avid marker import format (tab-delimited).

        The file can be imported via  Clip ▶ Markers ▶ Import Markers…  in
        Avid Media Composer.  Columns: Marker Name, Start TC, Track, Color, Comment.
        """
        lines = ["Marker Name\tIN\tOUT\tTrack\tColor\tComment"]
        for i, seg in enumerate(segments, start=1):
            in_tc = _seconds_to_avid_timecode(seg.start, fps)
            out_tc = _seconds_to_avid_timecode(seg.end, fps)
            safe_text = seg.text.replace("\t", " ").replace("\n", " ")
            lines.append(
                f"Sub {i:04d}\t{in_tc}\t{out_tc}\tV1\t{color}\t{safe_text}"
            )
        return "\n".join(lines)

    def to_plain_text(self, segments: List[TranscriptSegment]) -> str:
        """Plain paragraph transcript without timecodes."""
        return " ".join(seg.text for seg in segments)
