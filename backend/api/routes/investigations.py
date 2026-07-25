"""
Investigation endpoints.

Phase 2 makes `/analyze` real: it accepts an audio upload, validates it,
extracts header-level metadata, stores the file (local disk or S3-compatible,
see services/storage.py), and creates an Investigation + AudioMetadata row.

It does NOT run AASIST — there's no ML worker yet. The row is created with
status "awaiting_analysis" and prediction/confidence/fraud_score stay null
until Phase 3 wires up the Celery worker + AASIST wrapper.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.database.models.audio_metadata import AudioMetadata
from backend.database.models.investigation import Investigation, STATUS_AWAITING_ANALYSIS
from backend.database.models.user import User
from backend.database.session import get_db
from backend.schemas.investigation import InvestigationListResponse, InvestigationResponse
from backend.services.audio_metadata import UnsupportedAudioError, extract_metadata
from backend.services.storage import build_storage_key, get_storage_backend

router = APIRouter(prefix="/investigations", tags=["investigations"])
settings = get_settings()


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
        status=STATUS_AWAITING_ANALYSIS,
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
    return investigation


@router.get("", response_model=InvestigationListResponse)
def list_investigations(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 100))
    query = (
        db.query(Investigation)
        .filter(Investigation.user_id == current_user.id)
        .order_by(Investigation.created_at.desc())
    )
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return InvestigationListResponse(items=items, total=total, limit=limit, offset=offset)


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

    db.delete(investigation)
    db.commit()
    return None
