"""
Preprocessing for AASIST inference.

AASIST was trained on ASVspoof2019 LA, which is 16kHz mono FLAC, and its own
data loaders (ml/aasist/data_utils.py) read files with `soundfile` and pad/
truncate to a fixed 64600-sample window (~4.06s) with no resampling step,
because every training file was already 16kHz.

Real uploads won't all be 16kHz mono, so this module does what AASIST's
loaders implicitly assumed was already true: resample to 16kHz and downmix
to mono, before applying the same pad/truncate convention AASIST itself uses
(see `pad()` in ml/aasist/data_utils.py — tile-and-truncate, not zero-pad,
which is what the pretrained weights expect at inference time).
"""
import contextlib
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

AASIST_SAMPLE_RATE = 16000
AASIST_NUM_SAMPLES = 64600  # matches nb_samp in ml/aasist/config/AASIST.conf


@contextlib.contextmanager
def _prepared_for_decode(file_path: str):
    """For MP3 files, strips ID3 tags into a temp copy before handing the
    file to soundfile (which decodes MP3 via native libmpg123 on some
    libsndfile builds). Confirmed in practice: a malformed comment frame
    ("No comment text / valid description?") crashed the native decoder
    outright — not a catchable Python exception, a real process crash,
    which with a solo-pool Celery worker takes the whole worker down with
    it. Tags aren't needed to decode raw samples — only mutagen's separate
    metadata-only read (services/audio_metadata.py) needs them, and that
    already works fine on the same file. Stripping them removes the
    specific confirmed trigger before it reaches the native decoder at
    all. This is one half of the actual fix — the other half is running
    decode + inference in an isolated subprocess (backend/workers/
    subprocess_runner.py) so a crash from any cause, including ones not
    yet seen, can't take the worker down regardless.
    """
    if Path(file_path).suffix.lower() != ".mp3":
        yield file_path
        return

    tmp_path = None
    try:
        from mutagen.mp3 import MP3

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(tmp_fd)
        shutil.copyfile(file_path, tmp_path)

        audio = MP3(tmp_path)
        audio.delete()  # strips ID3 tags from the copy, in place

        yield tmp_path
    except Exception:
        # Best-effort sanitization — if stripping itself fails for any
        # reason, fall back to the original file rather than blocking the
        # whole pipeline on this step.
        yield file_path
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _resample(x: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return x
    # Lazy import: scipy is only needed for the (uncommon) case of a file
    # that isn't already 16kHz, so it doesn't need to be a hard dependency
    # of the metadata-only Phase 2 upload path.
    from scipy.signal import resample_poly

    gcd = np.gcd(orig_sr, target_sr)
    return resample_poly(x, target_sr // gcd, orig_sr // gcd).astype(np.float32)


def _pad_or_truncate(x: np.ndarray, max_len: int = AASIST_NUM_SAMPLES) -> np.ndarray:
    """Matches ml/aasist/data_utils.py's `pad()` exactly: truncate if long
    enough, otherwise tile the clip to fill the window. Zero-padding a short
    clip instead would shift the input distribution away from what the
    pretrained weights were trained on."""
    x_len = x.shape[0]
    if x_len >= max_len:
        return x[:max_len]
    num_repeats = int(max_len / x_len) + 1
    return np.tile(x, num_repeats)[:max_len]


def load_for_aasist(file_path: str) -> np.ndarray:
    """Loads an audio file and returns a float32 mono array of exactly
    AASIST_NUM_SAMPLES samples at AASIST_SAMPLE_RATE, ready to hand to the
    model wrapper."""
    with _prepared_for_decode(file_path) as safe_path:
        data, sr = sf.read(safe_path, always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)  # downmix to mono
    data = data.astype(np.float32)
    data = _resample(data, sr, AASIST_SAMPLE_RATE)
    return _pad_or_truncate(data, AASIST_NUM_SAMPLES)
