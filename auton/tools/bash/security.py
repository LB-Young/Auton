"""Bash Security — 危险命令过滤与读写语义分类

7 层安全校验第 1-3 层：
  Layer 1: 命令读写语义分类（read-only / write / destructive）
  Layer 2: 路径安全校验（见 path_validator.py）
  Layer 3: 危险命令黑名单过滤
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class CommandCategory(Enum):
    """命令分类"""
    READ_ONLY = "read_only"      # 仅读取信息，不修改任何内容
    WRITE = "write"              # 写入文件系统（文件/目录创建、修改）
    DESTRUCTIVE = "destructive"  # 删除、格式化等不可逆操作
    NETWORK = "network"          # 网络操作
    UNKNOWN = "unknown"           # 未能分类


@dataclass
class SecurityCheckResult:
    """安全检查结果"""
    allowed: bool
    category: CommandCategory
    reason: str
    requires_confirmation: bool = False


# ─── 危险命令黑名单 ─────────────────────────────────────────────────────────

# 立即拒绝的命令（无条件拦截）
DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    # 递归强制删除
    re.compile(r"^\s*rm\s+-rf\s+/\s*$"),
    re.compile(r"^\s*rm\s+-rf\s+/"),
    re.compile(r"rm\s+(-rf|\s).*\*.*\*"),  # rm -rf * * or rm -rf /*
    # 格式化
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bmkfs\.\b"),
    # 管道执行远程代码（常见攻击向量）
    re.compile(r"curl\s+.*\|\s*(sh|bash|ksh|zsh)"),
    re.compile(r"wget\s+.*\|\s*(sh|bash|ksh|zsh)"),
    re.compile(r"python\s+.*\|\s*(sh|bash)"),
    re.compile(r"fetch\s+.*\|\s*(sh|bash)"),
    # Fork bomb
    re.compile(r":\(\)\{\s*:\|\:&\s*\};:"),
    re.compile(r"fork\s*\(\s*\)\s*\{\s*\|\s*fork\s*;\s*\}\s*;\s*fork"),
    # 覆写启动文件
    re.compile(r">\s*~/.bashrc"),
    re.compile(r">\s*~/.zshrc"),
    re.compile(r">\s*~/.profile"),
    re.compile(r">\s*/etc/passwd"),
    re.compile(r">\s*/etc/shadow"),
    # DD 覆写磁盘
    re.compile(r"\bdd\s+if=.*of=/dev/sd"),
    re.compile(r"\bdd\s+if=.*of=/dev/hd"),
    # 权限修改逃逸
    re.compile(r"chmod\s+777\s+/"),
    re.compile(r"chmod\s+4755\s+"),
    # SSH 密钥覆写
    re.compile(r">\s*~/.ssh/authorized_keys"),
    # git bisect 破坏
    re.compile(r"git\s+bisect\s+start\s+--\s*git\s+reset\s+--hard"),
]

# 需要确认的命令（可能被滥用，但不立即拒绝）
CONFIRM_PATTERNS: list[re.Pattern[str]] = [
    # 大范围删除
    re.compile(r"rm\s+(-r?f?|[rf]+)\s+"),
    # 系统修改
    re.compile(r"sudo\s+"),
    re.compile(r"chmod\s+"),
    re.compile(r"chown\s+"),
    re.compile(r"systemctl\s+"),
    re.compile(r"launchctl\s+"),
    re.compile(r"service\s+"),
    # 网络操作
    re.compile(r"nc\s+"),
    re.compile(r"netcat\s+"),
    re.compile(r"ssh\s+"),
    re.compile(r"scp\s+"),
    re.compile(r"rsync\s+"),
    # 环境修改
    re.compile(r"export\s+"),
    re.compile(r"source\s+"),
    re.compile(r"eval\s+"),
    # Git 强制操作
    re.compile(r"git\s+push\s+--force"),
    re.compile(r"git\s+push\s+-f"),
    re.compile(r"git\s+reset\s+--hard"),
    re.compile(r"git\s+rebase\s+--\d+"),
    # 进程终止
    re.compile(r"kill\s+(-9|-SIGKILL)?\s*"),
    re.compile(r"killall\s+"),
    re.compile(r"pkill\s+"),
    # 下载执行
    re.compile(r"curl\s+"),
    re.compile(r"wget\s+"),
    # Docker/Systemd
    re.compile(r"docker\s+rm\s+"),
    re.compile(r"docker\s+rmi\s+"),
    re.compile(r"podman\s+"),
    # Crontab 修改
    re.compile(r"crontab\s+-r"),
    re.compile(r"\bcrontab\s+"),
    # 用户管理
    re.compile(r"useradd\b"),
    re.compile(r"userdel\b"),
    re.compile(r"passwd\s+"),
]

# 读取类命令（默认允许）
READ_ONLY_KEYWORDS: list[str] = [
    "ls", "cat", "head", "tail", "grep", "find", "which", "whereis",
    "pwd", "cd", "echo", "printenv", "env", "whoami", "id", "uname",
    "df", "du", "free", "top", "ps", "pgrep", "rg", "fd", "bat",
    "git status", "git log", "git diff", "git show", "git branch",
    "git tag", "git remote -v", "git config --list",
    "npm list", "pip list", "cargo tree",
    # 浏览器检测与启动
    "open ", "open -a ", "open /Applications/",  # macOS 启动应用
    "google-chrome", "chrome", "chromium",         # 浏览器检测
    "mdfind", "mdls",                             # macOS 元数据查询
    "gh api", "gh issue list", "gh pr list",
    "stat", "file", "md5sum", "sha256sum", "sha1sum",
    "wc", "sort", "uniq", "cut", "tr", "awk", "sed",
]

# 写入类关键词
WRITE_KEYWORDS: list[str] = [
    ">", ">>", "|",
    "touch", "mkdir", "cp", "mv", "tee",
    "write", "edit", "create", "append",
    "git add", "git commit", "git checkout", "git branch",
]


def classify_command(command: str) -> CommandCategory:
    """根据命令内容判断读写语义分类"""
    cmd_lower = command.lower()

    # 先检查危险命令
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return CommandCategory.DESTRUCTIVE

    # 统计读写关键词得分
    read_score = sum(1 for kw in READ_ONLY_KEYWORDS if kw in cmd_lower)
    write_score = sum(1 for kw in WRITE_KEYWORDS if kw in cmd_lower)

    # 检查危险确认命令
    for pattern in CONFIRM_PATTERNS:
        if pattern.search(command):
            if write_score > 0 or any(
                kw in cmd_lower for kw in ["rm", "delete", "destroy"]
            ):
                return CommandCategory.DESTRUCTIVE
            return CommandCategory.WRITE

    if read_score > 0 and write_score == 0:
        return CommandCategory.READ_ONLY
    if write_score > 0:
        return CommandCategory.WRITE
    return CommandCategory.UNKNOWN


def check_dangerous(command: str) -> bool:
    """快速检查命令是否危险（是否匹配黑名单）"""
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return True
    return False


def check_requires_confirmation(command: str) -> bool:
    """检查命令是否需要用户确认"""
    for pattern in CONFIRM_PATTERNS:
        if pattern.search(command):
            return True
    return False


def security_check(command: str) -> SecurityCheckResult:
    """综合安全检查"""
    # Layer 3: 危险命令黑名单
    if check_dangerous(command):
        return SecurityCheckResult(
            allowed=False,
            category=CommandCategory.DESTRUCTIVE,
            reason="Command matches dangerous pattern blacklist",
        )

    category = classify_command(command)

    if category == CommandCategory.DESTRUCTIVE:
        return SecurityCheckResult(
            allowed=False,
            category=category,
            reason="Command is classified as destructive",
        )

    if category == CommandCategory.WRITE:
        return SecurityCheckResult(
            allowed=True,
            category=category,
            reason="Command has write operations",
            requires_confirmation=True,
        )

    if category == CommandCategory.UNKNOWN:
        return SecurityCheckResult(
            allowed=True,
            category=category,
            reason="Command could not be classified",
            requires_confirmation=True,
        )

    return SecurityCheckResult(
        allowed=True,
        category=category,
        reason="Command is read-only",
    )
