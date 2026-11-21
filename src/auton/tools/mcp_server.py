"""Small real MCP stdio server, providing only a pure SHA256 tool."""

import hashlib
import json
import sys

PROTOCOL = "2025-11-25"
INPUT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string", "maxLength": 16384}},
    "required": ["text"],
    "additionalProperties": False,
}


def main() -> None:
    initialized = False
    for line in sys.stdin:
        if len(line) > 131072:
            return
        message = json.loads(line)
        method = message.get("method")
        if method == "notifications/initialized":
            initialized = True
            continue
        if "id" not in message:
            continue
        result: dict[str, object]
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "auton-local-sha256", "version": "1"},
            }
        elif method == "tools/list" and initialized:
            result = {
                "tools": [
                    {
                        "name": "sha256",
                        "description": "SHA256 of UTF-8 text, no side effects",
                        "inputSchema": INPUT_SCHEMA,
                        "annotations": {"readOnlyHint": True},
                    }
                ]
            }
        elif method == "tools/call" and initialized:
            params = message.get("params", {})
            arguments = params.get("arguments", {})
            if (
                params.get("name") != "sha256"
                or set(arguments) != {"text"}
                or not isinstance(arguments["text"], str)
                or len(arguments["text"]) > 16384
            ):
                result = {
                    "isError": True,
                    "content": [{"type": "text", "text": "Invalid tool input"}],
                }
            else:
                checksum = hashlib.sha256(arguments["text"].encode()).hexdigest()
                result = {
                    "content": [{"type": "text", "text": checksum}],
                    "structuredContent": {"sha256": checksum},
                    "isError": False,
                }
        else:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "error": {"code": -32601, "message": "Method not supported"},
                    }
                ),
                flush=True,
            )
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)


if __name__ == "__main__":
    main()
