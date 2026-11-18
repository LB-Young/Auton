from auton.context.ports import CompressorPort
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelMessage


class WholeTurnCompressor:
    def groups(self, history: tuple[ModelMessage, ...]) -> list[tuple[ModelMessage, ...]]:
        groups: list[list[ModelMessage]] = []
        pending: set[str] = set()
        for message in history:
            if pending and message.role != "tool":
                raise ApplicationError(
                    409,
                    "incomplete_tool_protocol",
                    "Tool calls need their real results before another model request",
                )
            if message.role == "tool":
                if message.tool_call_id not in pending:
                    raise ApplicationError(
                        409, "orphan_tool_result", "Tool response has no matching call"
                    )
                pending.remove(str(message.tool_call_id))
            if message.tool_calls:
                pending = {call.id for call in message.tool_calls}
                if len(pending) != len(message.tool_calls):
                    raise ApplicationError(
                        409, "duplicate_tool_call", "Duplicate tool ids in a message"
                    )
            if message.role == "user" or not groups:
                groups.append([])
            groups[-1].append(message)
        if pending:
            raise ApplicationError(
                409, "incomplete_tool_protocol", "Unresolved tool calls cannot be silently removed"
            )
        return [tuple(group) for group in groups]

    def retained(
        self, groups: list[tuple[ModelMessage, ...]], drop: int
    ) -> tuple[ModelMessage, ...]:
        if drop >= len(groups):
            raise ApplicationError(
                409, "critical_context_lost", "Latest user turn cannot be dropped"
            )
        return tuple(message for group in groups[drop:] for message in group)


class CompressorFactory:
    def create(self) -> CompressorPort:
        return WholeTurnCompressor()
