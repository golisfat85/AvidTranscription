from setuptools import setup, find_packages

setup(
    name="avid-transcription",
    version="1.0.0",
    description="Avid Media Composer third-party transcription and subtitle plugin",
    author="AvidTranscription Contributors",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        # Transcription engine (ctranslate2-based, no torch required)
        "faster-whisper>=0.10.0",
        # Audio / media helpers
        "ffmpeg-python>=0.2.0",
        # Subtitle format writers
        "pysrt>=1.1.2",
        "webvtt-py>=0.4.6",
        # Web server
        "fastapi>=0.110.0",
        "uvicorn>=0.29.0",
        "pydantic>=2.0.0",
        "httpx>=0.27.0",
        "aiofiles>=23.0.0",   # required by FastAPI StaticFiles
        # Utilities
        "requests>=2.31.0",
        "numpy>=1.24.0",
        "tqdm>=4.65.0",
    ],
    extras_require={
        # Fallback Whisper engine (pulls in ~2 GB of PyTorch)
        "whisper": ["openai-whisper>=20231117", "torch>=2.0.0"],
        # AAF round-trip (no arm64 wheel — install manually if needed)
        "aaf": ["aaf2>=1.5.0"],
        # Everything
        "all": [
            "openai-whisper>=20231117",
            "torch>=2.0.0",
            "aaf2>=1.5.0",
            "Pillow>=10.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "avid-transcription=avid_transcription.main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Topic :: Multimedia :: Video",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
