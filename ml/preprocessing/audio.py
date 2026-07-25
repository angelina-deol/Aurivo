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
import numpy as np
import soundfile as sf

AASIST_SAMPLE_RATE = 16000
AASIST_NUM_SAMPLES = 64600  # matches nb_samp in ml/aasist/config/AASIST.conf


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
    data, sr = sf.read(file_path, always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)  # downmix to mono
    data = data.astype(np.float32)
    data = _resample(data, sr, AASIST_SAMPLE_RATE)
    return _pad_or_truncate(data, AASIST_NUM_SAMPLES)
