class IngestionError(Exception):
    """Base ingestion exception."""


class RecordRejectedError(IngestionError):
    """Raised when a parsed record cannot be normalized."""


class SourceNotFoundError(IngestionError):
    """Raised when the requested source does not exist."""


class PayloadValidationError(IngestionError):
    """Raised when the inbound ingestion payload is invalid or too large."""
