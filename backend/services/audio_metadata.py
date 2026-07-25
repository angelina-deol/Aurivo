"""
Lightweight audio metadata extraction for the upload pipeline.

This deliberately does NOT decode audio into a waveform array — that's
`ml/preprocessing`'s job in Phase 3, once AASIST inference needs actual
samples. Here we only need header-level facts (duration, sample rate,
channels) to show the user what they uploaded and to store on the
Investigation record.

- WAV/FLAC: read via `soundfile`, which parses just the header.
- MP3: no universal header for duration, so we use `mutagen`, which reads
  frame headers/VBR info without full decoding.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import soundfile as sf
from mutagen.mp3 import MP3


class UnsupportedAudioError(ValueError):
    pass


@dataclass
class AudioMetadata:
    duration_seconds: float
    sample_rate: int
    channels: int
    file_size_bytes: int


def extract_metadata(file_obj: BinaryIO, filename: str) -> AudioMetadata:
    ext = Path(filename).suffix.lower()
    file_obj.seek(0, 2)
    file_size_bytes = file_obj.tell()
    file_obj.seek(0)

    if ext in (".wav", ".flac"):
        info = sf.info(file_obj)
        return AudioMetadata(
            duration_seconds=round(info.duration, 3),
            sample_rate=info.samplerate,
            channels=info.channels,
            file_size_bytes=file_size_bytes,
        )

    if ext == ".mp3":
        audio = MP3(file_obj)
        return AudioMetadata(
            duration_seconds=round(audio.info.length, 3),
            sample_rate=audio.info.sample_rate,
            channels=audio.info.channels,
            file_size_bytes=file_size_bytes,
        )

    raise UnsupportedAudioError(f"Unsupported audio extension: {ext}")
