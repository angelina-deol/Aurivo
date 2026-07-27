"""
Spectrogram generation for the investigation report (Phase 4).

Computed on the ORIGINAL uploaded audio (full duration, native sample
rate) — not the resampled/tiled 4-second window AASIST itself sees, since
this is meant to show what's actually in the recording, not the model's
input. Uses scipy for the actual STFT and matplotlib's non-interactive Agg
backend purely as a renderer (no display, no GUI dependency).
"""
import io

import matplotlib

matplotlib.use("Agg")  # headless — no display server exists in a worker container
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy.signal import spectrogram as scipy_spectrogram

from ml.preprocessing.audio import _prepared_for_decode


def generate_spectrogram_png(audio_path: str) -> bytes:
    with _prepared_for_decode(audio_path) as safe_path:
        data, sr = sf.read(safe_path, always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)  # downmix to mono for a single spectrogram

    # nperseg/noverlap chosen for a reasonable time/frequency tradeoff on
    # typical speech clips (a few seconds to a few minutes) — finer than
    # this mostly adds render time and image size without adding much
    # visible detail at report-viewing scale.
    frequencies, times, Sxx = scipy_spectrogram(data, fs=sr, nperseg=1024, noverlap=768)

    # Log-magnitude, floor to avoid log(0) on silence.
    Sxx_db = 10 * np.log10(np.maximum(Sxx, 1e-10))

    fig, ax = plt.subplots(figsize=(10, 4), dpi=120)
    ax.pcolormesh(times, frequencies, Sxx_db, shading="gouraud", cmap="magma")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_xlabel("Time (s)")
    fig.tight_layout(pad=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
