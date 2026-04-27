"""URL-specific exceptions."""
from fastapi import HTTPException


class URLNotFoundError(HTTPException):
    def __init__(self, detail: str = "URL not found"):
        super().__init__(status_code=404, detail=detail)


class URLExpiredError(HTTPException):
    def __init__(self, detail: str = "URL has expired"):
        super().__init__(status_code=410, detail=detail)


class CustomCodeExistsError(HTTPException):
    def __init__(self, detail: str = "Custom code already exists"):
        super().__init__(status_code=400, detail=detail)


class URLNotOwnedError(HTTPException):
    def __init__(self, detail: str = "URL not found or not owned by user"):
        super().__init__(status_code=404, detail=detail)

