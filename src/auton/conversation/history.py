"""Private atomic exports of an owned conversation's durable history."""

import json
import os
import secrets
from pathlib import Path

from auton.conversation.contracts import ConversationView
from auton.kernel.documents import key
from auton.kernel.ports import ApplicationError


class HistoryExporter:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.absolute()

    def write(self, owner: str, view: ConversationView, exported_at: str) -> tuple[str, int]:
        messages = []
        for run in view.turns:
            messages.append({"role": "user", "content": run.command.goal, "run_id": run.id})
            messages.append(
                {
                    "role": "assistant",
                    "content": run.final_text,
                    "run_id": run.id,
                    "status": run.status,
                    "reason": run.reason,
                    "model_id": run.resolved_model_id or run.command.model_id,
                }
            )
        data = (
            json.dumps(
                {
                    "schema_version": 1,
                    "exported_at": exported_at,
                    "durable_snapshot": True,
                    **view.model_dump(mode="json"),
                    "messages": messages,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode()
        if len(data) > 64 * 1024 * 1024:
            raise ApplicationError(413, "conversation_export_limit", "会话记录超过 64 MiB 导出上限")
        owner_key = key(owner, "conversation-history")
        filename = key(owner, view.conversation.id) + ".json"
        temporary = ".export-" + secrets.token_hex(16)
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            base = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fchmod(base, 0o700)
                try:
                    os.mkdir(owner_key, 0o700, dir_fd=base)
                except FileExistsError:
                    pass
                directory = os.open(
                    owner_key, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base
                )
            finally:
                os.close(base)
            try:
                os.fchmod(directory, 0o700)
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory,
                )
                try:
                    with os.fdopen(descriptor, "wb", closefd=False) as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.replace(temporary, filename, src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
            finally:
                try:
                    try:
                        os.unlink(temporary, dir_fd=directory)
                    except FileNotFoundError:
                        pass
                finally:
                    os.close(directory)
        except OSError as error:
            raise ApplicationError(
                503,
                "conversation_export_failed",
                "无法保存会话记录，请检查后端记录目录的权限和磁盘空间",
            ) from error
        return str(self.directory / owner_key / filename), len(data)
