import hashlib
import json
from typing import Literal

from jsonschema import Draft202012Validator, SchemaError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from auton.constitution.config import Principal


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
    )


class ToolCall(Contract):
    id: str
    name: str
    arguments: dict[str, JsonValue]


class ToolSpec(Contract):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    description: str = Field(default="", max_length=1000)
    parameters: dict[str, JsonValue]

    @model_validator(mode="after")
    def valid_schema(self) -> "ToolSpec":
        try:
            Draft202012Validator.check_schema(self.parameters)
        except SchemaError as error:
            raise ValueError("Invalid tool JSON schema") from error
        if self.parameters.get("type") != "object":
            raise ValueError("Tool parameters must describe an object")
        # External reference resolution is intentionally unsupported.
        if "$ref" in json.dumps(self.parameters):
            raise ValueError("Tool schemas cannot load external references")
        return self


class ModelMessage(Contract):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = Field(default=None, max_length=16000)
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    @model_validator(mode="after")
    def valid_role(self) -> "ModelMessage":
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("Tool results require tool_call_id")
        if self.role != "tool" and self.tool_call_id:
            raise ValueError("Only tool results may have tool_call_id")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("Only assistants may request tools")
        if self.content is None and not (self.role == "assistant" and self.tool_calls):
            raise ValueError("Message content is required")
        return self

    def wire(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"role": self.role, "content": self.content}
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            result["tool_calls"] = [
                {
                    "id": item.id,
                    "type": "function",
                    "function": {
                        "name": item.name,
                        "arguments": json.dumps(item.arguments, ensure_ascii=False),
                    },
                }
                for item in self.tool_calls
            ]
        return result


class ModelRequest(Contract):
    model_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=200)
    principal: Principal
    goal_id: str = Field(min_length=1, max_length=200)
    goal_revision: int = Field(default=1, ge=1)
    messages: tuple[ModelMessage, ...] = Field(min_length=1, max_length=100)
    max_output_tokens: int = Field(default=256, ge=1, le=2048)
    data_domain: Literal["public", "local-only", "secret"] = "local-only"
    output_format: Literal["text", "json"] = "text"
    tools: tuple[ToolSpec, ...] = Field(default=(), max_length=16)
    tool_choice: Literal["auto", "required", "none"] = "auto"

    @model_validator(mode="after")
    def valid_conversation(self) -> "ModelRequest":
        pending: set[str] = set()
        for message in self.messages:
            if pending and message.role != "tool":
                raise ValueError("Tool calls must be followed by their results")
            if message.role == "tool":
                if not message.tool_call_id or message.tool_call_id not in pending:
                    raise ValueError("Orphan tool result")
                pending.remove(message.tool_call_id)
            if message.tool_calls:
                pending = {call.id for call in message.tool_calls}
                if len(pending) != len(message.tool_calls):
                    raise ValueError("Duplicate tool call id")
        if pending:
            raise ValueError("Missing tool results")
        if len({tool.name for tool in self.tools}) != len(self.tools):
            raise ValueError("Duplicate tool name")
        if self.tool_choice == "required" and not self.tools:
            raise ValueError("Required tool selection needs tools")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class ModelUsage(Contract):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_microusd: int = Field(default=0, ge=0)
    cost_is_estimate: Literal[True] = True


class ModelResult(Contract):
    redacted: bool = False
    request_id: str
    model_id: str
    reported_model: str
    system_fingerprint: str | None = None
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: Literal["stop", "tool_calls", "length"]
    usage: ModelUsage
    source: Literal["remote", "test"]
    latency_ms: int


class ModelChunk(Contract):
    kind: Literal["delta", "completed"]
    content: str = ""
    result: ModelResult | None = None


class ModelInfo(Contract):
    id: str
    provider: str
    location: Literal["local", "remote"]
    declared_revision: str
    executor_tier: Literal["small_2b", "small_7b", "strong", "test_fixture"] = "strong"
    base_revision: str | None = None
    adapter_revision: str | None = None
    template_revision: str | None = None
    runtime_revision: str = "deepseek-http-sse-v2"
    quantization: str | None = None
    revision_is_pinned: bool
    context_tokens: int
    declared_context_tokens: int
    max_output_tokens: int
    capabilities: tuple[str, ...]
    capability_source: Literal["provider-declared", "test-fixture"]
    health: Literal["not_checked", "available", "unavailable", "credential_missing", "test_fixture"]
    price_revision: str
    input_microusd_per_million: int
    output_microusd_per_million: int
