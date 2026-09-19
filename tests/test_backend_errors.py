from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from support_agent.backend import _execute, handler


def setup_env(monkeypatch, store, mode="none"):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("TABLE_NAME", store.table)
    monkeypatch.setenv("CUSTOMER_ID", store.customer)
    monkeypatch.setenv("STAGE", "test")
    monkeypatch.setenv("FAULT_MODE", mode)
    return SimpleNamespace(
        aws_request_id="test-request",
        client_context=SimpleNamespace(
            custom={"bedrockAgentCoreToolName": "SupportTools___check_order"},
        ),
    )


def test_backend_lost_response_mode_recovers_existing_receipt(monkeypatch, store):
    ctx = setup_env(monkeypatch, store)
    args = {"order_id": "retry", "amount_cents": 100, "idempotency_key": "lost-response-123"}
    for _ in range(3):
        response = _execute(args, ctx, "refund_customer", "lost_response", None)
        assert response["error"]["retryable"]
    receipt = _execute(args, ctx, "refund_customer", "none", None)
    assert receipt["ok"]
    assert store.order("retry")["refundable_cents"] == 199900


def test_backend_500_is_retryable_envelope(monkeypatch, store, capsys):
    ctx = setup_env(monkeypatch, store)
    response = _execute({"order_id": "123"}, ctx, "check_order", "backend_500", None)
    assert response["error"] == {"code": "UPSTREAM_500", "retryable": True}
    assert "UPSTREAM_500" in capsys.readouterr().out


def test_production_rejects_injection_flag(monkeypatch, store):
    ctx = setup_env(monkeypatch, store, "timeout")
    monkeypatch.setenv("STAGE", "prod")
    with pytest.raises(RuntimeError, match="forbidden"):
        handler({"order_id": "123"}, ctx)


def test_unexpected_failure_is_not_logged_as_success(monkeypatch, store, capsys):
    ctx = setup_env(monkeypatch, store)
    monkeypatch.setattr(
        "support_agent.backend.dispatch", Mock(side_effect=RuntimeError("injected"))
    )
    with pytest.raises(RuntimeError):
        _execute({"order_id": "123"}, ctx, "check_order", "none", None)
    assert "INTERNAL_ERROR" in capsys.readouterr().out


def test_storage_access_denied_is_not_retryable(monkeypatch, store):
    ctx = setup_env(monkeypatch, store)
    error = ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetItem")
    monkeypatch.setattr("support_agent.backend.dispatch", Mock(side_effect=error))
    result = _execute({"order_id": "123"}, ctx, "check_order", "none", None)
    assert result["error"] == {"code": "STORAGE_UNAVAILABLE", "retryable": False}
