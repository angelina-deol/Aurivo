"""
Tests for ml/preprocessing/audio.py's _prepared_for_decode.

Regression test for a real, confirmed bug: soundfile decodes MP3 via
native libmpg123 on some libsndfile builds, and a malformed ID3 comment
frame ("No comment text / valid description?") crashed that native
decoder outright — not a catchable Python exception, an actual process
crash that took down the whole Celery worker (which runs with
--pool=solo, so there's no parent process left to detect and report a
crashed child the way Celery's default prefork pool would).

Uses ffmpeg to generate a real MP3 with a real ID3 tag — skipped if
ffmpeg isn't available, to keep this portable, though it's present on
GitHub Actions' ubuntu-latest runners by default.
"""
import shutil
import subprocess

import pytest

from ml.preprocessing.audio import AASIST_NUM_SAMPLES, _prepared_for_decode, load_for_aasist

HAS_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.fixture
def mp3_with_id3_tag(tmp_path):
    path = tmp_path / "test.mp3"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-metadata", "comment=test comment",
            "-codec:a", "libmp3lame",
            str(path),
        ],
        check=True,
    )
    return str(path)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not available to generate a test MP3")
def test_prepared_for_decode_strips_id3_tags(mp3_with_id3_tag):
    from mutagen.mp3 import MP3

    before = MP3(mp3_with_id3_tag)
    assert before.tags  # sanity check the fixture actually has tags to strip

    with _prepared_for_decode(mp3_with_id3_tag) as safe_path:
        assert safe_path != mp3_with_id3_tag, "should be a sanitized copy, not the original"
        after = MP3(safe_path)
        assert not after.tags, "ID3 tags should be stripped"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not available to generate a test MP3")
def test_prepared_for_decode_does_not_mutate_original_file(mp3_with_id3_tag):
    from mutagen.mp3 import MP3

    with _prepared_for_decode(mp3_with_id3_tag):
        pass

    still_there = MP3(mp3_with_id3_tag)
    assert still_there.tags, "the original file's tags must not be touched"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not available to generate a test MP3")
def test_prepared_for_decode_cleans_up_temp_file(mp3_with_id3_tag):
    import os

    captured_path = None
    with _prepared_for_decode(mp3_with_id3_tag) as safe_path:
        captured_path = safe_path
        assert os.path.exists(captured_path)

    assert not os.path.exists(captured_path), "temp file should be cleaned up after the context exits"


def test_prepared_for_decode_passes_through_non_mp3_files(tmp_path):
    wav_path = tmp_path / "test.wav"
    wav_path.write_bytes(b"fake wav content")  # content doesn't matter — only the extension check does

    with _prepared_for_decode(str(wav_path)) as safe_path:
        assert safe_path == str(wav_path), "non-MP3 files should pass through unchanged"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not available to generate a test MP3")
def test_load_for_aasist_works_end_to_end_on_real_mp3_with_id3_tag(mp3_with_id3_tag):
    """The actual regression test: the full preprocessing pipeline must
    complete on a real MP3 with a real ID3 tag, not just the stripping
    step in isolation."""
    result = load_for_aasist(mp3_with_id3_tag)
    assert result.shape[0] == AASIST_NUM_SAMPLES
