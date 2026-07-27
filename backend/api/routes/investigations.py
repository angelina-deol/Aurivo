"""
Investigation endpoints.

`/analyze` accepts an audio upload, validates it, extracts header-level
metadata, stores the file (local disk or S3-compatible, see
services/storage.py), creates an Investigation + AudioMetadata row, and
enqueues a Celery task (backend/workers/tasks.py) that runs AASIST inference
and fills in prediction/confidence/fraud_score once it completes.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.database.models.audio_metadata import AudioMetadata
from backend.database.models.investigation import (
    Investigation,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PROCESSING,
)
from backend.database.models.user import User
from backend.database.session import get_db
from backend.schemas.investigation import (
    DailyCountPoint,
    DailyRatePoint,
    HistogramBucket,
    InvestigationListResponse,
    InvestigationResponse,
    InvestigationStatsResponse,
)
from backend.services.audio_metadata import UnsupportedAudioError, extract_metadata
from backend.services.storage import build_storage_key, get_storage_backend
from backend.workers.tasks import analyze_investigation

router = APIRouter(prefix="/investigations", tags=["investigations"])
settings = get_settings()

# Comfortably above celery_app.py's task_time_limit (300s) — if an
# investigation is still "processing" after this long, the task didn't
# just run long, it's actually gone. The most likely real-world cause:
# the worker process got OOM-killed mid-task. A SIGKILL bypasses every
# try/except in backend/workers/tasks.py entirely — there's no Python
# exception to catch, the process just vanishes — so that task's own
# error handling (however careful) can never mark the investigation
# failed. This check lives here, in the read path, specifically because
# it runs in the backend/API process, not the worker process that might
# have crashed — it doesn't depend on the thing that failed still being
# alive to report its own failure.
STALE_PROCESSING_THRESHOLD_SECONDS = 360


def _reconcile_if_stale(investigation: Investigation, db: Session) -> None:
    if investigation.status not in (STATUS_PROCESSING, "awaiting_analysis"):
        return

    updated_at = investigation.updated_at
    if updated_at.tzinfo is None:
        # SQLite doesn't round-trip tzinfo; everything is written via
        # datetime.utcnow(), so naive timestamps are always UTC.
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
    if age_seconds > STALE_PROCESSING_THRESHOLD_SECONDS:
        investigation.status = STATUS_FAILED
        db.commit()
        db.refresh(investigation)


def _validate_upload(file: UploadFile) -> str:
    """Returns the lowercased extension, or raises a 4xx."""
    if not file.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing filename")

    ext = ("." + file.filename.rsplit(".", 1)[-1].lower()) if "." in file.filename else ""
    if ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported file type '{ext}'. Allowed: {', '.join(settings.ALLOWED_AUDIO_EXTENSIONS)}",
        )
    return ext


@router.post("/analyze", response_model=InvestigationResponse, status_code=status.HTTP_202_ACCEPTED)
def analyze(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_upload(file)

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file.file.seek(0, 2)
    size_bytes = file.file.tell()
    file.file.seek(0)
    if size_bytes > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB limit",
        )
    if size_bytes == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")

    try:
        meta = extract_metadata(file.file, file.filename)
    except UnsupportedAudioError as e:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(e))
    except Exception:
        # Header parsing failed — most likely a corrupt or mislabeled file.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Could not read audio metadata. Is the file a valid WAV, FLAC, or MP3?",
        )

    storage_key = build_storage_key(file.filename)
    storage = get_storage_backend()
    storage.save(file.file, storage_key)

    investigation = Investigation(
        user_id=current_user.id,
        filename=file.filename,
        status=STATUS_PROCESSING,
    )
    db.add(investigation)
    db.flush()  # assign investigation.id before creating the child row

    db.add(
        AudioMetadata(
            investigation_id=investigation.id,
            original_filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            storage_key=storage_key,
            duration_seconds=meta.duration_seconds,
            sample_rate=meta.sample_rate,
            channels=meta.channels,
            file_size_bytes=meta.file_size_bytes,
        )
    )
    db.commit()
    db.refresh(investigation)

    try:
        analyze_investigation.delay(str(investigation.id))
    except Exception:
        # The upload itself succeeded — the file is stored and the row is
        # committed. A broker connection failure here (e.g. Redis isn't
        # running) shouldn't turn that success into a 500 for the client;
        # mark the investigation failed instead so the UI shows the honest,
        # already-built "analysis failed" state rather than the browser
        # seeing an opaque server error on what was actually a successful
        # upload.
        investigation.status = STATUS_FAILED
        db.commit()
        db.refresh(investigation)

    return investigation


@router.get("", response_model=InvestigationListResponse)
def list_investigations(
    limit: int = 20,
    offset: int = 0,
    search: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    prediction: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    query = db.query(Investigation).filter(Investigation.user_id == current_user.id)

    if search:
        query = query.filter(Investigation.filename.ilike(f"%{search}%"))
    if status_filter:
        query = query.filter(Investigation.status == status_filter)
    if prediction:
        query = query.filter(Investigation.prediction == prediction)

    query = query.order_by(Investigation.created_at.desc())
    total = query.count()
    items = query.offset(offset).limit(limit).all()

    for inv in items:
        _reconcile_if_stale(inv, db)

    return InvestigationListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/stats", response_model=InvestigationStatsResponse)
def get_investigation_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate stats for the dashboard/analytics screens (Phase 5).

    Computed in Python over the user's investigations rather than with
    DB-specific date-truncation SQL (Postgres and SQLite disagree on how to
    do that), which keeps this correct across both — the dev/test SQLite
    path and the real Postgres deployment. Fine at the scale of one user's
    investigation history; would need to move to DB-side aggregation if
    this ever needs to scale to a very large history.
    """
    investigations = (
        db.query(Investigation).filter(Investigation.user_id == current_user.id).all()
    )

    now = datetime.now(timezone.utc)
    today = now.date()
    window_start = today - timedelta(days=13)  # last 14 days, inclusive of today

    completed = [i for i in investigations if i.status == STATUS_COMPLETE]
    confidences = [i.confidence for i in completed if i.confidence is not None]
    latencies = [i.processing_time_seconds for i in completed if i.processing_time_seconds is not None]

    fraud_count = sum(1 for i in completed if i.prediction == "ai_generated")
    real_count = sum(1 for i in completed if i.prediction == "real")

    def _as_date(dt: datetime):
        # SQLite doesn't preserve tzinfo on round-trip; treat naive
        # timestamps as UTC (everything is written via datetime.utcnow()).
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).date()

    today_count = sum(1 for i in investigations if _as_date(i.created_at) == today)

    uploads_by_day: dict = defaultdict(int)
    completed_by_day: dict = defaultdict(list)  # date -> list of Investigation
    latency_by_day: dict = defaultdict(list)  # date -> list of float

    for inv in investigations:
        d = _as_date(inv.created_at)
        if d < window_start:
            continue
        uploads_by_day[d] += 1
        if inv.status == STATUS_COMPLETE:
            completed_by_day[d].append(inv)
            if inv.processing_time_seconds is not None:
                latency_by_day[d].append(inv.processing_time_seconds)

    daily_uploads = []
    daily_fraud_rate = []
    daily_avg_latency = []
    for offset_days in range(14):
        d = window_start + timedelta(days=offset_days)
        date_str = d.isoformat()
        daily_uploads.append(DailyCountPoint(date=date_str, count=uploads_by_day.get(d, 0)))

        day_completed = completed_by_day.get(d, [])
        fraud_rate = (
            (sum(1 for i in day_completed if i.prediction == "ai_generated") / len(day_completed) * 100)
            if day_completed
            else 0.0
        )
        daily_fraud_rate.append(DailyRatePoint(date=date_str, value=round(fraud_rate, 1)))

        day_latencies = latency_by_day.get(d, [])
        avg_latency = sum(day_latencies) / len(day_latencies) if day_latencies else 0.0
        daily_avg_latency.append(DailyRatePoint(date=date_str, value=round(avg_latency, 2)))

    # Confidence histogram: 10 buckets from 0-100%.
    histogram_counts = [0] * 10
    for c in confidences:
        bucket_index = min(9, int(c * 10))
        histogram_counts[bucket_index] += 1
    confidence_histogram = [
        HistogramBucket(label=f"{i*10}-{i*10+10}%", count=histogram_counts[i]) for i in range(10)
    ]

    return InvestigationStatsResponse(
        total_analyses=len(investigations),
        today_analyses_count=today_count,
        fraud_detected_count=fraud_count,
        real_count=real_count,
        average_confidence=round(sum(confidences) / len(confidences), 4) if confidences else None,
        average_processing_time_seconds=(
            round(sum(latencies) / len(latencies), 3) if latencies else None
        ),
        daily_uploads=daily_uploads,
        daily_fraud_rate=daily_fraud_rate,
        daily_avg_latency=daily_avg_latency,
        confidence_histogram=confidence_histogram,
    )


@router.get("/{investigation_id}", response_model=InvestigationResponse)
def get_investigation(
    investigation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id, Investigation.user_id == current_user.id)
        .first()
    )
    if not investigation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found")
    _reconcile_if_stale(investigation, db)
    return investigation


@router.delete("/{investigation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_investigation(
    investigation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id, Investigation.user_id == current_user.id)
        .first()
    )
    if not investigation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found")

    if investigation.audio_metadata:
        storage = get_storage_backend()
        storage.delete(investigation.audio_metadata.storage_key)
        if investigation.audio_metadata.spectrogram_storage_key:
            storage.delete(investigation.audio_metadata.spectrogram_storage_key)

    db.delete(investigation)
    db.commit()
    return None


def _get_owned_investigation(
    investigation_id: uuid.UUID, current_user: User, db: Session
) -> Investigation:
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id, Investigation.user_id == current_user.id)
        .first()
    )
    if not investigation or not investigation.audio_metadata:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found")
    return investigation


@router.get("/{investigation_id}/audio")
def get_investigation_audio(
    investigation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Streams the original uploaded/recorded audio, for the waveform
    viewer's playback. Requires auth + ownership, same as everything else
    here — unlike a public S3 URL, this doesn't leak audio to anyone who
    guesses an investigation ID."""
    investigation = _get_owned_investigation(investigation_id, current_user, db)
    storage = get_storage_backend()
    with storage.local_path(investigation.audio_metadata.storage_key) as path:
        with open(path, "rb") as f:
            data = f.read()

    media_type = investigation.audio_metadata.content_type or "application/octet-stream"
    return Response(content=data, media_type=media_type)


@router.get("/{investigation_id}/spectrogram")
def get_investigation_spectrogram(
    investigation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    investigation = _get_owned_investigation(investigation_id, current_user, db)
    if not investigation.audio_metadata.spectrogram_storage_key:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No spectrogram available yet for this investigation.",
        )

    storage = get_storage_backend()
    with storage.local_path(investigation.audio_metadata.spectrogram_storage_key) as path:
        with open(path, "rb") as f:
            data = f.read()

    return Response(content=data, media_type="image/png")
