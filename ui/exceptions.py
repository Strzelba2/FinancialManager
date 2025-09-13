class UnauthorizedError(Exception):
    """Raised when user is not authorized (HTTP 401)."""
    def __init__(self, message="Unauthorized"):
        super().__init__(message)


class BadRequestError(Exception):
    """Raised on bad request (HTTP 400)."""
    def __init__(self, message="Bad Request"):
        super().__init__(message)


class InternalServerError(Exception):
    """Raised for internal errors (HTTP 500)."""
    def __init__(self, message="Internal Server Error"):
        super().__init__(message)