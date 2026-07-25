"""
Investigation endpoints — routes exist now so the frontend and API contract
are stable, but real handlers (upload -> queue -> AASIST inference -> report)
land in Phase 3 once ml/inference is wired up. For now they return
`501 Not Implemented` rather than fake data.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth.dependencies import get_current_user
from backend.database.models.user import User

router = APIRouter(prefix="/investigations", tags=["investigations"])

NOT_IMPLEMENTED = HTTPException(
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    detail="Wired up in Phase 3 once AASIST inference is integrated.",
)


@router.post("/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze(current_user: User = Depends(get_current_user)):
    raise NOT_IMPLEMENTED


@router.get("")
def list_investigations(current_user: User = Depends(get_current_user)):
    raise NOT_IMPLEMENTED


@router.get("/{investigation_id}")
def get_investigation(investigation_id: str, current_user: User = Depends(get_current_user)):
    raise NOT_IMPLEMENTED


@router.delete("/{investigation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_investigation(investigation_id: str, current_user: User = Depends(get_current_user)):
    raise NOT_IMPLEMENTED
