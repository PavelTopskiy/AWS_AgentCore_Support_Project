import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from support_agent.controls import Controls, LoopLimit
from support_agent.reliability import ReliableMCPClient, retry_call


def result(ok=True, retryable=False, code="OK"):
    return {
        "status": "success",
        "content": [
            {
                "text": json.dumps(
                    {
                        "ok": ok,
                        "error": {"code": code, "retryable": retryable},
                    }
                )
            }
        ],
    }


def test_timeout_then_success():
    call = AsyncMock(side_effect=[httpx.ReadTimeout("injected"), result()])
    sleep = AsyncMock()
    asyncio.run(retry_call(call, sleep=sleep))
    assert call.await_count == 2
    assert 0 <= sleep.call_args.args[0] <= 0.25


def test_http_500_then_success():
    request = httpx.Request("POST", "https://example.invalid/mcp")
    error = httpx.HTTPStatusError(
        "injected", request=request, response=httpx.Response(500, request=request)
    )
    call = AsyncMock(side_effect=[error, result()])
    asyncio.run(retry_call(call, sleep=AsyncMock()))
    assert call.await_count == 2


@pytest.mark.parametrize("status", [400, 401, 403])
def test_no_retry_on_authorization_or_invalid_request(status):
    request = httpx.Request("POST", "https://example.invalid/mcp")
    error = httpx.HTTPStatusError(
        "denied", request=request, response=httpx.Response(status, request=request)
    )
    call = AsyncMock(side_effect=error)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(retry_call(call, sleep=AsyncMock()))
    assert call.await_count == 1


def test_retry_budget():
    call = AsyncMock(return_value=result(False, True, "UPSTREAM_500"))
    sleep = AsyncMock()
    assert asyncio.run(retry_call(call, sleep=sleep))["status"] == "error"
    assert call.await_count == 3 and sleep.await_count == 2


def test_business_denial_is_never_retried():
    call = AsyncMock(return_value=result(False, False, "REFUND_LIMIT_EXCEEDED"))
    asyncio.run(retry_call(call, sleep=AsyncMock()))
    assert call.await_count == 1


def test_pinned_strands_preserves_typed_timeouts():
    client = ReliableMCPClient(lambda: None)
    with pytest.raises(TimeoutError):
        client._handle_tool_execution_error(
            "test", McpError(ErrorData(code=408, message="timeout"))
        )
    denied = client._handle_tool_execution_error(
        "test", McpError(ErrorData(code=-32000, message="denied"))
    )
    assert denied["status"] == "error"


def test_model_cannot_replace_operation_key_or_filter_over_limit_before_gateway():
    event = SimpleNamespace(
        tool_use={
            "name": "SupportTools___refund_customer",
            "input": {
                "amount_cents": 500000,
                "idempotency_key": "attacker-chosen-key",
            },
        },
        cancel_tool=False,
    )
    Controls("operation-123").before_tool(event)
    assert event.tool_use["input"]["idempotency_key"] == "operation-123"
    assert event.tool_use["input"]["amount_cents"] == 500000  # Cedar receives malicious amount.
    assert not event.cancel_tool


def test_missing_operation_disables_refund():
    event = SimpleNamespace(tool_use={"name": "refund_customer", "input": {}}, cancel_tool=False)
    Controls().before_tool(event)
    assert event.cancel_tool


def test_wrong_tool_selection_is_observable(capsys):
    controls = Controls(expected_tool="check_order")
    controls.before_tool(SimpleNamespace(tool_use={"name": "get_customer", "input": {}}))
    assert "wrong_tool_selection" in capsys.readouterr().out


def test_llm_loop_stops_before_seventh_model_call(capsys):
    controls = Controls(max_model_calls=6)
    for _ in range(6):
        controls.before_model(None)
    with pytest.raises(LoopLimit):
        controls.before_model(None)
    assert "llm_loop" in capsys.readouterr().out
