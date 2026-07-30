"""
应用异常体系
统一错误码和结构化错误响应
"""

from __future__ import annotations


class AppException(Exception):
    """应用基础异常"""
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    detail: str | None = None

    def __init__(self, detail: str | None = None):
        self.detail = detail
        super().__init__(detail or self.error_code)


class AuthenticationError(AppException):
    status_code = 401
    error_code = "AUTHENTICATION_FAILED"


class RateLimitExceeded(AppException):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


class NotFoundError(AppException):
    status_code = 404
    error_code = "NOT_FOUND"


class ValidationError(AppException):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class ProviderError(AppException):
    status_code = 502
    error_code = "PROVIDER_ERROR"


class ProviderTimeoutError(ProviderError):
    status_code = 504
    error_code = "PROVIDER_TIMEOUT"


class ProviderAuthError(ProviderError):
    status_code = 502
    error_code = "PROVIDER_AUTHENTICATION_FAILED"


class ToolExecutionError(AppException):
    status_code = 502
    error_code = "TOOL_EXECUTION_ERROR"


class ConfigurationError(AppException):
    status_code = 500
    error_code = "CONFIGURATION_ERROR"
