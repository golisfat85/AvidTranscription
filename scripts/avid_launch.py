"""
Avid Script – Launch AvidTranscription plugin from Media Composer.

Usage
-----
Place this script in your Avid Script directory and assign it to a
keyboard shortcut or toolbar button in Media Composer.

When activated, it launches the AvidTranscription GUI and (optionally)
passes the currently selected bin clip to the tool.

Requirements: the `avid-transcription` package must be installed in the
same Python environment used to run this script.
"""

import subprocess
import sys


def main():
    cmd = [sys.executable, "-m", "avid_transcription.main"]
    subprocess.Popen(cmd)


if __name__ == "__main__":
    main()
