"""Local CLI for the same HTTP agent application port used by the workbench."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from auton.agent.contracts import CreateRun, RunCommand
from auton.cli.factory import AgentClientFactory
from auton.experience.contracts import RecoveryCommand
from auton.kernel.ports import ApplicationError


async def main(args: argparse.Namespace) -> None:
    client = AgentClientFactory().create(args.base)
    try:
        await client.start()
        if args.operation == "init":
            notes = await asyncio.to_thread(Path(args.notes).read_text) if args.notes else None
            value: object = await client.initialize(
                args.project, args.title, not args.editable, notes
            )
        elif args.operation == "create":
            # Explicit CLI input, not an agent filesystem capability.
            command = CreateRun.model_validate_json(
                await asyncio.to_thread(Path(args.file).read_text)
            )
            value = (await client.create(command)).model_dump(mode="json")
        elif args.operation == "trajectory":
            value = (await client.trajectory(args.project, args.run)).model_dump(mode="json")
        elif args.operation == "recover":
            recovery = RecoveryCommand(
                request_id=args.request_id or str(uuid4()),
                expected_version=args.version,
                expected_goal_revision=args.revision,
                checkpoint_event_id=args.checkpoint_event,
            )
            value = (await client.recover(args.project, args.run, recovery)).model_dump(mode="json")
        elif args.operation == "get":
            value = (await client.get(args.run)).model_dump(mode="json")
        elif args.operation == "list":
            value = [r.model_dump(mode="json") for r in await client.list(args.project)]
        else:
            command_id = args.request_id or str(uuid4())
            action = RunCommand.model_validate(
                {
                    "request_id": command_id,
                    "action": args.action,
                    "expected_goal_revision": args.revision,
                    "goal": args.goal,
                }
            )
            value = (await client.command(args.run, action)).model_dump(mode="json")
        print(json.dumps(value, ensure_ascii=False, indent=2))
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    sub = parser.add_subparsers(dest="operation", required=True)
    init = sub.add_parser("init")
    init.add_argument("project")
    init.add_argument("--title", default="CLI project")
    init.add_argument("--editable", action="store_true")
    init.add_argument("--notes", help="Explicitly import and publish a selected public notes file")
    create = sub.add_parser("create")
    create.add_argument("--file", required=True, help="CreateRun JSON with a stable request_id")
    get = sub.add_parser("get")
    get.add_argument("run")
    listing = sub.add_parser("list")
    listing.add_argument("project")
    trajectory = sub.add_parser("trajectory")
    trajectory.add_argument("run")
    trajectory.add_argument("--project", required=True)
    recover = sub.add_parser("recover")
    recover.add_argument("run")
    recover.add_argument("--project", required=True)
    recover.add_argument("--version", type=int, required=True)
    recover.add_argument("--revision", type=int, required=True)
    recover.add_argument("--checkpoint-event", required=True)
    recover.add_argument("--request-id")
    command = sub.add_parser("command")
    command.add_argument("run")
    command.add_argument(
        "action", choices=["pause", "cancel", "resume", "approve", "reconcile", "revise"]
    )
    command.add_argument("--revision", type=int, required=True)
    command.add_argument("--request-id")
    command.add_argument("--goal")
    try:
        asyncio.run(main(parser.parse_args()))
    except ApplicationError as error:
        raise SystemExit(error.code + ": " + str(error)) from None
    except (ValidationError, ValueError):
        raise SystemExit("Invalid CLI input; input values are not echoed") from None
