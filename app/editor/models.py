class EditorError(Exception):
    def __init__(self, category, message, status_code=422, details=None):
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.details = details or []
