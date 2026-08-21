from __future__ import annotations


class BusinessError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ModelError(BusinessError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, 502)
