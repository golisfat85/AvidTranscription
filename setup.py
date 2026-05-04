from setuptools import setup, find_packages

setup(
    name="avid-transcription",
    version="1.0.0",
    description="Avid Media Composer third-party transcription and subtitle plugin",
    author="AvidTranscription Contributors",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "openai-whisper>=20231117",
        "faster-whisper>=0.10.0",
        "ffmpeg-python>=0.2.0",
        "aaf2>=1.5.0",
        "pysrt>=1.1.2",
        "webvtt-py>=0.4.6",
        "torch>=2.0.0",
        "tqdm>=4.65.0",
        "numpy>=1.24.0",
        "Pillow>=10.0.0",
        "requests>=2.31.0",
    ],
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
