"""Auton Core — 统一错误类型"""

from typing import Optional


class AutonError(Exception):
    """Auton 所有错误的基类"""

    def __init__(self, message: str, *, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class RetryableError(AutonError):
    """可重试错误：网络超时、限流等，Agent 可以自动重试"""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, details: Optional[dict] = None) -> None:
        super().__init__(message, details=details)
        self.retry_after = retry_after  # 秒数，建议等待时间


class FatalError(AutonError):
    """不可重试错误：权限拒绝、用户中断等，不应重试"""

    def __init__(self, message: str, *, code: str = "FATAL", details: Optional[dict] = None) -> None:
        super().__init__(message, details=details)
        self.code = code


class ToolExecutionError(FatalError):
    """工具执行失败"""

    def __init__(self, tool_name: str, message: str, *, details: Optional[dict] = None) -> None:
        super().__init__(message, code="TOOL_ERROR", details={"tool": tool_name, **(details or {})})
        self.tool_name = tool_name


class PermissionError(FatalError):
    """权限拒绝"""

    def __init__(self, message: str, *, tool: Optional[str] = None, details: Optional[dict] = None) -> None:
        super().__init__(message, code="PERMISSION_DENIED", details={"tool": tool, **(details or {})})
        self.tool = tool


class LLMError(RetryableError):
    """LLM API 调用失败"""

    def __init__(self, message: str, *, provider: str = "unknown", status_code: Optional[int] = None, details: Optional[dict] = None) -> None:
        super().__init__(message, details={"provider": provider, "status_code": status_code, **(details or {})})
        self.provider = provider
        self.status_code = status_code


class ConfigurationError(FatalError):
    """配置错误"""

    def __init__(self, message: str, *, key: Optional[str] = None, details: Optional[dict] = None) -> None:
        super().__init__(message, code="CONFIG_ERROR", details={"key": key, **(details or {})})
        self.key = key


class SessionError(FatalError):
    """会话错误"""

    def __init__(self, message: str, *, session_id: Optional[str] = None, details: Optional[dict] = None) -> None:
        super().__init__(message, code="SESSION_ERROR", details={"session_id": session_id, **(details or {})})
        self.session_id = session_id
