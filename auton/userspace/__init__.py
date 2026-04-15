"""Userspace — ~/.auton 用户配置目录管理

负责：
  1. 启动时校验并创建 ~/.auton 完整目录结构（bootstrap）
  2. Session 启动时加载用户安装的 skill / subagent / workflow（loader）
"""

from .bootstrap import ensure_userspace, USERSPACE_ROOT, UserspaceLayout
from .loader import UserspaceLoader

__all__ = [
    "ensure_userspace",
    "USERSPACE_ROOT",
    "UserspaceLayout",
    "UserspaceLoader",
]
