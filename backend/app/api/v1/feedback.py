from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse
from app.services.feedback import create_or_update_feedback

router = APIRouter(tags=["Feedback"])


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse, status_code=201)
def create_message_feedback_endpoint(
    message_id: UUID,
    payload: FeedbackCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeedbackResponse:
    return create_or_update_feedback(
        db,
        message_id=message_id,
        payload=payload,
        current_user=current_user,
    )
