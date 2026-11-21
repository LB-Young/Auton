import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyTooLarge(Exception):
    pass


class RequestLimits:
    def __init__(self, app: ASGIApp, maximum: int = 2097152) -> None:
        self.app, self.maximum = app, maximum

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        address = scope.get("client")
        if address and address[0] not in {"127.0.0.1", "::1", "testclient"}:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await self.error(
                    send, 403, "loopback_required", "This service only accepts local clients"
                )
            return
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            await self.error(send, 400, "invalid_content_length", "Invalid content length")
            return
        if length < 0 or length > self.maximum:
            await self.error(
                send, 413, "request_too_large", "Request body exceeds the configured limit"
            )
            return
        consumed = 0
        started = False

        async def bounded_receive() -> Message:
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > self.maximum:
                raise BodyTooLarge
            return message

        async def private_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                if consumed > self.maximum:
                    raise BodyTooLarge
                started = True
                values = list(message.get("headers", []))
                if not any(k.lower() == b"cache-control" for k, v in values):
                    values.append((b"cache-control", b"no-store"))
                if not any(k.lower() == b"x-content-type-options" for k, v in values):
                    values.append((b"x-content-type-options", b"nosniff"))
                message = {**message, "headers": values}
            await send(message)

        try:
            await self.app(scope, bounded_receive, private_send)
        except BodyTooLarge:
            if not started:
                await self.error(
                    send, 413, "request_too_large", "Request body exceeds the configured limit"
                )
            else:
                raise

    @staticmethod
    async def error(send: Send, status: int, code: str, message: str) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps({"code": code, "message": message}).encode(),
            }
        )
