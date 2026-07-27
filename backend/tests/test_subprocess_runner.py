"""
Tests for backend/workers/subprocess_runner.py.

These specifically test crash scenarios — a hard process crash (os._exit,
simulating a native library crash/segfault), a timeout, and a normal
Python exception — since that's the entire point of this module. The
target functions must be module-level (not closures/lambdas) because the
'spawn' start method pickles them by reference, not by value.
"""
import time

import pytest

from backend.workers.subprocess_runner import SubprocessCrashError, run_isolated


def _returns_normally(a, b):
    return a + b


def _raises_a_normal_exception():
    raise ValueError("something went wrong, but normally")


def _crashes_hard():
    """Simulates a native library crash/segfault — os._exit skips all
    Python-level cleanup and exception handling entirely, the same way a
    real segfault would, unlike sys.exit() which raises a catchable
    SystemExit."""
    import os

    os._exit(1)


def _hangs_forever():
    time.sleep(999)


def test_normal_return_value_comes_back():
    result = run_isolated(_returns_normally, 2, 3)
    assert result == 5


def test_normal_exception_is_reraised_as_runtime_error():
    with pytest.raises(RuntimeError) as exc_info:
        run_isolated(_raises_a_normal_exception)
    assert "ValueError" in str(exc_info.value)
    assert "something went wrong" in str(exc_info.value)


def test_hard_crash_is_caught_as_subprocess_crash_error():
    """The actual point of this whole module: a hard crash (os._exit,
    standing in for a real native library crash) must be caught as a
    normal, catchable Python exception in the PARENT process — not take
    the parent down with it."""
    with pytest.raises(SubprocessCrashError):
        run_isolated(_crashes_hard)


def test_timeout_is_caught_as_subprocess_crash_error():
    with pytest.raises(SubprocessCrashError, match="Timed out"):
        run_isolated(_hangs_forever, timeout=2)


def test_parent_process_survives_a_child_crash():
    """Directly verifies the parent process itself is unaffected by a
    child crash — not just that an exception was raised, but that we're
    still here, in the same process, able to keep working afterward."""
    import os

    pid_before = os.getpid()

    with pytest.raises(SubprocessCrashError):
        run_isolated(_crashes_hard)

    assert os.getpid() == pid_before  # still the same process, unharmed
    # and the parent can keep doing normal work right after
    assert run_isolated(_returns_normally, 10, 5) == 15


def _returns_a_large_payload(size_bytes: int):
    return bytes(size_bytes)


def test_large_return_value_does_not_deadlock():
    """Regression test for a real bug found while wiring this into actual
    use: naively calling process.join() before draining the result queue
    deadlocks the moment the child's result is bigger than the OS pipe
    buffer (~64KB on Linux) — the child blocks writing to a full pipe
    while the parent blocks waiting for the child to exit, and neither
    side can proceed. All the tests above only ever returned small values
    (ints, short strings) and would never have caught this — a 64,600-
    element float32 array (~258KB) from the real
    ml.preprocessing.audio.load_for_aasist is what actually exposed it.
    This uses an even larger payload (1MB) to stay well clear of the pipe
    buffer size with margin."""
    result = run_isolated(_returns_a_large_payload, 1_000_000, timeout=30)
    assert len(result) == 1_000_000
