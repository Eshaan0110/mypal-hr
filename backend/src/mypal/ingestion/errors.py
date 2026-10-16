from mypal.errors import AppError


class DocumentRejected(AppError):
    """The file cannot be ingested (wrong type, too large, encrypted, no readable text...)."""

    status_code = 422
    code = "document_rejected"


class IngestionConflict(AppError):
    """The upload clashes with what is already stored (duplicate file or version label)."""

    status_code = 409
    code = "ingestion_conflict"
