import hashlib
import os
import re
import subprocess
from pathlib import Path

from auton.genome.contracts import Catalog, GenomeConfig
from auton.kernel.ports import ApplicationError


def error(code: str, message: str) -> ApplicationError:
    return ApplicationError(409, code, message)


class GitAssetRepository:
    def __init__(self, config: GenomeConfig) -> None:
        self.config = config

    def directory(self, owner: str, project_id: str) -> Path:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", project_id):
            raise error("invalid_project", "Invalid project id")
        return (
            self.config.directory
            / hashlib.sha256(owner.encode()).hexdigest()
            / (project_id + ".git")
        )

    @staticmethod
    def run(directory: Path, *args: str, data: bytes | None = None, missing: bool = False) -> bytes:
        env = {
            key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TMPDIR") if key in os.environ
        }
        env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_NO_REPLACE_OBJECTS="1",
            GIT_TERMINAL_PROMPT="0",
            GIT_AUTHOR_NAME="Auton",
            GIT_AUTHOR_EMAIL="auton@localhost",
            GIT_COMMITTER_NAME="Auton",
            GIT_COMMITTER_EMAIL="auton@localhost",
        )
        result = subprocess.run(
            ["git", "--git-dir", str(directory), *args],
            input=data,
            capture_output=True,
            env=env,
            timeout=15,
        )
        if result.returncode:
            if missing:
                return b""
            raise error(
                "asset_repository_conflict",
                "Asset repository command failed; reload the current revision",
            )
        return result.stdout

    def read(
        self, owner: str, project_id: str, branch: str = "main", revision: str | None = None
    ) -> tuple[str | None, Catalog | None]:
        directory = self.directory(owner, project_id)
        if not directory.exists():
            return None, None
        if branch not in {"main", "learning"}:
            raise error("invalid_branch", "Unsupported asset branch")
        if revision is not None and not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise error("invalid_revision", "Revision must be a full Git commit id")
        ref = revision or "refs/heads/" + branch
        identity = self.run(directory, "rev-parse", "--verify", ref, missing=True).decode().strip()
        if not identity:
            return None, None
        if revision:
            self.run(directory, "merge-base", "--is-ancestor", revision, "refs/heads/main")
        raw = self.run(directory, "show", identity + ":catalog.json")
        if len(raw) > 8 * 1024 * 1024:
            raise error("catalog_limit", "Catalog exceeds the configured bound")
        return identity, Catalog.model_validate_json(raw)

    def write(
        self, owner: str, project_id: str, branch: str, expected: str | None, catalog: Catalog
    ) -> str:
        directory = self.directory(owner, project_id)
        self.config.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.config.directory, 0o700)
        directory.parent.mkdir(exist_ok=True, mode=0o700)
        os.chmod(directory.parent, 0o700)
        directory.mkdir(exist_ok=True, mode=0o700)
        if not (directory / "HEAD").exists():
            self.run(directory, "init", "--bare", "--initial-branch=main")
        raw = catalog.model_dump_json().encode()
        if len(raw) > 8 * 1024 * 1024 or len(catalog.records) > 1000:
            raise error("catalog_limit", "Project asset limit reached")
        blob = self.run(directory, "hash-object", "-w", "--stdin", data=raw).decode().strip()
        tree = (
            self.run(directory, "mktree", data=f"100644 blob {blob}\tcatalog.json\n".encode())
            .decode()
            .strip()
        )
        commit = (
            self.run(
                directory,
                "commit-tree",
                tree,
                *(["-p", expected] if expected else []),
                data=b"Auton governed asset revision\n",
            )
            .decode()
            .strip()
        )
        self.run(directory, "update-ref", "refs/heads/" + branch, commit, expected or "0" * 40)
        return commit

    def history(self, owner: str, project_id: str) -> list[str]:
        directory = self.directory(owner, project_id)
        return (
            self.run(directory, "rev-list", "--max-count=100", "refs/heads/main")
            .decode()
            .splitlines()
        )


class AssetRepositoryFactory:
    def create(self, config: GenomeConfig) -> GitAssetRepository:
        return GitAssetRepository(config)
