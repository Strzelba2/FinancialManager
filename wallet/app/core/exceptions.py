class ImportMismatchError(Exception):
    """Raised when provided amount_after disagrees with computed balance."""
    def __init__(self, message="balance is not correct"):
        super().__init__(message)
