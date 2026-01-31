class UpstreamDownloadError(Exception):
    def __init__(self, message="CSV download failed"):
        super().__init__(message)
