"""One-command real workbench: prepare locked dependencies/resources, then serve."""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import os
import re
import shutil
import socket
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY_CHECK = (
    "from auton.constitution.secrets import SecretStoreFactory; "
    "from auton.kernel.ports import ApplicationError; "
    "import sys; "
    "\ntry: SecretStoreFactory().create().get('DEEPSEEK_API_KEY')"
    "\nexcept ApplicationError: sys.exit('请在项目 .env 中填写 DEEPSEEK_API_KEY')"
)


@contextmanager
def startup_lock(root: Path) -> Iterator[None]:
    directory = root / ".auton_local/server-bootstrap"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / "startup.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit("make server 已经启动或正在准备，请勿重复启动。") from None
        yield
    finally:
        os.close(fd)


def run(command: list[str], root: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=root, env=env, check=True)


def ensure_env(root: Path) -> bool:
    path = root / ".env"
    if path.is_file() or os.environ.get("DEEPSEEK_API_KEY"):
        return True
    if path.exists() or path.is_symlink():
        raise SystemExit(".env 必须是可读取的普通配置文件")
    try:
        with path.open("x") as handle:
            path.chmod(0o600)
            handle.write((root / ".env.example").read_text())
    except FileExistsError:
        return True
    print("已创建 .env。填写 DEEPSEEK_API_KEY 后重新运行 make server。", flush=True)
    return False


def node_candidates() -> list[Path]:
    # Conda may shadow a supported system/nvm runtime. Keep the caller's PATH
    # first, then inspect installed runtimes without modifying the shell setup.
    folders = [Path(v) for v in os.get_exec_path()]
    folders += [Path("/usr/local/bin"), Path("/opt/homebrew/bin"), Path("/usr/bin")]
    folders += [Path.home() / ".volta/bin"]
    for pattern in (
        ".nvm/versions/node/*/bin",
        ".local/share/fnm/node-versions/*/installation/bin",
    ):
        folders.extend(sorted(Path.home().glob(pattern), reverse=True))
    return list(dict.fromkeys(folder / "node" for folder in folders))


def select_node() -> None:
    observed: list[str] = []
    for node in node_candidates():
        if not node.is_file() or not os.access(node, os.X_OK):
            continue
        try:
            version = subprocess.check_output(
                [str(node), "--version"], text=True, stderr=subprocess.DEVNULL, timeout=5
            ).strip()
        except (OSError, subprocess.SubprocessError):
            continue
        observed.append(f"{node}: {version}")
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
        if not match:
            continue
        parts = tuple(int(v) for v in match.groups())
        if not ((22, 14, 0) <= parts < (23, 0, 0)):
            continue
        if shutil.which("npm", path=str(node.parent)) is None:
            continue
        os.environ["PATH"] = str(node.parent) + os.pathsep + os.environ.get("PATH", "")
        print(f"使用 Node.js {version}：{node}（仅当前启动进程）", flush=True)
        return
    detail = "；".join(observed) if observed else "未找到可执行的 Node.js"
    raise SystemExit(
        "未找到配套 npm 的 Node.js 22.14+（22.x）。检测结果："
        + detail
        + "。请安装 Node.js 22.x，或使用 nvm install 22，然后重试 make server。"
    )


def check_tools() -> None:
    missing = [name for name in ("uv", "git") if shutil.which(name) is None]
    if missing:
        raise SystemExit("请先安装运行工具：" + ", ".join(missing))
    select_node()


def check_ports(ports: tuple[int, ...] = (8000, 5173)) -> None:
    for port in ports:
        try:
            with socket.socket() as probe:
                # Match the server's restart behavior without bypassing live listeners.
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", port))
                probe.listen(1)
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                raise SystemExit(
                    f"端口 {port} 已占用；make server 不会停止现有服务。"
                    f"\n请运行 lsof -nP -iTCP:{port} -sTCP:LISTEN 确认占用进程。"
                    "\n若是之前启动的 Auton，请在原终端 Ctrl+C 停止后重试；"
                    "若前后端都正常运行，可直接打开 http://127.0.0.1:5173。"
                ) from None
            raise SystemExit(
                f"无法检查端口 {port}：{error.strerror}（errno={error.errno}），"
                "请检查当前终端的网络权限。"
            ) from None


def frontend_digest(root: Path) -> str:
    checksum = hashlib.sha256()
    for name in ("clients/web/package.json", "clients/web/package-lock.json"):
        checksum.update((root / name).read_bytes())
    return checksum.hexdigest()


def prepare(root: Path) -> Path:
    print("[1/4] 同步锁定的 Python 依赖（含本地判断运行时）…", flush=True)
    run(["uv", "sync", "--frozen", "--extra", "judgment"], root)
    python = root / ".venv/bin/python"
    run([str(python), "-c", KEY_CHECK], root)
    print("[2/4] 检查前端依赖…", flush=True)
    stamp = root / ".auton_local/server-bootstrap/frontend.sha256"
    digest = frontend_digest(root)
    if (
        not stamp.is_file()
        or stamp.read_text() != digest
        or not (root / "clients/web/node_modules/.bin/vite").exists()
        or not (root / "clients/web/node_modules/.package-lock.json").is_file()
    ):
        run(["npm", "ci", "--no-audit", "--no-fund"], root / "clients/web")
        stamp.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp.write_text(digest)
    print("[3/4] 校验上下文 tokenizer 和本地判断资源（缺失时下载，约 700 MB）…", flush=True)
    # Public pinned-resource downloads do not need provider credentials.
    download_env = {
        k: v
        for k, v in os.environ.items()
        if not any(part in k.upper() for part in ("API_KEY", "SECRET", "TOKEN", "PASSWORD"))
    }
    for script in ("download_context_tokenizers.py", "download_laya.py"):
        run([str(python), str(root / "scripts" / script)], root, download_env)
    return python


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="只检查已有环境，不安装、下载或启动服务"
    )
    args = parser.parse_args()
    if args.check:
        check_tools()
        python = ROOT / ".venv/bin/python"
        if not python.is_file():
            raise SystemExit("Python 环境尚未准备，请运行 make server")
        run([str(python), "-c", KEY_CHECK], ROOT)
        run([str(python), "-c", "import laya, transformers, torch"], ROOT)
        for path in (
            "weights/laya-multilingual/manifest.json",
            "weights/context-tokenizers/deepseek-flash/tokenizer.json",
            "weights/context-tokenizers/deepseek-v4-pro/tokenizer.json",
            "clients/web/node_modules/.bin/vite",
        ):
            if not (ROOT / path).is_file():
                raise SystemExit("缺少资源，请运行 make server：" + path)
        print("启动环境已就绪；预设配置为 config/server.toml（不显示密钥）。")
        return
    with startup_lock(ROOT):
        if not ensure_env(ROOT):
            return
        check_tools()
        check_ports()
        python = prepare(ROOT)
        environment = dict(os.environ)
        environment["AUTON_CONFIG"] = str(ROOT / "config/server.toml")
        print("[4/4] 启动真实任务工作台：http://127.0.0.1:5173（Ctrl+C 停止）", flush=True)
        run([str(python), str(ROOT / "scripts/dev.py"), "all"], ROOT, environment)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            f"准备或启动失败（退出码 {error.returncode}），修复上方错误后重试 make server。"
        ) from None
