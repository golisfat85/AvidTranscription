@echo off
REM Start the Avid Transcription local server (Windows).
REM Keep this window open while using Avid.

SET PORT=8765
IF NOT "%AVID_TRANSCRIPTION_PORT%"=="" SET PORT=%AVID_TRANSCRIPTION_PORT%

echo Starting Avid Transcription server on http://localhost:%PORT%
echo Keep this window open while working in Avid.
echo Press Ctrl+C to stop.
echo.

avid-transcription --server --port %PORT%
