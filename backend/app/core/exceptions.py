"""
Custom exceptions for NYC Subway Monitor.
"""

from typing import Optional


class SubwayMonitorException(Exception):
    """Base exception for application."""
    
    def __init__(
        self,
        detail: str,
        status_code: int = 500,
        error_code: Optional[str] = None,
    ):
        self.detail = detail
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        super().__init__(detail)


class FeedFetchError(SubwayMonitorException):
    """Error fetching GTFS-RT feed."""
    
    def __init__(self, feed_id: str, detail: str):
        super().__init__(
            detail=f"Failed to fetch feed {feed_id}: {detail}",
            status_code=503,
            error_code="FEED_FETCH_ERROR",
        )


class ModelNotFoundError(SubwayMonitorException):
    """ML model not found or not loaded."""
    
    def __init__(self, model_type: str):
        super().__init__(
            detail=f"Model {model_type} not found or not loaded",
            status_code=404,
            error_code="MODEL_NOT_FOUND",
        )


class InvalidConfigError(SubwayMonitorException):
    """Invalid configuration."""
    
    def __init__(self, detail: str):
        super().__init__(
            detail=f"Invalid configuration: {detail}",
            status_code=500,
            error_code="INVALID_CONFIG",
        )