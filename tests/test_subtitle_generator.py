"""Tests for SubtitleGenerator – no ML models or FFmpeg required."""

import pytest

from avid_transcription.config import TranscriptionConfig
from avid_transcription.subtitle_generator import (
    SubtitleGenerator,
    _merge_short_segments,
    _seconds_to_avid_timecode,
    _seconds_to_srt_timecode,
    _seconds_to_vtt_timecode,
)
from avid_transcription.transcriber import TranscriptSegment, TranscriptionResult


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_segment(id, start, end, text):
    return TranscriptSegment(id=id, start=start, end=end, text=text, language="en")


def _make_result(segments):
    return TranscriptionResult(
        segments=segments,
        language="en",
        duration=segments[-1].end if segments else 0.0,
        elapsed=1.0,
    )


SEGS = [
    _make_segment(0, 0.0, 3.5, "Hello and welcome to the show."),
    _make_segment(1, 4.0, 7.2, "Today we are talking about AI."),
    _make_segment(2, 7.5, 10.0, "It is a fascinating topic."),
]


# ---------------------------------------------------------------------------
# Timecode helpers
# ---------------------------------------------------------------------------

class TestTimecodes:
    def test_srt_basic(self):
        assert _seconds_to_srt_timecode(0) == "00:00:00,000"
        assert _seconds_to_srt_timecode(3661.5) == "01:01:01,500"

    def test_srt_sub_second(self):
        assert _seconds_to_srt_timecode(0.123) == "00:00:00,123"

    def test_vtt_uses_period(self):
        tc = _seconds_to_vtt_timecode(1.5)
        assert "." in tc
        assert "," not in tc

    def test_avid_timecode_25fps(self):
        # 1 second at 25 fps → frame 00
        assert _seconds_to_avid_timecode(1.0, fps=25) == "00:00:01:00"
        # 1 frame at 25 fps = 0.04 s
        assert _seconds_to_avid_timecode(0.04, fps=25) == "00:00:00:01"

    def test_avid_timecode_24fps(self):
        assert _seconds_to_avid_timecode(2.0, fps=24) == "00:00:02:00"


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

class TestMerge:
    def test_no_merge_when_long_enough(self):
        segs = [
            _make_segment(0, 0.0, 1.5, "A"),   # 1500 ms – long enough
            _make_segment(1, 2.0, 3.5, "B"),
        ]
        merged = _merge_short_segments(segs, min_duration_ms=1000, max_gap_ms=100)
        assert len(merged) == 2

    def test_merges_short_segment(self):
        segs = [
            _make_segment(0, 0.0, 0.3, "A"),   # only 300 ms – too short
            _make_segment(1, 0.35, 1.5, "B"),  # gap = 50 ms ≤ 200
        ]
        merged = _merge_short_segments(segs, min_duration_ms=500, max_gap_ms=200)
        assert len(merged) == 1
        assert merged[0].text == "A B"

    def test_does_not_merge_across_large_gap(self):
        segs = [
            _make_segment(0, 0.0, 0.3, "A"),
            _make_segment(1, 5.0, 6.0, "B"),   # gap = 4700 ms
        ]
        merged = _merge_short_segments(segs, min_duration_ms=500, max_gap_ms=200)
        assert len(merged) == 2

    def test_empty_input(self):
        assert _merge_short_segments([], 500, 200) == []


# ---------------------------------------------------------------------------
# SRT output
# ---------------------------------------------------------------------------

class TestSRT:
    def setup_method(self):
        cfg = TranscriptionConfig()
        cfg.output_formats = ["srt"]
        self.gen = SubtitleGenerator(cfg)

    def test_srt_block_count(self):
        srt = self.gen.to_srt(SEGS)
        blocks = [b for b in srt.strip().split("\n\n") if b.strip()]
        assert len(blocks) == 3

    def test_srt_index_starts_at_one(self):
        srt = self.gen.to_srt(SEGS)
        assert srt.lstrip().startswith("1\n")

    def test_srt_contains_timecode_arrow(self):
        srt = self.gen.to_srt(SEGS)
        assert " --> " in srt

    def test_srt_contains_text(self):
        srt = self.gen.to_srt(SEGS)
        assert "Hello and welcome" in srt


# ---------------------------------------------------------------------------
# VTT output
# ---------------------------------------------------------------------------

class TestVTT:
    def setup_method(self):
        cfg = TranscriptionConfig()
        cfg.output_formats = ["vtt"]
        self.gen = SubtitleGenerator(cfg)

    def test_vtt_header(self):
        vtt = self.gen.to_vtt(SEGS)
        assert vtt.startswith("WEBVTT")

    def test_vtt_no_comma_in_timecode(self):
        vtt = self.gen.to_vtt(SEGS)
        lines = vtt.splitlines()
        tc_lines = [l for l in lines if "-->" in l]
        for l in tc_lines:
            assert "," not in l


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

class TestCSV:
    def setup_method(self):
        cfg = TranscriptionConfig()
        cfg.output_formats = ["csv"]
        self.gen = SubtitleGenerator(cfg)

    def test_csv_header(self):
        csv = self.gen.to_csv(SEGS)
        assert csv.splitlines()[0].startswith("#")

    def test_csv_row_count(self):
        csv = self.gen.to_csv(SEGS)
        rows = csv.strip().splitlines()
        assert len(rows) == len(SEGS) + 1   # header + data rows


# ---------------------------------------------------------------------------
# Avid markers output
# ---------------------------------------------------------------------------

class TestAvidMarkers:
    def setup_method(self):
        cfg = TranscriptionConfig()
        self.gen = SubtitleGenerator(cfg)

    def test_avid_markers_header(self):
        text = self.gen.to_avid_markers(SEGS, fps=25)
        assert text.startswith("Marker Name\t")

    def test_avid_markers_row_count(self):
        text = self.gen.to_avid_markers(SEGS, fps=25)
        rows = text.strip().splitlines()
        assert len(rows) == len(SEGS) + 1   # header + rows

    def test_avid_markers_tab_separated(self):
        text = self.gen.to_avid_markers(SEGS, fps=25)
        rows = text.strip().splitlines()
        # Each data row should have 6 tab-separated fields
        for row in rows[1:]:
            fields = row.split("\t")
            assert len(fields) == 6, f"Expected 6 fields, got: {fields}"

    def test_avid_markers_color_present(self):
        text = self.gen.to_avid_markers(SEGS, fps=25, color="Green")
        assert "Green" in text


# ---------------------------------------------------------------------------
# generate() integration
# ---------------------------------------------------------------------------

class TestGenerate:
    def test_generate_produces_files(self, tmp_path):
        cfg = TranscriptionConfig()
        cfg.output_formats = ["srt", "vtt", "csv", "avid_markers"]
        cfg.min_duration_ms = 0   # don't merge anything in tests
        gen = SubtitleGenerator(cfg)
        result = _make_result(SEGS)

        outputs = gen.generate(result, output_dir=tmp_path, stem="test_clip", fps=25)

        assert "srt" in outputs
        assert "vtt" in outputs
        assert "csv" in outputs
        assert "avid_markers" in outputs

        for path in outputs.values():
            assert path.exists()
            assert path.stat().st_size > 0
