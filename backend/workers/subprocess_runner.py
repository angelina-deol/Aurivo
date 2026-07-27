"""
Subprocess isolation for decode+inference work (used by backend/workers/tasks.py).

Confirmed real bug this protects against: soundfile decodes some audio via
native libraries (libmpg123, for MP3, on some libsndfile builds), and a
malformed file was confirmed to crash that native decoder outright — a real
process crash, not a catchable Python exception. With the Celery worker
running --pool=solo (chosen to dodge a PyTorch+fork deadlock — see
celery_app.py), there's no parent process supervising a child the way
Celery's default prefork pool provides, so a native crash takes the entire
worker down with it, with no Python traceback at all.

The ID3-stripping fix in ml/preprocessing/audio.py patches the specific
confirmed trigger. This module is the general fix: run the risky work in an
isolated child process, so a crash from ANY cause — that trigger, a
different malformed file hitting some other native bug, anything not yet
seen — can only kill the child, never the worker itself.

Uses the 'spawn' start method, not fork, for the same reason Celery's
prefork pool is avoided elsewhere in this project: forking a process that
already has PyTorch's native thread pool initialized is a known source of
deadlocks. spawn starts each child completely fresh.

Real, honest tradeoff: because spawn starts fresh, ml/inference/
aasist_wrapper.py's "load the model once per worker process" optimization
no longer applies across isolated calls — each call to predict() through
run_isolated() reloads the AASIST checkpoint from scratch in the fresh
child process. That's real added latency (checkpoint load + model
construction) on every single analysis, traded deliberately for the
guarantee that no analysis can take the whole worker down with it.

A second real bug, found by testing this against a realistic return value
(not just the small ones in the original test suite): naively calling
process.join() before draining the result queue deadlocks the moment the
child's result is bigger than the OS pipe buffer (~64KB on Linux) — the
child blocks writing to a full pipe while the parent blocks waiting for
the child to exit, and neither side can proceed. A 64,600-element float32
array (~258KB, exactly what ml.preprocessing.audio.load_for_aasist
returns) hits this reliably. Fixed by using
multiprocessing.connection.wait() to wait for either the queue having data
or the process's sentinel becoming readable (i.e. it exited), whichever
comes first, and always draining the queue before joining.
"""
import multiprocessing as mp
import multiprocessing.connection
import time
import traceback


class SubprocessCrashError(RuntimeError):
    """Raised when the isolated subprocess died without producing a
    result — a crash, a timeout, or anything else that means there's no
    normal return value or re-raisable exception to work with."""


def _subprocess_entrypoint(fn, args, kwargs, result_queue):
    try:
        result = fn(*args, **kwargs)
        result_queue.put(("ok", result))
    except Exception as exc:
        # The exception object (and especially its traceback) often isn't
        # picklable across the process boundary — send the formatted
        # string instead, which always is.
        result_queue.put(("error", f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))


def run_isolated(fn, *args, timeout: float = 280, **kwargs):
    """Runs fn(*args, **kwargs) in an isolated child process.

    Returns fn's return value on normal success.
    Raises RuntimeError, with the child's original traceback in the
    message, if fn itself raised a normal Python exception.
    Raises SubprocessCrashError if the child crashed, timed out, or
    otherwise died without producing a result at all — this is the case
    that used to take the entire worker down with it.
    """
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()
    process = ctx.Process(target=_subprocess_entrypoint, args=(fn, args, kwargs, result_queue))
    process.start()

    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SubprocessCrashError(f"Timed out after {timeout}s and had to be killed")

            # Waits for EITHER the queue to have data ready, OR the process
            # to exit (its sentinel fd becomes readable) — whichever
            # happens first. This is the actual fix for the deadlock:
            # never block exclusively on process.join() without also
            # watching the queue, and never assume the queue has data just
            # because the process exited (drain it explicitly either way).
            ready = multiprocessing.connection.wait(
                [result_queue._reader, process.sentinel], timeout=remaining
            )

            if result_queue._reader in ready:
                status, payload = result_queue.get()
                if status == "error":
                    raise RuntimeError(f"Isolated subprocess raised an exception:\n{payload}")
                return payload

            if process.sentinel in ready:
                # Process exited. It may have still gotten a result onto
                # the queue right before exiting — check before concluding
                # it crashed with nothing to show for it.
                if not result_queue.empty():
                    status, payload = result_queue.get()
                    if status == "error":
                        raise RuntimeError(f"Isolated subprocess raised an exception:\n{payload}")
                    return payload
                raise SubprocessCrashError(
                    f"Subprocess exited (code {process.exitcode}) without producing a "
                    "result — likely a native crash (segfault, an OOM kill of just the "
                    "child, etc.)"
                )
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join(5)
        else:
            process.join(5)
        result_queue.close()
