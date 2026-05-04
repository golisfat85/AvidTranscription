# Avid Transcription Plugin

A third-party plugin for **Avid Media Composer** that automatically transcribes audio from video clips and generates subtitle/caption files using OpenAI Whisper.

---

## Features

| Feature | Details |
|---|---|
| **AI Transcription** | Powered by [OpenAI Whisper](https://github.com/openai/whisper) via the faster [faster-whisper](https://github.com/SYSTRAN/faster-whisper) backend |
| **Multi-language** | Auto-detect or force any of 99 supported languages |
| **Translation** | Optionally translate non-English audio to English in one pass |
| **Output formats** | SRT, WebVTT, CSV, Avid Marker import (tab-delimited) |
| **AAF integration** | Read Avid AAF files; write subtitle text back as comment markers |
| **Multi-track** | Choose which audio track to transcribe (multi-track MXF support) |
| **Clip subsets** | Transcribe a specific in/out range of a longer file |
| **GUI + CLI** | Graphical interface and headless command-line mode |
| **Batch mode** | Process multiple clips in one run |

---

## Requirements

- Python 3.9 or later
- [FFmpeg](https://ffmpeg.org/download.html) on your `PATH`
- (Optional) An NVIDIA GPU for faster transcription

---

## Installation

```bash
# Clone
git clone https://github.com/golisfat85/avidtranscription.git
cd avidtranscription

# Install (creates avid-transcription command)
pip install -e .
```

FFmpeg must be installed separately:

| OS | Command |
|---|---|
| macOS | `brew install ffmpeg` |
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Windows | Download from https://ffmpeg.org/download.html and add to PATH |

---

## Quick Start

### GUI mode

```bash
avid-transcription
```

1. Click **Browse…** to select one or more MXF/MOV/MP4 clips.
2. Choose your Whisper model (`base` is a good starting point).
3. Select output formats (SRT + VTT recommended).
4. Click **Transcribe**.

### CLI mode

```bash
# Transcribe a single file to SRT + VTT
avid-transcription --cli interview.mxf

# Translate French to English, use the large model
avid-transcription --cli --model large-v3 --task translate --language fr talk.mxf

# Batch + custom output directory
avid-transcription --cli --output-dir /exports clip1.mxf clip2.mxf clip3.mxf

# Force second audio track, 29.97 fps, Avid markers only
avid-transcription --cli --audio-track 1 --fps 29.97 --formats avid_markers scene.mxf
```

---

## Whisper Models

| Model | VRAM | Speed | Accuracy |
|---|---|---|---|
| `tiny` | ~1 GB | fastest | lowest |
| `base` | ~1 GB | very fast | good |
| `small` | ~2 GB | fast | better |
| `medium` | ~5 GB | moderate | great |
| `large-v3` | ~10 GB | slow | best |

On CPU the `base` or `small` model is recommended. With an NVIDIA GPU use `large-v3` for best accuracy.

---

## Output Formats

### SRT (SubRip)
Standard subtitle format, importable into most NLEs and players.

```
1
00:00:03,200 --> 00:00:06,800
Hello and welcome to the show.

2
00:00:07,100 --> 00:00:10,400
Today we are discussing AI transcription.
```

### WebVTT
Web standard format, compatible with HTML5 `<video>` and many NLEs.

### CSV
Spreadsheet-friendly format with columns: `#, Start (s), End (s), Duration (s), Text`.

### Avid Markers
Tab-delimited marker file importable directly into Avid Media Composer via **Clip ▶ Markers ▶ Import Markers…**

```
Marker Name	IN	OUT	Track	Color	Comment
Sub 0001	00:00:03:05	00:00:06:20	V1	Red	Hello and welcome to the show.
```

---

## AAF Integration

The plugin can read clip metadata from an Avid AAF export and write subtitle text back as **comment markers** directly into the AAF file.

1. From Media Composer, export your sequence or clip as an AAF (**File ▶ Export ▶ AAF…**).
2. In the plugin GUI, check **Export markers into AAF file** and select your `.aaf` file.
3. After transcription, a new `*_marked.aaf` file is created with subtitle markers embedded.
4. Re-import the marked AAF into Media Composer.

---

## Avid Script Integration

You can launch the plugin directly from within Media Composer using the included script:

1. Copy `scripts/avid_launch.py` to your Avid Script directory.
2. In Media Composer go to **Tools ▶ Script Editor**, open the script and assign it to a keyboard shortcut or toolbar button.

---

## Project Structure

```
avid_transcription/
├── main.py              # CLI + GUI entry point
├── config.py            # TranscriptionConfig dataclass
├── audio_extractor.py   # FFmpeg wrapper (extract 16 kHz WAV)
├── transcriber.py       # Whisper transcription engine
├── subtitle_generator.py # SRT / VTT / CSV / Avid marker export
├── aaf_handler.py       # Read/write Avid AAF files
├── pipeline.py          # Orchestrates the full workflow
└── gui.py               # Tkinter GUI

tests/
├── test_audio_extractor.py
├── test_config.py
├── test_pipeline.py
└── test_subtitle_generator.py

scripts/
└── avid_launch.py       # Avid script launcher
```

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## License

MIT
