"""Auton Core — 结构化日志（基于 Loguru）"""

import sys
from pathlib import Path
from loguru import logger as _logger


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    *,
    enable_console: bool = True,
    enable_file: bool = True,
    rotation: str = "100 MB",
    retention: str = "30 days",
    format_string: str | None = None,
) -> None:
    """配置日志系统（JSON + Console 双输出）

    Args:
        level: 日志级别（DEBUG / INFO / WARNING / ERROR / CRITICAL）
        log_file: 日志文件路径，None 则不写文件
        enable_console: 是否输出到 stderr
        enable_file: 是否输出到文件
        rotation: 文件轮转大小
        retention: 文件保留天数
        format_string: 自定义格式，None 则使用默认值
    """
    _logger.remove()

    if format_string is None:
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )

    if enable_console:
        _logger.add(
            sys.stderr,
            level=level,
            format=format_string,
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

    if enable_file and log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        _logger.add(
            log_file,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation=rotation,
            retention=retention,
            compression="gz",
            serialize=True,
            backtrace=True,
            diagnose=True,
        )


def get_logger(name: str | None = None):
    """获取带模块名的 logger 实例"""
    if name:
        return _logger.bind(name=name)
    return _logger
