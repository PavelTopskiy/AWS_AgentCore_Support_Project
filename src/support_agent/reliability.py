"""Bounded, jittered retries. Authorization and invalid arguments are never retried."""

import asyncio
import json
import random
from datetime import timedelta

import httpx
from mcp.shared.exceptions import McpError
from opentelemetry.trace import StatusCode
from strands.tools.mcp import MCPClient

from support_agent.telemetry import emit, tracer


def business_payload(result):
    for block in result.get("content", []):
        if "text" in block:
            try:
                parsed = json.loads(block["text"])
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict) and "ok" in parsed:
                return parsed
    return None


async def retry_call(call, *, sleep=asyncio.sleep, attempts=3):
    for attempt in range(1, attempts + 1):
        with tracer.start_as_current_span("gateway.attempt") as span:
            span.set_attribute("retry.attempt", attempt)
            try:
                result = await call()
                payload = business_payload(result)
                retryable = bool(
                    payload
                    and not payload["ok"]
                    and payload.get("error", {}).get("retryable") is True
                )
                if payload and not payload["ok"]:
                    span.set_status(StatusCode.ERROR)
                    emit("tool_failure", code=payload["error"]["code"], attempt=attempt)
                    result["status"] = "error"
                if not retryable or attempt == attempts:
                    return result
            except (httpx.TimeoutException, httpx.TransportError, TimeoutError) as exc:
                span.set_status(StatusCode.ERROR)
                emit("tool_failure", code=type(exc).__name__, attempt=attempt)
                if attempt == attempts:
                    raise
            except httpx.HTTPStatusError as exc:
                span.set_status(StatusCode.ERROR)
                emit("http_failure", status=exc.response.status_code, attempt=attempt)
                if exc.response.status_code not in {429, 500, 502, 503, 504} or attempt == attempts:
                    raise
        await sleep(random.uniform(0, min(4, 0.25 * 2 ** (attempt - 1))))
    raise AssertionError("unreachable")


class ReliableMCPClient(MCPClient):
    def _handle_tool_execution_error(self, tool_use_id, exception):
        # Pinned Strands turns transport exceptions into text by default. Preserve typed
        # transient failures so the retry layer never guesses from a denial's text.
        if isinstance(exception, (httpx.TransportError, httpx.HTTPStatusError, TimeoutError)):
            raise exception
        if isinstance(exception, McpError) and exception.error.code == 408:
            raise TimeoutError("MCP_RESPONSE_TIMEOUT") from exception
        return super()._handle_tool_execution_error(tool_use_id, exception)

    async def call_tool_async(self, **kwargs):
        # MCPAgentTool delegates here; overrides cover the actual async Strands path.
        kwargs["read_timeout_seconds"] = timedelta(seconds=20)
        base_call = super().call_tool_async
        with tracer.start_as_current_span("gateway.tool") as span:
            span.set_attribute("tool.name", kwargs["name"])
            result = await retry_call(lambda: base_call(**kwargs))
            if result.get("status") == "error":
                span.set_status(StatusCode.ERROR)
                emit("gateway_tool_error", tool=kwargs["name"])
            return result
