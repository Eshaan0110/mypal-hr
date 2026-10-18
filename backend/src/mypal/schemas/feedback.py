import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mypal.db.models import FeedbackRating

# Fixed choices only: free text could contain personal details.
ReasonCode = Literal["incorrect", "outdated", "unclear", "not_my_situation", "other"]


class FeedbackRequest(BaseModel):
    # Extra fields (e.g. a smuggled "question" or "comment") are rejected, not silently ignored.
    model_config = ConfigDict(extra="forbid")

    answer_id: uuid.UUID
    rating: FeedbackRating
    reason_code: ReasonCode | None = None


class FeedbackResponse(BaseModel):
    status: Literal["recorded"]
